"""数据加载入口。

负责把 .h5ad 文件读取为 anndata.AnnData 对象，并做基础的合法性校验。
不负责缓存 —— 缓存由 manager.py 统一管理。
"""

from __future__ import annotations

import os
from typing import Optional

import anndata as ad

from .validators import ensure_required_fields


def load_data(filepath: str, backed: Optional[str] = None) -> ad.AnnData:
    """加载 .h5ad 文件并校验必需字段。

    参数:
        filepath: .h5ad 文件的绝对或相对路径。
        backed: 若为 'r' 则以只读 backed 模式打开（不把 X 载入内存），
            适合数据量极大且只读 obs / obsm 的场景；为 None 则全量载入。

    返回:
        anndata.AnnData 实例。
    """
    if not filepath:
        raise ValueError("filepath 不能为空")
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到 h5ad 文件: {filepath}")
    if not filepath.lower().endswith(".h5ad"):
        raise ValueError(f"仅支持 .h5ad 格式, 当前: {filepath}")

    if backed:
        adata = ad.read_h5ad(filepath, backed=backed)
    else:
        adata = ad.read_h5ad(filepath)

    ensure_required_fields(adata)
    return adata
