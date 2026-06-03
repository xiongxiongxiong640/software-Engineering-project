"""
search_engine — ANN 索引构建与检索核心模块

本模块是单细胞 ANN 检索系统的核心引擎，负责:
    1. ANN 索引构建（FAISS / HNSWLIB 双后端）
    2. Top-K 相似细胞检索（多种距离度量）
    3. 索引保存/加载/管理
    4. 检索参数配置
    5. 性能基准测试

=========================================================================
（important.txt）要求指定接口
=========================================================================

    from apps.search_engine import build_index, search

    index = build_index(vectors)
    distances, indices = search(index, query_vector, top_k=10)

=========================================================================
推荐使用方式（IndexManager 高级封装）
=========================================================================

    from apps.search_engine import IndexManager, SearchConfig

    config = SearchConfig(backend="faiss", distance_metric="cosine")
    manager = IndexManager(config)
    manager.build(pca_vectors)
    distances, indices = manager.search(query_vec, top_k=10)
    manager.save("data/index/liver")

=========================================================================
快速切换后端
=========================================================================

    # 使用 HNSWLIB（轻量级，内存友好）
    config = SearchConfig(backend="hnswlib")
    manager = IndexManager(config).build(pca_vectors)

    # 使用 FAISS + IVF 倒排索引（适合中等规模数据）
    config = SearchConfig(backend="faiss", faiss_index_type="IVFFlat")

    # 使用 FAISS + IVFPQ（适合超大规模数据，压缩内存）
    config = SearchConfig(backend="faiss", faiss_index_type="IVFPQ", nbits=8)

=========================================================================
距离度量选择指南
=========================================================================

    "cosine"     — 推荐。适合单细胞数据，关注表达模式的相似性（方向）
    "euclidean"  — 考虑向量绝对大小，对表达量敏感
    "l2"         — 平方欧氏距离，计算更快（不开根号）
    "ip"         — 内积，适合已归一化的向量
"""

# ---- 核心接口（important.txt要求指定） ----
from .index_builder import build_index, save_index, load_index
from .retriever import search

# ---- 配置 ----
from .config import SearchConfig

# ---- 高级封装 ----
from .index_manager import IndexManager

# ---- 工具 ----
from .retriever import compute_distances

__all__ = [
    # （important.txt）指定接口
    "build_index",
    "search",
    # 索引持久化
    "save_index",
    "load_index",
    # 配置
    "SearchConfig",
    # 高级接口
    "IndexManager",
    # 工具
    "compute_distances",
]
