{# templates/admin_mapping_viewer.html #}

{% extends "admin_base.html" %} {# Kế thừa từ template admin cơ sở của bạn #}

{% block title %}{{ title or "Trình xem Bản đồ Ứng dụng" }}{% endblock %}

{% block head_extra %} {# Thêm CSS và JS cho Cytoscape #}
{# Nhúng thư viện Cytoscape.js #}
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.23.0/cytoscape.min.js"
    integrity="sha512-gF+H48HjY3w5hXGpqpP/5mX/uR5y+oFjBZJ3lB7jCmwVvYZ+83S+j/tP+TkbY1/qf4YqJdF+bQsL9+bI6Wc9AQ=="
    crossorigin="anonymous" referrerpolicy="no-referrer"></script>

<style>
    /* --- CSS cho Layout và Đồ thị --- */
    .row {
        min-height: 65vh;
    }
    .col-lg-8, .col-lg-4 {
        display: flex;
        flex-direction: column;
    }
    #cy-parent-card {
        flex-grow: 1;
        display: flex;
        flex-direction: column;
    }
    #cy-parent-card .card-body.graph-display-area {
        flex-grow: 1;
        padding: 0 !important;
        display: flex;
        position: relative;
        overflow: hidden;
        min-height: 500px;
    }
    #cy {
        width: 100%;
        height: 100%;
        display: block;
        border: none;
        background-color: #fdfdff;
        position: absolute;
        top: 0;
        left: 0;
        z-index: 1;
    }
    .loading-indicator {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-size: 1.5em;
        color: #888;
        z-index: 10;
        display: none;
        background-color: rgba(255, 255, 255, 0.8);
        padding: 15px 25px;
        border-radius: 5px;
    }
    #selection-details {
        font-size: 0.9em;
        max-height: 60vh;
        overflow-y: auto;
    }
    #selection-details h5 { font-size: 1.1em; margin-bottom: 0.75rem; }
    #selection-details h6 { font-size: 1em; margin-top: 1rem; margin-bottom: 0.5rem; }
    #selection-details .list-group-item { padding: 0.5rem 0.75rem; font-size: 0.85em; border: none; background-color: transparent; }
    #selection-details .list-group-item strong { min-width: 100px; display: inline-block; }
    #selection-details code { font-size: 90%; color: #d63384; background-color: #f8f9fa; padding: 0.1rem 0.3rem; border-radius: 0.2rem; word-break: break-all; }
    #selection-details pre code { white-space: pre-wrap; word-break: break-all; }
    #selection-details img.screenshot-thumbnail { max-width: 100%; max-height: 250px; border: 1px solid #ddd; border-radius: 4px; background-color: #fff; padding: 3px; margin-top: 5px; }
    /* --- CSS cho các phần tử Cytoscape (Tùy chỉnh nếu cần) --- */
    /* Các style cho node, edge, selected elements đã được định nghĩa trong style của cytoscape_instance.js */
