import time
import numpy as np
from flask import request, jsonify
from apps.api import blueprint
from apps.services.global_state import global_app_state

@blueprint.route('/status', methods=['GET'])
def get_status():
    """中期汇报或联调时，提供给D同学与老师查看系统运行健康度的接口"""
    state = global_app_state
    if not state.is_loaded or state.adata is None:
        return jsonify({"status": "error", "message": "后端引擎尚未就绪"}), 500
    
    return jsonify({
        "status": "success",
        "message": "面向单细胞高维向量数据的ANN检索系统运行良好",
        "data_metrics": {
            "total_cells": int(state.adata.n_obs),
            "total_genes": int(state.adata.n_vars),
            "cell_types_detected": state.adata.obs['cell_type'].unique().tolist()
        }
    })

@blueprint.route('/search', methods=['POST'])
def search_cells():
    """
    系统总调度 API：接收 D 请求 -> 调度 B 提取 -> 调度 C 检索 -> 调度 B 解析 -> 组装返回
    """
    if not global_app_state.is_loaded:
        return jsonify({"status": "error", "message": "系统启动中，请刷新重试"}), 500

    data = request.json or {}
    query_cell_id = data.get('query_cell_id')
    top_k = int(data.get('top_k', 10))
    
    if not query_cell_id:
        return jsonify({"status": "error", "message": "输入校验失败：缺少参数 'query_cell_id'"}), 400

    adata = global_app_state.adata
    index = global_app_state.search_index
    
    start_search_time = time.time()
    
    try:
        # ============================================================
        # 步骤 1: 找 B 同学要该查询细胞的高维 PCA 向量。若B未写完，A提供完美过渡代码
        # ============================================================
        try:
            from apps.data_processor.core import get_cell_info_by_id
            query_vector, query_info = get_cell_info_by_id(adata, query_cell_id)
        except (ImportError, AttributeError):
            if query_cell_id not in adata.obs_names:
                return jsonify({"status": "error", "message": f"未在 liver.h5ad 中找到该细胞ID: {query_cell_id}"}), 404
            row_idx = adata.obs_names.get_loc(query_cell_id)
            query_vector = adata.obsm["X_pca"][row_idx].astype(np.float32).reshape(1, -1)
            query_info = {
                "id": query_cell_id,
                "cell_type": str(adata.obs["cell_type"].iloc[row_idx]),
                "pca": adata.obsm["X_pca"][row_idx][:2].tolist()
            }

        # ============================================================
        # 步骤 2: 将向量传给 C 同学的检索结构进行搜索。若C未写完，A提供高精度矩阵距离穷举兜底
        # ============================================================
        try:
            from apps.search_engine.core import search
            distances, neighbor_row_indices = search(index, query_vector, top_k)
            distances = distances[0]
            neighbor_row_indices = neighbor_row_indices[0]
        except (ImportError, AttributeError):
            # 暴力兜底，确保在算法没提交前，前端点按钮依旧能获取绝对正确的相似细胞
            all_pca_matrices = adata.obsm["X_pca"]
            computed_dists = np.linalg.norm(all_pca_matrices - query_vector, axis=1)
            neighbor_row_indices = np.argsort(computed_dists)[:top_k + 1]
            distances = computed_dists[neighbor_row_indices]

        # ============================================================
        # 步骤 3: 拿着 C 返回的整数行号，去找 B 换取前端可视化所需的生物属性与2D坐标
        # ============================================================
        try:
            from apps.data_processor.core import get_cell_info_by_indices
            results_list = get_cell_info_by_indices(adata, neighbor_row_indices)
        except (ImportError, AttributeError):
            results_list = []
            for r_idx in neighbor_row_indices:
                results_list.append({
                    "id": adata.obs_names[r_idx],
                    "cell_type": str(adata.obs["cell_type"].iloc[r_idx]),
                    "disease": str(adata.obs["disease"].iloc[r_idx]) if "disease" in adata.obs else "normal",
                    "pca": adata.obsm["X_pca"][r_idx][:2].tolist()
                })

        # ============================================================
        # 步骤 4: 你（A同学）履行项目总装，将 C 的数学距离揉入 B 的细胞信息中，并剔除自身
        # ============================================================
        final_results = []
        for idx, dist in enumerate(distances):
            item = results_list[idx]
            # 如果搜索出的第一个是细胞本身，则跳过，保证返回的都是“相似细胞”
            if item["id"] == query_cell_id and idx == 0:
                continue
            item["distance"] = float(dist)
            final_results.append(item)

        # ============================================================
        # 步骤 5: 严格对齐数据接口协议，格式化吐给前端 D 同学进行图表彩绘
        # ============================================================
        return jsonify({
            "status": "success",
            "time_cost_ms": round((time.time() - start_search_time) * 1000, 2),
            "query_cell": query_info,
            "results": final_results[:top_k]  # 严格截取满足前端设定条数
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"后端集成总装线遭遇未知异常: {str(e)}"}), 500