"""
services — 业务服务编排层

协调 data_processor (B) 和 search_engine (C) 模块，提供完整的搜索工作流。
管理数据和索引的生命周期，为 API 层提供统一接口。

对外接口:
    SearchService  — 搜索编排服务
    DataService    — 数据集管理服务
    IndexService   — 索引管理服务
    AuthService    — 用户认证服务
"""

import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np


# ======================================================================
# 服务基类 / 工具
# ======================================================================

def _get_project_root() -> str:
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ======================================================================
# DataService — 数据集管理
# ======================================================================

class DataService:
    """数据集加载与信息查询服务

    封装 data_processor 模块，提供数据集加载、概览和细胞信息查询。
    """

    def __init__(self):
        self._adata = None
        self._loaded_file: Optional[str] = None

    @property
    def adata(self):
        if self._adata is None:
            raise RuntimeError("数据尚未加载，请先调用 load()")
        return self._adata

    @property
    def is_loaded(self) -> bool:
        return self._adata is not None

    def load(self, filepath: str) -> Dict:
        """加载数据集并返回概览"""
        from apps.data_processor import load_data, get_data_summary

        self._adata = load_data(filepath)
        self._loaded_file = filepath
        return get_data_summary(self._adata)

    def get_summary(self) -> Dict:
        """获取当前数据集的概览"""
        from apps.data_processor import get_data_summary
        return get_data_summary(self.adata)

    def get_cell_info_by_id(self, cell_ids: List[str]) -> List[Dict]:
        """根据细胞 ID 获取信息"""
        from apps.data_processor import get_cell_info
        return get_cell_info(self.adata, cell_ids)

    def get_cell_info_by_indices(self, indices: List[int]) -> List[Dict]:
        """根据行号获取信息"""
        from apps.data_processor import get_cell_info_by_indices
        return get_cell_info_by_indices(self.adata, indices)

    def get_all_vectors(self) -> np.ndarray:
        """获取全量 PCA 向量矩阵"""
        from apps.data_processor import get_all_vectors
        return get_all_vectors(self.adata)

    def list_datasets(self, data_dir: str = "data") -> List[Dict]:
        """列出 data 目录下所有可用的数据集文件"""
        root = _get_project_root()
        full_dir = os.path.join(root, data_dir)
        if not os.path.isdir(full_dir):
            return []

        datasets = []
        for fname in sorted(os.listdir(full_dir)):
            if fname.endswith((".h5ad", ".h5")):
                fpath = os.path.join(full_dir, fname)
                size_mb = os.path.getsize(fpath) / (1024 * 1024)
                datasets.append({
                    "filename": fname,
                    "path": os.path.join(data_dir, fname),
                    "size_mb": round(size_mb, 1),
                })
        return datasets


# ======================================================================
# IndexService — 索引管理
# ======================================================================

class IndexService:
    """ANN 索引管理服务

    封装 search_engine.IndexManager，提供索引构建/保存/加载/状态查询。
    """

    def __init__(self, config: Optional[Dict] = None):
        from apps.search_engine import SearchConfig, IndexManager

        self._config_dict = config or {}
        self._search_config = SearchConfig.from_dict(self._config_dict)
        self._manager = IndexManager(self._search_config)

    @property
    def manager(self):
        return self._manager

    @property
    def is_ready(self) -> bool:
        return self._manager.is_ready

    def build(self, vectors: np.ndarray) -> Dict:
        """构建索引并返回状态"""
        self._manager.build(vectors)
        return self._manager.get_stats()

    def save(self, filepath: str) -> str:
        """保存索引"""
        root = _get_project_root()
        full_path = os.path.join(root, filepath)
        return self._manager.save(full_path)

    def load(self, filepath: str) -> Dict:
        """加载索引"""
        root = _get_project_root()
        full_path = os.path.join(root, filepath)
        self._manager.load(full_path)
        return self._manager.get_stats()

    def get_stats(self) -> Dict:
        return self._manager.get_stats()

    def update_config(self, **kwargs) -> Dict:
        self._manager.update_config(**kwargs)
        return self._manager.get_config()

    def benchmark(self, query_vectors: np.ndarray, top_k: int = 10) -> Dict:
        return self._manager.benchmark(query_vectors, top_k)


# ======================================================================
# SearchService — 搜索编排
# ======================================================================