</style>
{% endblock %} {# Kết thúc head_extra #}

{% block content %}
<div class="container-fluid px-4">
    <h1 class="mt-4">{{ title or "Trình xem Bản đồ Ứng dụng" }}</h1>
    <ol class="breadcrumb mb-4">
        <li class="breadcrumb-item"><a href="{{ url_for('admin.index') }}">Bảng điều khiển</a></li>
        <li class="breadcrumb-item active">{{ title or "Trình xem Bản đồ Ứng dụng" }}</li>
    </ol>

    {# --- Phần chọn App --- #}
    <div class="card shadow-sm mb-4">
        <div class="card-header">
            Chọn ứng dụng để xem bản đồ
        </div>
        <div class="card-body">
            <form method="GET" id="appSelectForm" action="{{ url_for('admin.admin_mapping_viewer') }}">
                <div class="input-group input-group-sm">
                    <select class="form-select" id="app_name_select" name="app_name" aria-label="Chọn ứng dụng">
                        <option value="">-- Chọn một ứng dụng --</option>
                        {% for name in available_apps %}
                        <option value="{{ name }}" {{ 'selected' if name==selected_app_name else '' }}>
                            {{ name }}
                        </option>
                        {% endfor %}
                    </select>
                    <button class="btn btn-primary" type="submit" id="loadGraphButton">Tải Bản đồ</button> {# Thêm ID cho nút #}
                </div>
            </form>
            <script>
                // Tự động chuyển trang khi chọn app từ dropdown và submit form
                document.getElementById('app_name_select').addEventListener('change', function () {
                    const selectedApp = this.value;
                    const form = document.getElementById('appSelectForm');
                    if (selectedApp) {
                        // Cập nhật action của form để bao gồm app_name trong path
                        form.action = "{{ url_for('admin.admin_mapping_viewer', app_name='PLACEHOLDER') }}".replace('PLACEHOLDER', encodeURIComponent(selectedApp));
                    } else {
                        form.action = "{{ url_for('admin.admin_mapping_viewer') }}";
                    }
                    // Không cần tự động submit nữa nếu nút "Tải Bản đồ" có type="submit"
                    // form.submit(); // Bỏ dòng này nếu muốn người dùng bấm nút
                });
            </script>
        </div>
    </div>

    {# --- Phần hiển thị Đồ thị và Chi tiết --- #}
    {% if selected_app_name %}
    <div class="row">
        {# --- Cột cho Đồ thị --- #}
        <div class="col-lg-8 mb-4 d-flex">
            <div class="card shadow h-100 w-100" id="cy-parent-card">
                <div class="card-header py-3 d-flex justify-content-between align-items-center">
                    <h6 class="m-0 font-weight-bold text-primary">Bản đồ Tương tác Ứng dụng: {{ selected_app_name }}</h6>
                    <button id="refresh-graph-btn" class="btn btn-sm btn-outline-secondary" title="Làm mới Đồ thị">
                        <i class="fas fa-sync-alt fa-fw"></i> Làm mới
                    </button>
                </div>
                <div class="card-body graph-display-area">
                    <div id="loading" class="loading-indicator">Đang tải đồ thị...</div>
                    <div id="cy"></div> {# Nơi Cytoscape vẽ #}
                </div>
            </div>
        </div>

        {# --- Cột cho Thông tin Chi tiết --- #}
        <div class="col-lg-4 mb-4 d-flex">
            <div class="card shadow h-100 w-100">
                <div class="card-header py-3">
                    <h6 class="m-0 font-weight-bold text-info"><i class="fas fa-info-circle me-1"></i> Chi tiết Lựa chọn</h6>
                </div>
                <div class="card-body" id="selection-details">
                    <p class="text-muted fst-italic">Nhấp vào một node (màn hình) hoặc cạnh (chuyển tiếp) để xem chi tiết tại đây.</p>
                </div>
            </div>
        </div>
    </div>
    {# --- Hướng dẫn sử dụng --- #}
    <div class="alert alert-secondary small" role="alert">
        <i class="fas fa-mouse-pointer me-1"></i> <strong>Mẹo:</strong> Nhấp vào node màn hình để xem chi tiết và ảnh (nếu có), hoặc đến trang phân loại phần tử. Nhấp vào cạnh để xem chi tiết chuyển tiếp. Nhấp vào nền trống để bỏ chọn. Dùng bánh xe chuột để thu phóng, nhấp và kéo để di chuyển bản đồ.
    </div>
    {% else %}
    <div class="alert alert-info" role="alert">
        Vui lòng chọn một ứng dụng từ danh sách thả xuống ở trên để xem bản đồ của nó.
    </div>
    {% endif %}
</div>
{% endblock %}

{% block scripts %}
{{ super() }} {# Giữ lại script từ base template nếu có #}

{% if selected_app_name %} {# Chỉ chạy script Cytoscape nếu đã chọn app #}
<script>
    document.addEventListener("DOMContentLoaded", function () {
        const appName = "{{ selected_app_name }}";
        const graphContainer = document.getElementById('cy');
        const loadingIndicator = document.getElementById('loading');
        const selectionDetailsDiv = document.getElementById('selection-details');
        const refreshButton = document.getElementById('refresh-graph-btn');
        let cyInstance = null;

        function escapeHtml(unsafe) {
            if (unsafe === null || unsafe === undefined) return '';
            const str = typeof unsafe !== 'string' ? String(unsafe) : unsafe;
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

        function fetchAndRenderGraph(currentAppName) {
            if (!graphContainer || !loadingIndicator || !selectionDetailsDiv) {
                console.error("DOM elements for graph not found!");
                return;
            }
            if (typeof cytoscape === 'undefined') {
                console.error("Cytoscape library not loaded!");
                loadingIndicator.textContent = 'Lỗi: Cytoscape chưa tải.';
                loadingIndicator.style.display = 'block';
                return;
            }

            console.log(`[MappingViewer] Fetching graph data for app: ${currentAppName}`);
            loadingIndicator.style.display = 'block';
            selectionDetailsDiv.innerHTML = '<p class="text-muted fst-italic">Đang tải chi tiết...</p>';

            if (cyInstance) {
                cyInstance.destroy();
                cyInstance = null;
            }
            graphContainer.innerHTML = '';

            const apiUrl = `/admin/api/mapping_data?app_name=${encodeURIComponent(currentAppName)}`;
            console.log(`[MappingViewer] Calling API: ${apiUrl}`);

            fetch(apiUrl)
                .then(response => {
                    if (!response.ok) {
                        return response.text().then(text => { throw new Error(`API Error ${response.status}: ${text || response.statusText}`) });
                    }
                    return response.json();
                })
                .then(graphData => {
                    loadingIndicator.style.display = 'none';
                    console.log("[MappingViewer] Received graph data:", graphData);

                    if (!graphData || typeof graphData.nodes === 'undefined' || typeof graphData.edges === 'undefined') {
                        console.error("[MappingViewer] Invalid graph data structure:", graphData);
                        graphContainer.innerHTML = `<p class="text-center text-danger mt-5">Lỗi: Dữ liệu đồ thị không hợp lệ.</p>`;
                        return;
                    }
                    if (!graphData.nodes.length) {
                        console.warn("[MappingViewer] No nodes found for this app.");
                        graphContainer.innerHTML = '<p class="text-center text-muted mt-5">Chưa có dữ liệu bản đồ cho ứng dụng này.</p>';
                        return;
                    }

                    cyInstance = cytoscape({
                        container: graphContainer,
                        elements: graphData,
                        style: [
                            { selector: 'node', style: { 'background-color': '#66a3ff', 'label': 'data(label)', 'width': '30px', 'height': '30px', 'font-size': '8px', 'color': '#333', 'text-outline-width': 1, 'text-outline-color': '#fff', 'text-valign': 'center', 'text-halign': 'center', 'border-width': 1, 'border-color': '#444' } },
                            { selector: 'node[status="provisional"]', style: { 'background-color': '#66a3ff' } },
                            { selector: 'node[status="confirmed"]', style: { 'background-color': '#4CAF50' } },
                            { selector: 'node[status="error"]', style: { 'background-color': '#f44336' } },
                            { selector: 'node[status="needs_review"]', style: { 'background-color': '#ffeb3b' } },
                            { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#ff6600', 'background-color': '#ffa500' } },
                            { selector: 'edge', style: { 'width': 1.5, 'line-color': '#ccc', 'target-arrow-color': '#ccc', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'font-size': '7px', 'color': '#555', 'text-outline-width': 1, 'text-outline-color': '#fff', 'arrow-scale': 0.8, 'label': 'data(action_type)' } }, // Thêm label cho cạnh
                            { selector: 'edge[status="provisional"]', style: { 'line-color': '#aaaaaa', 'target-arrow-color': '#aaaaaa', 'line-style': 'dashed' } },
                            { selector: 'edge[status="confirmed"]', style: { 'line-color': '#4CAF50', 'target-arrow-color': '#4CAF50', 'line-style': 'solid' } },
                            { selector: 'edge[status="failed"]', style: { 'line-color': '#f44336', 'target-arrow-color': '#f44336', 'line-style': 'dotted', 'width': 1 } },
                            { selector: 'edge:selected', style: { 'line-color': '#ff6600', 'target-arrow-color': '#ff6600', 'width': 3 } }
                        ],
                        layout: { name: 'cose', idealEdgeLength: 120, nodeOverlap: 30, refresh: 30, fit: true, padding: 40, randomize: false, componentSpacing: 150, nodeRepulsion: (node) => 450000, edgeElasticity: (edge) => 100, nestingFactor: 5, gravity: 80, numIter: 1500, initialTemp: 200, coolingFactor: 0.95, minTemp: 1.0, animate: 'end', animationDuration: 500 },
                        wheelSensitivity: 0.2, minZoom: 0.1, maxZoom: 5
                    });

                    // Sự kiện khi nhấp vào Node
                    cyInstance.on('tap', 'node', function (evt) {
                        var node = evt.target;
                        const nodeData = node.data();
                        console.log('[MappingViewer] Node tapped:', nodeData);

                        let detailsHtml = `<h5>Chi tiết Node (Màn hình)</h5>
                            <ul class="list-group list-group-flush">
                              <li class="list-group-item"><strong>ID:</strong> <code>${escapeHtml(nodeData.id)}</code></li>
                              <li class="list-group-item"><strong>Nhãn:</strong> ${escapeHtml(nodeData.label)}</li>
                              <li class="list-group-item"><strong>Activity:</strong> ${escapeHtml(nodeData.activity)}</li>
                              <li class="list-group-item"><strong>Trạng thái:</strong> <span class="badge bg-info">${escapeHtml(nodeData.status || 'N/A')}</span></li>
                              <li class="list-group-item"><strong>Số Element:</strong> ${nodeData.element_count !== undefined ? nodeData.element_count : 'N/A'}</li>
                            </ul>`;

                        if (nodeData.screenshot_url) {
                            detailsHtml += `<div class="mt-3 text-center">
                                     <h6>Ảnh chụp màn hình</h6>
                                     <a href="${escapeHtml(nodeData.screenshot_url)}" target="_blank" title="Xem ảnh đầy đủ">
                                         <img src="${escapeHtml(nodeData.screenshot_url)}" alt="Ảnh chụp màn hình cho ${escapeHtml(nodeData.id)}"
                                              class="screenshot-thumbnail">
                                     </a>
                                 </div>`;
                        } else {
                            detailsHtml += '<p class="text-muted mt-2 text-center small">(Không có ảnh chụp)</p>';
                        }

                        const screenId = node.id();
                        if (screenId) {
                            const elementPageUrl = "{{ url_for('admin.admin_screen_elements', screen_id='PLACEHOLDER') }}".replace('PLACEHOLDER', encodeURIComponent(screenId));
                            detailsHtml += `<div class="mt-3">
                                <a href="${elementPageUrl}" class="btn btn-sm btn-outline-primary" target="_blank">
                                    <i class="fas fa-search me-1"></i> Xem/Phân loại Elements
                                </a>
                             </div>`;
                        }
                        selectionDetailsDiv.innerHTML = detailsHtml;
                    });

                    // Sự kiện khi nhấp vào Cạnh
                    cyInstance.on('tap', 'edge', function (evt) {
                        var edge = evt.target;
                        const edgeData = edge.data();
                        console.log('[MappingViewer] Edge tapped:', edgeData);

                        let edgeDetailsHtml = `<h5>Chi tiết Cạnh (Transition)</h5><ul class="list-group list-group-flush">`;
                        edgeDetailsHtml += `<li class="list-group-item"><strong>ID (Graph):</strong> <code>${escapeHtml(edge.id())}</code></li>`;
                        edgeDetailsHtml += `<li class="list-group-item"><strong>Nguồn:</strong> <code>${escapeHtml(edgeData.source)}</code></li>`;
                        edgeDetailsHtml += `<li class="list-group-item"><strong>Đích:</strong> <code>${escapeHtml(edgeData.target)}</code></li>`;
                        edgeDetailsHtml += `<li class="list-group-item"><strong>Trạng thái:</strong> <span class="badge bg-secondary">${escapeHtml(edgeData.status || 'N/A')}</span></li>`;
                        edgeDetailsHtml += `<li class="list-group-item"><strong>Action Type:</strong> ${escapeHtml(edgeData.action_type || 'N/A')}</li>`;
                        if (edgeData.macro_code) edgeDetailsHtml += `<li class="list-group-item"><strong>Macro:</strong> <code>${escapeHtml(edgeData.macro_code)}</code></li>`;
                        if (edgeData.element_id) edgeDetailsHtml += `<li class="list-group-item"><strong>On Element ID:</strong> <code>${escapeHtml(edgeData.element_id)}</code></li>`;
                        if (edgeData.element_text) edgeDetailsHtml += `<li class="list-group-item"><strong>On Element Text:</strong> ${escapeHtml(edgeData.element_text)}</li>`;
                        if (edgeData.attempt_count !== undefined) edgeDetailsHtml += `<li class="list-group-item"><strong>Thử:</strong> ${edgeData.attempt_count}</li>`;
                        if (edgeData.success_count !== undefined) edgeDetailsHtml += `<li class="list-group-item"><strong>Thành công:</strong> ${edgeData.success_count}</li>`;

                        if (edgeData.params_json) {
                            try {
                                const paramsObj = JSON.parse(edgeData.params_json);
                                const formattedParams = JSON.stringify(paramsObj, null, 2);
                                edgeDetailsHtml += `<li class="list-group-item"><strong>Params:</strong> <pre><code style="white-space: pre-wrap; word-break: break-all;">${escapeHtml(formattedParams)}</code></pre></li>`;
                            } catch (e) {
                                edgeDetailsHtml += `<li class="list-group-item"><strong>Params (Raw):</strong> <pre><code>${escapeHtml(edgeData.params_json)}</code></pre></li>`;
                            }
                        }
                        edgeDetailsHtml += `</ul>`;
                        selectionDetailsDiv.innerHTML = edgeDetailsHtml;
                    });

                    // Sự kiện khi nhấp vào nền trống
                    cyInstance.on('tap', function (event) {
                        if (event.target === cyInstance) {
                            selectionDetailsDiv.innerHTML = '<p class="text-muted fst-italic">Nhấp vào một node hoặc cạnh để xem chi tiết.</p>';
                        }
                    });

                    cyInstance.ready(function () {
                        cyInstance.fit(null, 50);
                        console.log("[MappingViewer] Cytoscape layout ready and fitted.");
                    });
                    cyInstance.resize();
                })
                .catch(error => {
                    loadingIndicator.style.display = 'none';
                    console.error("[MappingViewer] Error fetching or rendering graph:", error);
                    graphContainer.innerHTML = `<div class="alert alert-danger m-5" role="alert">
                                                <strong>Lỗi tải đồ thị:</strong> ${escapeHtml(error.message || 'Lỗi không xác định')}
                                               </div>`;
                    selectionDetailsDiv.innerHTML = '<p class="text-danger">Tải đồ thị thất bại.</p>';
                });
        }

        // Gọi hàm để tải và vẽ đồ thị lần đầu nếu appName đã có (từ URL)
        if (appName) {
            fetchAndRenderGraph(appName);
        }

        // Xử lý nút Refresh
        if (refreshButton) {
            refreshButton.addEventListener('click', function () {
                if (appName) {
                    console.log('[MappingViewer] Refresh button clicked.');
                    fetchAndRenderGraph(appName);
                } else {
                    alert("Vui lòng chọn một ứng dụng trước khi làm mới.");
                }
            });
        }

        // Xử lý nút "Tải Bản đồ" của form (nếu muốn dùng JS thay vì submit form)
        // Lưu ý: Form hiện tại đang dùng type="submit" nên sẽ tự reload trang
        const loadGraphButton = document.getElementById('loadGraphButton');
        const appNameSelect = document.getElementById('app_name_select');
        if (loadGraphButton && appNameSelect) {
            // Nếu bạn muốn nút này chỉ kích hoạt fetch bằng JS mà không reload trang:
            // loadGraphButton.addEventListener('click', function(event) {
            //     event.preventDefault(); // Ngăn submit form
            //     const selectedApp = appNameSelect.value;
            //     if (selectedApp) {
            //         // Cập nhật URL nếu muốn (ví dụ dùng history.pushState)
            //         // window.history.pushState({ app: selectedApp }, `Mapping for ${selectedApp}`, `{{ url_for('admin.admin_mapping_viewer') }}/${encodeURIComponent(selectedApp)}`);
            //         fetchAndRenderGraph(selectedApp);

            //         // Cập nhật title của trang (nếu muốn)
            //         document.title = `Mapping for: ${selectedApp} - HPT Automation`;
            //         const h1Title = document.querySelector('.container-fluid h1');
            //         if (h1Title) h1Title.textContent = `Mapping for: ${selectedApp}`;
            //     } else {
            //         alert("Vui lòng chọn một ứng dụng.");
            //     }
            // });
        }
    });
</script>
{% endif %} {# Kết thúc if selected_app_name #}

{% endblock %} {# Kết thúc block scripts #}