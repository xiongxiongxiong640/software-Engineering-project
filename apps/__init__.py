"""Flask 应用工厂"""
from flask import Flask


def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')

    # 注册 Home 蓝图（前端路由）
    from apps.home.routes import home_bp
    app.register_blueprint(home_bp)

    return app
