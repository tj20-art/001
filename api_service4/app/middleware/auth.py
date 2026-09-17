import jwt
from datetime import datetime, timedelta
from functools import wraps

from flask import g, request

from api_service4.app.services.model_2_denglu import UserAuthSystem
from api_service4.app.services.refresh_token_service import generate_refresh_token, hash_refresh_token
from api_service4.app.utils.response import error
from api_service4.config.init import get_config


config = get_config()
JWT_SECRET = config.JWT_SECRET
JWT_ACCESS_EXPIRE = config.JWT_ACCESS_EXPIRE
JWT_REFRESH_EXPIRE = config.JWT_REFRESH_EXPIRE

user_auth = UserAuthSystem(jwt_secret=JWT_SECRET)


def _decode_bearer_token(allow_expired=False):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, "missing"

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": not allow_expired},
        )
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "expired"
    except jwt.InvalidTokenError:
        return None, "invalid"


def _set_request_user(payload):
    g.user = {
        "user_id": payload["user_id"],
        "username": payload["username"],
        "role": payload["role"],
    }


MFA_ROLES = {"admin", "auditor"}


def _token_version_matches(payload, current_user):
    try:
        return int(payload.get("auth_version", 0)) == int(current_user.get("auth_version") or 0)
    except (TypeError, ValueError):
        return False


def generate_tokens(user_info, *, mfa_verified=False):
    if user_info["role"] in MFA_ROLES and not mfa_verified:
        raise PermissionError("管理员和审计员必须先完成 TOTP 验证")
    now = datetime.utcnow()
    access_payload = {
        "user_id": user_info["id"],
        "username": user_info["username"],
        "role": user_info["role"],
        "mfa_verified": bool(mfa_verified),
        "auth_version": int(user_info.get("auth_version") or 0),
        "iat": now,
        "exp": now + timedelta(seconds=JWT_ACCESS_EXPIRE),
    }
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm="HS256")
    refresh_token = generate_refresh_token()
    refresh_token_hash = hash_refresh_token(refresh_token)

    expiry = now + timedelta(seconds=JWT_REFRESH_EXPIRE)
    if not user_auth.store_refresh_token_hash(user_info["id"], refresh_token_hash, expiry):
        raise RuntimeError("refresh_token 存储失败")

    return {"access_token": access_token, "refresh_token": refresh_token}


def refresh_access_token():
    try:
        data = request.get_json(silent=True) or {}
        refresh_token = data.get("refresh_token")
        user_id = data.get("user_id")
        if not refresh_token or not user_id:
            return error(400, "缺少 user_id 或 refresh_token 参数")

        try:
            refresh_token_hash = hash_refresh_token(refresh_token)
        except ValueError:
            return error(400, "refresh_token 格式错误")

        # 原子消费旧令牌，防止同一个刷新令牌被并发或重复使用。
        if not user_auth.consume_refresh_token_hash(user_id, refresh_token_hash):
            return error(401, "令牌未存储或已失效")

        current_user = user_auth.get_user_by_id(user_id)
        if not current_user:
            return error(401, "用户不存在或已禁用")

        # 能进入此处的令牌只能由完成了相应登录/MFA 流程的 generate_tokens 签发。
        rotated_tokens = generate_tokens(
            current_user,
            mfa_verified=current_user["role"] in MFA_ROLES,
        )
        return {
            "code": 0,
            "data": rotated_tokens,
            "message": "令牌刷新成功",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as exc:
        return error(500, f"刷新令牌失败: {str(exc)}")


def jwt_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        payload, reason = _decode_bearer_token()
        if reason == "missing":
            return error(401, "未提供有效令牌，请先登录")
        if reason == "expired":
            return error(401, "令牌已过期，请重新登录")
        if reason == "invalid":
            return error(401, "无效令牌，请重新登录")

        current_user = user_auth.get_user_by_id(payload.get("user_id"))
        if not current_user:
            return error(401, "用户不存在、已禁用或登录状态已失效")
        if not _token_version_matches(payload, current_user):
            return error(401, "账号安全信息已变更，请重新登录")
        if current_user["role"] in MFA_ROLES and not payload.get("mfa_verified"):
            return error(401, "该角色必须完成 TOTP 双因素认证")
        payload["role"] = current_user["role"]
        payload["username"] = current_user["username"]
        _set_request_user(payload)
        return f(*args, **kwargs)

    return wrapper


def optional_jwt(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        g.user = None
        payload, reason = _decode_bearer_token()
        if reason is None and payload:
            current_user = user_auth.get_user_by_id(payload.get("user_id"))
            if current_user and _token_version_matches(payload, current_user):
                payload["role"] = current_user["role"]
                payload["username"] = current_user["username"]
                _set_request_user(payload)
        return f(*args, **kwargs)

    return wrapper


def role_required(*required_roles):
    allowed_roles = set(required_roles)

    def decorator(f):
        @wraps(f)
        @jwt_required
        def wrapper(*args, **kwargs):
            if g.user["role"] not in allowed_roles:
                return error(403, f"权限不足，需要角色: {', '.join(sorted(allowed_roles))}")
            return f(*args, **kwargs)

        return wrapper

    return decorator
