"""数据处理模块 (B 组交付)。

对外暴露的接口：
    load_data(filepath)                       -> AnnData
    get_cell_info(adata, cell_ids)            -> List[Dict]
    get_cell_info_by_indices(adata, indices)  -> List[Dict]
    get_all_vectors(adata)                    -> np.ndarray
    get_dataset_summary(adata)                -> Dict
    DatasetManager                            -> 多数据集管理类
    get_default_manager(data_dir=None)        -> 进程级单例
"""

from .loader import load_data
from .queries import (
    get_all_vectors,
    get_cell_info,
    get_cell_info_by_indices,
    get_dataset_summary,
)
from .manager import DatasetManager, DatasetEntry, get_default_manager
from .validators import (
    REQUIRED_OBS_FIELDS,
    REQUIRED_OBSM_KEYS,
    coerce_indices,
    ensure_required_fields,
    normalize_cell_ids,
)

__all__ = [
    "load_data",
    "get_cell_info",
    "get_cell_info_by_indices",
    "get_all_vectors",
    "get_dataset_summary",
    "DatasetManager",
    "DatasetEntry",
    "get_default_manager",
    "REQUIRED_OBS_FIELDS",
    "REQUIRED_OBSM_KEYS",
    "ensure_required_fields",
    "coerce_indices",
    "normalize_cell_ids",
]
