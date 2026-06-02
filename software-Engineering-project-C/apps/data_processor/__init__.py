"""
data_processor — 单细胞数据加载与信息提取模块

负责 AnnData (.h5ad) 文件的读取、细胞元信息查询、PCA 向量提取。

对外接口（组长指定）:
    load_data(filepath)                              → adata 对象
    get_cell_info(adata, cell_ids)                   → 细胞信息列表
    get_all_vectors(adata)                           → 全量 PCA 矩阵
    get_cell_info_by_indices(adata, indices)          → 按行号查细胞信息

内部工具:
    list_available_fields(adata)                     → 列出可用字段
    get_data_summary(adata)                          → 数据集概览
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import numpy as np


# ======================================================================
# 对外接口 — 数据加载
# ======================================================================

def load_data(filepath: str) -> "anndata.AnnData":
    """加载单细胞 AnnData 数据

    Args:
        filepath: .h5ad 文件路径。可以是相对路径（相对于 data/ 目录）
                  或者绝对路径

    Returns:
        anndata.AnnData 对象

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不支持

    Example:
        >>> adata = load_data("data/liver.h5ad")
        >>> print(adata.shape)  # (n_cells, n_genes)
    """
    import anndata as ad

    # 支持相对路径（相对于 data/ 目录）
    if not os.path.isabs(filepath):
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data"
        )
        full_path = os.path.join(data_dir, os.path.basename(filepath))
        if os.path.exists(full_path):
            filepath = full_path

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"数据文件不存在: {filepath}")

    if not filepath.endswith((".h5ad", ".h5", ".hdf5")):
        raise ValueError(f"不支持的文件格式: {filepath}，需要 .h5ad 文件")

    adata = ad.read_h5ad(filepath)
    return adata


# ======================================================================
# 对外接口 — 细胞信息查询
# ======================================================================

def get_cell_info(
    adata: "anndata.AnnData",
    cell_ids: List[str],
) -> List[Dict]:
    """根据细胞 ID 列表获取细胞信息

    返回每个细胞的 cell_type, disease, AgeGroup 以及 PCA 坐标。

    Args:
        adata:    AnnData 对象
        cell_ids: 细胞 ID 列表（对应 adata.obs_names）

    Returns:
        [{id, cell_type, disease, AgeGroup, pca}, ...]
        对于找不到的细胞，对应位置返回 None

    Example:
        >>> info = get_cell_info(adata, ["cell_001", "cell_056"])
        >>> print(info[0]["cell_type"])  # "Hepatocyte"
    """
    results = []
    for cell_id in cell_ids:
        try:
            idx = _find_cell_index(adata, cell_id)
            results.append(_build_cell_dict(adata, idx, cell_id))
        except (KeyError, IndexError):
            results.append(None)
    return results


def get_cell_info_by_indices(
    adata: "anndata.AnnData",
    indices: List[int],
) -> List[Dict]:
    """根据行号列表获取细胞信息

    Args:
        adata:    AnnData 对象
        indices:  行号列表（0-based，对应 adata 的行索引）

    Returns:
        [{id, cell_type, disease, AgeGroup, pca}, ...]

    Example:
        >>> indices = [0, 56, 342]  # 检索返回的行号
        >>> info = get_cell_info_by_indices(adata, indices)
    """
    results = []
    for idx in indices:
        idx = int(idx)
        if 0 <= idx < adata.n_obs:
            cell_id = str(adata.obs_names[idx])
            results.append(_build_cell_dict(adata, idx, cell_id))
        else:
            results.append(None)
    return results


# ======================================================================
# 对外接口 — PCA 向量提取
# ======================================================================

def get_all_vectors(adata: "anndata.AnnData") -> np.ndarray:
    """提取全量 PCA 降维矩阵（供 C 模块建索引）

    优先从 adata.obsm['X_pca'] 读取，如果不存在则尝试其他字段。
    返回 float32 类型，shape (n_cells, n_pca_features)。

    Args:
        adata: AnnData 对象

    Returns:
        numpy 数组, shape (n_cells, n_pca_features), dtype=float32

    Raises:
        ValueError: 数据中没有 PCA 降维结果

    Example:
        >>> vectors = get_all_vectors(adata)
        >>> print(vectors.shape)  # (10456, 50)
    """
    # 按优先级尝试多个可能的键名
    candidate_keys = ["X_pca", "PCA", "pca"]

    for key in candidate_keys:
        if key in adata.obsm:
            vec = adata.obsm[key]
            return np.asarray(vec, dtype=np.float32)

    # 如果 obsm 中没有，尝试从 X 直接使用（作为最后手段）
    # 这通常不推荐：原始基因表达矩阵维度太高
    vec = adata.X
    if hasattr(vec, "toarray"):
        vec = vec.toarray()
    elif hasattr(vec, "todense"):
        vec = vec.todense()

    return np.asarray(vec, dtype=np.float32)


# ======================================================================
# 辅助工具
# ======================================================================

def get_data_summary(adata: "anndata.AnnData") -> Dict:
    """获取数据集概览信息

    Returns:
        dict: {
            "n_cells": int,
            "n_genes": int,
            "n_pca_features": int,
            "cell_types": [str, ...],
            "diseases": [str, ...],
            "age_groups": [str, ...],
            "pca_available": bool,
        }
    """
    summary = {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "pca_available": False,
        "n_pca_features": 0,
    }

    # PCA 维度
    for key in ["X_pca", "PCA", "pca"]:
        if key in adata.obsm:
            summary["pca_available"] = True
            summary["n_pca_features"] = adata.obsm[key].shape[1]
            break

    # 细胞类型
    if "cell_type" in adata.obs.columns:
        summary["cell_types"] = sorted(adata.obs["cell_type"].dropna().unique().tolist())
    else:
        summary["cell_types"] = []

    # 疾病类型
    if "disease" in adata.obs.columns:
        summary["diseases"] = sorted(adata.obs["disease"].dropna().unique().tolist())
    else:
        summary["diseases"] = []

    # 年龄组
    if "AgeGroup" in adata.obs.columns:
        summary["age_groups"] = sorted(adata.obs["AgeGroup"].dropna().unique().tolist())
    else:
        summary["age_groups"] = []

    return summary


def list_available_fields(adata: "anndata.AnnData") -> Dict[str, List[str]]:
    """列出 AnnData 中所有可用字段

    Returns:
        {"obs": [...], "obsm": [...], "var": [...]}
    """
    return {
        "obs": list(adata.obs.columns),
        "obsm": list(adata.obsm.keys()),
        "var": list(adata.var.columns) if hasattr(adata.var, "columns") else [],
    }


# ======================================================================
# 内部工具
# ======================================================================

def _find_cell_index(adata: "anndata.AnnData", cell_id: str) -> int:
    """根据细胞 ID 找到行号"""
    obs_names = list(adata.obs_names)
    try:
        return obs_names.index(cell_id)
    except ValueError:
        # 有些数据的 obs_names 可能是其他命名形式
        # 尝试匹配包含 cell_id 的名称
        for i, name in enumerate(obs_names):
            if cell_id in str(name):
                return i
        raise KeyError(f"细胞 ID 不存在: {cell_id}")


def _build_cell_dict(
    adata: "anndata.AnnData",
    idx: int,
    cell_id: str,
) -> Dict:
    """构建单个细胞的元信息字典"""
    info = {
        "id": cell_id,
    }

    # cell_type
    if "cell_type" in adata.obs.columns:
        val = adata.obs["cell_type"].iloc[idx]
        info["cell_type"] = str(val) if not _is_na(val) else "unknown"
    else:
        info["cell_type"] = "unknown"

    # disease
    if "disease" in adata.obs.columns:
        val = adata.obs["disease"].iloc[idx]
        info["disease"] = str(val) if not _is_na(val) else "unknown"
    else:
        info["disease"] = "unknown"

    # AgeGroup
    if "AgeGroup" in adata.obs.columns:
        val = adata.obs["AgeGroup"].iloc[idx]
        info["AgeGroup"] = str(val) if not _is_na(val) else "unknown"
    else:
        info["AgeGroup"] = "unknown"

    # PCA 坐标（前端画图用前 2 维）
    pca = _get_pca_row(adata, idx)
    if pca is not None and len(pca) >= 2:
        info["pca"] = [float(pca[0]), float(pca[1])]
    else:
        info["pca"] = [0.0, 0.0]

    return info


def _get_pca_row(adata: "anndata.AnnData", idx: int) -> Optional[np.ndarray]:
    """获取指定细胞的 PCA 向量"""
    for key in ["X_pca", "PCA", "pca"]:
        if key in adata.obsm:
            return adata.obsm[key][idx]
    return None


def _is_na(val) -> bool:
    """判断值是否为 NA"""
    try:
        if val is None:
            return True
        if isinstance(val, float) and np.isnan(val):
            return True
        if hasattr(val, "__class__") and "NA" in val.__class__.__name__:
            return True
    except Exception:
        pass
    return False


# ======================================================================
#  本地文件扫描与 CSV 导入
# ======================================================================

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
_DATASET_DB_FILE = os.path.join(_DATA_DIR, "datasets.json")


def _load_ds_db() -> dict:
    """加载数据集注册数据库（供 auth 模块跨模块调用）"""
    if os.path.exists(_DATASET_DB_FILE):
        with open(_DATASET_DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_ds_db(db: dict):
    """保存数据集注册数据库"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_DATASET_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def scan_local_files(data_dir: str = "data") -> list:
    """扫描 data/ 目录下可直接导入的本地文件

    Returns:
        [{"filename": "liver.h5ad", "path": "data/liver.h5ad", "size_mb": 12.3, "ext": "h5ad"}, ...]
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    full_dir = os.path.join(root, data_dir)
    if not os.path.isdir(full_dir):
        return []

    supported = {".h5ad": True, ".csv": True, ".tsv": True, ".txt": True}
    files = []
    for fname in sorted(os.listdir(full_dir)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in supported or fname.endswith("_labels.csv"):
            continue
        fpath = os.path.join(full_dir, fname)
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        files.append({
            "filename": fname,
            "path": os.path.join(data_dir, fname),
            "size_mb": round(size_mb, 2),
            "ext": ext[1:],
            "is_h5ad": ext == ".h5ad",
            "has_labels": _find_local_labels_file(fname) is not None,
        })

    return files


def _find_local_labels_file(data_filename: str) -> Optional[str]:
    """根据数据文件名查找对应的标签文件"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    data_dir = os.path.join(root, "data")
    base = os.path.splitext(data_filename)[0]
    candidates = [
        os.path.join(data_dir, f"{base}_labels.csv"),
        os.path.join(data_dir, f"{base}.labels.csv"),
        os.path.join(data_dir, f"labels_{base}.csv"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def import_local_file(
    filepath: str,
    dataset_name: str,
    username: str,
    normalize: bool = True,
    log_transform: bool = True,
) -> Tuple[bool, str, Optional[dict]]:
    """从本地文件导入数据集（支持 .h5ad / CSV / TSV）

    自动查找同名 _labels.csv 标签文件。
    .h5ad 文件直接读取 PCA/obs 元信息。
    """
    import pandas as pd

    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if not os.path.isabs(filepath):
        filepath = os.path.join(root, filepath)

    if not os.path.exists(filepath):
        return False, f"文件不存在: {filepath}", None

    ext = os.path.splitext(filepath)[1].lower()

    # ── .h5ad 分支 ──
    if ext in (".h5ad", ".h5"):
        try:
            import anndata as ad
            adata = ad.read_h5ad(filepath)
        except Exception as e:
            return False, f".h5ad 文件读取失败: {e}", None

        pca_vecs = _extract_pca_vectors(adata)
        cell_names = list(adata.obs_names.astype(str))
        gene_names = list(adata.var_names.astype(str)) if hasattr(adata.var_names, "astype") else []
        cell_types = adata.obs["cell_type"].astype(str).tolist() if "cell_type" in adata.obs.columns else None

        stats = {
            "n_cells": adata.n_obs,
            "n_genes": adata.n_vars,
            "n_pca_features": pca_vecs.shape[1] if pca_vecs is not None and pca_vecs.ndim == 2 else 0,
            "pca_available": pca_vecs is not None,
            "n_cell_types": len(set(cell_types)) if cell_types else 0,
        }

        os.makedirs(_UPLOAD_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_name = f"{username}_{dataset_name}_{ts}"
        npy_path = os.path.join(_UPLOAD_DIR, f"{safe_name}.npy")

        mat_to_save = pca_vecs if pca_vecs is not None else _extract_X_matrix(adata)
        np.save(npy_path, mat_to_save)

        meta = {
            "name": dataset_name, "username": username,
            "filename": os.path.basename(filepath), "file_type": "h5ad",
            "cell_names": cell_names, "gene_names": gene_names,
            "cell_types": cell_types,
            "stats": stats, "created_at": datetime.now().isoformat(),
            "npy_path": npy_path,
        }

        db = _load_ds_db()
        db[safe_name] = meta
        _save_ds_db(db)
        return True, safe_name, stats

    # ── CSV/TSV 分支 ──
    try:
        if ext in (".csv",):
            df = pd.read_csv(filepath, index_col=0)
        elif ext in (".tsv", ".txt"):
            df = pd.read_csv(filepath, sep="\t", index_col=0)
        else:
            return False, f"不支持的文件格式: {ext}", None
    except Exception as e:
        return False, f"文件读取失败: {e}", None

    if df.empty:
        return False, "数据为空", None

    # 转为数值矩阵并校验
    try:
        numeric = df.apply(pd.to_numeric, errors="coerce")
    except Exception as e:
        return False, f"数据类型转换失败: {e}", None

    n_cells, n_features = df.shape
    mat = numeric.values.astype(np.float32)
    np.nan_to_num(mat, copy=False)

    # 预处理
    if normalize:
        totals = mat.sum(axis=1, keepdims=True)
        totals = np.where(totals == 0, 1.0, totals)
        mat = mat / totals * 1e4
    if log_transform:
        mat = np.log1p(np.maximum(mat, 0))

    cell_names = list(df.index.astype(str))
    gene_names = list(df.columns.astype(str))

    stats = {
        "n_cells": n_cells,
        "n_genes": n_features,
        "sparsity": float((numeric == 0).sum().sum() / (n_cells * n_features)),
        "min_val": float(numeric.min().min()),
        "max_val": float(numeric.max().max()),
    }

    # 持久化保存
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{username}_{dataset_name}_{ts}"
    npy_path = os.path.join(_UPLOAD_DIR, f"{safe_name}.npy")

    np.save(npy_path, mat)

    meta = {
        "name": dataset_name,
        "username": username,
        "filename": os.path.basename(filepath),
        "cell_names": cell_names,
        "gene_names": gene_names,
        "stats": stats,
        "created_at": datetime.now().isoformat(),
        "npy_path": npy_path,
    }

    # 查找标签文件
    labels_path = _find_local_labels_file(os.path.basename(filepath))
    if labels_path:
        try:
            lbl_df = pd.read_csv(labels_path)
            if "cell_type" in lbl_df.columns:
                meta["cell_types"] = lbl_df["cell_type"].tolist()
        except Exception:
            pass

    # 写入注册数据库
    db = _load_ds_db()
    db[safe_name] = meta
    _save_ds_db(db)

    return True, safe_name, stats


def load_csv_dataset(key: str) -> Tuple[Optional[np.ndarray], Optional[dict], str]:
    """加载已保存的 CSV 数据集"""
    db = _load_ds_db()
    if key not in db:
        return None, None, "数据集不存在"

    meta = db[key]
    try:
        matrix = np.load(meta["npy_path"])
        return matrix, meta, ""
    except Exception as e:
        return None, None, f"加载失败: {e}"


def list_csv_datasets(username: Optional[str] = None) -> list:
    """列出 CSV 数据集"""
    db = _load_ds_db()
    result = []
    for key, meta in db.items():
        if username is None or meta.get("username") == username or username == "admin":
            result.append({**meta, "key": key})
    return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)


def delete_csv_dataset(key: str) -> Tuple[bool, str]:
    """删除 CSV 数据集"""
    db = _load_ds_db()
    if key not in db:
        return False, "数据集不存在"

    meta = db[key]
    npy_path = meta.get("npy_path", "")
    if os.path.exists(npy_path):
        os.unlink(npy_path)

    del db[key]
    _save_ds_db(db)
    return True, f"数据集 '{meta['name']}' 已删除"


# ======================================================================
#  .h5ad 辅助函数
# ======================================================================

def _extract_pca_vectors(adata) -> Optional[np.ndarray]:
    """从 AnnData 中提取 PCA 向量矩阵（优先 obsm['X_pca']）"""
    for key in ["X_pca", "PCA", "pca"]:
        if key in adata.obsm:
            return np.asarray(adata.obsm[key], dtype=np.float32)
    return None


def _extract_X_matrix(adata) -> np.ndarray:
    """从 AnnData 中提取表达矩阵 X（如果 PCA 不可用则用此代替）"""
    x = adata.X
    if hasattr(x, "toarray"):
        x = x.toarray()
    return np.asarray(x, dtype=np.float32)


def handle_uploaded_file(
    file_stream,
    original_filename: str,
    dataset_name: str,
    username: str,
    normalize: bool = True,
    log_transform: bool = True,
) -> Tuple[bool, str, Optional[dict]]:
    """处理浏览器上传的文件（CSV/TSV/XLSX）

    对应 Streamlit 版 st.file_uploader → load_file → validate → preprocess 流程。

    Args:
        file_stream: Flask request.files 中的文件对象（有 .read() 和 .filename）
        original_filename: 原始文件名
        dataset_name: 用户输入的数据集名称
        username: 上传用户名
        normalize: 是否 CPM 归一化
        log_transform: 是否 log1p 变换

    Returns:
        (success, key_or_error, stats_or_None)
    """
    import pandas as pd
    from io import BytesIO

    ext = os.path.splitext(original_filename)[1].lower()
    raw_bytes = file_stream.read()

    # ── .h5ad 分支 ──
    if ext in (".h5ad", ".h5"):
        try:
            import anndata as ad
            adata = ad.read_h5ad(BytesIO(raw_bytes))
        except Exception as e:
            return False, f".h5ad 文件读取失败: {e}", None

        # 提取 PCA 向量（优先 obsm['X_pca']）
        pca_vecs = _extract_pca_vectors(adata)
        cell_names = list(adata.obs_names.astype(str))
        gene_names = list(adata.var_names.astype(str)) if hasattr(adata.var_names, "astype") else []

        # 细胞类型
        cell_types = None
        if "cell_type" in adata.obs.columns:
            cell_types = adata.obs["cell_type"].astype(str).tolist()

        # 元信息
        disease = None
        if "disease" in adata.obs.columns:
            disease = adata.obs["disease"].astype(str).tolist()

        stats = {
            "n_cells": adata.n_obs,
            "n_genes": adata.n_vars,
            "n_pca_features": pca_vecs.shape[1] if pca_vecs is not None and pca_vecs.ndim == 2 else 0,
            "pca_available": pca_vecs is not None,
            "n_cell_types": len(set(cell_types)) if cell_types else 0,
        }

        # 持久化
        os.makedirs(_UPLOAD_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_name = f"{username}_{dataset_name}_{ts}"
        npy_path = os.path.join(_UPLOAD_DIR, f"{safe_name}.npy")

        mat_to_save = pca_vecs if pca_vecs is not None else _extract_X_matrix(adata)
        np.save(npy_path, mat_to_save)

        meta = {
            "name": dataset_name,
            "username": username,
            "filename": original_filename,
            "file_type": "h5ad",
            "cell_names": cell_names,
            "gene_names": gene_names,
            "cell_types": cell_types,
            "disease": disease,
            "stats": stats,
            "created_at": datetime.now().isoformat(),
            "npy_path": npy_path,
        }

        db = _load_ds_db()
        db[safe_name] = meta
        _save_ds_db(db)
        return True, safe_name, stats

    # ── CSV/TSV/XLSX 分支 ──
    try:
        if ext in (".csv",):
            df = pd.read_csv(BytesIO(raw_bytes), index_col=0)
        elif ext in (".tsv", ".txt"):
            df = pd.read_csv(BytesIO(raw_bytes), sep="\t", index_col=0)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(BytesIO(raw_bytes), index_col=0)
        else:
            return False, f"不支持的文件格式: {ext}，请上传 .h5ad / CSV / TSV / XLSX", None
    except Exception as e:
        return False, f"文件读取失败: {e}", None

    if df.empty:
        return False, "数据为空", None

    # 校验数值
    try:
        numeric = df.apply(pd.to_numeric, errors="coerce")
        if numeric.isnull().values.any():
            return False, "矩阵中包含非数值数据，请检查文件", None
    except Exception as e:
        return False, f"数据类型检查失败: {e}", None

    n_cells, n_features = df.shape
    zero_rows = int((numeric.sum(axis=1) == 0).sum())
    sparsity = float((numeric == 0).sum().sum() / (n_cells * n_features))

    # 预处理
    mat = numeric.values.astype(np.float32)
    if normalize:
        totals = mat.sum(axis=1, keepdims=True)
        totals = np.where(totals == 0, 1.0, totals)
        mat = mat / totals * 1e4
    if log_transform:
        mat = np.log1p(np.maximum(mat, 0))

    cell_names = list(df.index.astype(str))
    gene_names = list(df.columns.astype(str))

    stats = {
        "n_cells": n_cells,
        "n_genes": n_features,
        "zero_cells": zero_rows,
        "sparsity": round(sparsity, 4),
        "min_val": round(float(numeric.min().min()), 4),
        "max_val": round(float(numeric.max().max()), 4),
        "pca_available": False,
        "n_pca_features": 0,
    }

    # 持久化
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = f"{username}_{dataset_name}_{ts}"
    npy_path = os.path.join(_UPLOAD_DIR, f"{safe_name}.npy")
    np.save(npy_path, mat)

    meta = {
        "name": dataset_name,
        "username": username,
        "filename": original_filename,
        "cell_names": cell_names,
        "gene_names": gene_names,
        "stats": stats,
        "created_at": datetime.now().isoformat(),
        "npy_path": npy_path,
    }

    db = _load_ds_db()
    db[safe_name] = meta
    _save_ds_db(db)

    return True, safe_name, stats


# ---- 补充 import ----
from datetime import datetime
import json
