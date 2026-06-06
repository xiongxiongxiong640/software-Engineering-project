"""多数据集管理：列表 / 注册 / 加载 / 卸载 / 默认数据集。

支持多个 .h5ad 同时在内存中（点名访问），并提供线程安全。
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .loader import load_data
from .queries import get_dataset_summary


@dataclass
class DatasetEntry:
    """单条已注册数据集的元信息 + 句柄。"""

    name: str                       # 数据集别名（前端 / 接口用）
    filepath: str                   # 原始 .h5ad 绝对路径
    adata: object = None            # 懒加载，先为 None
    summary: Optional[dict] = None  # 缓存概要，避免每次都重算
    size_bytes: int = 0


class DatasetManager:
    """线程安全的多数据集管理器。

    用法:
        mgr = DatasetManager()
        mgr.register("liver", "/abs/path/to/liver.h5ad")
        adata = mgr.get("liver")
        for name in mgr.list():
            ...
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[str, DatasetEntry] = {}
        self._data_dir = data_dir
        self._default: Optional[str] = None
        if data_dir and os.path.isdir(data_dir):
            self._scan_data_dir(data_dir)

    # ---------- 注册 / 列表 / 卸载 ----------
    def register(
        self,
        name: str,
        filepath: str,
        autoload: bool = True,
        set_default: bool = False,
    ) -> DatasetEntry:
        """注册一个数据集，可选立即加载到内存。"""
        with self._lock:
            if not name:
                raise ValueError("数据集 name 不能为空")
            abs_path = os.path.abspath(filepath)
            entry = DatasetEntry(name=name, filepath=abs_path,
                                 size_bytes=os.path.getsize(abs_path))
            if autoload:
                entry.adata = load_data(abs_path)
                entry.summary = get_dataset_summary(entry.adata)
            self._entries[name] = entry
            if set_default or self._default is None:
                self._default = name
            return entry

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._entries.pop(name, None) is not None

    def list(self) -> List[Dict]:
        """返回数据集元信息列表（不返回 AnnData 句柄，避免误改）。"""
        with self._lock:
            result = []
            for name, e in self._entries.items():
                result.append({
                    "name": name,
                    "filepath": e.filepath,
                    "n_cells": e.summary["n_cells"] if e.summary else None,
                    "n_genes": e.summary["n_genes"] if e.summary else None,
                    "loaded": e.adata is not None,
                    "is_default": name == self._default,
                })
            return result

    def names(self) -> List[str]:
        with self._lock:
            return list(self._entries.keys())

    def default(self) -> str:
        with self._lock:
            if not self._default:
                raise RuntimeError("尚未注册任何数据集")
            return self._default

    def set_default(self, name: str) -> None:
        with self._lock:
            if name not in self._entries:
                raise KeyError(f"数据集 {name} 未注册")
            self._default = name

    # ---------- 访问 ----------
    def get(self, name: Optional[str] = None):
        """获取 AnnData 句柄；首次访问会自动加载。"""
        with self._lock:
            target = name or self.default()
            if target not in self._entries:
                raise KeyError(f"数据集 {target} 未注册")
            entry = self._entries[target]
            if entry.adata is None:
                entry.adata = load_data(entry.filepath)
                entry.summary = get_dataset_summary(entry.adata)
            return entry.adata

    def get_summary(self, name: Optional[str] = None) -> Dict:
        with self._lock:
            target = name or self.default()
            entry = self._entries[target]
            if entry.summary is None:
                entry.summary = get_dataset_summary(
                    load_data(entry.filepath))
            return entry.summary

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._entries

    # ---------- 自动扫描 ----------
    def _scan_data_dir(self, data_dir: str) -> None:
        """启动时扫描 data/ 下的所有 .h5ad，自动注册（懒加载）。"""
        for fname in sorted(os.listdir(data_dir)):
            if fname.lower().endswith(".h5ad"):
                abs_path = os.path.abspath(os.path.join(data_dir, fname))
                # 用文件名（去后缀）作为默认别名
                alias = os.path.splitext(fname)[0]
                try:
                    self.register(alias, abs_path, autoload=False)
                except Exception as e:
                    # 单个文件损坏不应该影响其他数据集
                    print(f"[data_processor] 跳过 {fname}: {e}")


# 进程级单例 —— Flask 蓝图直接 import 这个用。
_default_manager: Optional[DatasetManager] = None
_manager_lock = threading.Lock()


def get_default_manager(data_dir: Optional[str] = None) -> DatasetManager:
    """获取（或懒创建）默认 DatasetManager 单例。"""
    global _default_manager
    with _manager_lock:
        if _default_manager is None:
            _default_manager = DatasetManager(data_dir=data_dir)
        return _default_manager
