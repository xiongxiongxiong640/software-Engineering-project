"""Home 蓝图 —— 前端路由"""
from flask import Blueprint

home_bp = Blueprint('home', __name__)

from apps.home.routes import *  # noqa: E402, F403
