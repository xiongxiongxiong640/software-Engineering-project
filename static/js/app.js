/**
 * 细胞相似性搜索 —— PCA 可视化 + 交互查询
 *
 * 请求格式：{"query_cell_id": "cell_001", "top_k": 10}
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

    // 防御性编程：检查必需的元素
    if (!chartDom || !errorMessage || !errorToast) {
        console.error('[错误] HTML 缺少必需的元素，应用无法启动');
        return;
    }

    initChart();
    fetchCellData();

    if (searchForm) {
        searchForm.addEventListener('submit', function (e) {
            e.preventDefault();
            if (cellIdInput) {
                performSearch(cellIdInput.value.trim());
            }
        });
    }

    if (cellIdInput) {
        cellIdInput.addEventListener('input', function () {
            if (!suggestionsList) return;
            var value = this.value.toLowerCase().trim();
            suggestionsList.innerHTML = '';
            if (!value) { suggestionsList.classList.add('hidden'); return; }

            var matches = allCellIds.filter(function (id) {
                return id.toLowerCase().indexOf(value) !== -1;
            });
            if (matches.length === 0) { suggestionsList.classList.add('hidden'); return; }

            matches.forEach(function (id) {
                var li = document.createElement('li');
                li.textContent = id;
                li.addEventListener('click', function () {
                    if (cellIdInput) cellIdInput.value = id;
                    if (suggestionsList) suggestionsList.classList.add('hidden');
                    performSearch(id);
                });
                suggestionsList.appendChild(li);
            });
            suggestionsList.classList.remove('hidden');
        });

        cellIdInput.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && suggestionsList) {
                suggestionsList.classList.add('hidden');
            }
        });
    }

    document.addEventListener('click', function (e) {
        if (suggestionsList && e.target !== cellIdInput && e.target !== suggestionsList) {
            suggestionsList.classList.add('hidden');
        }
    });

    if (resetChartBtn) {
        resetChartBtn.addEventListener('click', resetView);
    }
    
    window.addEventListener('resize', function () { if (chart) chart.resize(); });

    // ─── 获取细胞数据 ───────────────────────────────────────
    function fetchCellData() {
        fetch('/api/cells')
            .then(function (r) { return r.ok ? r.json() : Promise.reject('Failed to fetch cells'); })
            .then(function (ids) { 
                if (Array.isArray(ids)) allCellIds = ids;
            })
            .catch(function (err) { 
                console.warn('获取细胞 ID 失败，使用 Mock 数据:', err);
                allCellIds = Object.keys(_MOCK_CELLS);
            });

        fetch('/api/cells/pca')
            .then(function (r) { return r.ok ? r.json() : Promise.reject('Failed to fetch PCA'); })
            .then(function (cells) {
                if (Array.isArray(cells) && cells.length > 0) {
                    allCellsData = cells;
                    renderChart(cells);
                    buildLegend(cells);
                } else {
                    throw new Error('无效的 PCA 数据');
                }
            })
            .catch(function (err) {
                console.warn('获取 PCA 数据失败，使用 Mock 数据:', err);
                allCellsData = Object.values(_MOCK_CELLS).map(function (info, idx) {
                    return {id: 'cell_' + String(idx + 1).padStart(3, '0'), ...info};
                });
                renderChart(allCellsData);
                buildLegend(allCellsData);
            });
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
            grid: { left: 50, right: 40, top: 30, bottom: 50 },
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
            if (params && params.data && params.data.cellId) {
                if (cellIdInput) cellIdInput.value = params.data.cellId;
                performSearch(params.data.cellId);
            }
        });
    }

    // ─── 构建细胞类型图例 ────────────────────────────────────
    function buildLegend(cells) {
        if (!legendContainer || !cells || cells.length === 0) return;
        var typeCount = {};
        cells.forEach(function (c) {
            typeCount[c.cell_type] = (typeCount[c.cell_type] || 0) + 1;
        });
        legendContainer.innerHTML = '';
        Object.keys(typeCount).forEach(function (type) {
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

    // ─── 执行搜索 ───────────────────────────────────────────
    function performSearch(queryCellId) {
        if (!queryCellId) { showError('请输入细胞 ID 或点击图中细胞。'); return; }
        if (!topKInput) { showError('表单不完整，无法执行搜索。'); return; }
        
        var topK = parseInt(topKInput.value, 10);
        if (isNaN(topK) || topK < 1) { showError('top_k 必须是正整数。'); return; }

        if (abortController) abortController.abort();
        abortController = new AbortController();
        setLoading(true);
        if (cellIdInput) cellIdInput.value = queryCellId;

        fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_cell_id: queryCellId, top_k: topK }),
            signal: abortController.signal,
        })
        .then(function (r) { 
            return r.json().then(function (data) { 
                return {ok: r.ok, status: r.status, data: data}; 
            }).catch(function () {
                return {ok: r.ok, status: r.status, data: {status: 'error', message: '响应格式错误'}};
            });
        })
        .then(function (result) {
            if (!result.ok || !result.data || result.data.status === 'error') {
                var errMsg = (result.data && result.data.message) || ('请求失败 (HTTP ' + result.status + ')');
                showError(errMsg);
                setLoading(false); 
                return;
            }
            currentSearchResult = result.data;
            currentQueryCellId = queryCellId;
            onSearchSuccess(result.data);
            dismissError();
        })
        .catch(function (err) {
            if (err.name === 'AbortError') return;
            showError('网络请求失败: ' + err.message);
        })
        .finally(function () { setLoading(false); });
    }

    // ─── 搜索成功回调 ───────────────────────────────────────
    function onSearchSuccess(data) {
        if (!data || !data.query_cell || !allCellsData) return;
        
        var resultIds = {};
        if (data.results && data.results.length > 0) {
            data.results.forEach(function (r) { resultIds[r.id] = true; });
        }

        renderChart(allCellsData, { queryId: data.query_cell.id, resultIds: resultIds });

        if (selectedDisplay) selectedDisplay.classList.remove('hidden');
        if (selectedCellId) selectedCellId.textContent = data.query_cell.id;
        if (selectedCellType) selectedCellType.textContent = data.query_cell.cell_type || '—';

        renderResults(data);
        if (resetChartBtn) resetChartBtn.classList.remove('hidden');
    }

    // ─── 渲染结果详情 ───────────────────────────────────────
    function renderResults(data) {
        if (!data || !resultsSection || !emptyState) return;
        
        emptyState.classList.add('hidden');
        resultsSection.classList.remove('hidden');

        if (searchStatus) {
            searchStatus.className = 'search-status success';
            searchStatus.innerHTML =
                '✅ 搜索完成 · 耗时 <strong>' + data.time_cost_ms + ' ms</strong> · ' +
                '返回 <strong>' + (data.results ? data.results.length : 0) + '</strong> 条相似细胞';
        }

        var qc = data.query_cell;
        if (queryCellInfo && qc) {
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
        }

        if (resultsTbody) {
            resultsTbody.innerHTML = '';
            if (!data.results || data.results.length === 0) {
                resultsTbody.innerHTML =
                    '<tr><td colspan="5" style="text-align:center;padding:24px;color:#94a3b8;">未找到相似细胞</td></tr>';
            } else {
                data.results.forEach(function (cell, index) {
                    var row = document.createElement('tr');
                    row.innerHTML =
                        '<td class="rank-col">' + (index + 1) + '</td>' +
                        '<td><strong>' + escapeHtml(cell.id) + '</strong></td>' +
                        '<td class="distance-col">' + cell.distance.toFixed(4) + '</td>' +
                        '<td>' + escapeHtml(cell.cell_type || '—') + '</td>' +
                        '<td>' + escapeHtml(cell.disease || '—') + '</td>';
                    row.style.cursor = 'pointer';
                    row.addEventListener('click', function () {
                        if (cellIdInput) {
                            cellIdInput.value = cell.id;
                            performSearch(cell.id);
                        }
                    });
                    resultsTbody.appendChild(row);
                });
            }
        }
        
        if (resultsSection && resultsSection.scrollIntoView) {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    // ─── 重置视图 ───────────────────────────────────────────
    function resetView() {
        currentSearchResult = null;
        currentQueryCellId = null;
        if (cellIdInput) cellIdInput.value = '';
        if (selectedDisplay) selectedDisplay.classList.add('hidden');
        if (resultsSection) resultsSection.classList.add('hidden');
        if (emptyState) emptyState.classList.remove('hidden');
        if (resetChartBtn) resetChartBtn.classList.add('hidden');
        renderChart(allCellsData);
    }

    function setLoading(isLoading) {
        if (!searchBtn) return;
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

    function showError(message) {
        if (!errorMessage || !errorToast) return;
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

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }
});
