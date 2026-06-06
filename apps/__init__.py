import os
from flask import Flask
from flask_cors import CORS
from apps.services.global_state import global_app_state

def register_blueprints(app):
    # 注册你编写的核心 RESTful API 蓝图
    from apps.api import blueprint as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # 注册前端 D 同学页面蓝图 (做防错捕获，若D还没写，系统不崩溃)
    try:
        from apps.home import blueprint as home_blueprint
        app.register_blueprint(home_blueprint)
    except ImportError:
        print("[!] 提示: 前端 home 页面路由蓝图暂未检测到接入")

def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)
    
    # 启用跨域资源共享 (CORS)，方便 D 同学进行前后端分离开发调试
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