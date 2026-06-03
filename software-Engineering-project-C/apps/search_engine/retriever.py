"""
search_engine 检索核心模块

提供 Top-K 相似细胞检索，支持多种距离度量，兼容 FAISS 和 HNSWLIB 索引。

对外接口（要求指定的核心函数）:
    search(index, query_vector, top_k, config) → (distances, indices)

内部辅助:
    _compute_distances(query_vector, vectors, metric)
    _validate_index(index)

距离度量说明:
    - cosine:    余弦相似度 → 余弦距离 = 1 - cos_sim。值域 [0, 2]，越小越相似
    - euclidean:  欧氏距离（L2 距离未开根号时为平方欧氏距离）
    - l2:        平方欧氏距离，同 FAISS METRIC_L2，取值 [0, ∞)
    - ip:        内积，值越大越相似（注意：FAISS 返回值需取负号变成距离形式）
"""

import time
from typing import Optional, Tuple, Union

import numpy as np

from .config import SearchConfig


# ======================================================================
# 类型别名
# ======================================================================
IndexLike = object


# ======================================================================
# 对外接口 — Top-K 检索
# ======================================================================

def search(
    index: IndexLike,
    query_vector: Union[np.ndarray, list],
    top_k: int,
    config: Optional[SearchConfig] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Top-K 相似细胞检索

     important.txt 中指定的核心接口函数。

    Args:
        index:        build_index() 返回的索引对象（FAISS 或 HNSWLIB）
        query_vector: 查询向量，shape (n_features,) 或 list
        top_k:        返回 K 个最相似的细胞
        config:       检索配置（用于距离度量等参数的统一管理）

    Returns:
        (distances, indices):
            distances: 距离数组，shape (top_k,)。值越小越相似
            indices:   相似细胞在原始向量矩阵中的行索引，shape (top_k,)

    Example:
        >>> config = SearchConfig(distance_metric="cosine")
        >>> index = build_index(pca_vectors, config)
        >>> query = pca_vectors[0]  # 取第一个细胞作为查询
        >>> distances, indices = search(index, query, top_k=10, config=config)
        >>> print(indices)  # [0, 56, 342, 89, ...]
    """
    if config is None:
        config = SearchConfig()

    # ---- 输入规范化 ----
    query_vector = np.asarray(query_vector, dtype=np.float32)
    if query_vector.ndim == 1:
        query_vector = query_vector.reshape(1, -1)

    # ---- 余弦相似度需要归一化查询向量 ----
    if config.needs_normalization():
        query_vector = _normalize_single(query_vector)

    # ---- 超时记录 ----
    t_start = time.perf_counter()

    # ---- 按后端分发 ----
    try:
        import faiss
        if isinstance(index, faiss.Index):
            distances, indices = _faiss_search(index, query_vector, top_k, config)
            elapsed = (time.perf_counter() - t_start) * 1000
            if config.verbose:
                print(f"[Retriever] FAISS 检索完成: top_k={top_k}, 耗时={elapsed:.2f}ms")
            return distances[0], indices[0]
    except ImportError:
        pass

    try:
        import hnswlib
        if type(index).__name__ == "Index" and hasattr(index, "knn_query"):
            distances, indices = _hnswlib_search(index, query_vector, top_k, config)
            elapsed = (time.perf_counter() - t_start) * 1000
            if config.verbose:
                print(f"[Retriever] HNSWLIB 检索完成: top_k={top_k}, 耗时={elapsed:.2f}ms")
            return distances[0], indices[0]
    except ImportError:
        pass

    # sklearn 索引（dict 包装）
    if isinstance(index, dict) and index.get("_backend") == "sklearn":
        distances, indices = _sklearn_search(index, query_vector, top_k, config)
        elapsed = (time.perf_counter() - t_start) * 1000
        if config.verbose:
            print(f"[Retriever] sklearn 检索完成: top_k={top_k}, 耗时={elapsed:.2f}ms")
        return distances, indices

    raise TypeError(f"不支持的索引类型: {type(index)}。必须是由 build_index() 生成的索引对象")


# ======================================================================
# 内部实现 — FAISS 检索
# ======================================================================

def _faiss_search(
    index: "faiss.Index",
    query_vector: np.ndarray,
    top_k: int,
    config: SearchConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    """FAISS 检索"""

    # FAISS 的 cosine 模式：向量已归一化，索引基于 METRIC_INNER_PRODUCT
    # 返回的 distances 是 -inner_product（FAISS 习惯返回越小越好）
    distances, indices = index.search(query_vector, top_k)

    # ---- 距离后处理 ----
    if config.distance_metric == "cosine":
        # IP 模式: FAISS 返回 -ip; cosine distance = 1 - ip = 1 + distances
        distances = 1.0 + distances
    elif config.distance_metric == "ip":
        # IP 模式: FAISS 返回 -ip; 还原为 ip = -distances
        distances = -distances
    # L2 和 euclidean 无需特殊处理，FAISS 返回的就是 L2 距离

    return distances, indices


# ======================================================================
# 内部实现 — HNSWLIB 检索
# ======================================================================

def _hnswlib_search(
    index: "hnswlib.Index",
    query_vector: np.ndarray,
    top_k: int,
    config: SearchConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    """HNSWLIB 检索"""

    # 确保 ef_search 设置正确
    index.set_ef(max(top_k, config.hnsw_ef_search))

    indices, distances = index.knn_query(query_vector, k=top_k)

    # HNSWLIB 对不同 space 返回不同意义的 distances:
    #   'cosine' → cosine distance (0~2, 越小越相似), 不需要转换
    #   'l2'     → 平方欧氏距离, 不需要转换
    #   'ip'     → 负内积 (越小 = 越相似), 不需要转换

    return distances, indices


# ======================================================================
# 距离计算工具（不依赖索引的精确计算）
# ======================================================================

def compute_distances(
    query_vector: np.ndarray,
    candidate_vectors: np.ndarray,
    metric: str = "cosine",
) -> np.ndarray:
    """精确计算查询向量与候选向量集的距离

    当需要精确距离（而非 ANN 近似结果）时使用。

    Args:
        query_vector:      查询向量, shape (n_features,)
        candidate_vectors: 候选向量矩阵, shape (n_candidates, n_features)
        metric:            距离度量: "cosine" | "euclidean" | "l2" | "ip"

    Returns:
        距离数组, shape (n_candidates,)。值越小越相似

    Example:
        >>> exact_dists = compute_distances(query_vec, all_vectors, "euclidean")
    """
    query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
    candidates = np.asarray(candidate_vectors, dtype=np.float32)

    if metric in ("cosine",):
        # 余弦距离 = 1 - cosine_similarity
        from numpy.linalg import norm
        q_norm = query / (norm(query, axis=1, keepdims=True) + 1e-10)
        c_norm = candidates / (norm(candidates, axis=1, keepdims=True) + 1e-10)
        sim = np.dot(q_norm, c_norm.T).flatten()
        return 1.0 - sim

    elif metric in ("euclidean",):
        # 欧氏距离（开根号）
        return np.sqrt(np.sum((candidates - query) ** 2, axis=1))

    elif metric in ("l2",):
        # 平方欧氏距离（不开根号）
        return np.sum((candidates - query) ** 2, axis=1)

    elif metric in ("ip",):
        # 内积（为保持"越小越相似"的语义，返回负内积）
        sim = np.dot(query, candidates.T).flatten()
        return -sim

    else:
        raise ValueError(f"不支持的距离度量: {metric}")


# ======================================================================
# 内部工具
# ======================================================================

def _normalize_single(vec: np.ndarray) -> np.ndarray:
    """L2 归一化单个向量"""
    norm = np.linalg.norm(vec, axis=1, keepdims=True)
    norm = np.where(norm == 0, 1.0, norm)
    return vec / norm


# ======================================================================
#  sklearn 检索
# ======================================================================

def _sklearn_search(
    index: dict,
    query_vector: np.ndarray,
    top_k: int,
    config: SearchConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    """sklearn 索引检索（KDTree / BallTree / LSHForest）"""
    tree = index["tree"]
    idx_type = index.get("_type", "BallTree")

    if idx_type in ("KDTree", "BallTree"):
        distances, indices = tree.query(query_vector, k=top_k)
        distances = distances.flatten()
        indices = indices.flatten().astype(np.int64)
    elif idx_type == "LSHForest":
        distances, indices = tree.kneighbors(query_vector, n_neighbors=top_k)
        distances = distances.flatten()
        indices = indices.flatten().astype(np.int64)
    else:
        raise ValueError(f"不支持的 sklearn 索引类型: {idx_type}")

    return distances, indices
