import base64
import io
import os
from datetime import datetime, timedelta
from threading import Lock

from flask import Blueprint, request, g, send_file

from api_service4.app.middleware.auth import jwt_required, role_required
from api_service4.app.middleware.validation import (
    validate_register,
    validate_user_query,
    validate_request,
)
from api_service4.app.middleware.rate_limit import (
    register_rate_limit,
    admin_api_rate_limit,
    common_api_rate_limit,
)
from api_service4.app.services.gm_crypto import sign_user_certificate, generate_root_ca_real
from api_service4.app.utils.response import success, error
from api_service4.config.init import get_config
from api_service4.app.services.model_2_denglu import UserAuthSystem
import traceback

users_bp = Blueprint("users", __name__, url_prefix="/api/v1/users")

config = get_config()
user_auth = UserAuthSystem(db_path=None, jwt_secret=config.JWT_SECRET)

_CERT_DELIVERY_LOCK = Lock()
_CERT_DELIVERY_CACHE = {}
_CERT_DELIVERY_TTL_MINUTES = 10
PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _is_truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _default_certificates_dir():
    return os.path.abspath(os.getenv("CERTIFICATES_DIR", os.path.join(PACKAGE_ROOT, "certificates")))


def _ensure_root_ca_files():
    cert_dir = _default_certificates_dir()
    os.makedirs(cert_dir, exist_ok=True)

    root_private_key_path = os.path.abspath(
        os.getenv("ROOT_PRIVATE_KEY_PATH", os.path.join(cert_dir, "root_private_key.pem"))
    )
    root_cert_path = os.path.abspath(
        os.getenv("ROOT_CERT_PATH", os.path.join(cert_dir, "root_certificate.pem"))
    )

    if os.path.exists(root_private_key_path) and os.path.exists(root_cert_path):
        return root_private_key_path, root_cert_path

    private_key_pem, _public_key_pem, root_cert_pem = generate_root_ca_real()

    with open(root_private_key_path, "w", encoding="utf-8") as private_key_file:
        private_key_file.write(private_key_pem)
    with open(root_cert_path, "w", encoding="utf-8") as cert_file:
        cert_file.write(root_cert_pem)

    return root_private_key_path, root_cert_path


def get_root_private_key():
    root_private_key_path, _ = _ensure_root_ca_files()
    with open(root_private_key_path, "r", encoding="utf-8") as file:
        return file.read().strip()


def get_root_cert_pem():
    _, root_cert_path = _ensure_root_ca_files()
    with open(root_cert_path, "r", encoding="utf-8") as file:
        return file.read().strip()


def _send_pem_as_download(filename: str, pem_text: str):
    bio = io.BytesIO(pem_text.encode("utf-8"))
    bio.seek(0)
    try:
        return send_file(
            bio,
            as_attachment=True,
            download_name=filename,
            mimetype="application/x-pem-file",
        )
    except TypeError:
        bio.seek(0)
        return send_file(
            bio,
            as_attachment=True,
            attachment_filename=filename,
            mimetype="application/x-pem-file",
        )


def _resolve_target_user_id():
    raw_user_id = request.args.get("user_id") or request.view_args.get("user_id")
    if raw_user_id in (None, ""):
        return g.user["user_id"]
    try:
        return int(raw_user_id)
    except (TypeError, ValueError):
        return None


def _ensure_self_or_admin(target_user_id: int):
    if target_user_id is None:
        return error(400, "user_id 格式错误")
    if g.user["user_id"] != target_user_id and g.user["role"] != "admin":
        return error(403, "没有权限访问该用户资源")
    return None


def _issue_user_certificate(user_info):
    root_private_key_pem = get_root_private_key()
    root_cert_pem = get_root_cert_pem()
    user_cert_pem = sign_user_certificate(
        user_public_key_pem=user_info["sm2_public_key"],
        user_private_key_pem=user_info.get("sm2_private_key"),
        root_private_key_pem=root_private_key_pem,
        root_cert_pem=root_cert_pem,
        username=user_info["username"],
    )
    return user_cert_pem, root_cert_pem


