"""
apps.api — RESTful API 蓝图

提供 JSON API 接口，供前端通过 AJAX 调用。

接口列表:
    GET  /api/status                → 系统状态
    GET  /api/datasets              → 可用数据集列表
    POST /api/load                  → 加载数据集并构建索引
    POST /api/search                → 细胞相似性搜索
    POST /api/search/by-vector      → 向量搜索
    GET  /api/cells/random          → 随机细胞列表
    GET  /api/cells/<cell_id>       → 细胞详情
    POST /api/index/save            → 保存索引
    POST /api/index/load            → 加载索引
    GET  /api/benchmark             → 性能测试
"""

from flask import Blueprint, request, jsonify, current_app
import numpy as np

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ======================================================================
# 辅助 — 获取服务实例
# ======================================================================

def _get_search_service():
    """从 Flask app 上下文中获取 SearchService 单例"""
    return current_app.config["search_service"]


# ======================================================================
# 系统状态
# ======================================================================

@api_bp.route("/status", methods=["GET"])
def system_status():
    """获取系统整体状态（数据是否加载、索引是否就绪等）"""
    svc = _get_search_service()
    return jsonify(svc.get_system_status())


# ======================================================================
# 数据集管理
# ======================================================================

@api_bp.route("/datasets", methods=["GET"])
def list_datasets():
    """列出所有可用数据集（已导入优先）"""
    from apps.data_processor import list_csv_datasets

    imported = list_csv_datasets()
    datasets = []
    for imp in imported:
        datasets.append({
            "filename": imp.get("filename", imp.get("name", "")),
            "path": imp.get("npy_path", ""),
            "key": imp.get("key", ""),
            "name": imp.get("name", ""),
            "username": imp.get("username", ""),
            "stats": imp.get("stats", {}),
            "cell_types": imp.get("cell_types"),
            "created_at": imp.get("created_at", ""),
            "imported": True,
            "file_type": imp.get("file_type", "csv"),
        })

    # 兜底：data/ 目录下未导入的原始文件
    svc = _get_search_service()
    imported_names = {imp.get("filename", "") for imp in imported}
    raw = svc.data_service.list_datasets()
    for r in raw:
        if r["filename"] not in imported_names:
            datasets.append({
                "filename": r["filename"],
                "path": r["path"].replace("\\", "/"),
                "key": r["path"].replace("\\", "/"),
                "name": r["filename"],
                "size_mb": r.get("size_mb", 0),
                "imported": False,
            })

    return jsonify({"datasets": datasets})


@api_bp.route("/load", methods=["POST"])
def load_dataset():
    """加载数据集并构建 ANN 索引

    请求体:
        {"data_file": "data/liver.h5ad"}   # 原始 .h5ad
        或 {"data_file": "admin_liver_2026..."}  # 已导入的 key
    """
    svc = _get_search_service()
    body = request.get_json(silent=True) or {}

    data_file = body.get("data_file")
    index_file = body.get("index_file")

    if not data_file:
        return jsonify({"status": "error", "message": "缺少 data_file 参数"}), 400

    # 判断是导入的 key 还是原始文件路径
    from apps.data_processor import load_csv_dataset, _load_ds_db
    ds_db = _load_ds_db()

    if data_file in ds_db:
        # 已导入的数据集：从 npy 加载
        matrix, meta, err = load_csv_dataset(data_file)
        if err:
            return jsonify({"status": "error", "message": err}), 404

        # 直接设置到 SearchService
        svc.data_service._adata = _numpy_to_anndata_proxy(matrix, meta)
        svc.data_service._loaded_file = data_file

        # 构建索引
        vectors = matrix.astype(np.float32) if matrix.dtype != np.float32 else matrix
        stats = svc.index_service.build(vectors)

        summary = {
            "n_cells": meta["stats"]["n_cells"],
            "n_genes": meta["stats"]["n_genes"],
            "n_pca_features": meta["stats"].get("n_pca_features", vectors.shape[1]),
            "cell_types": list(set(meta.get("cell_types", []))) if meta.get("cell_types") else [],
        }

        return jsonify({
            "status": "success",
            "data_summary": summary,
            "index_status": stats,
        })

    # 原始 .h5ad 文件
    try:
        result = svc.init(data_file=data_file, index_file=index_file)
        return jsonify({"status": "success", **result})
    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _numpy_to_anndata_proxy(matrix, meta):
    """从 numpy 矩阵 + 元信息创建一个最小 AnnData 代理对象"""
    import anndata as ad
    import pandas as pd

    n_cells = matrix.shape[0]
    cell_names = meta.get("cell_names", [f"cell_{i}" for i in range(n_cells)])
    if len(cell_names) != n_cells:
        cell_names = [f"cell_{i}" for i in range(n_cells)]

    gene_names = meta.get("gene_names", [f"gene_{i}" for i in range(matrix.shape[1])])
    if len(gene_names) != matrix.shape[1]:
        gene_names = [f"gene_{i}" for i in range(matrix.shape[1])]

    adata = ad.AnnData(
        X=matrix.copy(),
        obs=pd.DataFrame(index=cell_names),
        var=pd.DataFrame(index=gene_names),
    )
    # 同时写入 obsm 以便 PCA 可视化
    adata.obsm["X_pca"] = matrix.copy()

    if meta.get("cell_types"):
        types = meta["cell_types"]
        if len(types) != n_cells:
            types = types[:n_cells] if len(types) > n_cells else types + ["unknown"] * (n_cells - len(types))
        adata.obs["cell_type"] = types

    if meta.get("disease"):
        adata.obs["disease"] = meta["disease"][:n_cells]

    return adata


