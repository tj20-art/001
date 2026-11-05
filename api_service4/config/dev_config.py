# app/config/dev_config.py
import os

class DevConfig:
    """开发者环境配置（MySQL适配）"""
    # 启用MySQL（实验七已适配MySQL，开发者环境强制开启）
    USE_MYSQL = True

    # MySQL连接配置：需手动填写你的本地MySQL信息
    MYSQL_CONFIG = {
        "host": "localhost",  # 默认本地，无需修改
        "port": 3306,  # MySQL默认端口，无需修改
        "user": "root",  # 手动填写你的MySQL用户名（如root）
        "password": os.getenv("MYSQL_PASSWORD", "tj200625!"),  # 手动填写你的MySQL密码（如123456）
        "db": "adb",  # 手动填写数据库名（需提前在MySQL中创建该库）
        "charset": "utf8mb4"  # 字符集，无需修改
    }

    # JWT密钥：手动填写一个随机字符串（如"your-256-bit-secret"，建议越长越安全）
    JWT_SECRET = os.getenv("JWT_SECRET", "tj200625")
    # JWT过期时间：access_token 1小时，refresh_token 7天（无需修改）
    JWT_ACCESS_EXPIRE = 3600
    JWT_REFRESH_EXPIRE = 604800
    # API服务端口：默认2333（文档1中run.py标注2333，可手动修改）
    PORT = 2333

    HTTPS_ENABLED = os.getenv("HTTPS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    TLS_CERT_PATH = os.getenv("TLS_CERT_PATH")
    TLS_KEY_PATH = os.getenv("TLS_KEY_PATH")
    CORS_ORIGINS = [
        item.strip()
        for item in os.getenv(
            "CORS_ORIGINS",
            "https://127.0.0.1:8081,https://localhost:8081,http://127.0.0.1:8081,http://localhost:8081",
        ).split(",")
        if item.strip()
    ]
    TUNNEL_REQUIRED = os.getenv("TUNNEL_REQUIRED", "true").strip().lower() in {"1", "true", "yes", "on"}

    # SM4_KEY_HEX: 32 hex chars (16 bytes), example:
    # export SM4_KEY_HEX=00112233445566778899aabbccddeeff
