from datetime import datetime, timedelta
import secrets

import jwt
from flask import Blueprint, request

from api_service4.app.services.model_2_denglu import UserAuthSystem
from api_service4.app.middleware.auth import MFA_ROLES, generate_tokens, refresh_access_token
from api_service4.app.middleware.rate_limit import login_rate_limit
from api_service4.app.middleware.validation import validate_login
from api_service4.app.services.gm_crypto import CertificateFormatError, extract_certificate_common_name
from api_service4.app.services.security_control import SecurityControlSystem
from api_service4.app.services.totp_service import (
    build_otpauth_uri,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_totp,
)
from api_service4.app.utils.response import success, error
from api_service4.config.init import get_config


auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

config = get_config()
user_auth = UserAuthSystem(db_path=None, jwt_secret=config.JWT_SECRET)
security_control = SecurityControlSystem()


def _audit_auth_failure(reason, *, status=401, user=None, event_type="AUTH_LOGIN"):
    security_control.record_audit(
        event_type=event_type,
        operation="verify",
        result="denied",
        http_status=status,
        user=user,
        ip_address=request.remote_addr,
        request_method=request.method,
        request_path=request.path,
        details={"reason": reason},
    )


def _mfa_token(user_info, purpose, *, secret=None):
    now = datetime.utcnow()
    payload = {
        "type": "mfa_pending",
        "purpose": purpose,
        "user_id": user_info["id"],
        "username": user_info["username"],
        "role": user_info["role"],
        "auth_version": int(user_info.get("auth_version") or 0),
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    if secret:
        payload["totp_secret"] = secret
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def _decode_mfa_token(token, expected_purpose):
    if not token:
        return None, error(400, "缺少 mfa_token")
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, error(401, "MFA 验证会话已过期，请重新上传证书登录")
    except jwt.InvalidTokenError:
        return None, error(401, "无效的 MFA 验证会话")
    if payload.get("type") != "mfa_pending" or payload.get("purpose") != expected_purpose:
        return None, error(401, "MFA 验证会话用途不匹配")
    current = user_auth.get_user_by_id(payload.get("user_id"))
    if not current or current["role"] != payload.get("role") or current["role"] not in MFA_ROLES:
        return None, error(401, "用户角色已变化，请重新登录")
    if int(payload.get("auth_version", 0)) != int(current.get("auth_version") or 0):
        return None, error(401, "账号安全信息已变更，请重新上传证书登录")
    return payload, None


def _tokens_response(user_info, *, recovery_codes=None, message="登录成功"):
    tokens = generate_tokens(user_info, mfa_verified=user_info["role"] in MFA_ROLES)
    security_control.record_audit(
        event_type="AUTH_LOGIN",
        operation="login",
        result="success",
        http_status=200,
        user={"user_id": user_info["id"], "username": user_info["username"], "role": user_info["role"]},
        ip_address=request.remote_addr,
        request_method=request.method,
        request_path=request.path,
        details={"mfa_verified": user_info["role"] in MFA_ROLES},
    )
    data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "user_info": {
            "user_id": user_info["id"],
            "username": user_info["username"],
            "role": user_info["role"],
            "mfa_verified": user_info["role"] in MFA_ROLES,
        },
    }
    if recovery_codes:
        data["recovery_codes"] = recovery_codes
    return success(data=data, message=message)


