"""数据管理 REST 接口（B 组交付）。

端点列表：
    GET    /api/datasets                       列出已注册数据集
    POST   /api/datasets                       注册新数据集（{name, filepath}）
    GET    /api/datasets/<name>                数据集概要
    DELETE /api/datasets/<name>                注销数据集
    POST   /api/datasets/<name>/default        设为默认
    GET    /api/datasets/<name>/vectors        导出全量 PCA 矩阵（C 建索引用）
    GET    /api/datasets/<name>/cells          按 cell_id 批量查询
                                                ?ids=cell_001,cell_002
    GET    /api/datasets/<name>/cells/index    按行号批量查询
                                                ?indices=0,1,2
"""

from __future__ import annotations

import os
from typing import List

from flask import Blueprint, jsonify, request

from apps.data_processor import get_default_manager
from apps.data_processor.queries import (
    get_all_vectors,
    get_cell_info,
    get_cell_info_by_indices,
)


data_bp = Blueprint("data", __name__, url_prefix="/api/datasets")


# ---------- 辅助：解析 ids / indices 参数 ----------
def _parse_csv(arg_name: str) -> List[str]:
    raw = request.args.get(arg_name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_indices() -> List[int]:
    raw = request.args.get("indices", "")
    out: List[int] = []
    for x in raw.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(int(x))
        except ValueError:
            raise ValueError(f"indices 含非整数: {x}")
    return out


# ---------- 数据集管理 ----------
@data_bp.get("")
def list_datasets():
    mgr = get_default_manager()
    return jsonify({"status": "success", "datasets": mgr.list()})


@data_bp.post("")
def register_dataset():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    filepath = payload.get("filepath")
    if not name or not filepath:
        return jsonify({"status": "error",
                        "message": "缺少 name 或 filepath"}), 400
    if not os.path.exists(filepath):
        return jsonify({"status": "error",
                        "message": f"文件不存在: {filepath}"}), 400

    mgr = get_default_manager()
    try:
        entry = mgr.register(name, filepath, autoload=True)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({
        "status": "success",
        "dataset": {"name": entry.name, "filepath": entry.filepath,
                    "n_cells": entry.summary["n_cells"] if entry.summary else None}
    })


@data_bp.get("/<name>")
def dataset_summary(name: str):
    mgr = get_default_manager()
    if not mgr.has(name):
        return jsonify({"status": "error", "message": f"数据集 {name} 未注册"}), 404
    return jsonify({"status": "success", "summary": mgr.get_summary(name)})


@data_bp.delete("/<name>")
def remove_dataset(name: str):
    mgr = get_default_manager()
    removed = mgr.remove(name)
    return jsonify({"status": "success" if removed else "error",
                    "removed": removed,
                    "message": "" if removed else f"数据集 {name} 未注册"})


@data_bp.post("/<name>/default")
def set_default(name: str):
    mgr = get_default_manager()
    try:
        mgr.set_default(name)
    except KeyError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    return jsonify({"status": "success", "default": mgr.default()})


# ---------- 查询 ----------
@data_bp.get("/<name>/vectors")
def export_vectors(name: str):
    """导出全量 PCA 矩阵，供 C 组建 FAISS / HNSW 索引用。

    由于数据可能很大（69032×30 ≈ 16MB），直接 JSON 仍可接受；
    若后续性能瓶颈，可改为 msgpack / numpy 二进制流。
    """
    mgr = get_default_manager()
    if not mgr.has(name):
        return jsonify({"status": "error", "message": f"数据集 {name} 未注册"}), 404
    adata = mgr.get(name)
    vectors = get_all_vectors(adata)
    return jsonify({
        "status": "success",
        "n_cells": int(vectors.shape[0]),
        "dim": int(vectors.shape[1]),
        "dtype": str(vectors.dtype),
        "vectors": vectors.tolist(),
    })


@data_bp.get("/<name>/cells")
def get_cells(name: str):
    mgr = get_default_manager()
    if not mgr.has(name):
        return jsonify({"status": "error", "message": f"数据集 {name} 未注册"}), 404
    cell_ids = _parse_csv("ids")
    if not cell_ids:
        return jsonify({"status": "error",
                        "message": "ids 参数不能为空, e.g. ?ids=cell_001,cell_002"}), 400
    adata = mgr.get(name)
    cells = get_cell_info(adata, cell_ids)
    return jsonify({"status": "success", "cells": cells})


@data_bp.get("/<name>/cells/index")
def get_cells_by_index(name: str):
    mgr = get_default_manager()
    if not mgr.has(name):
        return jsonify({"status": "error", "message": f"数据集 {name} 未注册"}), 404
    try:
        indices = _parse_indices()
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    if not indices:
        return jsonify({"status": "error",
                        "message": "indices 参数不能为空"}), 400
    adata = mgr.get(name)
    try:
        cells = get_cell_info_by_indices(adata, indices)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "success", "cells": cells})
