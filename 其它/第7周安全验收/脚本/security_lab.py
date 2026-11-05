"""Real HTTP lab using the production Flask app and an isolated MySQL schema.

No production rows are changed. JWTs are issued by the test fixture to exercise
authorization, not used as evidence that the certificate/MFA login flow passed.
"""
import argparse
import csv
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")


def start_lab(phase, port):
    if phase == "before":
        # Reproduce the saved pre-fix modules without overwriting the user's files.
        import importlib.abc
        import importlib.util
        baseline = OUT / "修复记录/修复前源码"
        original_modules = {
            "api_service4.run", "api_service4.app.middleware.rate_limit",
            "api_service4.app.api.v1.security", "api_service4.app.api.v1.products",
            "api_service4.app.utils.response",
        }
        class BaselineFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname in original_modules:
                    source = baseline / (fullname.replace(".", "/") + ".py")
                    return importlib.util.spec_from_file_location(fullname, source)
                return None
        sys.meta_path.insert(0, BaselineFinder())
    import pymysql
    from api_service4.config.init import get_config
    config = get_config()
    # Only this process's class object is changed, never the on-disk config.
    original = dict(config.MYSQL_CONFIG)
    schema = "week7_test_20261014_" + phase + "_" + secrets.token_hex(4)
    conn = pymysql.connect(**{k: original[k] for k in ("host", "port", "user", "password", "charset")},
                           connect_timeout=5, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cursor:
        cursor.execute("CREATE DATABASE `" + schema + "` CHARACTER SET utf8mb4")
    conn.close()
    with (OUT / "原始证据/isolated-databases.jsonl").open("a",encoding="utf-8") as registry:
        registry.write(json.dumps({"created_by":"security_lab.py","phase":phase,"schema":schema,"timestamp_utc":datetime.utcnow().isoformat()+"Z"})+"\n")
    config.MYSQL_CONFIG = dict(original, db=schema)
    config.JWT_SECRET = secrets.token_hex(32)
    state = OUT / ".tools" / ("lab-" + phase)
    state.mkdir(exist_ok=True)
    os.environ["CERTIFICATES_DIR"] = str(state / "certificates")
    os.environ["ROOT_CERT_PATH"] = str(state / "certificates/root_certificate.pem")
    os.environ["ROOT_PRIVATE_KEY_PATH"] = str(state / "certificates/root_private_key.pem")
    os.environ["TUNNEL_KEYS_DIR"] = str(state / "tunnel-keys")
    os.environ["PRODUCT_UPLOAD_DIR"] = str(state / "uploads")
    os.environ["SM4_KEY_HEX"] = secrets.token_hex(16)
    from api_service4.run import app
    from api_service4.app.middleware.auth import user_auth
    from api_service4.app.api.v1.products import product_system
    from api_service4.app.api.v1.security import security_control
    import jwt
    users, tokens = {}, {}
    for i, role in enumerate(("user", "merchant", "admin", "auditor"), 1):
        name = "wk7_" + role
        ok, message = user_auth.register(name, "Test!" + secrets.token_hex(5) + "Aa1", "1380000000" + str(i), role=role)
        if not ok:
            raise RuntimeError("fixture user creation failed: " + message)
        user = user_auth.get_user(name)
        users[role] = user
        tokens[role] = jwt.encode({"user_id": user["id"], "username": name, "role": role, "auth_version": 0,
                                  "mfa_verified": role in {"admin", "auditor"}, "exp": datetime.utcnow() + timedelta(hours=1)},
                                 config.JWT_SECRET, algorithm="HS256")
    ok, product = product_system.create_product(seller_id=users["merchant"]["id"], name="安全测试商品",
        description="fixture only", category="test", price="10.00", stock=10)
    if not ok:
        raise RuntimeError("fixture product creation failed: " + str(product))
    # A legacy attacker-controlled CSV field, harmless formula with no network/DDE.
    security_control.record_audit(event_type="FIXTURE_CSV", operation="probe", result="denied", http_status=400,
        ip_address="=1+1", request_path="/fixture", user={"user_id": users["user"]["id"], "username": "wk7_user", "role": "user"})
    app.config["TESTING"] = False
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", port, app, ssl_context="adhoc", threaded=False)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    lab = {"schema": schema, "users": users, "tokens": tokens, "server": server, "app": app, "product": product,
           "base": "https://127.0.0.1:" + str(port), "phase": phase, "product_system": product_system}
    # Authentication material remains private local state, outside the deliverable.
    (state / "session.json").write_text(json.dumps({"base": lab["base"], "tokens": tokens}, indent=2), encoding="utf-8")
    return lab


