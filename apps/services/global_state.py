import time
import os
import scanpy as sc

class AppState:
    def __init__(self):
        self.adata = None
        self.search_index = None
        self.is_loaded = False

    def init_app(self, data_path):
        if self.is_loaded:
            return
        
        print(f"[*] [AppState] 启动载入核心单细胞数据: {data_path} ...")
        start_time = time.time()
        
        # 🌟 修改点 1：对接 B 的 loader.py
        try:
            from apps.data_processor.loader import load_data
            self.adata = load_data(data_path)
            print(f"[+] B模块数据托管成功。耗时: {time.time() - start_time:.2f} 秒。样本总数: {self.adata.n_obs}")
        except Exception as e:
            print(f"[!] 提示: B同学的载入模块调用失败({e})，框架自动启动原生 Scanpy 兜底")
            self.adata = sc.read_h5ad(data_path)
        
        # 🌟 修改点 2：对接 B 的 queries.py
        print("[*] [AppState] 启动构建/加载高维空间 ANN 索引树 ...")
        try:
            from apps.data_processor.queries import get_all_vectors
            from apps.search_engine.core import build_index
            
            vectors = get_all_vectors(self.adata)
            self.search_index = build_index(vectors)
            print("[+] C同学的检索索引树全量构建成功，常驻内存就绪！")
        except Exception as e:
            print(f"[!] 提示: 索引层暂未接入或出现异常({e})。目前将启用降维矩阵暴力穷举形式兜底。")
            self.search_index = None
        
        self.is_loaded = True

global_app_state = AppState()