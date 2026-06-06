import os
from flask import Flask
from flask_cors import CORS
from apps.services.global_state import global_app_state


def register_blueprints(app):
    # 1. 注册 A 同学编写的核心 RESTful API 蓝图
    from apps.api import blueprint as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # 2. 兼容并注册 B 同学的数据测试蓝图 (如果存在)
    try:
        from apps.api.data_routes import data_bp
        app.register_blueprint(data_bp, url_prefix='/api/data')
    except ImportError:
        pass
    
    # 3. 注册前端 D 同学页面蓝图 (防错捕获)
    try:
        from apps.home import home_bp
        app.register_blueprint(home_bp)
    except ImportError:
        print("[!] 提示: 前端 home 页面路由蓝图暂未检测到接入")


def create_app(config):
    # 使用绝对路径定位模板和静态文件（更稳定，不依赖当前工作目录）
    base_dir = os.path.dirname(os.path.dirname(__file__))  # software-Engineering-project 目录
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')
    
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config.from_object(config)
    
    # 启用跨域资源共享 (CORS)
    CORS(app)
    
    # 注册所有模块蓝图
    register_blueprints(app)
    
    # 核心管理：服务器启动时自动单例初始化大文件，常驻内存
    data_path = os.path.join(os.getcwd(), 'data', 'liver.h5ad')
    if os.path.exists(data_path):
        global_app_state.init_app(data_path=data_path)
    else:
        print(f"[!] 警告: 未在指定路径找到核心单细胞文件: {data_path}，请检查 data 目录！")
        
    return app
