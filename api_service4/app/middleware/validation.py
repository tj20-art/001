from functools import wraps
from html import escape
import re

from flask import request

from api_service4.app.utils.response import error


def _validate_field(value, field_type):
    if field_type == "username":
        return bool(re.match(r"^[a-zA-Z0-9_]{5,20}$", value)), "用户名需为5-20位字母、数字或下划线"
    if field_type == "password":
        return bool(re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()+=-]).{8,20}$", value)), "密码需含大小写字母、数字、特殊符号，8-20位"
    if field_type == "phone":
        return bool(re.match(r"^1[3-9]\d{9}$", value)), "手机号需为11位合法格式（如13800138000）"
    if field_type == "role":
        valid_roles = ["user", "merchant", "admin", "auditor"]
        return value in valid_roles, f"角色仅支持{valid_roles}"
    if field_type == "str":
        return isinstance(value, str) and len(value.strip()) > 0, "字段需为非空字符串"
    if field_type == "int":
        try:
            int(value)
            return True, ""
        except (ValueError, TypeError):
            return False, "字段需为整数"
    if field_type == "float":
        try:
            float(value)
            return True, ""
        except (ValueError, TypeError):
            return False, "字段需为数字"
    return True, ""


def _xss_escape(data):
    if isinstance(data, dict):
        return {key: _xss_escape(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_xss_escape(item) for item in data]
    if isinstance(data, str):
        return escape(data)
    return data


def validate_request(required_fields=None, optional_fields=None):
    required_fields = required_fields or {}
    optional_fields = optional_fields or {}

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return error(400, "请求格式错误，仅支持application/json")

            request_data = request.get_json(silent=True) or {}
            cleaned_data = _xss_escape(request_data)

            missing_fields = [field for field in required_fields if field not in cleaned_data]
            if missing_fields:
                return error(400, f"缺少必填字段：{','.join(missing_fields)}")

            all_fields = {**required_fields, **optional_fields}
            for field, field_type in all_fields.items():
                if field not in cleaned_data and field in optional_fields:
                    continue
                value = cleaned_data[field]
                is_valid, err_msg = _validate_field(value, field_type)
                if not is_valid:
                    return error(400, f"{field}格式错误：{err_msg}")

            request.cleaned_data = cleaned_data
            return f(*args, **kwargs)

        return wrapper

    return decorator


def validate_register():
    return validate_request(
        required_fields={
            "username": "username",
            "password": "password",
            "phone": "phone",
        },
        optional_fields={"role": "role"},
    )


def validate_login():
    """
    用户登录接口专用验证器（口令 + 证书登录版）。
    当前 /api/v1/auth/login 使用 multipart/form-data 上传 certificate 文件和口令。
    支持 .crt/.pem/.cer/.der。
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            content_type = request.content_type or ""
            if "multipart/form-data" not in content_type:
                return error(400, "请求格式错误，仅支持multipart/form-data")

            cert_file = request.files.get("certificate")
            if not cert_file:
                return error(400, "缺少证书文件")

            filename = (cert_file.filename or "").strip()
            if not filename:
                return error(400, "证书文件名为空")

            allowed_ext = (".crt", ".pem", ".cer", ".der")
            if "." in filename and not filename.lower().endswith(allowed_ext):
                return error(400, "证书文件格式错误，仅支持 .crt/.pem/.cer/.der")

            password = request.form.get("password")
            if not password:
                return error(400, "缺少登录密码")

            return f(*args, **kwargs)

        return wrapper

    return decorator


def validate_user_query():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            name = request.args.get("name")
            phone = request.args.get("phone")
            user_id = request.args.get("user_id")
            product_id = request.args.get("product_id")

            cleaned_params = {
                "name": escape(name) if name else None,
                "phone": escape(phone) if phone else None,
                "user_id": user_id,
                "product_id": product_id,
            }

            if user_id:
                is_valid, err_msg = _validate_field(user_id, "int")
                if not is_valid:
                    return error(400, f"user_id格式错误：{err_msg}")

            if product_id:
                is_valid, err_msg = _validate_field(product_id, "int")
                if not is_valid:
                    return error(400, f"商品ID格式错误：{err_msg}")

            if phone:
                is_valid, err_msg = _validate_field(phone, "phone")
                if not is_valid:
                    return error(400, f"phone格式错误：{err_msg}")

            request.cleaned_params = cleaned_params
            return f(*args, **kwargs)

        return wrapper

    return decorator
