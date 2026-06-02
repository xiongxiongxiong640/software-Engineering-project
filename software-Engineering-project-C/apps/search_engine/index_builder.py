"""
search_engine 索引构建模块

支持 FAISS 和 HNSWLIB 两种后端，提供统一的构建/保存/加载接口。

对外接口（指定的核心函数）:
    build_index(vectors, config)      → 索引对象
    save_index(index, filepath)       → None
    load_index(filepath, config)      → 索引对象

内部辅助:
    _build_faiss_index(vectors, dim, config)
    _build_hnswlib_index(vectors, dim, config)
    _normalize_vectors(vectors)

依赖:
    - faiss-cpu   (或 faiss-gpu, 团队统一用 faiss-cpu)
    - hnswlib
    - numpy
"""

import os
import pickle
from typing import Optional, Union, Tuple

import numpy as np

from .config import SearchConfig


# ======================================================================
# 类型别名
# ======================================================================
# 索引对象可能是 faiss.Index 或 hnswlib.Index，这里用 Any 避免强耦合
IndexLike = object       # faiss.Index | hnswlib.Index
VectorType = np.ndarray  # shape: (n_samples, n_features) 的 float32 矩阵


# ======================================================================
# 对外接口 — 构建索引
# ======================================================================

def build_index(
    vectors: Union[np.ndarray, list],
    config: Optional[SearchConfig] = None,
) -> IndexLike:
    """构建 ANN 索引

    Args:
        vectors: PCA 向量矩阵，shape (n_cells, n_features)，支持 numpy 数组或 list
        config:  检索配置。None 时使用默认配置（FAISS + IVFFlat + cosine）

    Returns:
        FAISS 或 HNSWLIB 索引对象

    Example:
        >>> adata = load_data("data/liver.h5ad")
        >>> pca_vectors = get_all_vectors(adata)  # shape (10000, 50)
        >>> config = SearchConfig(backend="faiss", distance_metric="cosine")
        >>> index = build_index(pca_vectors, config)
    """
    if config is None:
        config = SearchConfig()

    # ---- 输入规范化 ----
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2:
        raise ValueError(f"vectors 必须是二维矩阵，当前 shape={vectors.shape}")

    n_cells, dim = vectors.shape
    if config.verbose:
        print(f"[IndexBuilder] 输入: {n_cells} 个细胞, 维度={dim}")
        print(f"[IndexBuilder] 后端={config.backend}, "
              f"距离度量={config.distance_metric}")

    # ---- 余弦相似度需要先归一化 ----
    if config.needs_normalization():
        vectors = _normalize_vectors(vectors)
        if config.verbose:
            print("[IndexBuilder] 已对向量做 L2 归一化（用于余弦相似度）")

    # ---- 按后端分发 ----
    if config.backend == "faiss":
        return _build_faiss_index(vectors, dim, config)
    elif config.backend == "hnswlib":
        return _build_hnswlib_index(vectors, dim, config)
    else:
        raise ValueError(f"不支持的后端类型: {config.backend}，请使用 'faiss' 或 'hnswlib'")


# ======================================================================
# 对外接口 — 保存 / 加载索引
# ======================================================================

def save_index(index: IndexLike, filepath: str) -> None:
    """将索引保存到磁盘

    自动识别 FAISS / HNSWLIB 索引类型，使用对应方式序列化。

    Args:
        index:    build_index() 返回的索引对象
        filepath: 保存路径（不含扩展名）。实际会生成:
                  - {filepath}.faiss    (FAISS 主索引)
                  - {filepath}.pkl      (FAISS 元数据 / HNSWLIB 元数据)
                  - {filepath}.hnsw.bin (HNSWLIB 索引文件)

    Example:
        >>> save_index(index, "data/index/liver_ivf")
        # 生成: data/index/liver_ivf.faiss + data/index/liver_ivf.pkl
    """
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    # ---- 判断索引类型 ----
    try:
        import faiss
        if isinstance(index, faiss.Index):
            _save_faiss_index(index, filepath)
            return
    except ImportError:
        pass

    try:
        import hnswlib
        # hnswlib.Index 是 SWIG 类型，用类名判断
        if type(index).__name__ == "Index" and hasattr(index, "save_index"):
            _save_hnswlib_index(index, filepath)
            return
    except ImportError:
        pass

    raise TypeError(f"不支持的索引类型: {type(index)}。必须是 faiss.Index 或 hnswlib.Index")


