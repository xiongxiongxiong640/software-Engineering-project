from flask import Blueprint

# A 同学的核心调度蓝图
blueprint = Blueprint('api', __name__)
from apps.api import routes

# 兼容 B 同学导出的测试蓝图
try:
    from .data_routes import data_bp
    __all__ = ["blueprint", "data_bp"]
except ImportError:
    __all__ = ["blueprint"]