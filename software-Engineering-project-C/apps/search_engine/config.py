"""
search_engine 检索参数配置模块

提供统一的检索参数管理，支持 FAISS 和 HNSWLIB 两种后端。
所有参数均有合理的默认值，可直接使用或按需覆盖。
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# 距离度量类型
# ---------------------------------------------------------------------------
DISTANCE_METRICS = Literal["cosine", "euclidean", "l2", "ip"]

# FAISS 索引类型
FAISS_INDEX_TYPES = Literal[
    "Flat",         # 暴力搜索，精确但慢
    "IVFFlat",      # 倒排索引 + 精确距离
    "IVFPQ",        # 倒排索引 + 乘积量化，压缩内存
    "HNSWFlat",     # 基于 FAISS 的 HNSW 实现
]

# 后端类型
BACKEND_TYPES = Literal["faiss", "hnswlib"]


# ---------------------------------------------------------------------------
# 距离度量 → FAISS 内部 metric_type 映射表
# ---------------------------------------------------------------------------
# FAISS 的 METRIC_L2 / METRIC_INNER_PRODUCT 是整型枚举
# 余弦相似度：先对向量做 L2 归一化，再用内积搜索
_FAISS_METRIC_MAP = {
    "l2":        1,   # METRIC_L2
    "euclidean": 1,   # METRIC_L2（euclidean 等价于 l2）
    "ip":        0,   # METRIC_INNER_PRODUCT
    "cosine":    0,   # 归一化后使用内积
}


# ---------------------------------------------------------------------------
# 距离度量 → HNSWLIB space 映射表
# ---------------------------------------------------------------------------
_HNSWLIB_SPACE_MAP = {
    "cosine":    "cosine",
    "euclidean": "l2",
    "l2":        "l2",
    "ip":        "ip",
}


@dataclass
class SearchConfig:
    """检索参数配置

    所有字段均有合理默认值。简单场景只需:

        config = SearchConfig()
        index = build_index(vectors, config)
        distances, indices = search(index, query, top_k=10, config=config)

    复杂场景可按需覆盖:

        config = SearchConfig(
            backend="faiss",
            distance_metric="cosine",
            faiss_index_type="IVFPQ",
            nlist=200,
            top_k=20,
        )
    """

    # ---- 后端选择 ----
    backend: BACKEND_TYPES = "faiss"
    """检索后端: "faiss" 或 "hnswlib" """

    # ---- 距离度量 ----
    distance_metric: DISTANCE_METRICS = "cosine"
    """距离度量方式: "cosine" | "euclidean" | "l2" | "ip" """

    # ---- 通用检索参数 ----
    top_k: int = 10
    """默认返回的相似细胞数量"""

    # ---- FAISS 专属参数 ----
    faiss_index_type: FAISS_INDEX_TYPES = "IVFFlat"
    """FAISS 索引类型。Flat=精确; IVFFlat=聚类加速; IVFPQ=压缩; HNSWFlat=图搜索"""

    nlist: int = 100
    """IVF 系列索引的聚类中心数。nlist 越大越精确但越慢；
       经验值: 数据量较小时取 sqrt(N)，大数据时取 4*sqrt(N) ~ 16*sqrt(N)"""

    nprobe: int = 10
    """IVF 查询时探测的聚类数。值越大精度越高速度越慢"""

    M_faiss: int = 32
    """FAISS HNSW 的每层连接数"""

    nbits: int = 8
    """IVFPQ 每个子向量的编码位数（仅 faiss_index_type="IVFPQ" 时生效）"""

    # ---- HNSWLIB 专属参数 ----
    hnsw_M: int = 16
    """HNSW 图中每个节点的最大连接数。越大精度越高但内存越大"""

    hnsw_ef_construction: int = 200
    """HNSW 建图时的搜索宽度。越大建图越慢但图质量越高"""

    hnsw_ef_search: int = 50
    """HNSW 查询时的搜索宽度。越大精度越高但越慢；必须 <= ef_construction"""

    # ---- 索引持久化 ----
    index_save_dir: str = "data/index"
    """索引文件默认保存目录"""

    # ---- 调试 ----
    verbose: bool = False
    """是否输出详细日志"""

    # ==================================================================
    # 便捷方法
    # ==================================================================

    def get_faiss_metric(self) -> int:
        """将 distance_metric 转换为 FAISS 内部 metric_type 整型常量"""
        return _FAISS_METRIC_MAP[self.distance_metric]

    def get_hnswlib_space(self) -> str:
        """将 distance_metric 转换为 hnswlib 的 space 字符串"""
        return _HNSWLIB_SPACE_MAP[self.distance_metric]

    def needs_normalization(self) -> bool:
        """判断是否需要先对向量做 L2 归一化（余弦相似度需要）"""
        return self.distance_metric == "cosine"

    def to_dict(self) -> dict:
        """导出为 dict（用于 JSON 序列化/前端传递）"""
        return {
            "backend": self.backend,
            "distance_metric": self.distance_metric,
            "top_k": self.top_k,
            "faiss_index_type": self.faiss_index_type,
            "nlist": self.nlist,
            "nprobe": self.nprobe,
            "M_faiss": self.M_faiss,
            "nbits": self.nbits,
            "hnsw_M": self.hnsw_M,
            "hnsw_ef_construction": self.hnsw_ef_construction,
            "hnsw_ef_search": self.hnsw_ef_search,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SearchConfig":
        """从 dict 创建配置（用于前端参数反序列化）"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid_keys})
