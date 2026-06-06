"""冒烟测试：覆盖 B 组所有交付接口。

直接 python tests/test_data_processor.py 即可运行。
要求 data/liver.h5ad 已就位。
"""

from __future__ import annotations

import os
import sys
import time
import traceback

# 把仓库根目录加进 path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.data_processor import (
    get_all_vectors,
    get_cell_info,
    get_cell_info_by_indices,
    get_dataset_summary,
    get_default_manager,
    load_data,
)


DATA_PATH = os.path.join(ROOT, "data", "liver.h5ad")


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  [OK] {msg}")


def test_load_data():
    print("[1] load_data")
    adata = load_data(DATA_PATH)
    assert_true(adata.n_obs > 0, f"adata.n_obs = {adata.n_obs}")
    assert_true("cell_type" in adata.obs, "obs 含 cell_type")
    assert_true("disease" in adata.obs, "obs 含 disease")
    assert_true("AgeGroup" in adata.obs, "obs 含 AgeGroup")
    assert_true("X_pca" in adata.obsm, "obsm 含 X_pca")
    return adata


def test_summary(adata):
    print("[2] get_dataset_summary")
    s = get_dataset_summary(adata)
    assert_true(s["n_cells"] == adata.n_obs, "n_cells 一致")
    assert_true(s["pca_dim"] == adata.obsm["X_pca"].shape[1],
                f"pca_dim = {s['pca_dim']}")
    print(f"    n_cells={s['n_cells']}  n_genes={s['n_genes']}  "
          f"pca_dim={s['pca_dim']}")
    print(f"    cell_types: {len(s['cell_types'])} 类")
    print(f"    diseases:   {s['diseases']}")
    print(f"    age_groups: {s['age_groups']}")


def test_get_cell_info(adata):
    print("[3] get_cell_info (按 cell_id)")
    sample_ids = list(adata.obs_names[:3])
    t0 = time.perf_counter()
    cells = get_cell_info(adata, sample_ids)
    dt = (time.perf_counter() - t0) * 1000
    assert_true(len(cells) == 3, f"返回 {len(cells)} 条")
    for c in cells:
        assert_true("id" in c and "cell_type" in c and "disease" in c
                    and "AgeGroup" in c and "pca" in c,
                    f"字段齐全: {list(c.keys())}")
        assert_true(len(c["pca"]) == adata.obsm["X_pca"].shape[1],
                    f"pca 维度 {len(c['pca'])}")
    print(f"    耗时 {dt:.2f}ms, 样例: {cells[0]['id']} -> {cells[0]['cell_type']}")

    # 未知 ID 应被忽略
    mix = sample_ids + ["not_exist_id_xxx"]
    cells2 = get_cell_info(adata, mix)
    assert_true(len(cells2) == 3, f"未知 ID 被忽略, 剩 {len(cells2)} 条")


def test_get_all_vectors(adata):
    print("[4] get_all_vectors")
    t0 = time.perf_counter()
    vecs = get_all_vectors(adata)
    dt = (time.perf_counter() - t0) * 1000
    import numpy as np
    assert_true(isinstance(vecs, np.ndarray), "返回 numpy.ndarray")
    assert_true(vecs.shape == adata.obsm["X_pca"].shape,
                f"shape = {vecs.shape}")
    assert_true(vecs.dtype == np.float32, f"dtype = {vecs.dtype} (期望 float32)")
    print(f"    shape={vecs.shape}  dtype={vecs.dtype}  耗时 {dt:.2f}ms")


def test_get_cell_info_by_indices(adata):
    print("[5] get_cell_info_by_indices (按行号)")
    indices = [0, 1, 2, 100, 5000]
    t0 = time.perf_counter()
    cells = get_cell_info_by_indices(adata, indices)
    dt = (time.perf_counter() - t0) * 1000
    assert_true(len(cells) == len(set(indices)),
                f"去重后 {len(cells)} 条")
    for c in cells:
        assert_true("id" in c, f"含 id: {c['id']}")
    print(f"    耗时 {dt:.2f}ms")

    # 越界应抛错
    try:
        get_cell_info_by_indices(adata, [adata.n_obs + 100])
        assert_true(False, "越界应当抛 ValueError")
    except ValueError:
        print("    [OK] 越界检查生效")


def test_manager():
    print("[6] DatasetManager 多数据集管理")
    mgr = get_default_manager(data_dir=os.path.join(ROOT, "data"))
    names = mgr.names()
    assert_true("liver" in names, f"自动扫描到 liver, 实际: {names}")
    summary = mgr.get_summary("liver")
    assert_true(summary["n_cells"] > 0, "summary 可访问")
    print(f"    注册列表: {names}")
    print(f"    默认数据集: {mgr.default()}")


def test_flask_routes():
    print("[7] Flask 数据管理路由")
    try:
        from flask import Flask
        from apps.api import data_bp
    except ImportError as e:
        print(f"    ! 跳过 (Flask 未装): {e}")
        return
    app = Flask(__name__)
    app.register_blueprint(data_bp)
    client = app.test_client()
    r = client.get("/api/datasets")
    assert_true(r.status_code == 200, f"GET /api/datasets -> {r.status_code}")
    data = r.get_json()
    assert_true(data["status"] == "success", f"status = {data['status']}")
    print(f"    列出 {len(data['datasets'])} 个数据集")

    r = client.get("/api/datasets/liver/summary".replace("summary", ""))
    # 上面这行是为了不真正调路径；改成：
    r = client.get("/api/datasets/liver")
    assert_true(r.status_code == 200, f"GET /api/datasets/liver -> {r.status_code}")
    print(f"    summary keys: {list(r.get_json()['summary'].keys())}")

    r = client.get("/api/datasets/liver/cells?ids="
                   + ",".join(["AAACCTGAGCAGGTCA-1_2",
                               "AAACCTGAGGCCATAG-1_2"]))
    assert_true(r.status_code == 200, f"GET /cells -> {r.status_code}")
    print(f"    返回 {len(r.get_json()['cells'])} 个 cell")

    r = client.get("/api/datasets/liver/cells/index?indices=0,1,2")
    assert_true(r.status_code == 200, f"GET /cells/index -> {r.status_code}")
    print(f"    按行号返回 {len(r.get_json()['cells'])} 个 cell")


def main():
    print(f"=== B 组冒烟测试 | data: {DATA_PATH} ===")
    if not os.path.exists(DATA_PATH):
        print(f"!! 数据不存在: {DATA_PATH}")
        sys.exit(1)
    try:
        adata = test_load_data()
        test_summary(adata)
        test_get_cell_info(adata)
        test_get_all_vectors(adata)
        test_get_cell_info_by_indices(adata)
        del adata  # 释放内存
        test_manager()
        test_flask_routes()
        print("\n=== 全部通过 ===")
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
