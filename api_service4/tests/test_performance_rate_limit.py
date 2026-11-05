"""Exercise the local benchmark switch through HTTP requests without a database."""
from flask import Flask
import pytest

from api_service4.app.middleware import rate_limit as limiter


@pytest.fixture(autouse=True)
def clear_rate_records():
    limiter._request_records.clear()
    yield
    limiter._request_records.clear()


@pytest.mark.parametrize("mode", [None, "0", "true", "1"])
@pytest.mark.parametrize("kind,normal_limit", [("login", 10), ("common", 60)])
def test_only_explicit_benchmark_mode_raises_http_budget(monkeypatch, mode, kind, normal_limit):
    if mode is None:
        monkeypatch.delenv("PERF_TEST_MODE", raising=False)
    else:
        monkeypatch.setenv("PERF_TEST_MODE", mode)
    app = Flask(__name__)
    decorator = limiter.login_rate_limit if kind == "login" else limiter.common_api_rate_limit

    @app.route("/probe", methods=["POST"])
    @decorator()
    def probe():
        return "ok"

    client = app.test_client()
    for _ in range(normal_limit):
        assert client.post("/probe").status_code == 200
    response = client.post("/probe")
    if mode == "1":
        assert response.status_code == 200
    else:
        assert response.status_code == 429
        assert response.get_json()["details"]["limit"] == normal_limit


@pytest.mark.parametrize("kind,limit", [("register", 5), ("admin", 30)])
def test_benchmark_mode_keeps_other_route_limits(monkeypatch, kind, limit):
    monkeypatch.setenv("PERF_TEST_MODE", "1")
    app = Flask(__name__)
    decorator = limiter.register_rate_limit if kind == "register" else limiter.admin_api_rate_limit

    @app.route("/probe", methods=["POST"])
    @decorator()
    def probe():
        return "ok"

    client = app.test_client()
    for _ in range(limit):
        assert client.post("/probe").status_code == 200
    response = client.post("/probe")
    assert response.status_code == 429
    assert response.get_json()["details"]["limit"] == limit
