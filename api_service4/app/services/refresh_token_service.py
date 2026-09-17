import hashlib
import secrets


def generate_refresh_token():
    """生成只向客户端展示一次的高熵不透明刷新令牌。"""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token):
    """生成用于数据库存储和查找的刷新令牌哈希。"""
    if not isinstance(token, str) or not token:
        raise ValueError("refresh_token 必须是非空字符串")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
