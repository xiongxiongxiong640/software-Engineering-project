"""D 模块：前端路由 + 搜索 API + PCA 可视化数据

依赖 B（apps.data_processor）:
    load_data(filepath) → adata
    get_cell_info(adata, cell_ids) → List[Dict]   (每个 Dict: id/cell_type/disease/AgeGroup/pca)
    get_all_vectors(adata) → np.ndarray
    get_cell_info_by_indices(adata, indices) → List[Dict]

依赖 C（apps.search_engine）:
    build_index(vectors) → index
    search(index, query_vector, top_k) → (distances, indices)

请求格式:  {"query_cell_id": "cell_001", "top_k": 10}
响应格式:  {"status": "success", "time_cost_ms": 12.5, "query_cell": {...}, "results": [...]}
"""
import os
import time
import numpy as np
from flask import render_template, request, jsonify

# 使用相对导入避免循环依赖
from . import home_bp
from apps.services.global_state import global_app_state


# ─── 尝试导入 B / C 模块 ──────────────────────────────────────────────
try:
    from apps.data_processor import get_cell_info, get_all_vectors, get_cell_info_by_indices
    _B_READY = True
except ImportError:
    _B_READY = False

try:
    from apps.search_engine import search
    _C_READY = True
except ImportError:
    _C_READY = False

# ─── 全局缓存 ─────────────────────────────────────────────────────────
_adata = None
_index = None
_vectors = None


def _ensure_ready():
    """确保数据已加载（从全局状态获取）"""
    global _adata, _index, _vectors
    
    # 优先使用全局状态中的数据（已由 apps.__init__ 预加载）
    if global_app_state.is_loaded and global_app_state.adata is not None:
        _adata = global_app_state.adata
        _index = global_app_state.search_index
        _vectors = get_all_vectors(_adata) if _B_READY else None
        return _B_READY and _adata is not None
    
    # 降级方案：如果全局状态未就绪，则返回 False（使用 Mock）
    return False


