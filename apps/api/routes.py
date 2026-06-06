import time
import numpy as np
from flask import request, jsonify
from apps.api import blueprint
from apps.services.global_state import global_app_state

@blueprint.route('/status', methods=['GET'])
def get_status():
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
        # 步骤 1: 🌟 调度 B 的 queries 模块，获取信息并转换格式
        # ============================================================
        # ============================================================
        # 步骤 1: 适配 B 同学的 queries.py 接口 (传入列表)
        # ============================================================
        try:
            from apps.data_processor.queries import get_cell_info
            # 必须传入列表 [query_cell_id]
            info_list = get_cell_info(adata, [query_cell_id]) 
            
            if not info_list:
                return jsonify({"status": "error", "message": f"未在数据集中找到细胞: {query_cell_id}"}), 404
            
            query_info_full = info_list[0] 
            # 提取向量喂给 C (确保是 float32 矩阵)
            query_vector = np.array(query_info_full["pca"], dtype=np.float32).reshape(1, -1)
            # 整理返回给前端 D 的坐标 (截取前两维)
            query_info = query_info_full.copy()
            query_info["pca"] = query_info_full["pca"][:2]
            
    
        except Exception as e:
            # 暴力兜底
            if query_cell_id not in adata.obs_names:
                return jsonify({"status": "error", "message": f"未找到细胞ID: {query_cell_id}"}), 404
            row_idx = adata.obs_names.get_loc(query_cell_id)
            query_vector = adata.obsm["X_pca"][row_idx].astype(np.float32).reshape(1, -1)
            query_info = {
                "id": query_cell_id, "cell_type": str(adata.obs["cell_type"].iloc[row_idx]),
                "pca": adata.obsm["X_pca"][row_idx][:2].tolist()
            }

        # ============================================================
        # 步骤 2: C 同学检索引擎
        # ============================================================
        try:
            from apps.search_engine.core import search
            distances, neighbor_row_indices = search(index, query_vector, top_k)
            distances = distances[0]
            neighbor_row_indices = neighbor_row_indices[0]
        except (ImportError, AttributeError):
            all_pca_matrices = adata.obsm["X_pca"]
            computed_dists = np.linalg.norm(all_pca_matrices - query_vector, axis=1)
            neighbor_row_indices = np.argsort(computed_dists)[:top_k + 1]
            distances = computed_dists[neighbor_row_indices]

        # ============================================================
        # 步骤 3: 🌟 再次调度 B 模块解析结果，并截取二维坐标给前端
        # ============================================================
        try:
            from apps.data_processor.queries import get_cell_info_by_indices
            results_list_raw = get_cell_info_by_indices(adata, neighbor_row_indices)
            
            results_list = []
            for item in results_list_raw:
                item_copy = item.copy()
                item_copy["pca"] = item_copy["pca"][:2] # 截取两维画图
                results_list.append(item_copy)
        except Exception:
            results_list = []
            for r_idx in neighbor_row_indices:
                results_list.append({
                    "id": adata.obs_names[r_idx], "cell_type": str(adata.obs["cell_type"].iloc[r_idx]),
                    "disease": str(adata.obs["disease"].iloc[r_idx]) if "disease" in adata.obs else "normal",
                    "pca": adata.obsm["X_pca"][r_idx][:2].tolist()
                })

        # ============================================================
        # 步骤 4: 揉入数学距离，剔除自身
        # ============================================================
        final_results = []
        for idx, dist in enumerate(distances):
            item = results_list[idx]
            if item["id"] == query_cell_id and idx == 0:
                continue
            item["distance"] = float(dist)
            final_results.append(item)

        return jsonify({
            "status": "success",
            "time_cost_ms": round((time.time() - start_search_time) * 1000, 2),
            "query_cell": query_info,
            "results": final_results[:top_k]
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"后端集成遭遇异常: {str(e)}"}), 500