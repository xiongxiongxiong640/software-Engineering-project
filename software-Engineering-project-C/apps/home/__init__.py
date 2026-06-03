"""
apps.home — 前端页面路由

提供前端 HTML 页面的路由，使用 Flask 模板引擎。
按五大模块组织：

路由:
    GET /management       → 数据导入（数据管理模块）
    GET /index-management → 索引管理（索引构建模块）
    GET /                 → 检索搜索（查询检索模块）
    GET /dashboard        → 可视化展示（可视化展示模块）
    GET /user-info        → 用户信息（用户信息模块）
    GET /login            → 登录页面
"""

from flask import Blueprint, render_template

home_bp = Blueprint("home", __name__, url_prefix="")


@home_bp.route("/login")
def login_page():
    """登录页面"""
    return render_template("login.html")


@home_bp.route("/")
def index():
    """检索搜索主页"""
    return render_template("index.html")


@home_bp.route("/dashboard")
def dashboard():
    """可视化展示 — 数据仪表盘"""
    return render_template("dashboard.html")


@home_bp.route("/management")
def management():
    """数据导入 — 数据集上传/导入/管理"""
    return render_template("data_import.html")


@home_bp.route("/index-management")
def index_management():
    """索引管理 — ANN 索引构建/管理"""
    return render_template("index_management.html")


@home_bp.route("/user-info")
def user_info():
    """用户信息 — 账号管理与统计"""
    return render_template("user_info.html")
