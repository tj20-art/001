import json
import os
import uuid

from flask import Blueprint, g, request
from werkzeug.utils import secure_filename

from api_service4.app.middleware.auth import jwt_required, optional_jwt, role_required
from api_service4.app.middleware.rate_limit import common_api_rate_limit
from api_service4.app.services.model_3_product import ProductSystem
from api_service4.app.utils.response import error, success
import traceback
from datetime import datetime, date


products_bp = Blueprint("products", __name__, url_prefix="/api/v1/products")
product_system = ProductSystem()

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
UPLOAD_WEB_PREFIX = "/static/uploads/products"
UPLOAD_DIR = os.path.abspath(
    os.getenv("PRODUCT_UPLOAD_DIR", os.path.join(PACKAGE_ROOT, "static", "uploads", "products"))
)
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg", "mov"}
MAX_IMAGE_COUNT = 6
VALID_PRODUCT_STATUS = {"on_sale", "off_shelf"}


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _is_truthy(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


def _get_extension(filename):
    return filename.rsplit(".", 1)[1].lower() if filename and "." in filename else ""


def _save_media_file(file_storage, allowed_exts, prefix):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None, None
    filename = secure_filename(file_storage.filename)
    ext = _get_extension(filename)
    if ext not in allowed_exts:
        return None, f"文件格式不支持：{filename}"
    _ensure_upload_dir()
    new_filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, new_filename)
    file_storage.save(save_path)
    return f"{UPLOAD_WEB_PREFIX}/{new_filename}", None


def _save_image_files(file_list):
    saved_paths = []
    for file_storage in file_list:
        file_path, file_err = _save_media_file(file_storage, ALLOWED_IMAGE_EXTENSIONS, "product_img")
        if file_err:
            for path in saved_paths:
                _delete_media_file(path)
            return None, file_err
        if file_path:
            saved_paths.append(file_path)
    return saved_paths, None


def _delete_media_file(relative_path):
    if not relative_path:
        return
    normalized = "/" + str(relative_path).lstrip("/")
    if not normalized.startswith(f"{UPLOAD_WEB_PREFIX}/"):
        return
    filename = os.path.basename(normalized)
    abs_path = os.path.abspath(os.path.join(UPLOAD_DIR, filename))
    if os.path.commonpath([UPLOAD_DIR, abs_path]) != UPLOAD_DIR:
        return
    if os.path.exists(abs_path):
        os.remove(abs_path)


def _delete_media_files(paths):
    for path in paths or []:
        _delete_media_file(path)


def _build_public_media_url(relative_path):
    if not relative_path:
        return ""
    if relative_path.startswith("http://") or relative_path.startswith("https://"):
        return relative_path
    return "/" + relative_path.lstrip("/")