def load_index(
    filepath: str,
    config: Optional[SearchConfig] = None,
) -> IndexLike:
    """从磁盘加载索引

    自动识别保存格式（.faiss / .hnsw.bin）。

    Args:
        filepath: 索引文件路径（不含扩展名），同 save_index() 的 filepath
        config:   检索配置。加载 HNSWLIB 索引时必须提供（需要 ef_search）
                 加载 FAISS 索引时可选，仅用于日志

    Returns:
        恢复的索引对象

    Example:
        >>> config = SearchConfig(hnsw_ef_search=50)
        >>> index = load_index("data/index/liver_ivf", config)
    """
    if config is None:
        config = SearchConfig()

    faiss_path = filepath + ".faiss"
    hnsw_path = filepath + ".hnsw.bin"

    if os.path.exists(faiss_path):
        return _load_faiss_index(filepath, config)
    elif os.path.exists(hnsw_path):
        return _load_hnswlib_index(filepath, config)
    else:
        raise FileNotFoundError(
            f"未找到索引文件: 尝试过 {faiss_path} 和 {hnsw_path}"
        )


# ======================================================================
# 内部实现 — FAISS
# ======================================================================

def _build_faiss_index(
    vectors: np.ndarray,
    dim: int,
    config: SearchConfig,
) -> "faiss.Index":
    """构建 FAISS 索引"""
    import faiss

    metric = config.get_faiss_metric()
    n_cells = vectors.shape[0]
    idx_type = config.faiss_index_type

    if config.verbose:
        print(f"[FAISS] 索引类型={idx_type}, metric={metric}, nlist={config.nlist}")

    # ---- Flat（暴力搜索，精确）----
    if idx_type == "Flat":
        if metric == faiss.METRIC_INNER_PRODUCT:
            index = faiss.IndexFlatIP(dim)
        else:
            index = faiss.IndexFlatL2(dim)

    # ---- IVFFlat（聚类 + 精确距离）----
    elif idx_type == "IVFFlat":
        # 量化器：用 Flat 做粗量化
        quantizer = faiss.IndexFlatL2(dim) if metric == faiss.METRIC_L2 else faiss.IndexFlatIP(dim)
        index = faiss.IndexIVFFlat(quantizer, dim, config.nlist, metric)
        # IVF 需要先训练
        if not index.is_trained:
            if config.verbose:
                print(f"[FAISS] 开始训练 IVFFlat...")
            index.train(vectors)
            if config.verbose:
                print(f"[FAISS] 训练完成")

    # ---- IVFPQ（聚类 + 乘积量化，适合超大规模数据）----
    elif idx_type == "IVFPQ":
        quantizer = faiss.IndexFlatL2(dim) if metric == faiss.METRIC_L2 else faiss.IndexFlatIP(dim)
        m = max(1, dim // 2)  # 子向量数，默认 dim/2
        index = faiss.IndexIVFPQ(
            quantizer, dim, config.nlist, m, config.nbits, metric
        )
        if not index.is_trained:
            if config.verbose:
                print(f"[FAISS] 开始训练 IVFPQ (M={m}, nbits={config.nbits})...")
            index.train(vectors)
            if config.verbose:
                print(f"[FAISS] 训练完成")

    # ---- HNSWFlat（FAISS 内置 HNSW）----
    elif idx_type == "HNSWFlat":
        index = faiss.IndexHNSWFlat(dim, config.M_faiss, metric)

    else:
        raise ValueError(f"不支持的 FAISS 索引类型: {idx_type}")

    # ---- 添加向量 ----
    index.add(vectors)

    # ---- 设置查询参数 ----
    if hasattr(index, "nprobe"):
        index.nprobe = config.nprobe

    if config.verbose:
        print(f"[FAISS] 索引构建完成: {index.ntotal} 条向量")

    return index


def _save_faiss_index(index: "faiss.Index", filepath: str) -> None:
    """保存 FAISS 索引（.faiss + .pkl 元数据）"""
    import faiss

    faiss_path = filepath + ".faiss"
    meta_path = filepath + ".pkl"

    faiss.write_index(index, faiss_path)

    # 保存元数据（方便恢复时判断类型）
    meta = {
        "backend": "faiss",
        "ntotal": index.ntotal,
        "d": index.d,
    }
    with open(meta_path, "wb") as f:
        pickle.dump(meta, f)


def _load_faiss_index(filepath: str, config: SearchConfig) -> "faiss.Index":
    """加载 FAISS 索引"""
    import faiss

    faiss_path = filepath + ".faiss"
    index = faiss.read_index(faiss_path)

    # 恢复 nprobe
    if hasattr(index, "nprobe"):
        index.nprobe = config.nprobe

    if config.verbose:
        print(f"[FAISS] 索引已加载: {index.ntotal} 条向量, 维度={index.d}")

    return index


# ======================================================================
# 内部实现 — HNSWLIB
# ======================================================================

def _build_hnswlib_index(
    vectors: np.ndarray,
    dim: int,
    config: SearchConfig,
) -> "hnswlib.Index":
    """构建 HNSWLIB 索引"""
    import hnswlib

    space = config.get_hnswlib_space()
    n_cells = vectors.shape[0]

    index = hnswlib.Index(space=space, dim=dim)
    index.init_index(
        max_elements=n_cells,
        ef_construction=config.hnsw_ef_construction,
        M=config.hnsw_M,
    )

    # 添加向量（hnswlib 需要 int 索引）
    ids = np.arange(n_cells, dtype=np.int64)
    index.add_items(vectors, ids)

    # 设置查询参数
    index.set_ef(config.hnsw_ef_search)

    if config.verbose:
        print(f"[HNSWLIB] 索引构建完成: {n_cells} 条向量, "
              f"dim={dim}, space={space}, M={config.hnsw_M}, "
              f"ef_construction={config.hnsw_ef_construction}")

    return index


def _save_hnswlib_index(index: "hnswlib.Index", filepath: str) -> None:
    """保存 HNSWLIB 索引（.hnsw.bin + .pkl 元数据）"""
    hnsw_path = filepath + ".hnsw.bin"
    meta_path = filepath + ".pkl"
    pkl_path = filepath + ".pkl"

    index.save_index(hnsw_path)

    meta = {
        "backend": "hnswlib",
        "element_count": index.element_count,
        "dim": index.dim,
        "space": index.space,
    }
    # pkl 保存到同一路径
    with open(pkl_path, "wb") as f:
        pickle.dump(meta, f)


def _load_hnswlib_index(filepath: str, config: SearchConfig) -> "hnswlib.Index":
    """加载 HNSWLIB 索引"""
    import hnswlib

    pkl_path = filepath + ".pkl"
    hnsw_path = filepath + ".hnsw.bin"

    # 读取元数据
    if not os.path.exists(pkl_path):
        raise FileNotFoundError(f"缺少索引元数据文件: {pkl_path}")

    with open(pkl_path, "rb") as f:
        meta = pickle.load(f)

    dim = meta["dim"]
    space = meta["space"]
    max_elements = meta["element_count"]

    # 重建索引对象
    index = hnswlib.Index(space=space, dim=dim)
    index.load_index(hnsw_path, max_elements=max_elements)
    index.set_ef(config.hnsw_ef_search)

    if config.verbose:
        print(f"[HNSWLIB] 索引已加载: {max_elements} 条向量, "
              f"dim={dim}, space={space}")

    return index


# ======================================================================
# 内部工具
# ======================================================================

def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2 归一化（in-place 副本），避免修改原数组"""
    vectors = vectors.copy()
    faiss_normalize_L2(vectors)
    return vectors


def faiss_normalize_L2(x: np.ndarray) -> None:
    """FAISS 风格的 L2 行归一化（原地操作）

    等价于 faiss.normalize_L2(x)，但避免了对 faiss 的硬依赖。
    """
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # 避免除零
    x /= norms


# ======================================================================
#  索引注册表（供 auth 等模块跨模块查询）
# ======================================================================

_INDEX_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_INDEX_DB_FILE = os.path.join(_INDEX_DB_DIR, "indices.json")


def _load_index_db() -> dict:
    """加载索引注册数据库"""
    if os.path.exists(_INDEX_DB_FILE):
        import json
        with open(_INDEX_DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_index_db(db: dict):
    """保存索引注册数据库"""
    os.makedirs(_INDEX_DB_DIR, exist_ok=True)
    import json
    with open(_INDEX_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
