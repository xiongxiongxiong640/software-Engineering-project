"""
apps.home — 前端页面路由

提供前端 HTML 页面的路由，使用 Flask 模板引擎。

路由:
    GET /                    → 搜索主页
    GET /login               → 登录页面
    GET /dashboard           → 数据仪表盘
    GET /management          → 数据集管理页面
"""

from flask import Blueprint, render_template, current_app

home_bp = Blueprint("home", __name__, url_prefix="")


@home_bp.route("/login")
def login_page():
    """登录页面"""
    return render_template("login.html")

@home_bp.route("/")
def index():
    """搜索主页 — 单细胞 ANN 检索入口"""
    return render_template("index.html")


@home_bp.route("/dashboard")
def dashboard():
    """数据仪表盘 — 数据集概览"""
    return render_template("dashboard.html")


@home_bp.route("/management")
def management():
    """数据集管理 — 加载/卸载/索引管理"""
    return render_template("management.html")
