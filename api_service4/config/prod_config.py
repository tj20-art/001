import os


class ProdConfig:
    """Production settings are supplied exclusively through environment variables."""

    USE_MYSQL = True
    MYSQL_CONFIG = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", ""),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "db": os.getenv("MYSQL_DATABASE", ""),
        "charset": "utf8mb4",
    }
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    JWT_ACCESS_EXPIRE = int(os.getenv("JWT_ACCESS_EXPIRE", "3600"))
    JWT_REFRESH_EXPIRE = int(os.getenv("JWT_REFRESH_EXPIRE", "604800"))
    PORT = int(os.getenv("PORT", "2333"))
    HTTPS_ENABLED = True
    TLS_CERT_PATH = os.getenv("TLS_CERT_PATH")
    TLS_KEY_PATH = os.getenv("TLS_KEY_PATH")
    CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "").split(",") if item.strip()]
    TUNNEL_REQUIRED = True

    @classmethod
    def validate(cls):
        missing = []
        if not cls.MYSQL_CONFIG["user"]:
            missing.append("MYSQL_USER")
        if not cls.MYSQL_CONFIG["password"]:
            missing.append("MYSQL_PASSWORD")
        if not cls.MYSQL_CONFIG["db"]:
            missing.append("MYSQL_DATABASE")
        if len(cls.JWT_SECRET) < 32:
            missing.append("JWT_SECRET(至少32字符)")
        if not cls.TLS_CERT_PATH or not cls.TLS_KEY_PATH:
            missing.append("TLS_CERT_PATH/TLS_KEY_PATH")
        if not cls.CORS_ORIGINS:
            missing.append("CORS_ORIGINS")
        if missing:
            raise RuntimeError(f"生产环境缺少安全配置: {', '.join(missing)}")
