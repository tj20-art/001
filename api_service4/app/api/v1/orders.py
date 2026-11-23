from uuid import UUID

from flask import Blueprint, g, request

from api_service4.app.middleware.auth import role_required
from api_service4.app.middleware.rate_limit import common_api_rate_limit
from api_service4.app.services.model_4_cart_order import CartOrderSystem
from api_service4.app.utils.pagination import pagination_data, parse_pagination
from api_service4.app.utils.response import error, success


orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders")
cart_order_system = CartOrderSystem()


@orders_bp.route("", methods=["POST"])
@common_api_rate_limit()
@role_required("user")
def create_order():
    data = request.get_json(silent=True)
    if data is not None and not isinstance(data, dict):
        return error(400, "下单请求格式错误")
    request_key = (data or {}).get("checkout_key")
    if request_key is not None:
        if not isinstance(request_key, str) or len(request_key) != 36:
            return error(400, "下单标识格式错误")
        try:
            request_key = str(UUID(request_key))
        except ValueError:
            return error(400, "下单标识格式错误")
    result, payload = cart_order_system.create_order_from_selected_cart(g.user["user_id"], request_key)
    if not result:
        return error(400, payload)
    return success(data={"order": payload["order"]}, message=payload["message"]), 200 if payload["replayed"] else 201


@orders_bp.route("", methods=["GET"])
@common_api_rate_limit()
@role_required("user")
def list_orders():
    status = request.args.get("status") or None
    if status and status not in {"pending", "paid", "cancelled"}:
        return error(400, "订单状态不受支持")
    try:
        page, page_size = parse_pagination(request.args)
    except ValueError as exc:
        return error(400, str(exc))
    orders, total, summary = cart_order_system.list_orders(g.user["user_id"], status, page=page, page_size=page_size)
    return success(data={
        "order_list": orders,
        "pagination": pagination_data(page, page_size, total),
        "summary": summary,
    })


@orders_bp.route("/status", methods=["GET"])
@common_api_rate_limit()
@role_required("user")
def get_order_status():
    order_no = request.args.get("order_no", "").strip()
    if not order_no or len(order_no) > 64:
        return error(400, "订单号格式错误")
    order = cart_order_system.get_order_status(order_no, g.user["user_id"])
    if not order:
        return error(404, "订单不存在")
    return success(data={"order": order})


@orders_bp.route("/<int:order_id>", methods=["GET"])
@common_api_rate_limit()
@role_required("user")
def get_order_detail(order_id):
    order = cart_order_system.get_order_detail(order_id, g.user["user_id"])
    if not order:
        return error(404, "订单不存在")
    return success(data={"order": order})


@orders_bp.route("/<int:order_id>/cancel", methods=["POST"])
@common_api_rate_limit()
@role_required("user")
def cancel_order(order_id):
    result, msg = cart_order_system.cancel_order(order_id, g.user["user_id"])
    if not result:
        return error(403 if "无权限" in msg else 400, msg)
    order = cart_order_system.get_order_detail(order_id, g.user["user_id"])
    return success(data={"order": order}, message=msg)
