import time

import numpy as np
from flask import jsonify, request

from apps.api import blueprint
from apps.services.global_state import global_app_state


def _require_loaded():
    if not global_app_state.is_loaded or global_app_state.adata is None:
        return False, jsonify({"status": "error", "message": "数据尚未加载"}), 500
    return True, None, None


def _index_stats():
    index = global_app_state.search_index
    if index is None:
        return {"status": "empty", "message": "索引尚未构建"}

    stats = {"status": "ready", "type": type(index).__name__}
    for attr, key in [("ntotal", "ntotal"), ("d", "dimension"), ("nprobe", "nprobe")]:
        if hasattr(index, attr):
            try:
                stats[key] = int(getattr(index, attr))
            except Exception:
                stats[key] = str(getattr(index, attr))
    if hasattr(index, "element_count"):
        stats["ntotal"] = int(index.element_count)
    if hasattr(index, "dim"):
        stats["dimension"] = int(index.dim)
    return stats


@blueprint.route("/auth/register", methods=["POST"])
def auth_register():
    from apps.auth import init_admin, register_user
    init_admin()

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400

    ok, message = register_user(username, password)
    return jsonify({"status": "success" if ok else "error", "message": message}), 200 if ok else 409


@blueprint.route("/auth/login", methods=["POST"])
def auth_login():
    from apps.auth import init_admin, login_user
    init_admin()

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "error", "message": "用户名和密码不能为空"}), 400

    ok, message, user = login_user(username, password)
    if not ok:
        return jsonify({"status": "error", "message": message}), 401
    return jsonify({"status": "success", "message": message, "user": user})


@blueprint.route("/auth/me", methods=["GET"])
def auth_current_user():
    from apps.auth import get_user_stats, init_admin
    init_admin()

    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"status": "error", "message": "未提供用户名"}), 401
    return jsonify({"status": "success", "user": get_user_stats(username)})


@blueprint.route("/auth/users", methods=["GET"])
def auth_users():
    from apps.auth import get_all_users, init_admin
    init_admin()

    return jsonify({"status": "success", "users": get_all_users()})


@blueprint.route("/auth/users/<username>/role", methods=["PUT"])
def auth_update_role(username):
    from apps.auth import init_admin, update_user_role
    init_admin()

    data = request.get_json(silent=True) or {}
    role = data.get("role", "user")
    ok, message = update_user_role(username, role)
    return jsonify({"status": "success" if ok else "error", "message": message}), 200 if ok else 404


@blueprint.route("/index/status", methods=["GET"])
def index_status():
    ok, response, status = _require_loaded()
    if not ok:
        return response, status
    return jsonify({"status": "success", "index": _index_stats()})


@blueprint.route("/index/rebuild", methods=["POST"])
def index_rebuild():
    ok, response, status = _require_loaded()
    if not ok:
        return response, status

    try:
        from apps.data_processor.queries import get_all_vectors
        from apps.search_engine.index_builder import build_index

        vectors = get_all_vectors(global_app_state.adata)
        start = time.perf_counter()
        global_app_state.search_index = build_index(vectors)
        elapsed = (time.perf_counter() - start) * 1000
        return jsonify({
            "status": "success",
            "time_cost_ms": round(elapsed, 2),
            "index": _index_stats(),
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@blueprint.route("/benchmark", methods=["GET"])
def benchmark():
    ok, response, status = _require_loaded()
    if not ok:
        return response, status
    if global_app_state.search_index is None:
        return jsonify({"status": "error", "message": "索引尚未构建"}), 500

    try:
        from apps.data_processor.queries import get_all_vectors
        from apps.search_engine import search

        top_k = request.args.get("top_k", 10, type=int)
        n_queries = request.args.get("n_queries", 50, type=int)
        vectors = get_all_vectors(global_app_state.adata)
        n_queries = max(1, min(n_queries, vectors.shape[0]))
        rng = np.random.default_rng(42)
        query_indices = rng.choice(vectors.shape[0], size=n_queries, replace=False)

        times = []
        for idx in query_indices:
            start = time.perf_counter()
            search(global_app_state.search_index, vectors[int(idx)], top_k)
            times.append((time.perf_counter() - start) * 1000)

        arr = np.array(times, dtype=np.float64)
        return jsonify({
            "status": "success",
            "benchmark": {
                "avg_time_ms": round(float(arr.mean()), 3),
                "p50_ms": round(float(np.percentile(arr, 50)), 3),
                "p99_ms": round(float(np.percentile(arr, 99)), 3),
                "qps": round(1000.0 / float(arr.mean()), 1) if arr.mean() > 0 else None,
                "n_runs": int(n_queries),
                "top_k": int(top_k),
            },
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@blueprint.route("/search/by-vector", methods=["POST"])
def search_by_vector():
    ok, response, status = _require_loaded()
    if not ok:
        return response, status
    if global_app_state.search_index is None:
        return jsonify({"status": "error", "message": "索引尚未构建"}), 500

    data = request.get_json(silent=True) or {}
    query_vector = data.get("query_vector")
    top_k = int(data.get("top_k", 10))
    if query_vector is None:
        return jsonify({"status": "error", "message": "缺少 query_vector 参数"}), 400

    try:
        from apps.data_processor.queries import get_all_vectors, get_cell_info_by_indices
        from apps.search_engine import search

        vectors = get_all_vectors(global_app_state.adata)
        query = np.asarray(query_vector, dtype=np.float32)
        expected_dim = vectors.shape[1]
        if query.ndim != 1 or query.shape[0] != expected_dim:
            actual_dim = int(query.shape[0]) if query.ndim else 1
            return jsonify({
                "status": "error",
                "message": f"查询向量维度不匹配：需要 {expected_dim} 维，当前为 {actual_dim} 维",
            }), 400

        start = time.perf_counter()
        distances, indices = search(global_app_state.search_index, query, top_k)
        elapsed = (time.perf_counter() - start) * 1000
        distances = distances[0] if getattr(distances, "ndim", 1) > 1 else distances
        indices = indices[0] if getattr(indices, "ndim", 1) > 1 else indices

        cells = get_cell_info_by_indices(global_app_state.adata, indices)
        results = []
        for cell, dist in zip(cells, distances):
            if cell is None:
                continue
            item = cell.copy()
            item["pca"] = item.get("pca", [])[:2]
            item["distance"] = float(dist)
            results.append(item)

        return jsonify({
            "status": "success",
            "time_cost_ms": round(elapsed, 2),
            "query_cell": {"id": "vector_query", "cell_type": "vector", "pca": query[:2].tolist()},
            "results": results[:top_k],
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
