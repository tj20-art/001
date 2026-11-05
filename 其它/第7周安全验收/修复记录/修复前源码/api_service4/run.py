import os

from cryptography.exceptions import InvalidTag
from flask import Flask, g, request
from flask_cors import CORS

from api_service4.app.api.v1.auth import auth_bp
from api_service4.app.api.v1.carts import carts_bp
from api_service4.app.api.v1.orders import orders_bp
from api_service4.app.api.v1.payments import payments_bp
from api_service4.app.api.v1.products import products_bp
from api_service4.app.api.v1.users import users_bp
from api_service4.app.api.v1.security import security_bp
from api_service4.app.services.security_control import SecurityControlSystem
from api_service4.app.services.security_tunnel import decrypt_flask_request, encrypt_flask_response
from api_service4.app.services.security_tunnel_policy import requires_security_tunnel
from api_service4.app.utils.response import error
from api_service4.app.services.gm_crypto import generate_root_ca_real
from api_service4.config.init import get_config


PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.path.abspath(os.getenv("CERTIFICATES_DIR", os.path.join(PACKAGE_ROOT, "certificates")))
ROOT_CERT_PATH = os.path.abspath(os.getenv("ROOT_CERT_PATH", os.path.join(CERT_DIR, "root_certificate.pem")))
ROOT_PRIVATE_KEY_PATH = os.path.abspath(
    os.getenv("ROOT_PRIVATE_KEY_PATH", os.path.join(CERT_DIR, "root_private_key.pem"))
)



def check_and_generate_root_ca():
    os.makedirs(CERT_DIR, exist_ok=True)
    if os.path.exists(ROOT_CERT_PATH) and os.path.exists(ROOT_PRIVATE_KEY_PATH):
        print("根证书和私钥已存在，跳过生成步骤。")
        return

    print("根证书或私钥不存在，正在生成根证书...")
    private_key_pem, _public_key_pem, root_cert_pem = generate_root_ca_real()
    with open(ROOT_CERT_PATH, "w", encoding="utf-8") as cert_file:
        cert_file.write(root_cert_pem)
    with open(ROOT_PRIVATE_KEY_PATH, "w", encoding="utf-8") as private_key_file:
        private_key_file.write(private_key_pem)
    print("根证书和私钥生成并保存成功！")


check_and_generate_root_ca()
config = get_config(env="dev")

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
CORS(app, origins=config.CORS_ORIGINS, expose_headers=["X-Secure-Response", "Content-Disposition"])

security_control = SecurityControlSystem()

@app.before_request
def open_application_security_tunnel():
    if not requires_security_tunnel(
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        mimetype=request.mimetype,
    ):
        return None
    if request.headers.get("X-Secure-Envelope") != "1":
        if config.TUNNEL_REQUIRED:
            return error(400, "敏感写请求必须使用应用层安全信封", details={"reason": "envelope_required"})
        return None
    if not request.is_json:
        return error(400, "安全信封必须使用 application/json", details={"reason": "invalid_envelope"})
    try:
        decrypt_flask_request(security_control)
    except TimeoutError as exc:
        return error(408, str(exc), details={"reason": "expired_timestamp"})
    except FileExistsError as exc:
        return error(409, str(exc), details={"reason": "replay_detected"})
    except InvalidTag:
        return error(400, "SM4-GCM 完整性校验失败，请求可能被篡改", details={"reason": "invalid_tag"})
    except (ValueError, TypeError) as exc:
        return error(400, str(exc), details={"reason": "invalid_envelope"})


@app.after_request
def audit_and_seal_response(response):
    user = getattr(g, "user", None)
    should_audit = bool(user) and (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        or user.get("role") in {"admin", "auditor"}
        or response.status_code >= 400
    )
    if should_audit:
        view_args = request.view_args or {}
        resource_id = next((value for key, value in view_args.items() if key.endswith("_id")), None)
        security_control.record_audit(
            event_type=(request.endpoint or "UNKNOWN").upper(),
            resource_type=(request.blueprint or "api").lower(),
            resource_id=resource_id,
            operation=request.method.lower(),
            result="success" if response.status_code < 400 else "denied" if response.status_code in {401, 403} else "failure",
            http_status=response.status_code,
            user=user,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            request_method=request.method,
            request_path=request.path,
            details={"secure_tunnel": bool(getattr(g, "secure_tunnel", None))},
        )
    return encrypt_flask_response(response)

app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(products_bp)
app.register_blueprint(carts_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(payments_bp)
app.register_blueprint(security_bp)


if __name__ == "__main__":
    ssl_context = None
    if config.HTTPS_ENABLED:
        if config.TLS_CERT_PATH and config.TLS_KEY_PATH:
            ssl_context = (config.TLS_CERT_PATH, config.TLS_KEY_PATH)
        else:
            ssl_context = "adhoc"
    app.run(
        host="0.0.0.0",
        port=config.PORT,
        debug=os.getenv("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
        ssl_context=ssl_context,
    )
