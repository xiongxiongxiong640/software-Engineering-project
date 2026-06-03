"""
run.py — 单细胞 ANN 检索系统 应用入口

启动方式:
    python run.py

    或指定参数:
    python run.py --host 0.0.0.0 --port 5000 --debug

    WSGI 部署（生产环境）:
    gunicorn "run:create_app()" -w 4 -b 0.0.0.0:5000
"""

import os
import sys
import argparse

from flask import Flask
from flask_cors import CORS


# ======================================================================
# 应用工厂
# ======================================================================

def create_app(config_overrides: dict = None) -> Flask:
    """创建 Flask 应用实例

    Args:
        config_overrides: 可选的配置覆盖字典

    Returns:
        配置完成的 Flask app 对象
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    # ---- 基础配置 ----
    app.config.update({
        "SECRET_KEY": os.environ.get("SECRET_KEY", "single-cell-ann-secret-key"),
        "MAX_CONTENT_LENGTH": None,  # 不限制（大文件用本地导入更靠谱）
        "JSON_AS_ASCII": False,                   # 支持中文 JSON
    })

    if config_overrides:
        app.config.update(config_overrides)

    # ---- CORS ----
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ---- 服务单例初始化 ----
    from apps.services import SearchService
    search_service = SearchService()
    app.config["search_service"] = search_service

    # ---- 初始化默认管理员 ----
    from apps.auth import init_admin
    init_admin()

    # ---- 注册蓝图 ----
    from apps.api import api_bp
    from apps.home import home_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(home_bp)

    # ---- 错误处理 ----
    @app.errorhandler(404)
    def not_found(e):
        return {"status": "error", "message": "接口不存在"}, 404

    @app.errorhandler(500)
    def server_error(e):
        return {"status": "error", "message": "服务器内部错误"}, 500

    return app


# ======================================================================
# 入口
# ======================================================================

def _parse_args():
    parser = argparse.ArgumentParser(
        description="单细胞 ANN 检索系统"
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="监听地址 (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="监听端口 (default: 5000)"
    )
    parser.add_argument(
        "--debug", action="store_true", default=False,
        help="开启调试模式"
    )
    parser.add_argument(
        "--auto-load", type=str, default=None,
        help="启动时自动加载的数据集文件路径"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    app = create_app()

    # ---- 可选：启动时自动加载数据 ----
    if args.auto_load:
        with app.app_context():
            svc = app.config["search_service"]
            print(f"[启动] 自动加载数据集: {args.auto_load}")
            try:
                result = svc.init(data_file=args.auto_load)
                summary = result["data_summary"]
                print(f"[启动] 加载成功: {summary['n_cells']} 细胞, "
                      f"{summary['n_genes']} 基因, "
                      f"PCA 维度={summary.get('n_pca_features', 'N/A')}")
            except Exception as e:
                print(f"[启动] 自动加载失败: {e}")

    # ---- 启动 ----
    print(f"\n{'='*60}")
    print(f"  单细胞 ANN 检索系统")
    print(f"  访问地址: http://{args.host}:{args.port}")
    print(f"  API 文档: http://{args.host}:{args.port}/api/status")
    print(f"{'='*60}\n")

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
    )