@auth_bp.route("/login", methods=["POST"])
@login_rate_limit()
@validate_login()
def login():
    """口令和证书验证；管理员/审计员随后必须完成 TOTP。"""
    cert_file = request.files.get("certificate")
    if not cert_file:
        return error(400, "缺少证书文件")

    try:
        cert_data = cert_file.read()
        username = extract_certificate_common_name(cert_data)
    except CertificateFormatError as exc:
        _audit_auth_failure("bad_certificate", status=400)
        return error(400, f"证书解析失败(证书过期或证书有误): {str(exc)}", details={"reason": "bad_certificate"})
    except Exception as exc:
        _audit_auth_failure("bad_certificate", status=400)
        return error(400, f"证书解析失败(证书过期或证书有误): {str(exc)}", details={"reason": "bad_certificate"})

    user_info, auth_error = user_auth.authenticate_by_certificate(username, cert_data)
    if auth_error:
        _audit_auth_failure(
            auth_error.get("reason", "verification_failed"),
            status=auth_error.get("status", 401),
            user={"username": username},
        )
        return error(
            auth_error.get("status", 401),
            auth_error.get("message", "证书验证失败"),
            details={"reason": auth_error.get("reason", "verification_failed")},
        )

    password_user = user_auth.authenticate(username, request.form.get("password"))
    if not password_user or password_user["id"] != user_info["id"]:
        _audit_auth_failure(
            "bad_password",
            user={"user_id": user_info["id"], "username": username, "role": user_info["role"]},
        )
        return error(401, "用户名、密码或证书不匹配")

    if user_info["role"] in MFA_ROLES:
        mfa_record = user_auth.get_mfa_record(user_info["id"])
        if not mfa_record:
            return error(500, "读取 MFA 配置失败")
        if not mfa_record.get("totp_enabled"):
            secret = generate_totp_secret()
            return success(
                data={
                    "mfa_required": True,
                    "mfa_setup_required": True,
                    "mfa_token": _mfa_token(user_info, "enroll", secret=secret),
                    "totp_secret": secret,
                    "otpauth_uri": build_otpauth_uri(secret, user_info["username"]),
                    "expires_in": 300,
                },
                message="请先绑定认证器并输入动态验证码",
            ), 202
        return success(
            data={
                "mfa_required": True,
                "mfa_setup_required": False,
                "mfa_token": _mfa_token(user_info, "verify"),
                "expires_in": 300,
            },
            message="请输入认证器动态验证码或一次性恢复码",
        ), 202

    try:
        response = _tokens_response(user_info)
    except Exception as exc:
        return error(500, f"生成令牌失败: {str(exc)}")

    return response


@auth_bp.route("/mfa/enroll", methods=["POST"])
@login_rate_limit()
def enroll_mfa():
    data = request.get_json(silent=True) or {}
    payload, token_error = _decode_mfa_token(data.get("mfa_token"), "enroll")
    if token_error:
        return token_error
    secret = payload.get("totp_secret")
    counter = verify_totp(secret, data.get("code"), valid_window=1)
    if counter is None:
        _audit_auth_failure(
            "invalid_totp",
            user={"user_id": payload["user_id"], "username": payload["username"], "role": payload["role"]},
            event_type="AUTH_MFA",
        )
        return error(401, "动态验证码无效，请检查认证器时间")

    recovery_codes = generate_recovery_codes()
    recovery_hashes = [hash_recovery_code(payload["user_id"], code) for code in recovery_codes]
    if not user_auth.enable_totp(payload["user_id"], secret, recovery_hashes, counter):
        _audit_auth_failure(
            "enroll_conflict",
            status=409,
            user={"user_id": payload["user_id"], "username": payload["username"], "role": payload["role"]},
            event_type="AUTH_MFA",
        )
        return error(409, "TOTP 绑定失败或当前角色不需要 MFA")
    user_info = user_auth.get_user_by_id(payload["user_id"])
    return _tokens_response(user_info, recovery_codes=recovery_codes, message="TOTP 绑定并登录成功")


@auth_bp.route("/mfa/verify", methods=["POST"])
@login_rate_limit()
def verify_mfa():
    data = request.get_json(silent=True) or {}
    payload, token_error = _decode_mfa_token(data.get("mfa_token"), "verify")
    if token_error:
        return token_error
    record = user_auth.get_mfa_record(payload["user_id"])
    if not record or not record.get("totp_enabled"):
        return error(409, "该账号尚未绑定 TOTP")

    submitted = str(data.get("code") or "").strip()
    counter = verify_totp(record["totp_secret"], submitted, valid_window=1)
    if counter is not None:
        if not user_auth.consume_totp_counter(payload["user_id"], counter):
            _audit_auth_failure(
                "totp_replay",
                status=409,
                user={"user_id": record["id"], "username": record["username"], "role": record["role"]},
                event_type="AUTH_MFA",
            )
            return error(409, "该动态验证码已经使用，疑似重放请求")
    else:
        recovery_hash = hash_recovery_code(payload["user_id"], submitted)
        if not user_auth.consume_recovery_code(payload["user_id"], recovery_hash):
            _audit_auth_failure(
                "invalid_totp_or_recovery_code",
                user={"user_id": record["id"], "username": record["username"], "role": record["role"]},
                event_type="AUTH_MFA",
            )
            return error(401, "动态验证码或恢复码无效")

    user_info = user_auth.get_user_by_id(payload["user_id"])
    return _tokens_response(user_info, message="双因素认证通过，登录成功")


@auth_bp.route("/refresh", methods=["POST"])
def handle_refresh():
    """刷新 access_token 接口：POST /api/v1/auth/refresh"""
    return refresh_access_token()
