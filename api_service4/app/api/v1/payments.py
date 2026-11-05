import os
import secrets
import time
from urllib.parse import urlencode

from flask import Blueprint, g, redirect, request

from api_service4.app.middleware.auth import role_required
from api_service4.app.middleware.rate_limit import common_api_rate_limit
from api_service4.app.services.model_4_cart_order import CartOrderSystem
from api_service4.app.services.payment_crypto import (
    build_sign_raw,
    get_payment_key,
    open_digital_envelope,
    sm2_sign,
)
from api_service4.app.utils.response import error, success


payments_bp = Blueprint("payments", __name__, url_prefix="/api/v1/pay")
cart_order_system = CartOrderSystem()


def _merchant_id() -> str:
    return os.getenv("PAYMENT_MERCHANT_ID", "MERCHANT_1001")


def _bank_pay_url() -> str:
    return os.getenv("PAYMENT_BANK_PAY_URL", "http://127.0.0.1:8080/pay")


def _frontend_result_base() -> str:
    # 银行占用 8080 时，建议 Vue 开发服务器改到 8081：npm run serve -- --port 8081
    return os.getenv("ECOMMERCE_FRONTEND_BASE_URL", "https://127.0.0.1:8081/#/pay-result")


def _backend_base_url() -> str:
    return os.getenv("ECOMMERCE_BACKEND_BASE_URL") or request.host_url.rstrip("/")


def _merchant_private_key() -> str:
    return get_payment_key("PAYMENT_MERCHANT_PRIVATE_KEY_HEX", "merchant_private.key")


def _ecommerce_private_key() -> str:
    return get_payment_key("PAYMENT_ECOMMERCE_PRIVATE_KEY_HEX", "ecommerce_private.key")


def _open_bank_envelope(payload):
    return open_digital_envelope(payload, _ecommerce_private_key())


@payments_bp.route("/start/<int:order_id>", methods=["POST"])
@common_api_rate_limit()
@role_required("user")
def start_payment(order_id):
    """电商端生成带 SM2 签名的支付请求，返回银行跳转地址。"""
    order = cart_order_system.get_order_detail(order_id, g.user["user_id"])
    if not order:
        return error(404, "订单不存在")
    if order["status"] != "pending":
        return error(400, "只有待支付订单可以发起支付")

    merchant_id = _merchant_id()
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    amount_cents = int(order["total_amount_cents"])

    raw = build_sign_raw(
        order_no=order["order_no"],
        amount_cents=amount_cents,
        merchant_id=merchant_id,
        timestamp=timestamp,
        nonce=nonce,
    )
    signature = sm2_sign(_merchant_private_key(), raw)

    params = {
        "order_no": order["order_no"],
        "amount_cents": amount_cents,
        "merchant_id": merchant_id,
        "timestamp": timestamp,
        "nonce": nonce,
        "return_url": f"{_backend_base_url()}/api/v1/pay/return",
        "notify_url": f"{_backend_base_url()}/api/v1/pay/callback",
        "signature": signature,
    }
    pay_url = f"{_bank_pay_url()}?{urlencode(params)}"
    return success(
        data={
            "pay_url": pay_url,
            "order_no": order["order_no"],
            "amount_cents": amount_cents,
            "sign_raw": raw,
        },
        message="支付请求已生成，请跳转银行确认支付",
    )


@payments_bp.route("/return", methods=["GET"])
def pay_return():
    """同步跳转入口：仅解密并把展示结果交给前端页面，不作为订单最终入账依据。"""
    envelope = {
        "encrypted_key": request.args.get("encrypted_key"),
        "iv": request.args.get("iv"),
        "data": request.args.get("data"),
    }
    try:
        result = _open_bank_envelope(envelope)
        params = {
            "order_no": result.get("order_no", ""),
            "status": result.get("status", "UNKNOWN"),
            "bank_trade_no": result.get("bank_trade_no", ""),
            "message": result.get("message") or result.get("reason") or "银行已返回支付结果",
        }
    except Exception as exc:
        params = {
            "status": "FAILED",
            "message": f"支付结果解密失败：{str(exc)}",
        }
    return redirect(f"{_frontend_result_base()}?{urlencode(params)}")


@payments_bp.route("/callback", methods=["POST"])
def pay_callback():
    """异步回调入口：银行后台通知电商，电商解密后幂等更新订单状态。"""
    envelope = request.get_json(silent=True) or {}
    try:
        result = _open_bank_envelope(envelope)
    except Exception as exc:
        return error(400, "支付回调解密失败", details=str(exc))

    try:
        result_timestamp = int(result.get("timestamp", 0))
    except (TypeError, ValueError):
        return error(400, "支付结果 timestamp 格式错误")
    if abs(int(time.time()) - result_timestamp) > 600:
        return error(400, "支付结果已过期，疑似重放")

    if result.get("status") != "SUCCESS":
        return error(400, result.get("reason") or "银行返回支付失败")

    order_no = result.get("order_no")
    amount_cents = result.get("amount_cents")
    bank_trade_no = result.get("bank_trade_no")
    if not order_no or amount_cents is None or not bank_trade_no:
        return error(400, "支付结果字段不完整")

    ok, msg = cart_order_system.mark_order_paid_by_no(
        order_no=order_no,
        amount_cents=int(amount_cents),
        bank_trade_no=bank_trade_no,
    )
    if not ok:
        return error(400, msg)

    return success(data={"order_no": order_no}, message=msg)
