# app/utils/response.py
from flask import jsonify
from datetime import datetime

def success(data=None, message="操作成功"):
    """成功响应：code=0，包含数据、提示、时间戳"""
    return jsonify({
        "code": 0,
        "message": message,
        "data": data or {},
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    })

def error(code=400, message="操作失败", details=None):
    """错误响应：包含错误码、提示、详情、时间戳"""
    return jsonify({
        "code": code,
        "message": message,
        "details": details or {},
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }), code  # 返回HTTP状态码