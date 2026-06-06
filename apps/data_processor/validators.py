"""数据合法性校验工具。

约定：所有"细胞级元信息"必须包含 cell_type / disease / AgeGroup 三个字段，
降维结果放在 obsm['X_pca']。如果数据不满足这些要求，应当尽早报错，
而不是等到查询阶段才发现。
"""

from __future__ import annotations

from typing import Iterable, List

import numpy as np

# 业务侧约定的必需字段。
REQUIRED_OBS_FIELDS: List[str] = ["cell_type", "disease", "AgeGroup"]
# 业务侧约定的降维结果键。
REQUIRED_OBSM_KEYS: List[str] = ["X_pca"]


def ensure_required_fields(adata) -> None:
    """检查 AnnData 是否包含业务必需的 obs 字段与 obsm 降维结果。

    参数:
        adata: anndata.AnnData 实例。

    抛出:
        ValueError: 当缺少必需字段或降维结果时。
    """
    missing_obs = [f for f in REQUIRED_OBS_FIELDS if f not in adata.obs.columns]
    if missing_obs:
        raise ValueError(
            f"AnnData.obs 缺少必需字段: {missing_obs}。"
            f"已存在的字段: {list(adata.obs.columns)[:10]}..."
        )
    missing_obsm = [k for k in REQUIRED_OBSM_KEYS if k not in adata.obsm]
    if missing_obsm:
        raise ValueError(
            f"AnnData.obsm 缺少必需降维结果: {missing_obsm}。"
            f"已存在的键: {list(adata.obsm.keys())}"
        )


def normalize_cell_ids(cell_ids: Iterable[str], obs_index) -> List[str]:
    """去重并保持顺序，同时校验 cell_id 是否存在于 obs_index。

    参数:
        cell_ids: 来自前端的细胞 ID 列表。
        obs_index: adata.obs.index（细胞 ID 序列）。

    返回:
        去重后的 cell_id 列表。
    """
    seen = set()
    result: List[str] = []
    unknown = []
    for cid in cell_ids:
        if cid in seen:
            continue
        seen.add(cid)
        if cid in obs_index:
            result.append(cid)
        else:
            unknown.append(cid)
    if unknown:
        # 允许部分未知 ID，但给出提示，方便前端排查。
        # 这里用 print 而非异常，避免一次错误请求炸掉整次响应。
        print(f"[data_processor] 以下 cell_id 在数据集中不存在: {unknown[:5]}..."
              f" (共 {len(unknown)} 个)")
    return result


def coerce_indices(indices: Iterable[int], n_obs: int) -> np.ndarray:
    """把前端传入的 indices 转成 numpy int 数组，并做边界校验。

    参数:
        indices: 行号列表或可迭代对象。
        n_obs: AnnData 总行数。

    返回:
        np.ndarray[int64]，去重后的合法行号。
    """
    arr = np.asarray(list(indices), dtype=np.int64)
    if arr.size == 0:
        return arr
    if (arr < 0).any() or (arr >= n_obs).any():
        raise ValueError(
            f"indices 越界: 合法范围 [0, {n_obs}),"
            f" 实际范围 [{arr.min()}, {arr.max()}]"
        )
    return np.unique(arr)
