# app/config/__init__.py
from api_service4.config.dev_config import DevConfig
from api_service4.config.prod_config import ProdConfig  # 生产环境配置，开发者环境暂不用

def get_config(env="dev"):
    """获取环境配置（默认开发者环境）"""
    if env.lower() == "prod":
        ProdConfig.validate()
        return ProdConfig
    return DevConfig  # 开发者环境默认返回DevConfig
