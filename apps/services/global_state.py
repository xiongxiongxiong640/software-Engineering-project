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
        
        # 🌟 修改点 2：对接 B 的 queries 和 C 的引擎
        print("[*] [AppState] 启动构建/加载高维空间 ANN 索引树 ...")
        try:
            from apps.data_processor.queries import get_all_vectors
            from apps.search_engine.index_builder import build_index  # 确保引用路径是 C 的模块
            from apps.search_engine import search as search_index

            vectors = get_all_vectors(self.adata)
            self.search_index = build_index(vectors)  # 将 C 的索引存入全局状态

            # 额外验证：对第一条向量做一次简单检索，确保索引可查询
            if vectors.shape[0] > 0:
                query_vector = vectors[0]
                distances, indices = search_index(self.search_index, query_vector, top_k=1)
                if len(indices) == 0:
                    raise RuntimeError("索引构建成功，但检索返回空结果")
                print(f"[+] C 同学的检索索引树构建成功！验证通过：第一条样本最近邻索引={indices[0]}, 距离={float(distances[0]):.6f}")
            else:
                print("[!] 警告：向量矩阵为空，无法进行索引验证")
        except Exception as e:
            print(f"[!] 索引构建失败: {e}，启用穷举兜底。")
            self.search_index = None  # 保持 None，routes.py 会自动 fallback
        
        self.is_loaded = True

global_app_state = AppState()