"""细胞信息查询接口。

提供给上层（C 检索引擎 / D 前端）使用的只读查询函数。
所有函数都假设入参 adata 已经过 loader.load_data 校验。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Union

import numpy as np
import pandas as pd

from .validators import coerce_indices, normalize_cell_ids


# 暴露给前端的元信息字段（元数据 + 降维坐标）。
INFO_FIELDS: List[str] = ["cell_type", "disease", "AgeGroup"]


def _row_to_info(
    cell_id: str,
    row: pd.Series,
    pca_row: np.ndarray,
) -> Dict:
    """把 obs 的一行 + 对应 PCA 坐标组装成前端友好的 dict。"""
    return {
        "id": cell_id,
        "cell_type": str(row["cell_type"]),
        "disease": str(row["disease"]),
        "AgeGroup": str(row["AgeGroup"]),
        "pca": [float(x) for x in pca_row],
    }


def _index_to_info(
    idx: int,
    cell_id: str,
    pca_matrix: np.ndarray,
    obs_df: pd.DataFrame,
) -> Dict:
    """按行号取信息，供 get_cell_info_by_indices 使用。"""
    row = obs_df.iloc[idx]
    return _row_to_info(cell_id, row, pca_matrix[idx])


def get_cell_info(
    adata,
    cell_ids: Sequence[str],
) -> List[Dict]:
    """根据 cell_id 列表查询细胞信息。

    参数:
        adata: anndata.AnnData 实例。
        cell_ids: 细胞 ID 列表（adata.obs.index 中的值）。

    返回:
        与输入一一对应的 dict 列表，结构形如:
        {
            "id": "AAACCTGAGCAGGTCA-1_2",
            "cell_type": "hepatocyte",
            "disease": "normal",
            "AgeGroup": "Ped",
            "pca": [0.12, -0.34, ...]
        }
    """
    valid_ids = normalize_cell_ids(cell_ids, adata.obs.index)
    if not valid_ids:
        return []

    pca = adata.obsm["X_pca"]
    obs = adata.obs.loc[valid_ids, INFO_FIELDS]
    return [
        _row_to_info(cid, obs.loc[cid], pca[adata.obs.index.get_loc(cid)])
        for cid in valid_ids
    ]


def get_all_vectors(adata) -> np.ndarray:
    """提取全量 PCA 矩阵，供 C 建索引使用。

    返回:
        np.ndarray, shape=(n_cells, n_components), dtype=float32。
        转 float32 是因为 FAISS / HNSW 默认吃 float32，且能省一半内存。
    """
    pca = adata.obsm["X_pca"]
    # 复制一份避免上层意外改到原数据
    return np.ascontiguousarray(pca, dtype=np.float32)


def get_cell_info_by_indices(
    adata,
    indices: Sequence[int],
) -> List[Dict]:
    """按行号（0-based）查询细胞信息。

    用于：拿到 C 检索返回的 indices 列表后，反查每个结果的元信息。

    参数:
        adata: anndata.AnnData 实例。
        indices: 行号列表，范围 [0, n_obs)。

    返回:
        与输入 indices 等长、去重后按行号升序排列的 dict 列表。
    """
    arr = coerce_indices(indices, adata.n_obs)
    if arr.size == 0:
        return []

    pca = adata.obsm["X_pca"]
    obs = adata.obs
    return [
        _index_to_info(int(idx), adata.obs_names[int(idx)], pca, obs)
        for idx in arr
    ]


def get_dataset_summary(adata) -> Dict:
    """返回数据集概要信息（供前端/管理接口展示）。"""
    cell_type_counts = adata.obs["cell_type"].astype(str).value_counts()
    disease_counts = adata.obs["disease"].astype(str).value_counts()
    age_counts = adata.obs["AgeGroup"].astype(str).value_counts()

    pca = adata.obsm["X_pca"]
    return {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "pca_dim": int(pca.shape[1]) if pca.ndim == 2 else 0,
        "embeddings": list(adata.obsm.keys()),
        "cell_types": cell_type_counts.to_dict(),
        "diseases": disease_counts.to_dict(),
        "age_groups": age_counts.to_dict(),
    }
