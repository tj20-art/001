import csv
import io

from flask import Blueprint, Response, request

from api_service4.app.middleware.auth import role_required
from api_service4.app.middleware.rate_limit import admin_api_rate_limit, common_api_rate_limit
from api_service4.app.services.security_control import SecurityControlSystem
from api_service4.app.services.security_tunnel import (
    ALGORITHM_NAME,
    PROTOCOL_VERSION,
    load_or_create_tunnel_keypair,
)
from api_service4.app.utils.response import error, success


security_bp = Blueprint("security", __name__, url_prefix="/api/v1/security")
security_control = SecurityControlSystem()


PERMISSION_MATRIX = {
    "user": {
        "description": "普通用户，只能管理自己的购物车、订单、支付和个人资料",
        "permissions": [
            "product:read:public",
            "profile:read:self",
            "profile:update:self",
            "cart:*:self",
            "order:*:self",
            "payment:create:self",
        ],
    },
    "merchant": {
        "description": "商户，只能发布和管理自己名下的商品",
        "permissions": [
            "product:read:public",
            "product:create:own",
            "product:update:own",
            "product:delete:own",
            "profile:read:self",
            "profile:update:self",
        ],
    },
    "admin": {
        "description": "管理员，管理用户与全站商品，登录必须完成 TOTP",
        "permissions": [
            "user:read:any",
            "user:role:update",
            "user:delete:any",
            "product:*:any",
            "audit:read",
            "audit:export",
            "certificate:issue",
        ],
    },
    "auditor": {
        "description": "审计员，只读查看与导出审计数据，登录必须完成 TOTP",
        "permissions": ["audit:read", "audit:export", "security:read"],
    },
}


@security_bp.route("/public-key", methods=["GET"])
@common_api_rate_limit()
def get_tunnel_public_key():
    keypair = load_or_create_tunnel_keypair()
    return success(
        data={
            "version": PROTOCOL_VERSION,
            "algorithm": ALGORITHM_NAME,
            "public_key": keypair["public_key"],
            "time_window_seconds": 120,
        },
        message="应用层安全隧道公钥",
    )


@security_bp.route("/permissions", methods=["GET"])
@admin_api_rate_limit()
@role_required("admin", "auditor")
def get_permission_matrix():
    return success(data={"roles": PERMISSION_MATRIX})


def _audit_filters():
    try:
        limit = int(request.args.get("limit", 100))
        user_id = request.args.get("user_id")
        if user_id not in (None, ""):
            user_id = int(user_id)
    except (TypeError, ValueError):
        return None, error(400, "limit 或 user_id 格式错误")
    return {
        "limit": max(1, min(limit, 500)),
        "event_type": request.args.get("event_type") or None,
        "result": request.args.get("result") or None,
        "user_id": user_id,
    }, None


@security_bp.route("/audit-logs", methods=["GET"])
@admin_api_rate_limit()
@role_required("admin", "auditor")
def get_audit_logs():
    filters, filter_error = _audit_filters()
    if filter_error:
        return filter_error
    rows = security_control.list_audit_logs(**filters)
    return success(data={"audit_logs": rows}, message=f"共返回 {len(rows)} 条审计记录")


@security_bp.route("/audit-logs/export", methods=["GET"])
@admin_api_rate_limit()
@role_required("admin", "auditor")
def export_audit_logs():
    filters, filter_error = _audit_filters()
    if filter_error:
        return filter_error
    filters["limit"] = min(filters["limit"], 500)
    rows = security_control.list_audit_logs(**filters)
    output = io.StringIO()
    fieldnames = [
        "id",
        "created_at",
        "user_id",
        "username",
        "role",
        "event_type",
        "resource_type",
        "resource_id",
        "operation",
        "result",
        "http_status",
        "ip_address",
        "request_method",
        "request_path",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv", "Cache-Control": "no-store"},
    )
