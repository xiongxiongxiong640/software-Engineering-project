import time
import os
import scanpy as sc

class AppState:
    """
    单例状态机：杜绝每次前端请求重复读取几GB文件的灾难性设计。
    """
    def __init__(self):
        self.adata = None
        self.search_index = None
        self.is_loaded = False

    def init_app(self, data_path):
        if self.is_loaded:
            return
        
        print(f"[*] [AppState] 启动载入核心单细胞数据: {data_path} ...")
        start_time = time.time()
        
        # 1. 尝试调用 B 同学的方法；若B还没交卷，启用系统内置 scanpy 自动兜底加载
        try:
            from apps.data_processor.core import load_data
            self.adata = load_data(data_path)
        except (ImportError, AttributeError):
            print("[!] 提示: B同学的载入模块尚未接入，框架自动启动原生 Scanpy 进行数据托管载入")
            self.adata = sc.read_h5ad(data_path)
        
        print(f"[+] 细胞数据托管成功。耗时: {time.time() - start_time:.2f} 秒。样本总数: {self.adata.n_obs}")

        # 2. 尝试调用 B同学的特征提取 和 C同学的 FAISS 索引构建
        print("[*] [AppState] 启动构建/加载高维空间 ANN 索引树 ...")
        try:
            from apps.data_processor.core import get_all_vectors
            from apps.search_engine.core import build_index
            
            vectors = get_all_vectors(self.adata)
            self.search_index = build_index(vectors)
            print("[+] C同学的检索索引树全量构建成功，常驻内存就绪！")
        except (ImportError, AttributeError):
            print("[!] 提示: C同学的索引算法或B同学的提向量函数尚未接入。检索系统目前将自动在 A 蓝图中以降维矩阵暴力穷举形式进行高精度检索兜底。")
            self.search_index = None
        
        self.is_loaded = True

global_app_state = AppState()