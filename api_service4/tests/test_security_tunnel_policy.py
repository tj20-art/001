from api_service4.app.services.security_tunnel_policy import requires_security_tunnel


def test_bodyless_write_requests_require_security_tunnel():
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert requires_security_tunnel(
            method=method,
            path="/api/v1/orders/1/cancel",
            endpoint="orders.cancel_order",
            mimetype=None,
        )


def test_only_explicit_non_json_protocols_are_exempt():
    assert not requires_security_tunnel(
        method="POST",
        path="/api/v1/auth/login",
        endpoint="auth.login",
        mimetype="multipart/form-data",
    )
    assert not requires_security_tunnel(
        method="POST",
        path="/api/v1/products",
        endpoint="products.create_product",
        mimetype="multipart/form-data",
    )
    assert requires_security_tunnel(
        method="POST",
        path="/api/v1/orders",
        endpoint="orders.create_order",
        mimetype="multipart/form-data",
    )


def test_safe_and_non_api_requests_do_not_require_security_tunnel():
    assert not requires_security_tunnel(method="GET", path="/api/v1/orders")
    assert not requires_security_tunnel(method="POST", path="/health")
