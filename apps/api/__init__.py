from flask import Blueprint

blueprint = Blueprint('api', __name__)

# 引入路由建立映射关系
from apps.api import routes