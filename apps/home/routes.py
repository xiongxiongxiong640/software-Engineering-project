"""前端路由：页面渲染 + 搜索 API + PCA 可视化数据

请求格式：
    {"query_cell_id": "cell_001", "top_k": 10}

响应格式：
    {
        "status": "success",
        "time_cost_ms": 12.5,
        "query_cell": {"id": "cell_001", "cell_type": "Hepatocyte", "pca": [...]},
        "results": [{"id": "...", "distance": 0.12, "cell_type": "...", "disease": "...", "pca": [...]}]
    }
"""
import time
import numpy as np
from flask import render_template, request, jsonify

from apps.home import home_bp


# ─── 尝试导入 B（data_processor）和 C（search_engine）模块 ──────────────
try:
    from apps.data_processor import load_data, get_cell_info, get_all_vectors, get_cell_info_by_indices
    _DATA_PROCESSOR_READY = True
except ImportError:
    _DATA_PROCESSOR_READY = False

try:
    from apps.search_engine import build_index, search
    _SEARCH_ENGINE_READY = True
except ImportError:
    _SEARCH_ENGINE_READY = False

# ─── 懒加载的全局状态 ──────────────────────────────────────────────────
_adata = None       # 数据对象
_index = None       # FAISS/HNSW 索引
_vectors = None     # 全量 PCA 矩阵


def _ensure_data_loaded():
    """确保数据已加载（懒加载）"""
    global _adata, _index, _vectors

    if not _DATA_PROCESSOR_READY or not _SEARCH_ENGINE_READY:
        return False

    if _adata is None:
        _adata = load_data('data')
    if _vectors is None:
        _vectors = get_all_vectors(_adata)
    if _index is None:
        _index = build_index(_vectors)
    return True