def exercise(lab, proxy=None):
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    from api_service4.app.middleware import rate_limit
    from api_service4.app.services.security_tunnel import request_aad, sm4_gcm_encrypt, sm4_gcm_decrypt
    from api_service4.app.services.payment_crypto import sm2_encrypt
    session = requests.Session()
    session.trust_env = False
    if proxy:
        session.proxies = {"https": proxy, "http": proxy}
    records, checks = [], []

    def call(method, path, *, role=None, headers=None, data=None, secure=False):
        request_headers = dict(headers or {})
        if role:
            request_headers["Authorization"] = "Bearer " + lab["tokens"][role]
        key = None
        if secure:
            public = session.get(lab["base"] + "/api/v1/security/public-key", verify=False, timeout=20).json()["data"]["public_key"]
            key, nonce, rid = secrets.token_bytes(16), secrets.token_hex(16), secrets.token_hex(16)
            ts = int(time.time() * 1000)
            enc = sm4_gcm_encrypt(json.dumps(data, ensure_ascii=False).encode(), key,
                                  aad=request_aad(method, path, ts, nonce, rid))
            data = dict(version="1", algorithm="SM2+SM4-GCM", encrypted_key=sm2_encrypt(public, key),
                        nonce=nonce, timestamp=ts, request_id=rid, **enc)
            request_headers["X-Secure-Envelope"] = "1"
        response = session.request(method, lab["base"] + path, headers=request_headers, json=data,
                                   verify=False, timeout=20)
        visible = response.text
        parsed = None
        try:
            parsed = response.json()
            if key and response.headers.get("X-Secure-Response") == "1":
                parsed = json.loads(sm4_gcm_decrypt(ciphertext_hex=parsed["ciphertext"], key=key,
                    iv_hex=parsed["iv"], tag_hex=parsed["tag"], aad=("RESPONSE\n" + rid).encode()))
                visible = json.dumps(parsed, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
        # Redacted raw transcript: no bearer tokens, private keys or cookie values.
        safe_headers = {k: ("Bearer <TEST_FIXTURE_TOKEN>" if k.lower() == "authorization" else v) for k,v in request_headers.items()}
        safe_response = {k:v for k,v in response.headers.items() if k.lower() not in {"set-cookie"}}
        records.append({"request": {"method": method, "url": lab["base"] + path, "headers": safe_headers, "body": data},
                        "response": {"status": response.status_code, "headers": safe_response, "body": visible}})
        return response, parsed

    # V1: demonstrate same network peer bypassing login throttling via spoofed XFF.
    rate_limit._request_records.clear()
    statuses = []
    for i in range(12):
        response, _ = call("POST", "/api/v1/auth/login", headers={"X-Forwarded-For": "198.51.100." + str(i+1)})
        statuses.append(response.status_code)
    checks.append({"id": "V1", "class": "CWE-307 / CWE-807", "statuses": statuses,
                   "vulnerable": all(status != 429 for status in statuses), "fixed": statuses[10:] == [429,429]})
    rate_limit._request_records.clear()
    # Positive control: a normal product listing still succeeds.
    response, body = call("GET", "/api/v1/products")
    checks.append({"id": "normal-product-list", "passed": response.status_code == 200 and bool(body["data"]["product_list"])})
    # V2: export actual stored fixture audit row through authenticated endpoint.
    response, _ = call("GET", "/api/v1/security/audit-logs/export", role="auditor")
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))))
    formula_row = next(row for row in rows if row["event_type"] == "FIXTURE_CSV")
    checks.append({"id": "V2", "class": "CWE-1236", "csv_cell": formula_row["ip_address"],
                   "vulnerable": formula_row["ip_address"] == "=1+1", "fixed": formula_row["ip_address"] == "'=1+1"})
    # V3: controlled DB exception fault injection, never alter the real DB service.
    from unittest.mock import patch
    marker = "INTERNAL_ONLY db=week7_fixture table=products driver=pymysql"
    with patch.object(lab["product_system"], "list_products", side_effect=RuntimeError(marker)):
        response, body = call("GET", "/api/v1/products")
    checks.append({"id": "V3", "class": "CWE-209", "status": response.status_code,
                   "fault_injection": "list_products raises a synthetic RuntimeError; DB outage not induced",
                   "vulnerable": marker in response.text, "fixed": response.status_code == 500 and marker not in response.text})
    # Existing security controls: unauthorized access and SQL injection attempts.
    response, _ = call("GET", "/api/v1/users", role="user")
    checks.append({"id": "rbac-user-admin", "passed": response.status_code == 403})
    response, body = call("GET", "/api/v1/products?name=%27%20OR%201%3D1--")
    checks.append({"id": "sql-injection-product-name", "passed": response.status_code == 200 and not body["data"]["product_list"]})
    response, _ = call("GET", "/api/v1/products?product_id=1%20OR%201%3D1")
    checks.append({"id": "sql-injection-product-id", "passed": response.status_code == 400})
    # Cross-user order isolation uses real MySQL fixtures.
    from api_service4.app.services.model_4_cart_order import CartOrderSystem
    carts = CartOrderSystem()
    with carts._db_lock:
        carts.cursor.execute("INSERT INTO orders (order_no,user_id,total_amount_cents,status) VALUES (%s,%s,%s,%s)",
                             ("WK7_FOREIGN_" + secrets.token_hex(4),lab["users"]["admin"]["id"],1000,"pending"))
        foreign_id = carts.cursor.lastrowid
        carts.conn.commit()
    response, _ = call("GET", "/api/v1/orders/" + str(foreign_id), role="user")
    checks.append({"id": "idor-foreign-order", "passed": response.status_code == 404})
    # Cross-origin/unauthenticated JSON writes cannot reach business handlers.
    response, _ = call("POST", "/api/v1/orders", headers={"Origin": "https://attacker.invalid"}, data={})
    checks.append({"id": "csrf-cross-origin-unsealed-write", "passed": response.status_code == 400 and "Access-Control-Allow-Origin" not in response.headers,
                   "scope": "JSON tunnel gate and CORS only; no claim of full CSRF coverage for multipart endpoints"})
    response, body = call("POST", "/api/v1/orders", data={}, secure=True)
    checks.append({"id": "valid-envelope-unauthenticated", "passed": response.status_code == 401 and response.headers.get("X-Secure-Response") == "1" and body.get("code") == 401})
    response, body = call("POST", "/api/v1/orders", role="user", data={}, secure=True)
    checks.append({"id": "valid-envelope-business-error", "passed": response.status_code == 400 and response.headers.get("X-Secure-Response") == "1" and body.get("code") == 400})
    output = {"phase": lab["phase"], "timestamp_utc": datetime.utcnow().isoformat() + "Z", "base": lab["base"], "database": lab["schema"],
              "authentication": "test-issued JWTs in an isolated schema; no claim of certificate/MFA end-to-end login validation",
              "proxy": proxy, "checks": checks, "transcripts": records}
    target = OUT / "原始证据" / ("http-" + lab["phase"] + ".json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"phase":lab["phase"],"checks":checks}, ensure_ascii=False, indent=2), flush=True)
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["before","after"])
    p.add_argument("--port",type=int,default=2443)
    p.add_argument("--proxy")
    p.add_argument("--hold",action="store_true")
    args = p.parse_args()
    lab = start_lab(args.phase,args.port)
    result = exercise(lab,args.proxy)
    if args.hold:
        print("LAB_READY " + lab["base"], flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    lab["server"].shutdown()
    expected = "vulnerable" if args.phase == "before" else "fixed"
    if not all(c.get(expected, c.get("passed",True)) for c in result["checks"]):
        raise SystemExit(1)