class SearchService:
    """单细胞相似性搜索编排服务

    协调 DataService + IndexService，完成从查询到结果格式化的完整流程。

    使用方式:
        svc = SearchService()
        svc.init(data_file="data/liver.h5ad")

        # 按细胞 ID 查询
        result = svc.search_by_cell_id("cell_001", top_k=10)

        # 按向量查询
        result = svc.search_by_vector(query_vec, top_k=10)
    """

    def __init__(self):
        self.data_service = DataService()
        self.index_service = IndexService()

    # ==================================================================
    # 初始化
    # ==================================================================

    def init(
        self,
        data_file: str,
        index_file: Optional[str] = None,
    ) -> Dict:
        """初始化数据和索引

        Args:
            data_file:  数据文件路径（相对于 data/ 目录或绝对路径）
            index_file: 索引文件路径（相对于项目根目录）。为 None 时自动构建

        Returns:
            {"data_summary": {...}, "index_status": {...}}
        """
        # 加载数据
        data_summary = self.data_service.load(data_file)

        # 构建或加载索引
        if index_file:
            index_status = self.index_service.load(index_file)
        else:
            vectors = self.data_service.get_all_vectors()
            index_status = self.index_service.build(vectors)

        return {
            "data_summary": data_summary,
            "index_status": index_status,
        }

    def ensure_ready(self):
        """确保数据和索引都已就绪"""
        if not self.data_service.is_loaded:
            raise RuntimeError("数据未加载，请先调用 init()")
        if not self.index_service.is_ready:
            vectors = self.data_service.get_all_vectors()
            self.index_service.build(vectors)

    # ==================================================================
    # 搜索接口
    # ==================================================================

    def search_by_cell_id(
        self,
        cell_id: str,
        top_k: int = 10,
        filter_cell_type: Optional[str] = None,
    ) -> Dict:
        """根据细胞 ID 查询相似细胞

        这是主要的搜索入口，返回前端需要的数据格式。

        Args:
            cell_id:          查询细胞 ID
            top_k:            返回数量
            filter_cell_type: 可选，限定相似细胞的细胞类型（后过滤）

        Returns:
            {
                "status": "success" | "error",
                "time_cost_ms": float,
                "query_cell": {id, cell_type, pca},
                "results": [{id, distance, cell_type, disease, pca}, ...]
            }
        """
        self.ensure_ready()

        t_start = time.perf_counter()

        try:
            # 1. 获取查询细胞信息
            cell_info = self.data_service.get_cell_info_by_id([cell_id])
            if cell_info[0] is None:
                return {"status": "error", "message": f"细胞 ID 不存在: {cell_id}"}

            query_info = cell_info[0]

            # 2. 获取查询细胞的 PCA 向量
            vectors = self.data_service.get_all_vectors()
            cell_idx = self._find_cell_index(cell_id)
            query_vector = vectors[cell_idx]

            # 3. 执行 ANN 检索（多取一些，便于后过滤）
            fetch_k = top_k * 3 if filter_cell_type else top_k
            distances, indices = self.index_service.manager.search(query_vector, fetch_k)

            # 4. 获取相似细胞信息
            results = []
            for dist, idx in zip(distances, indices):
                idx = int(idx)
                if idx == cell_idx:
                    continue  # 跳过自身

                info = self.data_service.get_cell_info_by_indices([idx])[0]
                if info is None:
                    continue

                # 类型过滤
                if filter_cell_type and info.get("cell_type") != filter_cell_type:
                    continue

                info["distance"] = round(float(dist), 6)
                results.append(info)

                if len(results) >= top_k:
                    break

            elapsed = (time.perf_counter() - t_start) * 1000

            return {
                "status": "success",
                "time_cost_ms": round(elapsed, 2),
                "query_cell": {
                    "id": query_info["id"],
                    "cell_type": query_info.get("cell_type", "unknown"),
                    "disease": query_info.get("disease", "unknown"),
                    "AgeGroup": query_info.get("AgeGroup", "unknown"),
                    "pca": query_info.get("pca", [0, 0]),
                },
                "results": results,
            }

        except Exception as e:
            elapsed = (time.perf_counter() - t_start) * 1000
            return {
                "status": "error",
                "time_cost_ms": round(elapsed, 2),
                "message": str(e),
                "query_cell": {"id": cell_id, "cell_type": "unknown", "pca": []},
                "results": [],
            }

    def search_by_vector(
        self,
        query_vector: List[float],
        top_k: int = 10,
    ) -> Dict:
        """根据向量查询相似细胞"""
        self.ensure_ready()

        t_start = time.perf_counter()

        try:
            arr = np.array(query_vector, dtype=np.float32)
            distances, indices = self.index_service.manager.search(arr, top_k)

            results = []
            for dist, idx in zip(distances, indices):
                idx = int(idx)
                info = self.data_service.get_cell_info_by_indices([idx])[0]
                if info:
                    info["distance"] = round(float(dist), 6)
                    results.append(info)

            elapsed = (time.perf_counter() - t_start) * 1000

            return {
                "status": "success",
                "time_cost_ms": round(elapsed, 2),
                "query_cell": {"id": "vector_query", "cell_type": "vector", "pca": query_vector[:2]},
                "results": results,
            }

        except Exception as e:
            elapsed = (time.perf_counter() - t_start) * 1000
            return {
                "status": "error",
                "time_cost_ms": round(elapsed, 2),
                "message": str(e),
                "query_cell": {"id": "vector_query", "cell_type": "vector", "pca": []},
                "results": [],
            }

    # ==================================================================
    # 统计接口
    # ==================================================================

    def get_system_status(self) -> Dict:
        """获取系统整体状态"""
        status = {
            "data_loaded": self.data_service.is_loaded,
            "index_ready": self.index_service.is_ready,
        }

        if self.data_service.is_loaded:
            status["data_summary"] = self.data_service.get_summary()

        if self.index_service.is_ready:
            status["index_status"] = self.index_service.get_stats()

        return status

    def run_benchmark(self, n_queries: int = 100, top_k: int = 10) -> Dict:
        """运行检索性能基准测试"""
        self.ensure_ready()
        vectors = self.data_service.get_all_vectors()
        n_total = vectors.shape[0]
        n_queries = min(n_queries, n_total)

        rng = np.random.default_rng(42)
        sample_indices = rng.choice(n_total, size=n_queries, replace=False)
        query_vecs = vectors[sample_indices]

        return self.index_service.benchmark(query_vecs, top_k)

    # ==================================================================
    # 辅助
    # ==================================================================

    def _find_cell_index(self, cell_id: str) -> int:
        """通过细胞 ID 找行号"""
        obs_names = list(self.data_service.adata.obs_names)
        try:
            return obs_names.index(cell_id)
        except ValueError:
            for i, name in enumerate(obs_names):
                if cell_id in str(name):
                    return i
            raise KeyError(f"细胞 ID 不存在: {cell_id}")

    def get_random_cells(self, n: int = 5) -> List[Dict[str, str]]:
        """获取随机细胞作为查询候选"""
        self.ensure_ready()
        adata = self.data_service.adata
        n_total = adata.n_obs
        n = min(n, n_total)

        rng = np.random.default_rng()
        indices = rng.choice(n_total, size=n, replace=False)

        cells = []
        for idx in indices:
            cell_id = str(adata.obs_names[int(idx)])
            ct = "unknown"
            if "cell_type" in adata.obs.columns:
                val = adata.obs["cell_type"].iloc[int(idx)]
                ct = str(val) if not (hasattr(val, "__class__") and "NA" in val.__class__.__name__) else "unknown"
            cells.append({"id": cell_id, "cell_type": ct})

        return cells


# ======================================================================
# AuthService — 用户认证服务
# ======================================================================

class AuthService:
    """用户认证服务

    封装 auth 模块，提供面向 API 层的简洁接口。
    """

    def __init__(self):
        from apps import auth as _auth
        _auth.init_admin()
        self._auth = _auth

    def register(self, username: str, password: str) -> Tuple[bool, str]:
        return self._auth.register_user(username, password)

    def login(self, username: str, password: str) -> Tuple[bool, str, Optional[dict]]:
        return self._auth.login_user(username, password)

    def get_stats(self, username: str) -> dict:
        return self._auth.get_user_stats(username)

    def get_all_users(self) -> list:
        return self._auth.get_all_users()

    def update_role(self, username: str, role: str) -> Tuple[bool, str]:
        return self._auth.update_user_role(username, role)

    def delete_user(self, username: str) -> Tuple[bool, str]:
        return self._auth.delete_user(username)
