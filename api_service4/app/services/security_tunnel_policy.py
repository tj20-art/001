"""Request policy for the application-layer security tunnel."""


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

TUNNEL_EXEMPT_PATHS = {
    "/api/v1/auth/login",  # Certificate login uses multipart/form-data over HTTPS.
    "/api/v1/pay/callback",  # Bank callback uses its own SM2 + SM4 envelope.
}

PLAIN_MULTIPART_ENDPOINTS = {
    "products.create_product",
    "products.update_product",
}


def requires_security_tunnel(*, method, path, endpoint=None, mimetype=None):
    """Return whether an API request must carry the application-layer envelope."""
    if str(method).upper() in SAFE_METHODS or not str(path).startswith("/api/v1/"):
        return False
    if path in TUNNEL_EXEMPT_PATHS:
        return False
    if endpoint in PLAIN_MULTIPART_ENDPOINTS and mimetype == "multipart/form-data":
        return False
    return True


__all__ = ["requires_security_tunnel"]