def _cache_certificate_for_delivery(filename: str, pem_text: str):
    token = base64.urlsafe_b64encode(os.urandom(24)).decode("utf-8").rstrip("=")
    expires_at = datetime.utcnow() + timedelta(minutes=_CERT_DELIVERY_TTL_MINUTES)
    with _CERT_DELIVERY_LOCK:
        expired_tokens = [
            item_token
            for item_token, item in _CERT_DELIVERY_CACHE.items()
            if item["expires_at"] <= datetime.utcnow()
        ]
        for item_token in expired_tokens:
            _CERT_DELIVERY_CACHE.pop(item_token, None)

        _CERT_DELIVERY_CACHE[token] = {
            "filename": filename,
            "pem_text": pem_text,
            "expires_at": expires_at,
        }
    return token, expires_at


def _build_certificate_success_response(user_info, cert_filename: str, user_cert_pem: str, root_cert_pem: str):
    delivery_token, expires_at = _cache_certificate_for_delivery(cert_filename, user_cert_pem)
    return success(
        data={
            "user_info": {
                "user_id": user_info["id"],
                "username": user_info["username"],
                "role": user_info["role"],
            },
            "certificate": {
                "filename": cert_filename,
                "pem": user_cert_pem,
                "base64": base64.b64encode(user_cert_pem.encode("utf-8")).decode("utf-8"),
                "content_type": "application/x-pem-file",
            },
            "root_certificate": {
                "filename": "root_certificate.pem",
                "pem": root_cert_pem,
            },
            "certificate_delivery": {
                "download_token": delivery_token,
                "download_url": f"/api/v1/users/certificate/delivery/{delivery_token}",
                "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        },
        message="注册成功，证书已签发",
    )


@users_bp.route("/certificate/delivery/<token>", methods=["GET"])
@common_api_rate_limit()
def download_certificate_by_delivery_token(token):
    with _CERT_DELIVERY_LOCK:
        delivery = _CERT_DELIVERY_CACHE.get(token)

    if not delivery:
        return error(404, "证书下载令牌不存在或已失效")

    if delivery["expires_at"] <= datetime.utcnow():
        with _CERT_DELIVERY_LOCK:
            _CERT_DELIVERY_CACHE.pop(token, None)
        return error(410, "证书下载令牌已过期，请重新注册或联系管理员补发")

    return _send_pem_as_download(delivery["filename"], delivery["pem_text"])


@users_bp.route("/certificate/download", methods=["GET"])
@common_api_rate_limit()
@jwt_required
def download_user_certificate():
    """下载用户证书接口：GET /api/v1/users/certificate/download"""
    user_id = _resolve_target_user_id()
    permission_error = _ensure_self_or_admin(user_id)
    if permission_error:
        return permission_error

    user_info = user_auth.get_user_by_id(user_id, include_private_key=True)
    if not user_info:
        return error(404, "用户不存在")

    try:
        user_cert_pem, _root_cert_pem = _issue_user_certificate(user_info)
    except Exception as exc:
        return error(500, "签发用户证书失败", details=str(exc))

    cert_filename = f"{user_info['username']}_certificate.crt"
    return _send_pem_as_download(cert_filename, user_cert_pem)


@users_bp.route("/register", methods=["POST"])
@register_rate_limit()
@validate_register()
def register():
    """用户注册接口：POST /api/v1/users/register"""
    data = request.cleaned_data

    username = data["username"]
    password = data["password"]
    phone = data["phone"]
    # Public registration must never be able to self-assign a privileged role.
    role = "user"

    register_result, err_msg = user_auth.register(username, password, phone, role)
    if not register_result:
        return error(409, err_msg)

    user_info = user_auth.get_user(username, include_private_key=True)
    if not user_info:
        user_auth.delete_user_by_username(username)
        return error(500, "注册回查失败，已回滚用户数据")

    try:
        user_cert_pem, root_cert_pem = _issue_user_certificate(user_info)
    except Exception as exc:
        traceback.print_exc()
        user_auth.delete_user_by_username(username)
        return error(500, "证书签发失败，注册已回滚，请重试", details=str(exc))

    cert_filename = f"{username}_certificate.crt"
    if _is_truthy(request.args.get("download")):
        return _send_pem_as_download(cert_filename, user_cert_pem)

    return _build_certificate_success_response(
        user_info=user_info,
        cert_filename=cert_filename,
        user_cert_pem=user_cert_pem,
        root_cert_pem=root_cert_pem,
    )


@users_bp.route("", methods=["GET"])
@admin_api_rate_limit()
@role_required("admin")
@validate_user_query()
def get_user_list():
    params = request.cleaned_params
    users = user_auth.search_users(
        name=params["name"],
        phone=params["phone"],
        user_id=params["user_id"],
    )
    return success(data={"user_list": users}, message=f"共查询到{len(users)}个用户")


@users_bp.route("/<int:user_id>", methods=["GET"])
@common_api_rate_limit()
@jwt_required
def get_user(user_id):
    permission_error = _ensure_self_or_admin(user_id)
    if permission_error:
        return permission_error

    user = user_auth.search_users(user_id=user_id)
    if not user:
        return error(404, "用户不存在")
    return success(data={"user_info": user[0]})


@users_bp.route("/<int:user_id>", methods=["DELETE"])
@admin_api_rate_limit()
@role_required("admin")
def delete_user(user_id):
    if int(g.user["user_id"]) == int(user_id):
        return error(409, "管理员不能删除当前登录账号")
    try:
        with user_auth._db_lock:
            user_auth.cursor.execute(
                "UPDATE users SET is_active = 0 WHERE id = %s AND is_active = 1",
                (user_id,),
            )
            if user_auth.cursor.rowcount == 0:
                user_auth.conn.rollback()
                return error(404, "用户不存在")
            user_auth.conn.commit()
        return success(message=f"用户{user_id}已禁用")
    except Exception as exc:
        user_auth.conn.rollback()
        return error(500, "删除用户失败", details=str(exc))


@users_bp.route("/<int:user_id>/role", methods=["PUT"])
@admin_api_rate_limit()
@role_required("admin")
def update_user_role(user_id):
    data = request.get_json(silent=True) or {}
    role = str(data.get("role") or "").strip().lower()
    if role not in {"user", "merchant", "admin", "auditor"}:
        return error(400, "role 仅支持 user、merchant、admin、auditor")
    if int(g.user["user_id"]) == int(user_id) and role != "admin":
        return error(409, "不能降低当前登录管理员自己的权限")
    updated, message = user_auth.set_user_role(user_id, role)
    if not updated:
        return error(404 if message == "用户不存在" else 400, message)
    return success(data={"user_id": user_id, "role": role}, message=message)


@users_bp.route("/<int:user_id>/admin-reset", methods=["PUT"])
@admin_api_rate_limit()
@role_required("admin")
def admin_reset_user_info(user_id):
    if int(g.user["user_id"]) == int(user_id):
        return error(409, "请通过个人中心修改当前管理员资料，不能在此重置自己")

    data = request.get_json(silent=True) or {}
    username = data.get("username") if "username" in data else None
    phone = data.get("phone") if "phone" in data else None
    new_password = data.get("new_password") if "new_password" in data else None

    target = user_auth.get_user_by_id(user_id, include_private_key=True)
    if not target:
        return error(404, "用户不存在")

    replacement_certificate = None
    normalized_username = str(username).strip() if username is not None else None
    username_changed = normalized_username is not None and normalized_username != target["username"]
    if username_changed:
        if not user_auth._validate_input("username", normalized_username):
            return error(400, "用户名格式错误（5-20位字母、数字、下划线）")
        certificate_user = dict(target)
        certificate_user["username"] = normalized_username
        try:
            cert_pem, _root_cert_pem = _issue_user_certificate(certificate_user)
            cert_filename = f"{normalized_username}_certificate.crt"
            delivery_token, expires_at = _cache_certificate_for_delivery(cert_filename, cert_pem)
            replacement_certificate = {
                "filename": cert_filename,
                "pem": cert_pem,
                "base64": base64.b64encode(cert_pem.encode("utf-8")).decode("utf-8"),
                "download_url": f"/api/v1/users/certificate/delivery/{delivery_token}",
                "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        except Exception as exc:
            return error(500, "新用户名证书签发失败，用户信息未修改", details=str(exc))

    updated, message, reset_summary = user_auth.admin_reset_user_info(
        user_id=user_id,
        username=normalized_username,
        phone=phone,
        new_password=new_password,
    )
    if not updated:
        status = 404 if message == "用户不存在" else 409 if "已被使用" in message else 400
        return error(status, message)

    user_info = user_auth.get_user_by_id(user_id)
    response_data = {
        "user_info": user_info,
        "reset_summary": reset_summary,
        "sessions_revoked": True,
    }
    if replacement_certificate:
        response_data["replacement_certificate"] = replacement_certificate
    return success(data=response_data, message=message)


@users_bp.route("/<int:user_id>/mfa/reset", methods=["POST"])
@admin_api_rate_limit()
@role_required("admin")
def reset_user_mfa(user_id):
    if int(g.user["user_id"]) == int(user_id):
        return error(409, "当前管理员不能重置自己的双因素认证，请由其他管理员操作")
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return error(400, "请确认重置双因素认证")

    target = user_auth.get_user_by_id(user_id)
    if not target:
        return error(404, "用户不存在")
    if target["role"] not in {"admin", "auditor"}:
        return error(400, "仅管理员和审计员账号使用双因素认证")

    reset, message = user_auth.reset_user_mfa(user_id)
    if not reset:
        return error(404 if message == "用户不存在" else 400, message)
    return success(
        data={
            "user_id": user_id,
            "username": target["username"],
            "totp_enabled": False,
            "sessions_revoked": True,
        },
        message=message,
    )


@users_bp.route("/<int:user_id>/update", methods=["PUT"])
@common_api_rate_limit()
@jwt_required
@validate_request(
    required_fields={
        "old_password": "password",
        "phone": "phone",
    },
    optional_fields={
        "new_username": "username",
        "new_password": "password",
    },
)
def update_user(user_id):
    permission_error = _ensure_self_or_admin(user_id)
    if permission_error:
        return permission_error

    data = request.cleaned_data
    result, err_msg = user_auth.update_user_info(
        user_id=user_id,
        old_password=data["old_password"],
        new_username=data.get("new_username"),
        new_password=data.get("new_password"),
        phone=data["phone"],
    )
    if not result:
        return error(400, err_msg)
    return success(message=err_msg)


@users_bp.route("/ca/generate_root", methods=["POST"])
@admin_api_rate_limit()
@role_required("admin")
def generate_root_ca_route():
    _root_private_key_path, _root_cert_path = _ensure_root_ca_files()
    root_cert_pem = get_root_cert_pem()
    return success(
        data={
            "root_cert_pem": root_cert_pem,
        },
        message="Root CA 已就绪（私钥不会通过接口返回）",
    )


@users_bp.route("/ca/sign_user", methods=["POST"])
@admin_api_rate_limit()
@role_required("admin")
def sign_user_cert_route():
    """使用服务端 CA 为数据库中的用户补发证书。"""
    data = request.get_json() or {}

    user_id = data.get("user_id")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return error(400, "缺少有效的 user_id")
    user_info = user_auth.get_user_by_id(user_id, include_private_key=True)
    if not user_info:
        return error(404, "用户不存在")

    try:
        user_cert_pem, _ = _issue_user_certificate(user_info)
    except Exception as exc:
        return error(500, "用户证书签发失败", details=str(exc))

    return success(
        data={"user_id": user_id, "username": user_info["username"], "user_cert_pem": user_cert_pem},
        message="用户证书补发成功",
    )