# ─── Mock 数据 ────────────────────────────────────────────────────────
_MOCK_CELLS = {
    'cell_001': {'cell_type': 'Hepatocyte',    'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [1.23, -0.45]},
    'cell_002': {'cell_type': 'Hepatocyte',    'disease': 'cirrhosis',   'AgeGroup': 'Senior',  'pca': [1.20, -0.40]},
    'cell_003': {'cell_type': 'Kupffer Cell',  'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [2.10, 0.85]},
    'cell_004': {'cell_type': 'HSC',           'disease': 'fibrosis',    'AgeGroup': 'Senior',  'pca': [0.80, -1.20]},
    'cell_005': {'cell_type': 'Hepatocyte',    'disease': 'normal',      'AgeGroup': 'Young',   'pca': [1.25, -0.48]},
    'cell_006': {'cell_type': 'Cholangiocyte', 'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [-0.55, 1.80]},
    'cell_007': {'cell_type': 'Endothelial',   'disease': 'cirrhosis',   'AgeGroup': 'Senior',  'pca': [3.10, 0.15]},
    'cell_008': {'cell_type': 'Hepatocyte',    'disease': 'steatosis',   'AgeGroup': 'Adult',   'pca': [1.18, -0.43]},
    'cell_009': {'cell_type': 'Kupffer Cell',  'disease': 'fibrosis',    'AgeGroup': 'Senior',  'pca': [2.05, 0.90]},
    'cell_010': {'cell_type': 'HSC',           'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [0.85, -1.15]},
    'cell_011': {'cell_type': 'Hepatocyte',    'disease': 'cirrhosis',   'AgeGroup': 'Young',   'pca': [1.22, -0.42]},
    'cell_012': {'cell_type': 'Endothelial',   'disease': 'normal',      'AgeGroup': 'Adult',   'pca': [3.05, 0.12]},
    'cell_013': {'cell_type': 'Hepatocyte',    'disease': 'normal',      'AgeGroup': 'Senior',  'pca': [1.26, -0.47]},
    'cell_014': {'cell_type': 'Cholangiocyte', 'disease': 'fibrosis',    'AgeGroup': 'Senior',  'pca': [-0.50, 1.78]},
    'cell_015': {'cell_type': 'Kupffer Cell',  'disease': 'normal',      'AgeGroup': 'Young',   'pca': [2.12, 0.82]},
    'cell_016': {'cell_type': 'Hepatocyte',    'disease': 'steatosis',   'AgeGroup': 'Senior',  'pca': [1.19, -0.44]},
    'cell_017': {'cell_type': 'HSC',           'disease': 'cirrhosis',   'AgeGroup': 'Adult',   'pca': [0.82, -1.18]},
    'cell_018': {'cell_type': 'Endothelial',   'disease': 'normal',      'AgeGroup': 'Young',   'pca': [3.08, 0.14]},
    'cell_019': {'cell_type': 'Hepatocyte',    'disease': 'fibrosis',    'AgeGroup': 'Adult',   'pca': [1.21, -0.41]},
    'cell_020': {'cell_type': 'Cholangiocyte', 'disease': 'cirrhosis',   'AgeGroup': 'Young',   'pca': [-0.52, 1.82]},
}


def _euclidean(a, b):
    return float(np.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))


def _mock_search(cell_id: str, top_k: int):
    """Mock 搜索：暴力欧氏距离"""
    if cell_id not in _MOCK_CELLS:
        return None, None
    qv = _MOCK_CELLS[cell_id]['pca']
    scored = []
    for cid, info in _MOCK_CELLS.items():
        if cid == cell_id:
            continue
        scored.append((cid, _euclidean(qv, info['pca']), info))
    scored.sort(key=lambda x: x[1])
    return {
        'id': cell_id, 'cell_type': _MOCK_CELLS[cell_id]['cell_type'],
        'pca': qv,
    }, [{
        'id': cid, 'distance': round(d, 4),
        'cell_type': inf['cell_type'], 'disease': inf['disease'],
        'pca': inf['pca'],
    } for cid, d, inf in scored[:top_k]]


# ══════════════════════════════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════════════════════════════

@home_bp.route('/')
def index():
    return render_template('index.html')


@home_bp.route('/api/cells')
def list_cells():
    """GET /api/cells — 所有细胞 ID（前端自动补全）"""
    if _ensure_ready():
        try:
            ids = [str(n) for n in _adata.obs_names]
            return jsonify(ids)
        except Exception:
            pass
    return jsonify(list(_MOCK_CELLS.keys()))


@home_bp.route('/api/cells/pca')
def list_cells_pca():
    """GET /api/cells/pca — PCA 坐标 + 元数据（ECharts 散点图）

    优先从 B 模块获取真实数据，不可用时回退 Mock。
    返回: [{"id","cell_type","disease","AgeGroup","pca":[...]}, ...]
    """
    if _ensure_ready():
        try:
            vectors = get_all_vectors(_adata)
            n = _adata.n_obs

            # 大数据集采样（最多 5000 点）
            if n > 5000:
                import random
                rng = random.Random(42)
                idxs = sorted(rng.sample(range(n), 5000))
            else:
                idxs = range(n)

            cells = []
            for i in idxs:
                info = {
                    'id': str(_adata.obs_names[i]),
                    'cell_type': _safe_obs(_adata, i, 'cell_type'),
                    'disease': _safe_obs(_adata, i, 'disease'),
                    'AgeGroup': _safe_obs(_adata, i, 'AgeGroup'),
                    'pca': [float(vectors[i, 0]), float(vectors[i, 1])] if vectors.shape[1] >= 2 else [0.0, 0.0],
                }
                cells.append(info)
            return jsonify(cells)
        except Exception:
            pass

    # Mock
    return jsonify([
        {'id': cid, 'cell_type': i['cell_type'], 'disease': i['disease'],
         'AgeGroup': i['AgeGroup'], 'pca': i['pca']}
        for cid, i in _MOCK_CELLS.items()
    ])


@home_bp.route('/api/search', methods=['POST'])
def api_search():
    """POST /api/search — 细胞相似性搜索

    优先由 C 分支的 api 蓝图处理（apps/api/__init__.py 先注册）。
    本路由在 api 蓝图不可用时作为兜底。
    """
    t_start = time.time()
    body = request.get_json(silent=True) or {}
    cell_id = body.get('query_cell_id')
    top_k = body.get('top_k', 10)

    if not cell_id:
        return jsonify({'status': 'error', 'message': '缺少 query_cell_id'}), 400
    if not isinstance(top_k, int) or top_k < 1:
        return jsonify({'status': 'error', 'message': 'top_k 必须是正整数'}), 400

    # ── 真实数据路径（B + C）─────────────────────────────────────────
    if _ensure_ready():
        try:
            # B: 查查询细胞
            info_list = get_cell_info(_adata, [cell_id])
            if not info_list or info_list[0] is None:
                return jsonify({'status': 'error', 'message': f'未找到细胞 {cell_id}'}), 404
            qinfo = info_list[0]

            # C: 取 PCA + 搜索
            all_vecs = get_all_vectors(_adata)
            cell_idx = _find_idx(_adata, cell_id)
            query_vec = all_vecs[cell_idx]
            distances, indices = search(_index, query_vec, top_k + 1)

            # B: 获取结果细胞信息
            ridxs = [int(i) for i in indices if int(i) != cell_idx][:top_k]
            rinfo_list = get_cell_info_by_indices(_adata, ridxs)

            elapsed = (time.time() - t_start) * 1000
            results = []
            for j, idx in enumerate(ridxs):
                ri = rinfo_list[j] if rinfo_list[j] is not None else {}
                results.append({
                    'id': ri.get('id', f'cell_{idx}'),
                    'distance': round(float(distances[j]), 4),
                    'cell_type': ri.get('cell_type', 'unknown'),
                    'disease': ri.get('disease', 'unknown'),
                    'pca': ri.get('pca', []),
                })

            return jsonify({
                'status': 'success',
                'time_cost_ms': round(elapsed, 2),
                'query_cell': {
                    'id': qinfo['id'],
                    'cell_type': qinfo.get('cell_type', 'unknown'),
                    'pca': qinfo.get('pca', []),
                },
                'results': results,
            })
        except Exception:
            pass

    # ── Mock 兜底 ───────────────────────────────────────────────────
    qc, results = _mock_search(cell_id, top_k)
    if qc is None:
        return jsonify({
            'status': 'error',
            'message': f'未找到细胞 {cell_id}。可用: {list(_MOCK_CELLS.keys())}',
        }), 404

    return jsonify({
        'status': 'success',
        'time_cost_ms': round((time.time() - t_start) * 1000, 2),
        'query_cell': qc,
        'results': results,
    })


# ─── 辅助 ──────────────────────────────────────────────────────────

def _find_idx(adata, cell_id: str) -> int:
    """细胞 ID → 行号"""
    obs = list(adata.obs_names)
    try:
        return obs.index(cell_id)
    except ValueError:
        for i, n in enumerate(obs):
            if cell_id in str(n):
                return i
        raise KeyError(f'细胞 ID 不存在: {cell_id}')


def _safe_obs(adata, idx: int, col: str) -> str:
    """安全读取 obs 列，避免 NA 报错"""
    if col not in adata.obs.columns:
        return 'unknown'
    val = adata.obs[col].iloc[idx]
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 'unknown'
    except Exception:
        pass
    return str(val)