# ======================================================================
# 搜索接口
# ======================================================================

@api_bp.route("/search", methods=["POST"])
def search_cells():
    """细胞相似性搜索

    请求体（与组长指定的前端格式一致）:
        {
            "query_cell_id": "cell_001",
            "top_k": 10,
            "filter_cell_type": "Hepatocyte"   // 可选，限定细胞类型
        }

    返回:
        {
            "status": "success",
            "time_cost_ms": 12.5,
            "query_cell": {id, cell_type, disease, AgeGroup, pca},
            "results": [{id, distance, cell_type, disease, pca}, ...]
        }
    """
    svc = _get_search_service()
    body = request.get_json(silent=True) or {}

    query_cell_id = body.get("query_cell_id")
    top_k = body.get("top_k", 10)
    filter_cell_type = body.get("filter_cell_type")

    if not query_cell_id:
        return jsonify({"status": "error", "message": "缺少 query_cell_id 参数"}), 400

    try:
        result = svc.search_by_cell_id(
            cell_id=query_cell_id,
            top_k=top_k,
            filter_cell_type=filter_cell_type,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/search/by-vector", methods=["POST"])
def search_by_vector():
    """按向量搜索

    请求体:
        {
            "query_vector": [0.1, -0.3, ...],
            "top_k": 10
        }
    """
    svc = _get_search_service()
    body = request.get_json(silent=True) or {}

    query_vector = body.get("query_vector")
    top_k = body.get("top_k", 10)

    if not query_vector:
        return jsonify({"status": "error", "message": "缺少 query_vector 参数"}), 400

    try:
        result = svc.search_by_vector(query_vector, top_k)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================================================================
# 细胞信息
# ======================================================================

@api_bp.route("/cells/random", methods=["GET"])
def random_cells():
    """获取随机细胞列表（供前端查询下拉使用）"""
    n = request.args.get("n", 5, type=int)
    svc = _get_search_service()
    try:
        cells = svc.get_random_cells(n)
        return jsonify({"cells": cells})
    except Exception as e:
        return jsonify({"cells": [], "error": str(e)})


@api_bp.route("/cells/<cell_id>", methods=["GET"])
def cell_detail(cell_id: str):
    """获取单个细胞的详细信息"""
    svc = _get_search_service()
    try:
        info = svc.data_service.get_cell_info_by_id([cell_id])
        if info[0] is None:
            return jsonify({"status": "error", "message": f"细胞 {cell_id} 不存在"}), 404
        return jsonify({"status": "success", "cell": info[0]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================================================================
# 可视化 — 全局降维坐标
# ======================================================================

@api_bp.route("/viz/coordinates", methods=["GET"])
def viz_coordinates():
    """获取全局降维坐标用于可视化

    Query params:
        method: 降维方法，"pca"（默认）/ "umap" / "tsne"
        max_points: 最大返回点数（默认 5000，防止传输过大）

    返回:
        {
            "method": "pca",
            "total_cells": 69032,
            "points": [
                {"x": 1.23, "y": -0.45, "cell_type": "Hepatocyte", "cell_id": "cell_001"},
                ...
            ],
            "cell_types": ["Hepatocyte", "T cell", ...]
        }
    """
    svc = _get_search_service()
    if not svc.data_service.is_loaded:
        return jsonify({"status": "error", "message": "数据未加载"}), 400

    method = request.args.get("method", "pca").lower()
    max_points = request.args.get("max_points", 5000, type=int)

    try:
        adata = svc.data_service.adata
        n_cells = adata.n_obs

        # 选择降维方法
        obsm_key = None
        if method == "umap" and "X_umap" in adata.obsm:
            obsm_key = "X_umap"
        elif method == "tsne" and "X_tsne" in adata.obsm:
            obsm_key = "X_tsne"
        elif method == "pca" and "X_pca" in adata.obsm:
            obsm_key = "X_pca"
        else:
            # fallback: 尝试任一可用
            for k in ["X_pca", "X_umap", "X_tsne"]:
                if k in adata.obsm:
                    obsm_key = k
                    method = k.replace("X_", "")
                    break
            if obsm_key is None:
                return jsonify({"status": "error", "message": "无可用的降维数据"}), 400

        coords = np.asarray(adata.obsm[obsm_key], dtype=np.float32)

        # 随机采样避免数据过大
        n_sample = min(n_cells, max_points)
        if n_cells > n_sample:
            rng = np.random.default_rng(42)
            idx_sample = rng.choice(n_cells, size=n_sample, replace=False)
        else:
            idx_sample = np.arange(n_cells)

        # 归一化坐标到合理范围
        xs = coords[idx_sample, 0]
        ys = coords[idx_sample, 1]
        x_scale = 1.0 / (xs.std() + 1e-8)
        y_scale = 1.0 / (ys.std() + 1e-8)

        # 获取细胞类型
        cell_types_list = adata.obs["cell_type"].astype(str).tolist() if "cell_type" in adata.obs.columns else (["unknown"] * n_cells)

        points = []
        cell_types_set = set()
        for idx in idx_sample:
            ct = cell_types_list[idx]
            cell_types_set.add(ct)
            points.append({
                "x": round(float(xs[idx] * x_scale * 2), 2),
                "y": round(float(ys[idx] * y_scale * 2), 2),
                "cell_type": ct,
                "cell_id": str(adata.obs_names[idx]),
            })

        return jsonify({
            "status": "success",
            "method": method,
            "total_cells": n_cells,
            "sampled": len(points),
            "points": points,
            "cell_types": sorted(cell_types_set),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================================================================
# 索引管理
# ======================================================================

@api_bp.route("/index/save", methods=["POST"])
def save_index():
    """保存当前索引到磁盘

    请求体:
        {"filepath": "data/index/liver"}
    """
    svc = _get_search_service()
    body = request.get_json(silent=True) or {}

    filepath = body.get("filepath", "data/index/default")
    try:
        path = svc.index_service.save(filepath)
        return jsonify({"status": "success", "path": path})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/index/load", methods=["POST"])
def load_index():
    """从磁盘加载索引

    请求体:
        {"filepath": "data/index/liver"}
    """
    svc = _get_search_service()
    body = request.get_json(silent=True) or {}

    filepath = body.get("filepath")
    if not filepath:
        return jsonify({"status": "error", "message": "缺少 filepath 参数"}), 400

    try:
        stats = svc.index_service.load(filepath)
        return jsonify({"status": "success", "index_status": stats})
    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================================================================
# 性能评测
# ======================================================================

@api_bp.route("/benchmark", methods=["GET"])
def benchmark():
    """运行检索性能基准测试

    Query params:
        n_queries: 测试查询数 (default 100)
        top_k:     K 值 (default 10)
    """
    n_queries = request.args.get("n_queries", 100, type=int)
    top_k = request.args.get("top_k", 10, type=int)

    svc = _get_search_service()
    try:
        result = svc.run_benchmark(n_queries=n_queries, top_k=top_k)
        return jsonify({"status": "success", "benchmark": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================================================================
# 用户认证
# ======================================================================

def _get_auth_service():
    from apps.services import AuthService
    if "auth_service" not in current_app.config:
        current_app.config["auth_service"] = AuthService()
    return current_app.config["auth_service"]


@api_bp.route("/auth/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400
    svc = _get_auth_service()
    ok, msg = svc.register(username, password)
    if ok:
        return jsonify({"status": "success", "message": msg})
    return jsonify({"status": "error", "message": msg}), 409


@api_bp.route("/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400
    svc = _get_auth_service()
    ok, msg, info = svc.login(username, password)
    if ok:
        return jsonify({"status": "success", "message": msg, "user": info})
    return jsonify({"status": "error", "message": msg}), 401


@api_bp.route("/auth/me", methods=["GET"])
def current_user():
    username = request.args.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "未提供用户名"}), 401
    svc = _get_auth_service()
    stats = svc.get_stats(username)
    return jsonify({"status": "success", "user": stats})


@api_bp.route("/auth/users", methods=["GET"])
def list_users():
    svc = _get_auth_service()
    users = svc.get_all_users()
    return jsonify({"users": users})


@api_bp.route("/auth/users/<username>/role", methods=["PUT"])
def update_role(username: str):
    body = request.get_json(silent=True) or {}
    new_role = body.get("role", "user")
    svc = _get_auth_service()
    ok, msg = svc.update_role(username, new_role)
    return jsonify({"status": "success" if ok else "error", "message": msg})


# ======================================================================
# 本地数据导入
# ======================================================================

@api_bp.route("/local-files", methods=["GET"])
def list_local_files():
    from apps.data_processor import scan_local_files
    files = scan_local_files()
    return jsonify({"files": files})


@api_bp.route("/local-files/import", methods=["POST"])
def import_local_file():
    from apps.data_processor import import_local_file as _import
    body = request.get_json(silent=True) or {}
    filepath = body.get("filepath", "")
    ds_name = body.get("dataset_name", "")
    username = body.get("username", "admin")
    normalize = body.get("normalize", True)
    log_transform = body.get("log_transform", True)
    if not filepath or not ds_name:
        return jsonify({"status": "error", "message": "缺少 filepath 或 dataset_name"}), 400
    ok, key_or_err, stats = _import(filepath, ds_name, username, normalize, log_transform)
    if ok:
        return jsonify({"status": "success", "key": key_or_err, "stats": stats})
    return jsonify({"status": "error", "message": key_or_err}), 400


@api_bp.route("/csv-datasets", methods=["GET"])
def list_csv_datasets():
    from apps.data_processor import list_csv_datasets
    username = request.args.get("username")
    datasets = list_csv_datasets(username)
    return jsonify({"datasets": datasets})


@api_bp.route("/csv-datasets/<key>", methods=["DELETE"])
def delete_csv_dataset(key: str):
    from apps.data_processor import delete_csv_dataset
    ok, msg = delete_csv_dataset(key)
    return jsonify({"status": "success" if ok else "error", "message": msg})


# ======================================================================
# 索引构建（自定义配置）
# ======================================================================

@api_bp.route("/index/build", methods=["POST"])
def build_index_config():
    """使用自定义配置构建 ANN 索引

    请求体:
        {
            "dataset_key": "Jyyu_liver_2026...",
            "backend": "faiss" | "sklearn",
            "index_type": "FAISS-HNSWFlat" | "KDTree" | "BallTree" | ...,
            "distance_metric": "cosine" | "euclidean",
            "params": {"M": 32, "leaf_size": 40, ...}
        }

    成功返回:
        {"status": "success", "stats": {...}}
    """
    from apps.data_processor import load_csv_dataset, _load_ds_db as _ldb
    from apps.search_engine import SearchConfig, IndexManager
    import time

    body = request.get_json(silent=True) or {}
    ds_key = body.get("dataset_key", "")
    backend = body.get("backend", "faiss")
    index_type = body.get("index_type", "FAISS-IVFFlat")
    metric = body.get("distance_metric", "cosine")
    extra = body.get("params", {})

    if not ds_key:
        return jsonify({"status": "error", "message": "缺少 dataset_key"}), 400

    # 加载数据集矩阵
    matrix, meta, err = load_csv_dataset(ds_key)
    if err:
        return jsonify({"status": "error", "message": err}), 404

    vectors = matrix.astype(np.float32) if matrix.dtype != np.float32 else matrix

    # 构建配置
    if backend == "sklearn":
        config = SearchConfig(
            backend="sklearn",
            distance_metric=metric,
            sklearn_index_type=index_type,
            leaf_size=extra.get("leaf_size", 40),
            lsh_n_estimators=extra.get("lsh_n_estimators", 10),
        )
    elif backend == "faiss":
        config = SearchConfig(
            backend="faiss",
            distance_metric=metric,
            faiss_index_type=index_type.replace("FAISS-", ""),
            nlist=extra.get("nlist", 100),
            M_faiss=extra.get("M", 32),
            nprobe=extra.get("nprobe", 10),
        )
    elif backend == "hnswlib":
        config = SearchConfig(
            backend="hnswlib",
            distance_metric=metric,
            hnsw_M=extra.get("M", 16),
            hnsw_ef_construction=extra.get("ef_construction", 200),
            hnsw_ef_search=extra.get("ef_search", 50),
        )
    else:
        return jsonify({"status": "error", "message": f"不支持的后端: {backend}"}), 400

    # 构建并注册
    try:
        t0 = time.time()
        manager = IndexManager(config)
        manager.build(vectors)
        elapsed = time.time() - t0

        stats = manager.get_stats()
        stats["build_time_sec"] = round(elapsed, 3)
        stats["dataset_name"] = meta.get("name", "")

        # 注册到索引 DB
        from apps.search_engine.index_builder import _load_index_db, _save_index_db
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        idx_key = f"{meta.get('username','admin')}_{meta['name']}_{backend}_{index_type}_{ts}"
        idx_db = _load_index_db()
        idx_db[idx_key] = {
            "index_key": idx_key,
            "backend": backend,
            "index_type": index_type,
            "distance_metric": metric,
            "dataset_key": ds_key,
            "username": meta.get("username", "admin"),
            "stats": stats,
            "created_at": datetime.now().isoformat(),
        }
        _save_index_db(idx_db)

        # 存入 session
        svc = _get_search_service()
        svc.index_service._manager = manager

        return jsonify({"status": "success", "stats": stats, "index_key": idx_key})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/index/list", methods=["GET"])
def list_built_indices():
    """列出已构建的索引"""
    from apps.search_engine.index_builder import _load_index_db
    db = _load_index_db()
    indices = sorted(db.values(), key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"indices": indices})


@api_bp.route("/index/delete", methods=["POST"])
def delete_index_api():
    """删除一个已构建的索引"""
    from apps.search_engine.index_builder import _load_index_db, _save_index_db
    body = request.get_json(silent=True) or {}
    idx_key = body.get("index_key", "")
    if not idx_key:
        return jsonify({"status": "error", "message": "缺少 index_key"}), 400
    db = _load_index_db()
    if idx_key not in db:
        return jsonify({"status": "error", "message": "索引不存在"}), 404
    del db[idx_key]
    _save_index_db(db)
    return jsonify({"status": "success", "message": "索引已删除"})


# ======================================================================
# 文件上传
# ======================================================================

@api_bp.route("/upload", methods=["POST"])
def upload_file():
    """上传单细胞表达矩阵文件（CSV/TSV/XLSX）

    multipart/form-data:
        file:        文件（必填）
        dataset_name: 数据集名称（必填）
        username:     用户名（必填）
        normalize:    "true"/"false"（可选，默认 true）
        log_transform:"true"/"false"（可选，默认 true）

    返回:
        {"status": "success", "key": "...", "stats": {...}}
    """
    from apps.data_processor import handle_uploaded_file

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "文件名为空"}), 400

    ds_name = request.form.get("dataset_name", "").strip()
    username = request.form.get("username", "admin").strip()
    normalize = request.form.get("normalize", "true").lower() == "true"
    log_transform = request.form.get("log_transform", "true").lower() == "true"

    if not ds_name:
        return jsonify({"status": "error", "message": "缺少 dataset_name"}), 400

    ok, key_or_err, stats = handle_uploaded_file(
        file, file.filename, ds_name, username,
        normalize=normalize, log_transform=log_transform,
    )

    if ok:
        return jsonify({"status": "success", "key": key_or_err, "stats": stats})
    return jsonify({"status": "error", "message": key_or_err}), 400
