# 限流中间层：更贴近真实场景的滑动窗口限流
# 设计目标：
# 1. 已登录请求优先按 user_id 限流，未登录按 IP 限流
# 2. 限流维度细化到「请求方法 + 接口路径」，避免不同接口互相抢额度
# 3. 在 jwt_required 之前也尽量识别 Authorization 中的 user_id，避免所有鉴权接口都退化为按 IP 限流
# 4. 响应里返回 retry_after / limit / window_seconds，便于前端提示

from functools import wraps
from threading import Lock
import time

import jwt
from flask import g, request

from api_service4.app.utils.response import error
from api_service4.config.init import get_config


_request_records = {}
_record_lock = Lock()

config = get_config()
JWT_SECRET = config.JWT_SECRET


def _clean_expired_records(timestamps, window_seconds):
    current_time = time.time()
    return [ts for ts in timestamps if current_time - ts <= window_seconds]


def _extract_user_id_from_bearer():
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        return payload.get("user_id")
    except Exception:
        return None


def _request_identity():
    if hasattr(g, "user") and g.user and g.user.get("user_id"):
        return f"user:{g.user['user_id']}"

    token_user_id = _extract_user_id_from_bearer()
    if token_user_id:
        return f"user:{token_user_id}"

    return f"ip:{request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'}"


def _request_scope(scope="route"):
    if scope == "global":
        return "global"

    endpoint = request.endpoint or request.path or "unknown"
    method = request.method or "UNKNOWN"
    return f"{method}:{endpoint}"


def rate_limit(max_requests, window_seconds=60, scope="route", key_prefix="default"):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            identity = _request_identity()
            request_scope = _request_scope(scope)
            limit_key = f"{key_prefix}:{identity}:{request_scope}"

            with _record_lock:
                timestamps = _request_records.get(limit_key, [])
                valid_timestamps = _clean_expired_records(timestamps, window_seconds)

                if len(valid_timestamps) >= max_requests:
                    retry_after = max(
                        1,
                        int(window_seconds - (time.time() - valid_timestamps[0]))
                    )
                    return error(
                        code=429,
                        message=f"请求过于频繁，请{retry_after}秒后再试",
                        details={
                            "retry_after": retry_after,
                            "limit": max_requests,
                            "window_seconds": window_seconds,
                            "scope": request_scope,
                        },
                    )

                valid_timestamps.append(time.time())
                _request_records[limit_key] = valid_timestamps

            return f(*args, **kwargs)

        return wrapper

    return decorator


def login_rate_limit():
    # 登录接口：按路由 + IP / token-user 粒度限制，5 分钟最多 10 次
    return rate_limit(max_requests=10, window_seconds=300, scope="route", key_prefix="login")


def register_rate_limit():
    # 注册接口：5 分钟最多 5 次
    return rate_limit(max_requests=5, window_seconds=300, scope="route", key_prefix="register")


def common_api_rate_limit():
    # 普通接口：按用户 + 路由统计，1 分钟最多 60 次
    return rate_limit(max_requests=60, window_seconds=60, scope="route", key_prefix="common")


def admin_api_rate_limit():
    # 管理接口：按用户 + 路由统计，1 分钟最多 30 次
    return rate_limit(max_requests=30, window_seconds=60, scope="route", key_prefix="admin")