# ─── Mock 数据（B/C 模块不可用时使用）───────────────────────────────────
_MOCK_CELLS = {
    'cell_001': {'cell_type': 'Hepatocyte',    'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [1.23, -0.45, 0.67]},
    'cell_002': {'cell_type': 'Hepatocyte',    'disease': 'cirrhosis',   'AgeGroup': 'Senior',  'pca': [1.20, -0.40, 0.70]},
    'cell_003': {'cell_type': 'Kupffer Cell',  'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [2.10, 0.85, -0.33]},
    'cell_004': {'cell_type': 'HSC',           'disease': 'fibrosis',    'AgeGroup': 'Senior',  'pca': [0.80, -1.20, 1.10]},
    'cell_005': {'cell_type': 'Hepatocyte',    'disease': 'normal',      'AgeGroup': 'Young',   'pca': [1.25, -0.48, 0.65]},
    'cell_006': {'cell_type': 'Cholangiocyte', 'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [-0.55, 1.80, 0.20]},
    'cell_007': {'cell_type': 'Endothelial',   'disease': 'cirrhosis',   'AgeGroup': 'Senior',  'pca': [3.10, 0.15, 0.90]},
    'cell_008': {'cell_type': 'Hepatocyte',    'disease': 'steatosis',   'AgeGroup': 'Adult',   'pca': [1.18, -0.43, 0.72]},
    'cell_009': {'cell_type': 'Kupffer Cell',  'disease': 'fibrosis',    'AgeGroup': 'Senior',  'pca': [2.05, 0.90, -0.30]},
    'cell_010': {'cell_type': 'HSC',           'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [0.85, -1.15, 1.05]},
    'cell_011': {'cell_type': 'Hepatocyte',    'disease': 'cirrhosis',   'AgeGroup': 'Young',   'pca': [1.22, -0.42, 0.68]},
    'cell_012': {'cell_type': 'Endothelial',   'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [3.05, 0.12, 0.88]},
    'cell_013': {'cell_type': 'Hepatocyte',    'disease': 'normal',      'AgeGroup': 'Senior',  'pca': [1.26, -0.47, 0.64]},
    'cell_014': {'cell_type': 'Cholangiocyte', 'disease': 'fibrosis',    'AgeGroup': 'Senior',  'pca': [-0.50, 1.78, 0.22]},
    'cell_015': {'cell_type': 'Kupffer Cell',  'disease': 'normal',      'AgeGroup': 'Young',   'pca': [2.12, 0.82, -0.35]},
    'cell_016': {'cell_type': 'Hepatocyte',    'disease': 'steatosis',   'AgeGroup': 'Senior',  'pca': [1.19, -0.44, 0.69]},
    'cell_017': {'cell_type': 'HSC',           'disease': 'cirrhosis',   'AgeGroup': 'Adult',   'pca': [0.82, -1.18, 1.08]},
    'cell_018': {'cell_type': 'Endothelial',   'disease': 'normal',      'AgeGroup': 'Young',   'pca': [3.08, 0.14, 0.87]},
    'cell_019': {'cell_type': 'Hepatocyte',    'disease': 'fibrosis',    'AgeGroup': 'Adult',   'pca': [1.21, -0.41, 0.71]},
    'cell_020': {'cell_type': 'Cholangiocyte', 'disease': 'cirrhosis',   'AgeGroup': 'Young',   'pca': [-0.52, 1.82, 0.18]},
}


def _euclidean_distance(a, b):
    """计算两个向量的欧氏距离"""
    return float(np.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))


def _mock_search(query_cell_id: str, top_k: int):
    """使用 Mock 数据执行搜索"""
    if query_cell_id not in _MOCK_CELLS:
        return None, None

    query_cell = _MOCK_CELLS[query_cell_id]
    query_vec = query_cell['pca']

    distances = []
    for cid, info in _MOCK_CELLS.items():
        if cid == query_cell_id:
            continue
        dist = _euclidean_distance(query_vec, info['pca'])
        distances.append((cid, dist, info))

    distances.sort(key=lambda x: x[1])
    top_results = distances[:top_k]

    results = []
    for cid, dist, info in top_results:
        results.append({
            'id': cid,
            'distance': round(dist, 4),
            'cell_type': info['cell_type'],
            'disease': info['disease'],
            'pca': info['pca'],
        })

    return {
        'id': query_cell_id,
        'cell_type': query_cell['cell_type'],
        'pca': query_vec,
    }, results


# ─── 路由 ─────────────────────────────────────────────────────────────

@home_bp.route('/')
def index():
    """渲染搜索主页"""
    return render_template('index.html')


@home_bp.route('/api/cells')
def list_cells():
    """返回所有可查询的细胞 ID 列表（供前端自动补全）"""
    if _ensure_data_loaded():
        pass
    return jsonify(list(_MOCK_CELLS.keys()))


@home_bp.route('/api/cells/pca')
def list_cells_pca():
    """返回所有细胞的 PCA 坐标和元数据（供前端散点图可视化）

    响应格式：
        [{"id": "cell_001", "cell_type": "Hepatocyte", "disease": "normal",
          "AgeGroup": "Adult", "pca": [1.23, -0.45, 0.67]}, ...]
    """
    if _ensure_data_loaded():
        try:
            pass
        except Exception:
            pass

    cells = []
    for cid, info in _MOCK_CELLS.items():
        cells.append({
            'id': cid,
            'cell_type': info['cell_type'],
            'disease': info['disease'],
            'AgeGroup': info['AgeGroup'],
            'pca': info['pca'],
        })
    return jsonify(cells)


@home_bp.route('/api/search', methods=['POST'])
def api_search():
    """细胞相似性搜索 API"""
    t_start = time.time()

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': '请求体不能为空，请提供 JSON。'}), 400

    query_cell_id = data.get('query_cell_id')
    top_k = data.get('top_k', 10)

    if not query_cell_id:
        return jsonify({'status': 'error', 'message': '缺少 query_cell_id 字段。'}), 400
    if not isinstance(top_k, int) or top_k < 1:
        return jsonify({'status': 'error', 'message': 'top_k 必须是正整数。'}), 400

    # ── 尝试使用真实模块（B + C）────────────────────────────────────
    if _ensure_data_loaded():
        try:
            cell_info = get_cell_info(_adata, [query_cell_id])
            if query_cell_id not in cell_info:
                return jsonify({'status': 'error', 'message': f'未找到细胞 {query_cell_id}。'}), 404

            info = cell_info[query_cell_id]
            query_vector = info['X_pca']

            distances, indices = search(_index, query_vector, top_k + 1)

            result_indices = [int(i) for i in indices if _get_cell_id_by_index(_adata, int(i)) != query_cell_id][:top_k]
            result_info = get_cell_info_by_indices(_adata, result_indices)

            time_cost = (time.time() - t_start) * 1000

            results = []
            for i, idx in enumerate(result_indices):
                cell = result_info.get(idx, {})
                results.append({
                    'id': _get_cell_id_by_index(_adata, idx),
                    'distance': round(float(distances[i]), 4),
                    'cell_type': cell.get('cell_type', 'unknown'),
                    'disease': cell.get('disease', 'unknown'),
                    'pca': cell.get('X_pca', []),
                })

            return jsonify({
                'status': 'success',
                'time_cost_ms': round(time_cost, 2),
                'query_cell': {
                    'id': query_cell_id,
                    'cell_type': info.get('cell_type', 'unknown'),
                    'pca': query_vector,
                },
                'results': results,
            })
        except Exception:
            pass

    # ── 使用 Mock 数据 ────────────────────────────────────────────
    query_cell, results = _mock_search(query_cell_id, top_k)

    if query_cell is None:
        return jsonify({
            'status': 'error',
            'message': f'未找到细胞 {query_cell_id}。可用的细胞 ID: {list(_MOCK_CELLS.keys())}',
        }), 404

    time_cost = (time.time() - t_start) * 1000

    return jsonify({
        'status': 'success',
        'time_cost_ms': round(time_cost, 2),
        'query_cell': query_cell,
        'results': results,
    })


def _get_cell_id_by_index(adata, index: int) -> str:
    """通过行号获取细胞 ID"""
    try:
        return adata.obs_names[index]
    except Exception:
        return f'cell_{index:03d}'
