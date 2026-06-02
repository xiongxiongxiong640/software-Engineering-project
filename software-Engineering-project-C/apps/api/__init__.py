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
    """列出 data/ 目录下所有可用数据集"""
    svc = _get_search_service()
    datasets = svc.data_service.list_datasets()
    return jsonify({"datasets": datasets})


@api_bp.route("/load", methods=["POST"])
def load_dataset():
    """加载数据集并构建 ANN 索引

    请求体:
        {"data_file": "data/liver.h5ad", "index_file": null}
        或 {"data_file": "data/liver.h5ad", "index_file": "data/index/liver"}

    成功返回:
        {"status": "success", "data_summary": {...}, "index_status": {...}}
    """
    svc = _get_search_service()
    body = request.get_json(silent=True) or {}

    data_file = body.get("data_file")
    index_file = body.get("index_file")

    if not data_file:
        return jsonify({"status": "error", "message": "缺少 data_file 参数"}), 400

    try:
        result = svc.init(data_file=data_file, index_file=index_file)
        return jsonify({"status": "success", **result})
    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
