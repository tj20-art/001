from flask import Blueprint, g, request

from api_service4.app.middleware.auth import role_required
from api_service4.app.middleware.rate_limit import common_api_rate_limit
from api_service4.app.services.model_4_cart_order import CartOrderSystem
from api_service4.app.utils.response import error, success


orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders")
cart_order_system = CartOrderSystem()


@orders_bp.route("", methods=["POST"])
@common_api_rate_limit()
@role_required("user")
def create_order():
    result, payload = cart_order_system.create_order_from_selected_cart(g.user["user_id"])
    if not result:
        return error(400, payload)
    detail = cart_order_system.get_order_detail(payload["order_id"], g.user["user_id"])
    return success(data={"order": detail}, message=payload["message"]), 201


@orders_bp.route("", methods=["GET"])
@common_api_rate_limit()
@role_required("user")
def list_orders():
    status = request.args.get("status")
    orders = cart_order_system.list_orders(g.user["user_id"], status=status)
    return success(data={"order_list": orders}, message=f"共查询到{len(orders)}个订单")


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
