from flask import Blueprint, g, request

from api_service4.app.middleware.auth import role_required
from api_service4.app.middleware.rate_limit import admin_api_rate_limit, common_api_rate_limit
from api_service4.app.services.model_4_cart_order import CartOrderSystem
from api_service4.app.utils.pagination import pagination_data, parse_pagination
from api_service4.app.utils.response import error, success


carts_bp = Blueprint("carts", __name__, url_prefix="/api/v1/cart")
cart_order_system = CartOrderSystem()


def _normalize_cart_response(items):
    total_selected_cents = sum(item["subtotal_cents"] for item in items if item["selected"])
    return {
        "items": items,
        "selected_total_cents": total_selected_cents,
        "selected_total": total_selected_cents / 100.0,
    }


@carts_bp.route("/items", methods=["POST"])
@common_api_rate_limit()
@role_required("user")
def add_cart_item():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    quantity = data.get("quantity")
    if product_id in (None, "") or quantity in (None, ""):
        return error(400, "缺少 product_id 或 quantity")
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return error(400, "product_id 格式错误")
    result, msg = cart_order_system.add_to_cart(g.user["user_id"], product_id, quantity)
    if not result:
        return error(400, msg)
    items = cart_order_system.list_cart_items(g.user["user_id"])
    return success(data=_normalize_cart_response(items), message=msg)


@carts_bp.route("/items", methods=["GET"])
@common_api_rate_limit()
@role_required("user")
def list_cart_items():
    items = cart_order_system.list_cart_items(g.user["user_id"])
    return success(data=_normalize_cart_response(items), message=f"共查询到{len(items)}条购物车记录")


@carts_bp.route("/items/<int:cart_item_id>", methods=["PUT"])
@common_api_rate_limit()
@role_required("user")
def update_cart_item(cart_item_id):
    data = request.get_json(silent=True) or {}
    quantity = data.get("quantity") if "quantity" in data else None
    selected = data.get("selected") if "selected" in data else None
    result, msg = cart_order_system.update_cart_item(
        cart_item_id,
        g.user["user_id"],
        quantity=quantity,
        selected=selected,
    )
    if not result:
        status_code = 403 if "无权限" in msg else 400
        return error(status_code, msg)
    items = cart_order_system.list_cart_items(g.user["user_id"])
    return success(data=_normalize_cart_response(items), message=msg)


@carts_bp.route("/items/<int:cart_item_id>", methods=["DELETE"])
@common_api_rate_limit()
@role_required("user")
def delete_cart_item(cart_item_id):
    result, msg = cart_order_system.remove_cart_item(cart_item_id, g.user["user_id"])
    if not result:
        return error(403 if "无权限" in msg else 400, msg)
    items = cart_order_system.list_cart_items(g.user["user_id"])
    return success(data=_normalize_cart_response(items), message=msg)


@carts_bp.route("/items", methods=["DELETE"])
@common_api_rate_limit()
@role_required("user")
def clear_cart():
    result, msg = cart_order_system.clear_cart(g.user["user_id"])
    if not result:
        return error(400, msg)
    return success(data=_normalize_cart_response([]), message=msg)


@carts_bp.route("/select", methods=["PUT"])
@common_api_rate_limit()
@role_required("user")
def bulk_select_cart_items():
    data = request.get_json(silent=True) or {}
    if "selected" not in data:
        return error(400, "缺少 selected 字段")
    selected = bool(data.get("selected"))
    cart_item_ids = data.get("cart_item_ids") or []
    try:
        cart_item_ids = [int(item_id) for item_id in cart_item_ids]
    except (TypeError, ValueError):
        return error(400, "cart_item_ids 格式错误")
    result, msg = cart_order_system.set_selected_bulk(g.user["user_id"], selected, cart_item_ids or None)
    if not result:
        return error(400, msg)
    items = cart_order_system.list_cart_items(g.user["user_id"])
    return success(data=_normalize_cart_response(items), message=msg)


@carts_bp.route("/management", methods=["GET"])
@admin_api_rate_limit()
@role_required("admin")
def admin_list_cart_owners():
    try:
        page, page_size = parse_pagination(request.args)
    except ValueError as exc:
        return error(400, str(exc))
    raw_user_id = request.args.get("user_id", "").strip()
    try:
        user_id = int(raw_user_id) if raw_user_id else None
    except ValueError:
        return error(400, "用户 ID 须为有效的正整数")
    if user_id is not None and not 1 <= user_id <= 2_147_483_647:
        return error(400, "用户 ID 须为有效的正整数")
    username = request.args.get("username", "").strip()
    if len(username) > 64:
        return error(400, "用户名搜索词过长")

    owners, total = cart_order_system.list_cart_owners(
        user_id=user_id, username=username, page=page, page_size=page_size,
    )
    return success(data={"owners": owners, "pagination": pagination_data(page, page_size, total)})


@carts_bp.route("/management/<int:user_id>", methods=["GET"])
@admin_api_rate_limit()
@role_required("admin")
def admin_get_cart(user_id):
    cart = cart_order_system.get_cart_for_admin(user_id)
    if cart is None:
        return error(404, "用户不存在")
    owner, items = cart
    return success(data={"owner": owner, "items": items})


@carts_bp.route("/management/<int:user_id>/items/<int:cart_item_id>", methods=["PUT"])
@admin_api_rate_limit()
@role_required("admin")
def admin_update_cart_quantity(user_id, cart_item_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"quantity"}:
        return error(400, "请只提交商品数量")
    quantity = data["quantity"]
    if type(quantity) is not int or quantity < 1:
        return error(400, "数量须为正整数")
    updated, message = cart_order_system.update_cart_item(cart_item_id, user_id, quantity=quantity)
    if not updated:
        return error(404 if "无权限" in message else 400, message)
    return success(message=message)


@carts_bp.route("/management/<int:user_id>/items/<int:cart_item_id>", methods=["DELETE"])
@admin_api_rate_limit()
@role_required("admin")
def admin_delete_cart_item(user_id, cart_item_id):
    removed, message = cart_order_system.remove_cart_item(cart_item_id, user_id)
    if not removed:
        return error(404 if "无权限" in message else 400, message)
    return success(message=message)


@carts_bp.route("/management/<int:user_id>/items", methods=["DELETE"])
@admin_api_rate_limit()
@role_required("admin")
def admin_clear_cart(user_id):
    cleared, message = cart_order_system.clear_cart(user_id, require_owner=True)
    if not cleared:
        return error(404 if message == "用户不存在" else 400, message)
    return success(message=message)