def _parse_image_urls(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return [item for item in raw_value if item]
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [item for item in parsed if item]
        except Exception:
            if raw_value.strip():
                return [raw_value.strip()]
    return []


def _format_datetime(value):
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _normalize_product(product):
    item = dict(product)

    image_urls = _parse_image_urls(item.get("image_urls"))
    if not image_urls and item.get("image_url"):
        image_urls = [item.get("image_url")]

    public_image_urls = [_build_public_media_url(path) for path in image_urls]
    item["image_urls"] = public_image_urls
    item["image_url"] = public_image_urls[0] if public_image_urls else ""
    item["video_url"] = _build_public_media_url(item.get("video_url"))

    item["created_at"] = _format_datetime(item.get("created_at"))
    item["updated_at"] = _format_datetime(item.get("updated_at"))

    return item


def _get_uploaded_images():
    image_files = request.files.getlist("images")
    if not image_files:
        single_image = request.files.get("image")
        if single_image and getattr(single_image, "filename", ""):
            image_files = [single_image]
    return [file for file in image_files if getattr(file, "filename", "")]


def _get_request_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _parse_product_payload(required=False):
    raw = _get_request_payload()
    payload = {
        "name": (raw.get("name") or "").strip(),
        "category": (raw.get("category") or "").strip(),
        "description": (raw.get("description") or "").strip(),
        "price": raw.get("price"),
        "stock": raw.get("stock"),
        "status": raw.get("status"),
    }
    if required:
        if not payload["name"]:
            return None, error(400, "商品名称不能为空")
        if payload["price"] in (None, ""):
            return None, error(400, "价格不能为空")
        if payload["stock"] in (None, ""):
            return None, error(400, "库存不能为空")
    return payload, None


@products_bp.route("", methods=["POST"])
@common_api_rate_limit()
@role_required("merchant", "admin")
def create_product():
    payload, err = _parse_product_payload(required=True)
    if err:
        return err

    image_files = _get_uploaded_images()
    if len(image_files) > MAX_IMAGE_COUNT:
        return error(400, f"最多只能上传{MAX_IMAGE_COUNT}张图片")
    image_paths, image_err = _save_image_files(image_files)
    if image_err:
        return error(400, image_err)

    video_file = request.files.get("video") if not request.is_json else None
    video_path, video_err = _save_media_file(video_file, ALLOWED_VIDEO_EXTENSIONS, "product_video")
    if video_err:
        _delete_media_files(image_paths)
        return error(400, video_err)

    result, data = product_system.create_product(
        seller_id=g.user["user_id"],
        name=payload["name"],
        category=payload["category"],
        description=payload["description"],
        price=payload["price"],
        stock=payload["stock"],
        image_url=image_paths[0] if image_paths else None,
        image_urls=image_paths,
        video_url=video_path,
    )
    if not result:
        _delete_media_files(image_paths)
        _delete_media_file(video_path)
        return error(400, data)
    return success(data=data, message=data["message"]), 201


@products_bp.route("", methods=["GET"])
@optional_jwt
@common_api_rate_limit()
def list_products():
    product_id = request.args.get("product_id")
    name = request.args.get("name")
    seller_id = request.args.get("seller_id")
    mine = _is_truthy(request.args.get("mine"))
    status = request.args.get("status")

    try:
        product_id = int(product_id) if product_id else None
    except ValueError:
        return error(400, "product_id 格式错误")

    try:
        seller_id = int(seller_id) if seller_id else None
    except ValueError:
        return error(400, "seller_id 格式错误")

    if status and status not in VALID_PRODUCT_STATUS:
        return error(400, "status 仅支持 on_sale/off_shelf")

    include_off_shelf = mine
    if mine:
        if not g.user:
            return error(401, "查看自己的商品需要先登录")
        seller_id = g.user["user_id"]

    try:
        products = product_system.list_products(
            product_id=product_id,
            name=name,
            seller_id=seller_id,
            status=status,
            include_off_shelf=include_off_shelf,
        )
        processed = [_normalize_product(item) for item in products]
        return success(data={"product_list": processed}, message=f"共查询到{len(processed)}个商品")
    except ValueError as exc:
        return error(400, str(exc))
    except Exception as exc:
        traceback.print_exc()
        return error(500, "查询商品列表失败", details=str(exc))


@products_bp.route("/<int:product_id>", methods=["GET"])
@optional_jwt
@common_api_rate_limit()
def get_product(product_id):
    current_user_id = g.user["user_id"] if g.user else None
    is_admin = bool(g.user and g.user.get("role") == "admin")
    product = product_system.get_product_by_id(
        product_id,
        current_user_id=current_user_id,
        include_off_shelf=is_admin,
    )
    if not product:
        return error(404, "商品不存在")
    return success(data={"product_info": _normalize_product(product)})


@products_bp.route("/<int:product_id>", methods=["PUT"])
@common_api_rate_limit()
@role_required("merchant", "admin")
def update_product(product_id):
    existing = product_system.get_product_by_id(
        product_id,
        current_user_id=g.user["user_id"],
        include_off_shelf=g.user["role"] == "admin",
    )
    if not existing:
        return error(404, "商品不存在")
    if existing["seller_id"] != g.user["user_id"] and g.user["role"] != "admin":
        return error(403, "不能修改别人的商品")

    old_image_paths = _parse_image_urls(existing.get("image_urls"))
    if not old_image_paths and existing.get("image_url"):
        old_image_paths = [existing.get("image_url")]
    old_video_path = existing.get("video_url")

    if request.is_json:
        data = request.get_json(silent=True) or {}
        image_files = []
        video_file = None
        remove_all_images = _is_truthy(data.get("remove_all_images", False))
        remove_video = _is_truthy(data.get("remove_video", False))
    else:
        data = request.form.to_dict()
        image_files = _get_uploaded_images()
        video_file = request.files.get("video")
        remove_all_images = _is_truthy(request.form.get("remove_all_images", False))
        remove_video = _is_truthy(request.form.get("remove_video", False))

    if len(image_files) > MAX_IMAGE_COUNT:
        return error(400, f"最多只能上传{MAX_IMAGE_COUNT}张图片")

    update_data = {}
    if "name" in data and str(data.get("name")).strip():
        update_data["name"] = str(data.get("name")).strip()
    if "category" in data:
        update_data["category"] = str(data.get("category") or "").strip()
    if "description" in data:
        update_data["description"] = str(data.get("description") or "").strip()
    if "price" in data and str(data.get("price")).strip() != "":
        update_data["price"] = data.get("price")
    if "stock" in data and str(data.get("stock")).strip() != "":
        update_data["stock"] = data.get("stock")
    if "status" in data and str(data.get("status")).strip() != "":
        status = str(data.get("status")).strip()
        if status not in VALID_PRODUCT_STATUS:
            return error(400, "status 仅支持 on_sale/off_shelf")
        update_data["status"] = status

    new_image_paths = []
    if image_files:
        new_image_paths, image_err = _save_image_files(image_files)
        if image_err:
            return error(400, image_err)
        update_data["image_urls"] = new_image_paths
        update_data["image_url"] = new_image_paths[0] if new_image_paths else None
    elif remove_all_images:
        update_data["image_urls"] = []
        update_data["image_url"] = None

    new_video_path = None
    if video_file and getattr(video_file, "filename", ""):
        new_video_path, video_err = _save_media_file(video_file, ALLOWED_VIDEO_EXTENSIONS, "product_video")
        if video_err:
            _delete_media_files(new_image_paths)
            return error(400, video_err)
        update_data["video_url"] = new_video_path
    elif remove_video:
        update_data["video_url"] = None

    if not update_data:
        return error(400, "没有需要更新的字段")

    owner_id = existing["seller_id"] if g.user["role"] == "admin" else g.user["user_id"]
    result, msg = product_system.update_product_for_seller(product_id, owner_id, **update_data)
    if not result:
        _delete_media_files(new_image_paths)
        _delete_media_file(new_video_path)
        return error(400, msg)

    if "image_urls" in update_data:
        _delete_media_files(old_image_paths)
    if "video_url" in update_data and old_video_path and old_video_path != update_data["video_url"]:
        _delete_media_file(old_video_path)
    return success(message=msg)


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@common_api_rate_limit()
@role_required("merchant", "admin")
def off_shelf_product(product_id):
    existing = product_system.get_product_by_id(
        product_id,
        current_user_id=g.user["user_id"],
        include_off_shelf=g.user["role"] == "admin",
    )
    if not existing:
        return error(404, "商品不存在")
    if existing["seller_id"] != g.user["user_id"] and g.user["role"] != "admin":
        return error(403, "不能下架别人的商品")
    owner_id = existing["seller_id"] if g.user["role"] == "admin" else g.user["user_id"]
    result, msg = product_system.off_shelf_product(product_id, owner_id)
    if not result:
        return error(400, msg)
    return success(message="商品已下架")
