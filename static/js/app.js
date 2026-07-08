/**
 * 细胞相似性搜索 —— PCA 可视化 + 交互查询
 *
 * 请求格式：{"query_cell_id": "cell_001", "top_k": 10, "filter_cell_type": "Hepatocyte"}
 * 响应格式：{"status": "success", "time_cost_ms": 12.5, "query_cell": {...}, "results": [...]}
 */

// ─── 细胞类型颜色映射 ─────────────────────────────────────────
var CELL_TYPE_COLORS = {
    'Hepatocyte':    '#5470c6',
    'Kupffer Cell':  '#91cc75',
    'HSC':           '#fac858',
    'Cholangiocyte': '#ee6666',
    'Endothelial':   '#73c0de',
};
var FALLBACK_COLOR = '#a0aec0';

// ─── 全局状态 ────────────────────────────────────────────────
var allCellsData = [];
var allCellIds = [];
var chart = null;
var currentSearchResult = null;
var currentQueryCellId = null;
var abortController = null;

document.addEventListener('DOMContentLoaded', function () {
    var searchForm      = document.getElementById('search-form');
    var cellIdInput     = document.getElementById('query-cell-id');
    var topKInput       = document.getElementById('top-k');
    var filterCellType  = document.getElementById('filter-cell-type');
    var searchBtn       = document.getElementById('search-btn');
    var suggestionsList = document.getElementById('suggestions');
    var resultsSection  = document.getElementById('results-section');
    var emptyState      = document.getElementById('empty-state');
    var searchStatus    = document.getElementById('search-status');
    var queryCellInfo   = document.getElementById('query-cell-info');
    var resultsTbody    = document.getElementById('results-tbody');
    var errorToast      = document.getElementById('error-toast');
    var errorMessage    = document.getElementById('error-message');
    var resetChartBtn   = document.getElementById('reset-chart-btn');
    var selectedDisplay = document.getElementById('selected-cell-display');
    var selectedCellId  = document.getElementById('selected-cell-id');
    var selectedCellType = document.getElementById('selected-cell-badge');
    var legendContainer = document.getElementById('cell-type-legend');
    var chartDom        = document.getElementById('pca-chart');

    // 向量搜索相关
    var vectorSearchForm = document.getElementById('vector-search-form');
    var vectorInput      = document.getElementById('vector-input');
    var vectorTopK       = document.getElementById('vector-top-k');
    var vectorSearchBtn  = document.getElementById('vector-search-btn');

    // 高级选项
    var indexStatusBtn   = document.getElementById('index-status-btn');
    var benchmarkBtn     = document.getElementById('benchmark-btn');
    var indexRebuildBtn  = document.getElementById('index-rebuild-btn');
    var advancedResult   = document.getElementById('advanced-result');

    ensureErrorToast();

    initChart();
    fetchCellData();
    initCollapsiblePanels();

    // ─── 搜索表单 ──────────────────────────────────────────
    searchForm.addEventListener('submit', function (e) {
        e.preventDefault();
        performSearch(cellIdInput.value.trim());
    });

    // ─── 自动补全 ──────────────────────────────────────────
    cellIdInput.addEventListener('input', function () {
        var value = this.value.toLowerCase().trim();
        suggestionsList.innerHTML = '';
        if (!value) { suggestionsList.classList.add('hidden'); return; }

        var matches = allCellIds.filter(function (id) {
            return id.toLowerCase().indexOf(value) !== -1;
        }).slice(0, 15);
        if (matches.length === 0) { suggestionsList.classList.add('hidden'); return; }

        matches.forEach(function (id) {
            var li = document.createElement('li');
            li.textContent = id;
            li.addEventListener('click', function () {
                cellIdInput.value = id;
                suggestionsList.classList.add('hidden');
                performSearch(id);
            });
            suggestionsList.appendChild(li);
        });
        suggestionsList.classList.remove('hidden');
    });

    document.addEventListener('click', function (e) {
        if (e.target !== cellIdInput && e.target !== suggestionsList) {
            suggestionsList.classList.add('hidden');
        }
    });
    cellIdInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') suggestionsList.classList.add('hidden');
    });

    // ─── 向量搜索 ──────────────────────────────────────────
    if (vectorSearchForm) {
        vectorSearchForm.addEventListener('submit', function (e) {
            e.preventDefault();
            performVectorSearch();
        });
    }

    // ─── 高级选项按钮 ──────────────────────────────────────
    if (indexStatusBtn) {
        indexStatusBtn.addEventListener('click', fetchIndexStatus);
    }
    if (benchmarkBtn) {
        benchmarkBtn.addEventListener('click', fetchBenchmark);
    }
    if (indexRebuildBtn) {
        indexRebuildBtn.addEventListener('click', fetchIndexRebuild);
    }

    resetChartBtn.addEventListener('click', resetView);
    window.addEventListener('resize', function () { if (chart) chart.resize(); });

    // ─── 获取细胞数据 ─────────────────────────────────────
    function fetchCellData() {
        fetch('/api/cells')
            .then(function (r) { return r.ok ? r.json() : []; })
            .then(function (ids) { allCellIds = ids; })
            .catch(function () {});

        fetch('/api/cells/pca')
            .then(function (r) { return r.ok ? r.json() : []; })
            .then(function (cells) {
                allCellsData = cells;
                renderChart(cells);
                buildLegend(cells);
                populateCellTypeFilter(cells);
            })
            .catch(function (err) { console.error('获取 PCA 数据失败:', err); });
    }

    // ─── 初始化 ECharts ─────────────────────────────────────
    function initChart() {
        chart = echarts.init(chartDom);
    }

    // ─── 渲染散点图 ─────────────────────────────────────────
    function renderChart(cells, highlightData) {
        if (!chart) return;

        var queryId = highlightData ? highlightData.queryId : null;
        var resultIds = highlightData ? highlightData.resultIds : {};

        var seriesData = cells.map(function (cell) {
            var isQuery = (queryId === cell.id);
            var isResult = !isQuery && resultIds[cell.id];
            var color, size, symbol, opacity, borderColor, borderWidth, shadowBlur, shadowColor;

            if (isQuery) {
                color = '#dc2626'; size = 20; symbol = 'diamond'; opacity = 1;
                borderColor = '#991b1b'; borderWidth = 2; shadowBlur = 14;
                shadowColor = 'rgba(220,38,38,0.6)';
            } else if (isResult) {
                color = '#f97316'; size = 13; symbol = 'circle'; opacity = 0.9;
                borderColor = '#ea580c'; borderWidth = 1.5; shadowBlur = 8;
                shadowColor = 'rgba(249,115,22,0.5)';
            } else if (queryId) {
                color = '#cbd5e1'; size = 6; symbol = 'circle'; opacity = 0.28;
                borderColor = 'transparent'; borderWidth = 0; shadowBlur = 0;
                shadowColor = 'transparent';
            } else {
                color = CELL_TYPE_COLORS[cell.cell_type] || FALLBACK_COLOR;
                size = 10; symbol = 'circle'; opacity = 0.82;
                borderColor = 'transparent'; borderWidth = 0; shadowBlur = 0;
                shadowColor = 'transparent';
            }

            return {
                value: [cell.pca[0], cell.pca[1]],
                symbolSize: size, symbol: symbol,
                itemStyle: { color: color, opacity: opacity, borderColor: borderColor,
                    borderWidth: borderWidth, shadowBlur: shadowBlur, shadowColor: shadowColor },
                cellId: cell.id, cellType: cell.cell_type,
                disease: cell.disease, ageGroup: cell.AgeGroup,
            };
        });

        var option = {
            tooltip: {
                trigger: 'item',
                backgroundColor: 'rgba(30,41,59,0.92)',
                borderColor: '#334155',
                textStyle: { color: '#f1f5f9', fontSize: 13 },
                formatter: function (params) {
                    var d = params.data;
                    return [
                        '<strong style="font-size:14px">' + escapeHtml(d.cellId) + '</strong>',
                        '细胞类型: <b>' + escapeHtml(d.cellType) + '</b>',
                        '疾病状态: ' + escapeHtml(d.disease),
                        '年龄段: ' + escapeHtml(d.ageGroup),
                        'PC1: ' + d.value[0].toFixed(4),
                        'PC2: ' + d.value[1].toFixed(4),
                    ].join('<br/>');
                },
                extraCssText: 'border-radius:8px;padding:10px 14px;line-height:1.7;',
            },
            grid: { left: 60, right: 40, top: 30, bottom: 50 },
            xAxis: {
                name: 'PC1', nameLocation: 'center', nameGap: 32,
                nameTextStyle: { fontSize: 13, fontWeight: 600, color: '#64748b' },
                axisLine: { lineStyle: { color: '#cbd5e1' } },
                axisTick: { show: false },
                splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
            },
            yAxis: {
                name: 'PC2', nameLocation: 'center', nameGap: 40,
                nameTextStyle: { fontSize: 13, fontWeight: 600, color: '#64748b' },
                axisLine: { lineStyle: { color: '#cbd5e1' } },
                axisTick: { show: false },
                splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
            },
            dataZoom: [
                { type: 'inside', xAxisIndex: 0 },
                { type: 'inside', yAxisIndex: 0 },
            ],
            series: [{
                type: 'scatter', data: seriesData,
                emphasis: { scale: 1.6, focus: 'self',
                    itemStyle: { shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.3)' } },
                animation: true, animationDuration: 400, animationEasing: 'cubicOut',
            }],
        };

        chart.setOption(option, true);

        chart.off('click');
        chart.on('click', function (params) {
            if (params.data && params.data.cellId) {
                cellIdInput.value = params.data.cellId;
                performSearch(params.data.cellId);
            }
        });
    }

    // ─── 构建细胞类型图例 ────────────────────────────────────
    function buildLegend(cells) {
        var typeCount = {};
        cells.forEach(function (c) {
            typeCount[c.cell_type] = (typeCount[c.cell_type] || 0) + 1;
        });
        legendContainer.innerHTML = '';
        Object.keys(typeCount).sort().forEach(function (type) {
            var color = CELL_TYPE_COLORS[type] || FALLBACK_COLOR;
            var item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML =
                '<span class="legend-color" style="background:' + color + '"></span>' +
                '<span>' + escapeHtml(type) + '</span>' +
                '<span class="legend-count">' + typeCount[type] + '</span>';
            legendContainer.appendChild(item);
        });
    }

    // ─── 填充细胞类型筛选下拉框 ──────────────────────────────
    function populateCellTypeFilter(cells) {
        if (!filterCellType) return;
        var types = {};
        cells.forEach(function (c) {
            if (c.cell_type) types[c.cell_type] = true;
        });
        // 保留"全部类型"选项，追加其他类型
        Object.keys(types).sort().forEach(function (type) {
            var option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            filterCellType.appendChild(option);
        });
    }

    // ─── 执行搜索 ───────────────────────────────────────────
    function performSearch(queryCellId) {
        if (!queryCellId) { showErrorToast('请输入细胞 ID 或点击图中细胞。'); return; }
        var topK = parseInt(topKInput.value, 10);
        if (isNaN(topK) || topK < 1) { showErrorToast('top_k 必须是正整数。'); return; }

        if (abortController) abortController.abort();
        abortController = new AbortController();
        setSearchBtnLoading(true);
        cellIdInput.value = queryCellId;

        var body = { query_cell_id: queryCellId, top_k: topK };
        var filterType = filterCellType ? filterCellType.value : '';
        if (filterType) {
            body.filter_cell_type = filterType;
        }

        fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: abortController.signal,
        })
        .then(function (r) { return r.json().then(function (data) { return {ok: r.ok, data: data}; }); })
        .then(function (result) {
            if (!result.ok || result.data.status === 'error') {
                showErrorToast(result.data.message || '搜索失败。');
                setSearchBtnLoading(false); return;
            }
            currentSearchResult = result.data;
            currentQueryCellId = queryCellId;
            onSearchSuccess(result.data);
            dismissError();
        })
        .catch(function (err) {
            if (err.name === 'AbortError') return;
            showErrorToast('网络请求失败: ' + err.message);
        })
        .finally(function () { setSearchBtnLoading(false); });
    }

    // ─── 向量搜索 ───────────────────────────────────────────
    function performVectorSearch() {
        if (!vectorInput) return;
        var raw = vectorInput.value.trim();
        if (!raw) { showErrorToast('请输入 PCA 向量。'); return; }

        var parts = raw.split(',').map(function (s) { return parseFloat(s.trim()); });
        var nanIdx = parts.findIndex(function (v) { return isNaN(v); });
        if (nanIdx !== -1) {
            showErrorToast('向量第 ' + (nanIdx + 1) + ' 个值不是有效数字。');
            return;
        }

        var topK = parseInt(vectorTopK.value, 10) || 10;
        if (abortController) abortController.abort();
        abortController = new AbortController();
        setVectorBtnLoading(true);

        fetch('/api/search/by-vector', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_vector: parts, top_k: topK }),
            signal: abortController.signal,
        })
        .then(function (r) { return r.json().then(function (data) { return {ok: r.ok, data: data}; }); })
        .then(function (result) {
            if (!result.ok || result.data.status === 'error') {
                showErrorToast(result.data.message || '向量搜索失败。');
                setVectorBtnLoading(false); return;
            }
            currentSearchResult = result.data;
            currentQueryCellId = null;

            // 标记结果 ID 用于高亮
            var resultIds = {};
            result.data.results.forEach(function (r) { resultIds[r.id] = true; });
            renderChart(allCellsData, { queryId: null, resultIds: resultIds });
            renderVectorResults(result.data);
            dismissError();
        })
        .catch(function (err) {
            if (err.name === 'AbortError') return;
            showErrorToast('网络请求失败: ' + err.message);
        })
        .finally(function () { setVectorBtnLoading(false); });
    }

    // ─── 渲染向量搜索结果 ───────────────────────────────────
    function renderVectorResults(data) {
        emptyState.classList.add('hidden');
        resultsSection.classList.remove('hidden');
        resetChartBtn.classList.remove('hidden');

        searchStatus.className = 'search-status success';
        searchStatus.innerHTML =
            '✅ 向量搜索完成 · 耗时 <strong>' + data.time_cost_ms + ' ms</strong> · ' +
            '返回 <strong>' + data.results.length + '</strong> 条相似细胞';

        queryCellInfo.innerHTML =
            '<div class="info-item"><span class="info-label">查询方式</span>' +
            '<span class="info-value">向量查询 (' + (data.query_cell.pca ? data.query_cell.pca.length : '?') + ' 维)</span></div>' +
            '<div class="info-item"><span class="info-label">细胞类型</span>' +
            '<span class="info-value">向量查询（无特定细胞类型）</span></div>';

        renderResultsTable(data.results);
    }

    // ─── 搜索成功回调 ───────────────────────────────────────
    function onSearchSuccess(data) {
        var resultIds = {};
        data.results.forEach(function (r) { resultIds[r.id] = true; });

        renderChart(allCellsData, { queryId: data.query_cell.id, resultIds: resultIds });

        if (selectedDisplay) selectedDisplay.classList.remove('hidden');
        if (selectedCellId) selectedCellId.textContent = data.query_cell.id;
        if (selectedCellType) selectedCellType.textContent = data.query_cell.cell_type || '—';

        renderResults(data);
        resetChartBtn.classList.remove('hidden');
    }

    // ─── 渲染结果详情 ───────────────────────────────────────
    function renderResults(data) {
        emptyState.classList.add('hidden');
        resultsSection.classList.remove('hidden');

        var filterInfo = '';
        if (filterCellType && filterCellType.value) {
            filterInfo = ' · 筛选类型: <strong>' + escapeHtml(filterCellType.value) + '</strong>';
        }
        searchStatus.className = 'search-status success';
        searchStatus.innerHTML =
            '✅ 搜索完成 · 耗时 <strong>' + data.time_cost_ms + ' ms</strong> · ' +
            '返回 <strong>' + data.results.length + '</strong> 条相似细胞' + filterInfo;

        var qc = data.query_cell;
        var pcaHtml = '';
        if (qc.pca && qc.pca.length > 0) {
            pcaHtml = qc.pca.map(function (v) {
                return '<span class="pca-badge">' + v.toFixed(4) + '</span>';
            }).join(' ');
        }

        queryCellInfo.innerHTML =
            '<div class="info-item"><span class="info-label">细胞 ID</span>' +
            '<span class="info-value">' + escapeHtml(qc.id) + '</span></div>' +
            '<div class="info-item"><span class="info-label">细胞类型</span>' +
            '<span class="info-value">' + escapeHtml(qc.cell_type || '—') + '</span></div>' +
            '<div class="info-item" style="grid-column: 1 / -1;">' +
            '<span class="info-label">PCA 坐标</span>' +
            '<span class="info-value">' + (pcaHtml || '—') + '</span></div>';

        renderResultsTable(data.results);
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // ─── 渲染结果表格 ───────────────────────────────────────
    function renderResultsTable(results) {
        resultsTbody.innerHTML = '';
        if (results.length === 0) {
            resultsTbody.innerHTML =
                '<tr><td colspan="5" style="text-align:center;padding:24px;color:#94a3b8;">未找到相似细胞' +
                (filterCellType && filterCellType.value ? '（请尝试放宽筛选条件）' : '') + '</td></tr>';
        } else {
            results.forEach(function (cell, index) {
                var row = document.createElement('tr');
                row.innerHTML =
                    '<td class="rank-col">' + (index + 1) + '</td>' +
                    '<td><strong>' + escapeHtml(cell.id) + '</strong></td>' +
                    '<td class="distance-col">' + (cell.distance != null ? cell.distance.toFixed(4) : '—') + '</td>' +
                    '<td>' + escapeHtml(cell.cell_type || '—') + '</td>' +
                    '<td>' + escapeHtml(cell.disease || '—') + '</td>';
                row.style.cursor = 'pointer';
                row.addEventListener('click', function () {
                    cellIdInput.value = cell.id;
                    performSearch(cell.id);
                });
                resultsTbody.appendChild(row);
            });
        }
    }

    // ─── 查看索引状态 ──────────────────────────────────────
    function fetchIndexStatus() {
        showAdvancedLoading('正在查询索引状态...');
        fetch('/api/index/status')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'success' && data.index) {
                    var idx = data.index;
                    var html = '<div class="advanced-info">';
                    html += '<p><strong>索引状态:</strong> <span class="badge badge-success">' + escapeHtml(idx.status) + '</span></p>';
                    if (idx.type) html += '<p><strong>索引类型:</strong> ' + escapeHtml(idx.type) + '</p>';
                    if (idx.ntotal != null) html += '<p><strong>向量总数:</strong> ' + idx.ntotal + '</p>';
                    if (idx.dimension != null) html += '<p><strong>向量维度:</strong> ' + idx.dimension + '</p>';
                    if (idx.nprobe != null) html += '<p><strong>nprobe:</strong> ' + idx.nprobe + '</p>';
                    html += '</div>';
                    showAdvancedResult(html);
                } else {
                    showAdvancedResult('<p class="text-warning">' + escapeHtml(data.index ? data.index.message : '无法获取索引状态') + '</p>');
                }
            })
            .catch(function (err) {
                showAdvancedResult('<p class="text-error">请求失败: ' + escapeHtml(err.message) + '</p>');
            });
    }

    // ─── 性能评估 ──────────────────────────────────────────
    function fetchBenchmark() {
        showAdvancedLoading('正在进行性能评估...');
        fetch('/api/benchmark?top_k=10&n_queries=50')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'success' && data.benchmark) {
                    var bm = data.benchmark;
                    var html = '<div class="advanced-info">';
                    html += '<h5>📊 性能评估结果</h5>';
                    html += '<p><strong>平均耗时:</strong> ' + bm.avg_time_ms + ' ms</p>';
                    html += '<p><strong>P50 耗时:</strong> ' + bm.p50_ms + ' ms</p>';
                    html += '<p><strong>P99 耗时:</strong> ' + bm.p99_ms + ' ms</p>';
                    html += '<p><strong>QPS:</strong> ' + (bm.qps != null ? bm.qps : '—') + '</p>';
                    html += '<p><strong>测试次数:</strong> ' + bm.n_runs + ' (top_k=' + bm.top_k + ')</p>';
                    html += '</div>';
                    showAdvancedResult(html);
                } else {
                    showAdvancedResult('<p class="text-error">' + escapeHtml(data.message || '评估失败') + '</p>');
                }
            })
            .catch(function (err) {
                showAdvancedResult('<p class="text-error">请求失败: ' + escapeHtml(err.message) + '</p>');
            });
    }

    // ─── 重建索引 ──────────────────────────────────────────
    function fetchIndexRebuild() {
        showAdvancedLoading('正在重建索引，请稍候...');
        fetch('/api/index/rebuild', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'success') {
                    var html = '<div class="advanced-info">';
                    html += '<p><span class="badge badge-success">✅ 索引重建成功</span></p>';
                    html += '<p><strong>耗时:</strong> ' + data.time_cost_ms + ' ms</p>';
                    if (data.index && data.index.ntotal != null) {
                        html += '<p><strong>向量总数:</strong> ' + data.index.ntotal + '</p>';
                    }
                    html += '</div>';
                    showAdvancedResult(html);
                    if (typeof AuthUI !== 'undefined') AuthUI.showToast('索引重建成功！', 'success');
                } else {
                    showAdvancedResult('<p class="text-error">' + escapeHtml(data.message || '重建失败') + '</p>');
                }
            })
            .catch(function (err) {
                showAdvancedResult('<p class="text-error">请求失败: ' + escapeHtml(err.message) + '</p>');
            });
    }

    // ─── 高级选项面板辅助 ──────────────────────────────────
    function showAdvancedLoading(msg) {
        if (advancedResult) {
            advancedResult.classList.remove('hidden');
            advancedResult.innerHTML = '<p class="text-muted">⏳ ' + escapeHtml(msg) + '</p>';
        }
    }

    function showAdvancedResult(html) {
        if (advancedResult) {
            advancedResult.classList.remove('hidden');
            advancedResult.innerHTML = html;
        }
    }

    // ─── 折叠面板 ──────────────────────────────────────────
    function initCollapsiblePanels() {
        var panels = [
            { toggle: 'vector-search-toggle', panel: 'vector-search-panel' },
            { toggle: 'advanced-toggle', panel: 'advanced-panel' },
        ];
        panels.forEach(function (p) {
            var toggle = document.getElementById(p.toggle);
            var panel = document.getElementById(p.panel);
            if (!toggle || !panel) return;
            toggle.addEventListener('click', function () {
                var isHidden = panel.classList.contains('hidden');
                if (isHidden) {
                    panel.classList.remove('hidden');
                    toggle.classList.add('collapsed-open');
                } else {
                    panel.classList.add('hidden');
                    toggle.classList.remove('collapsed-open');
                }
            });
        });
    }

    // ─── 重置视图 ───────────────────────────────────────────
    function resetView() {
        currentSearchResult = null;
        currentQueryCellId = null;
        cellIdInput.value = '';
        selectedDisplay.classList.add('hidden');
        resultsSection.classList.add('hidden');
        emptyState.classList.remove('hidden');
        resetChartBtn.classList.add('hidden');
        renderChart(allCellsData);
    }

    function setSearchBtnLoading(isLoading) {
        var btnText = searchBtn.querySelector('.btn-text');
        var btnLoading = searchBtn.querySelector('.btn-loading');
        if (isLoading) {
            searchBtn.disabled = true;
            if (btnText) btnText.classList.add('hidden');
            if (btnLoading) btnLoading.classList.remove('hidden');
        } else {
            searchBtn.disabled = false;
            if (btnText) btnText.classList.remove('hidden');
            if (btnLoading) btnLoading.classList.add('hidden');
        }
    }

    function setVectorBtnLoading(isLoading) {
        if (!vectorSearchBtn) return;
        var btnText = vectorSearchBtn.querySelector('.btn-text');
        var btnLoading = vectorSearchBtn.querySelector('.btn-loading');
        if (isLoading) {
            vectorSearchBtn.disabled = true;
            if (btnText) btnText.classList.add('hidden');
            if (btnLoading) btnLoading.classList.remove('hidden');
        } else {
            vectorSearchBtn.disabled = false;
            if (btnText) btnText.classList.remove('hidden');
            if (btnLoading) btnLoading.classList.add('hidden');
        }
    }

    function showErrorToast(message) {
        ensureErrorToast();
        errorMessage.textContent = message;
        errorToast.classList.remove('hidden');
        clearTimeout(errorToast._timeout);
        errorToast._timeout = setTimeout(dismissError, 5000);
    }

    window.dismissError = function () {
        if (!errorToast) return;
        errorToast.classList.add('hidden');
        clearTimeout(errorToast._timeout);
    };

    function ensureErrorToast() {
        if (!errorToast) {
            errorToast = document.createElement('div');
            errorToast.id = 'error-toast';
            errorToast.className = 'toast toast-error hidden';
            document.body.appendChild(errorToast);
        }

        if (!errorMessage) {
            errorMessage = document.createElement('span');
            errorMessage.id = 'error-message';
            errorToast.appendChild(errorMessage);
        }

        if (!errorToast.querySelector('.toast-close')) {
            var closeBtn = document.createElement('button');
            closeBtn.className = 'toast-close';
            closeBtn.type = 'button';
            closeBtn.textContent = 'x';
            closeBtn.addEventListener('click', window.dismissError);
            errorToast.appendChild(closeBtn);
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }
});
