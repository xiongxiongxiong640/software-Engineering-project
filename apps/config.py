import os

class Config(object):
    SECRET_KEY = os.getenv('SECRET_KEY', 'single_cell_ann_secret_key_998877')
    # 确保 Flask jsonify 返回的中文字符不会被强制编码为 ASCII 码
    JSON_AS_ASCII = False 

class ProductionConfig(Config):
    DEBUG = False

class DebugConfig(Config):
    DEBUG = True

config_dict = {
    'Production': ProductionConfig,
    'Debug': DebugConfig
}