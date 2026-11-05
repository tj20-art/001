import os
import secrets
import sqlite3
import time
from datetime import datetime
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, render_template, request
from flask_cors import CORS

from crypto_utils import build_sign_raw, get_payment_key, make_digital_envelope, sm2_verify


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
CORS(app, origins="*")

DB_PATH = os.getenv("BANK_DB_PATH", "./mock_bank.db")
MERCHANT_ID = os.getenv("BANK_MERCHANT_ID", "MERCHANT_1001")
TIME_WINDOW_SECONDS = int(os.getenv("BANK_TIME_WINDOW_SECONDS", "300"))


def merchant_public_key() -> str:
    return get_payment_key("BANK_MERCHANT_PUBLIC_KEY_HEX", "merchant_public.key")


def ecommerce_public_key() -> str:
    return get_payment_key("BANK_ECOMMERCE_PUBLIC_KEY_HEX", "ecommerce_public.key")


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL UNIQUE,
                bank_trade_no TEXT NOT NULL UNIQUE,
                amount_cents INTEGER NOT NULL,
                merchant_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS used_nonces (
                nonce TEXT PRIMARY KEY,
                order_no TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def now_text() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_timestamp(timestamp: str):
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False, "timestamp 格式错误"
    if abs(int(time.time()) - ts) > TIME_WINDOW_SECONDS:
        return False, "支付请求已过期，疑似重放"
    return True, "ok"


def collect_payment_params(source):
    fields = ["order_no", "amount_cents", "merchant_id", "timestamp", "nonce", "return_url", "notify_url", "signature"]
    return {field: source.get(field, "") for field in fields}


def verify_payment_request(params):
    missing = [key for key, value in params.items() if not value and key not in {"return_url", "notify_url"}]
    if missing:
        return False, f"缺少参数：{','.join(missing)}"
    if params["merchant_id"] != MERCHANT_ID:
        return False, "商户号不正确"
    ok, msg = validate_timestamp(params["timestamp"])
    if not ok:
        return False, msg
    try:
        amount_cents = int(params["amount_cents"])
    except (TypeError, ValueError):
        return False, "金额格式错误"
    if amount_cents <= 0:
        return False, "金额必须大于0"

    raw = build_sign_raw(
        order_no=params["order_no"],
        amount_cents=amount_cents,
        merchant_id=params["merchant_id"],
        timestamp=params["timestamp"],
        nonce=params["nonce"],
    )
    if not sm2_verify(merchant_public_key(), raw, params["signature"]):
        return False, "签名验证失败，支付请求可能被篡改"
    return True, "ok"


def make_result(params, status="SUCCESS", reason=""):
    payload = {
        "order_no": params.get("order_no"),
        "amount_cents": int(params.get("amount_cents") or 0),
        "merchant_id": params.get("merchant_id"),
        "status": status,
        "bank_trade_no": params.get("bank_trade_no") or f"BANK{int(time.time())}{secrets.randbelow(100000):05d}",
        "timestamp": int(time.time()),
        "message": "支付成功" if status == "SUCCESS" else "支付失败",
    }
    if reason:
        payload["reason"] = reason
    return payload


def send_notify(notify_url: str, envelope):
    if not notify_url:
        return False, "notify_url 为空"
    last_error = ""
    for _ in range(3):
        try:
            resp = requests.post(notify_url, json=envelope, timeout=5)
            if 200 <= resp.status_code < 300:
                return True, resp.text
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    return False, last_error


def redirect_with_envelope(return_url: str, envelope):
    sep = "&" if "?" in return_url else "?"
    return redirect(f"{return_url}{sep}{urlencode(envelope)}")


@app.route("/")
def index():
    return redirect("/pay")


@app.route("/pay", methods=["GET"])
def pay_page():
    params = collect_payment_params(request.args)
    ok, msg = verify_payment_request(params)
    if not ok:
        return render_template("error.html", message=msg), 400

    with db_conn() as conn:
        existing = conn.execute("SELECT order_no FROM bank_transactions WHERE order_no = ?", (params["order_no"],)).fetchone()
    if existing:
        return render_template("error.html", message="该订单已处理，重复支付请求已拒绝"), 409

    return render_template(
        "pay.html",
        params=params,
        amount_yuan=int(params["amount_cents"]) / 100.0,
        sign_raw=build_sign_raw(params["order_no"], int(params["amount_cents"]), params["merchant_id"], params["timestamp"], params["nonce"]),
    )


@app.route("/pay/process", methods=["POST"])
def process_payment():
    params = collect_payment_params(request.form)
    ok, msg = verify_payment_request(params)
    if not ok:
        return render_template("error.html", message=msg), 400

    with db_conn() as conn:
        nonce_exists = conn.execute("SELECT nonce FROM used_nonces WHERE nonce = ?", (params["nonce"],)).fetchone()
        order_exists = conn.execute("SELECT order_no FROM bank_transactions WHERE order_no = ?", (params["order_no"],)).fetchone()
        if nonce_exists or order_exists:
            return render_template("error.html", message="重复支付请求已拒绝，银行不会重复扣款"), 409

        bank_trade_no = f"BANK{int(time.time())}{secrets.randbelow(100000):05d}"
        conn.execute(
            "INSERT INTO used_nonces (nonce, order_no, created_at) VALUES (?, ?, ?)",
            (params["nonce"], params["order_no"], now_text()),
        )
        conn.execute(
            """
            INSERT INTO bank_transactions (order_no, bank_trade_no, amount_cents, merchant_id, status, created_at)
            VALUES (?, ?, ?, ?, 'SUCCESS', ?)
            """,
            (params["order_no"], bank_trade_no, int(params["amount_cents"]), params["merchant_id"], now_text()),
        )
        conn.commit()

    params["bank_trade_no"] = bank_trade_no
    result = make_result(params, status="SUCCESS")
    envelope = make_digital_envelope(result, ecommerce_public_key())

    notify_ok, notify_msg = send_notify(params.get("notify_url"), envelope)
    print(f"[bank notify] order={params['order_no']} ok={notify_ok} msg={notify_msg}")

    return redirect_with_envelope(params["return_url"], envelope)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("BANK_PORT", "8080")), debug=True)
