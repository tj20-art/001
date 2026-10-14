"""Regression tests for three independently reproduced security weaknesses."""
from datetime import datetime, timedelta

from flask import Flask
import jwt
import pytest

from api_service4.app.middleware import rate_limit as limiter
from api_service4.app.api.v1.security import _csv_safe_value
from api_service4.app.utils.response import error


@pytest.fixture
def app():
    limiter._request_records.clear()
    application = Flask(__name__)
    yield application
    limiter._request_records.clear()


def test_spoofed_forwarded_headers_cannot_reset_limit(app):
    @app.route("/probe", methods=["POST"])
    @limiter.rate_limit(2, identity_scope="ip")
    def probe():
        return "ok"
    client = app.test_client()
    results = [client.post("/probe", headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code for i in range(3)]
    assert results == [200, 200, 429]


def test_login_budget_cannot_be_reset_with_valid_bearer_tokens(app):
    @app.route("/login", methods=["POST"])
    @limiter.login_rate_limit()
    def probe():
        return "ok"
    client = app.test_client()
    for i in range(10):
        token = jwt.encode({"user_id": i+1, "exp": datetime.utcnow()+timedelta(minutes=1)}, limiter.JWT_SECRET, algorithm="HS256")
        assert client.post("/login", headers={"Authorization": "Bearer " + token}).status_code == 200
    assert client.post("/login").status_code == 429


def test_distinct_network_peers_have_independent_budgets(app):
    @app.route("/probe")
    @limiter.rate_limit(1, identity_scope="ip")
    def probe():
        return "ok"
    client = app.test_client()
    assert client.get("/probe", environ_base={"REMOTE_ADDR":"192.0.2.1"}).status_code == 200
    assert client.get("/probe", environ_base={"REMOTE_ADDR":"192.0.2.1"}).status_code == 429
    assert client.get("/probe", environ_base={"REMOTE_ADDR":"192.0.2.2"}).status_code == 200


def test_expired_token_does_not_set_throttle_identity(app):
    token = jwt.encode({"user_id": 42, "exp": datetime.utcnow()-timedelta(minutes=1)},limiter.JWT_SECRET,algorithm="HS256")
    with app.test_request_context(headers={"Authorization":"Bearer " + token}, environ_base={"REMOTE_ADDR":"192.0.2.1"}):
        assert limiter._extract_user_id_from_bearer() is None
        assert limiter._request_identity() == "ip:192.0.2.1"


@pytest.mark.parametrize("payload", ["=1+1", "+SUM(1,2)", "-1+2", "@SUM(1,2)", "  =1+1", "\t=1+1", "\r=1+1", "\n=1+1"])
def test_csv_formula_prefixes_are_neutralized(payload):
    assert _csv_safe_value(payload) == "'" + payload


@pytest.mark.parametrize("value", ["普通审计记录", "2026-10-14", "GET", 200, -1, None])
def test_csv_normal_values_are_preserved(value):
    assert _csv_safe_value(value) == value


def test_server_errors_do_not_disclose_exception_details(app):
    with app.app_context():
        response, status = error(500, "database credentials INTERNAL_ONLY", details="driver/internal/path")
        assert status == 500
        data = response.get_json()
        assert data["details"] == {"reason":"internal_error"}
        assert "INTERNAL_ONLY" not in response.get_data(as_text=True)
        assert "driver/internal/path" not in response.get_data(as_text=True)


def test_validation_error_details_remain_available(app):
    with app.app_context():
        response, status = error(400, "请求格式错误", details={"reason":"invalid_envelope"})
        assert status == 400
        assert response.get_json()["details"]["reason"] == "invalid_envelope"
