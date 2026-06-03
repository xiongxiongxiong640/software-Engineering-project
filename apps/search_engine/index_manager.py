"""
search_engine 索引管理器

提供索引全生命周期管理的高级接口，封装构建 → 保存 → 加载 → 检索 → 统计。

使用方式:
    from apps.search_engine import IndexManager, SearchConfig

    config = SearchConfig(backend="faiss", distance_metric="cosine")
    manager = IndexManager(config)

    # 构建
    manager.build(pca_vectors)
    # 检索
    distances, indices = manager.search(query_vec, top_k=10)
    # 保存
    manager.save("data/index/liver")
    # 下次加载
    manager2 = IndexManager(config)
    manager2.load("data/index/liver")
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import SearchConfig
from .index_builder import build_index, save_index, load_index
from .retriever import search


class IndexManager:
    """索引生命周期管理器

    封装了索引的构建、保存、加载、检索和统计信息查询，
    是 search_engine 模块的推荐入口类。

    Attributes:
        config: 检索参数配置
        index:  当前活跃的索引对象
        built:  索引是否已构建/加载
    """

    def __init__(self, config: Optional[SearchConfig] = None):
        """
        Args:
            config: 检索配置。为 None 时使用默认配置
        """
        self.config = config if config is not None else SearchConfig()
        self._index: Optional[object] = None
        self._vectors_shape: Optional[Tuple[int, int]] = None
        self._index_path: Optional[str] = None

    # ==================================================================
    # 核心操作
    # ==================================================================

    @property
    def index(self):
        """获取当前索引对象"""
        if self._index is None:
            raise RuntimeError("索引尚未构建或加载，请先调用 build() 或 load()")
        return self._index

    @property
    def is_ready(self) -> bool:
        """索引是否已就绪"""
        return self._index is not None

    def build(self, vectors: np.ndarray) -> "IndexManager":
        """构建索引

        Args:
            vectors: PCA 向量矩阵，shape (n_cells, n_features)

        Returns:
            self，支持链式调用

        Example:
            >>> manager = IndexManager(config)
            >>> manager.build(pca_vectors).search(query, 10)
        """
        vectors = np.asarray(vectors, dtype=np.float32)
        self._vectors_shape = vectors.shape
        self._index = build_index(vectors, self.config)
        return self

    def search(
        self,
        query_vector: np.ndarray,
        top_k: Optional[int] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Top-K 检索

        Args:
            query_vector: 查询向量，shape (n_features,)
            top_k:        返回数量。为 None 时使用 config.top_k

        Returns:
            (distances, indices)
        """
        if top_k is None:
            top_k = self.config.top_k
        return search(self.index, query_vector, top_k, self.config)

    def save(self, filepath: str) -> str:
        """保存当前索引到磁盘

        Args:
            filepath: 保存路径（不含扩展名）

        Returns:
            实际保存路径
        """
        save_index(self.index, filepath)
        self._index_path = filepath
        return filepath

    def load(self, filepath: str) -> "IndexManager":
        """从磁盘加载索引

        Args:
            filepath: 索引文件路径（不含扩展名）

        Returns:
            self，支持链式调用
        """
        self._index = load_index(filepath, self.config)
        self._index_path = filepath
        return self

    # ==================================================================
    # 配置管理
    # ==================================================================

    def update_config(self, **kwargs) -> "IndexManager":
        """动态更新检索配置

        注意: 某些参数（如 backend、faiss_index_type）仅在构建时生效，
        查询时参数（如 nprobe、hnsw_ef_search）更新后立即生效。

        支持的参数: nprobe, hnsw_ef_search, top_k, distance_metric, verbose

        Example:
            >>> manager.update_config(nprobe=20, top_k=5)
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        # 对已构建的索引立即应用查询参数
        if self._index is not None:
            self._apply_query_params()

        return self

    def _apply_query_params(self):
        """将 config 中的查询参数应用到当前索引"""
        if self._index is None:
            return

        # FAISS IVF 系列: nprobe
        if hasattr(self._index, "nprobe"):
            self._index.nprobe = self.config.nprobe

        # HNSWLIB: ef_search
        if hasattr(self._index, "set_ef"):
            self._index.set_ef(self.config.hnsw_ef_search)

    def get_config(self) -> dict:
        """获取当前配置的字典表示"""
        return self.config.to_dict()

    # ==================================================================
    # 统计信息
    # ==================================================================

    def get_stats(self) -> dict:
        """获取索引统计信息

        Returns:
            dict: 包含索引类型、条目数、维度、文件路径等信息
        """
        if self._index is None:
            return {"status": "empty", "message": "索引尚未构建或加载"}

        stats = {
            "status": "ready",
            "backend": self.config.backend,
            "distance_metric": self.config.distance_metric,
            "index_path": self._index_path,
        }

        # 尝试获取索引条目数
        try:
            stats["ntotal"] = self._index.ntotal
        except AttributeError:
            try:
                stats["ntotal"] = self._index.element_count
            except AttributeError:
                stats["ntotal"] = "unknown"

        # 尝试获取维度
        try:
            stats["dimension"] = self._index.d
        except AttributeError:
            try:
                stats["dimension"] = self._index.dim
            except AttributeError:
                stats["dimension"] = "unknown"

        # FAISS 特有信息
        try:
            import faiss
            if isinstance(self._index, faiss.Index):
                stats["faiss_index_type"] = self.config.faiss_index_type
                if hasattr(self._index, "nlist"):
                    stats["nlist"] = self._index.nlist
                if hasattr(self._index, "nprobe"):
                    stats["nprobe"] = self._index.nprobe
        except ImportError:
            pass

        # HNSWLIB 特有信息
        try:
            if hasattr(self._index, "space"):
                stats["hnsw_space"] = self._index.space
                stats["hnsw_ef_search"] = self.config.hnsw_ef_search
                stats["hnsw_M"] = self.config.hnsw_M
        except Exception:
            pass

        return stats

    def benchmark(
        self,
        query_vectors: np.ndarray,
        top_k: int = 10,
        n_runs: int = 50,
    ) -> dict:
        """检索性能基准测试

        Args:
            query_vectors: 查询向量集，shape (n_queries, n_features)
            top_k:         每次检索返回数量
            n_runs:        总查询次数（从 query_vectors 中循环采样）

        Returns:
            dict:
                - avg_time_ms: 平均查询耗时（毫秒）
                - p50_ms:      中位数耗时
                - p99_ms:      99 分位耗时
                - qps:         每秒查询数
                - n_runs:      测试次数
                - top_k:       K 值
        """
        import time

        query_vectors = np.asarray(query_vectors, dtype=np.float32)
        n_queries = query_vectors.shape[0]

        times = []
        for i in range(n_runs):
            q = query_vectors[i % n_queries]
            t0 = time.perf_counter()
            self.search(q, top_k)
            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)

        times = np.array(times)
        return {
            "avg_time_ms": round(float(np.mean(times)), 3),
            "p50_ms": round(float(np.percentile(times, 50)), 3),
            "p99_ms": round(float(np.percentile(times, 99)), 3),
            "qps": round(1000.0 / float(np.mean(times)), 1),
            "n_runs": n_runs,
            "top_k": top_k,
        }

    def __repr__(self) -> str:
        if self._index is None:
            return f"<IndexManager: empty (backend={self.config.backend})>"
        stats = self.get_stats()
        return (f"<IndexManager: {stats.get('backend')}/{stats.get('faiss_index_type', '')}, "
                f"ntotal={stats.get('ntotal')}, dim={stats.get('dimension')}>")
