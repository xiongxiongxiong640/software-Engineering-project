import os
from apps import create_app
from apps.config import config_dict

# 从环境变量中读取DEBUG模式，默认开启
DEBUG = os.getenv('DEBUG', 'True') == 'True'
get_config_mode = 'Debug' if DEBUG else 'Production'
app_config = config_dict[get_config_mode]

app = create_app(app_config)



if __name__ == "__main__":
    # 允许局域网或容器内通过 5000 端口访问
    app.run(host='0.0.0.0', port=5000, debug=DEBUG)

