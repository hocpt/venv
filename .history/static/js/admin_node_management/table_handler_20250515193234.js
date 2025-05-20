// static/js/admin_node_management/table_handler.js
// Cần import sendApiRequest từ utils.js và các hàm mở modal nếu dùng ES Modules
// import { sendApiRequest } from './utils.js';
// import { openManagePieConditionsModal } from './modal_manage_pie.js';
// import { APP_CONFIG } from './config.js'; // Hoặc truy cập window.APP_CONFIG

function initTableHandler() {
    const nodesTableBody = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODES_TABLE_BODY);
    const filterForm = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODE_FILTER_FORM);
    const appNameFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.APP_NAME_FILTER_SELECT);
    const statusFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.STATUS_FILTER_SELECT);
    const paginationContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.PAGINATION_CONTAINER);

    function buildApiUrl(page = 1, appName = null, statusFilter = null) {
        const params = new URLSearchParams();
        params.append('page', page);
        if (appName) {
            params.append('app_name_filter', appName);
        }
        if (statusFilter) {
            params.append('filter_status', statusFilter);
        }
        return `${APP_CONFIG.API_MANAGED_NODES_URL}?${params.toString()}`;
    }

    function renderNodeRow(node) {
        const row = document.createElement('tr');
        // Gán các data-* attributes quan trọng vào thẻ <tr>
        row.dataset.nodeNeo4jId = node.id || node.element_id || ''; // Neo4j internal ID
        row.dataset.currentScreenId = node.screen_id || '';
        row.dataset.appName = node.app_name || '';
        row.dataset.nodeStatus = node.status || 'unknown';
        row.dataset.screenshotFilename = node.screenshot_path || ''; // Chỉ tên file
        row.dataset.activityName = node.activity_name || '';
        row.dataset.pieLogicalName = node.logical_pie_name || '';
        row.dataset.width = node.width || ''; // Kích thước gốc của màn hình
        row.dataset.height = node.height || '';

        // 1. Checkbox
        const cellCheckbox = `<td><input type="checkbox" class="node-checkbox" value="${node.screen_id || ''}"></td>`;

        // 2. Screen ID (link to elements page)
        const screenElementsUrl = APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id || ''));
        const cellScreenId = `<td><a href="${screenElementsUrl}" target="_blank" title="Xem elements của: ${node.screen_id}"><code class="small">${(node.screen_id || 'N/A').substring(0, 20)}</code></a></td>`;

        // 3. App Name
        const cellAppName = `<td><code class="small">${node.app_name || 'N/A'}</code></td>`;

        // 4. Activity
        const cellActivity = `<td><code class="small" title="${node.activity_name || ''}">${(node.activity_name || 'N/A').substring(0, 20)}</code></td>`;

        // 5. Ảnh Thumbnail (sẽ gắn class APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER)
        let cellImage = `<td><span class="text-muted small ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" style="cursor:pointer; display:inline-block; width:70px; height:70px; border:1px dashed #ccc; text-align:center; line-height:70px;" title="Quản lý PIE Conditions">N/A</span></td>`;
        if (node.screenshot_full_url) { // API đã trả về URL đầy đủ
            cellImage = `<td><img src="${node.screenshot_full_url}" alt="ss_${node.screen_id}" class="node-thumbnail ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" title="Quản lý PIE Conditions"></td>`;
        }

        // 6. Tên Logic PIE
        let cellPieName = '<td><em class="text-muted small">Chưa có PIE</em></td>';
        if (node.logical_pie_name && node.logical_pie_name !== "PIE Def không tìm thấy" && node.logical_pie_name !== "Lỗi lấy PIE Def") {
            cellPieName = `<td><span title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}</span></td>`;
        } else if (node.logical_pie_name) { // Hiển thị lỗi nếu có
            cellPieName = `<td><em class="text-danger small" title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}</em></td>`;
        }

        // 7. Status Badge
        let statusClass = 'bg-secondary';
        if (node.status === 'defined') statusClass = 'bg-success';
        else if (node.status === 'provisional_unknown') statusClass = 'bg-warning text-dark';
        else if (node.status === 'merged_to_defined') statusClass = 'bg-info text-dark';
        const cellStatus = `<td><span class="badge ${statusClass}">${node.status || 'N/A'}</span></td>`;

        // 8. Phân loại Node (Dropdown)
        const classificationsOpts = [ /* Giữ nguyên như trong file HTML */ { v: "", l: "-- Chưa --" }, { v: "login_screen", l: "Login" }, /*...*/ { v: "other", l: "Khác" }];
        let classificationSelectHtml = `<select class="form-select form-select-sm ${APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT}" data-current-screen-id="${node.screen_id}" data-app-name="${node.app_name}">`;
        classificationsOpts.forEach(opt => {
            classificationSelectHtml += `<option value="${opt.v}" ${node.node_classification == opt.v ? 'selected' : ''}>${opt.l}</option>`;
        });
        classificationSelectHtml += `</select><span class="classification-status small ms-1"></span>`;
        const cellClassification = `<td>${classificationSelectHtml}</td>`;

        // 9. Element Count
        const elemCount = node.actual_element_count_rel ?? node.defined_element_count ?? 0; // Ưu tiên actual_element_count_rel
        const cellElemCount = `<td class="text-center">${elemCount}</td>`;

        // 10. Transitions Count
        const cellTransCount = `<td class="text-center">${node.incoming_transitions_count || 0} / ${node.outgoing_transitions_count || 0}</td>`;

        // 11. Last Seen
        const lastSeenDate = node.last_seen ? new Date(node.last_seen).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }) : 'N/A';
        const cellLastSeen = `<td class="small text-nowrap">${lastSeenDate}</td>`;

        // 12. Hành động
        let actionButtonsHtml = `<div class="action-button-row mb-1">
                                    <a href="${screenElementsUrl}" target="_blank" class="btn btn-xs btn-outline-info view-elements-btn me-1" title="Xem Elements (Trang riêng)" data-bs-toggle="tooltip"><i class="fas fa-search-plus"></i> Elements</a>
                                    <button type="button" class="btn btn-xs btn-outline-danger ${APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN}" title="Xóa Node" data-bs-toggle="tooltip"><i class="fas fa-trash-alt"></i> Xóa</button>
                                 </div>`;
        if (node.status === 'unknown' || node.status === 'provisional_unknown') {
            actionButtonsHtml += `<div class="action-button-row">
                                    <button type="button" class="btn btn-xs btn-outline-success ${APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER}" title="Tạo PIE Mới cho Node này" data-bs-toggle="tooltip"><i class="fas fa-plus-circle"></i> Tạo PIE Mới</button>
                                 </div>`;
        }
        const cellActions = `<td class="action-buttons text-nowrap">${actionButtonsHtml}</td>`;

        row.innerHTML = cellCheckbox + cellScreenId + cellAppName + cellActivity + cellImage + cellPieName + cellStatus + cellClassification + cellElemCount + cellTransCount + cellLastSeen + cellActions;
        return row;
    }

    function renderNodePagination(paginationData, currentPageFilters) {
        if (!paginationContainer || !paginationData) return;
        paginationContainer.innerHTML = '';
        if (paginationData.total_pages <= 1) return;

        let html = '<ul class="pagination pagination-sm justify-content-center">';
        // Prev
        html += `<li class="page-item ${paginationData.has_prev ? '' : 'disabled'}">
                    <a class="page-link" href="#" data-page="${paginationData.prev_num || 1}" aria-label="Previous">&laquo;</a>
                 </li>`;
        // Pages
        const windowSize = 2;
        let startPage = Math.max(1, paginationData.page - windowSize);
        let endPage = Math.min(paginationData.total_pages, paginationData.page + windowSize);

        if (startPage > 1) {
            html += `<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>`;
            if (startPage > 2) html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
        for (let i = startPage; i <= endPage; i++) {
            html += `<li class="page-item ${i === paginationData.page ? 'active' : ''}">
                        <a class="page-link" href="#" data-page="${i}">${i}</a>
                     </li>`;
        }
        if (endPage < paginationData.total_pages) {
            if (endPage < paginationData.total_pages - 1) html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
            html += `<li class="page-item"><a class="page-link" href="#" data-page="${paginationData.total_pages}">${paginationData.total_pages}</a></li>`;
        }
        // Next
        html += `<li class="page-item ${paginationData.has_next ? '' : 'disabled'}">
                    <a class="page-link" href="#" data-page="${paginationData.next_num || paginationData.total_pages}" aria-label="Next">&raquo;</a>
                 </li>`;
        html += '</ul>';
        paginationContainer.innerHTML = html;

        // Gắn sự kiện cho các link phân trang mới tạo
        paginationContainer.querySelectorAll('.page-link').forEach(link => {
            if (link.closest('.page-item.disabled')) return;
            link.addEventListener('click', function (e) {
                e.preventDefault();
                fetchAndRenderTableNodes(parseInt(this.dataset.page), currentPageFilters.appName, currentPageFilters.status);
            });
        });
    }

    async function handleDeleteNode(screenId, appName) {
        if (!confirm(`Bạn có chắc chắn muốn xóa Node '${screenId}' của app '${appName}' không? Hành động này không thể hoàn tác.`)) {
            return;
        }
        const deleteUrl = APP_CONFIG.API_DELETE_NODE_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(screenId));
        try {
            const result = await sendApiRequest(deleteUrl, 'POST', { app_name: appName });
            if (result.success) {
                alert(result.message || 'Xóa Node thành công!');
                fetchAndRenderTableNodes(); // Tải lại bảng (trang hiện tại hoặc trang 1)
            } else {
                alert("Lỗi Xóa Node: " + (result.error || result.message || "Thao tác thất bại."));
            }
        } catch (error) {
            console.error('Lỗi Fetch khi xóa Node:', error);
            alert('Lỗi máy chủ khi xóa Node: ' + (error.data?.error || error.message || 'Lỗi không xác định'));
        }
    }

    async function handleNodeClassificationChange(event) {
        const selectElement = event.target;
        const screenId = selectElement.dataset.currentScreenId; // Đã sửa data attribute trong renderNodeRow
        const appName = selectElement.dataset.appName;
        const newClassification = selectElement.value;
        const statusSpan = selectElement.closest('td').querySelector('.classification-status');

        if (statusSpan) { statusSpan.textContent = 'Đang lưu...'; statusSpan.className = 'classification-status small ms-1 text-muted'; }

        const classifyUrl = APP_CONFIG.API_CLASSIFY_NODE_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(screenId));
        try {
            const result = await sendApiRequest(classifyUrl, 'POST', {
                app_name: appName,
                node_classification: newClassification
            });
            if (statusSpan) {
                if (result.success) {
                    statusSpan.textContent = 'Đã lưu!'; statusSpan.className = 'classification-status small ms-1 text-success';
                } else {
                    statusSpan.textContent = 'Lỗi!'; statusSpan.className = 'classification-status small ms-1 text-danger';
                    alert("Lỗi cập nhật phân loại: " + (result.error || result.message || "Thất bại."));
                }
                setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000);
            }
        } catch (error) {
            if (statusSpan) {
                statusSpan.textContent = 'Lỗi mạng!'; statusSpan.className = 'classification-status small ms-1 text-danger';
                setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000);
            }
            console.error('Lỗi Fetch khi phân loại Node:', error);
            alert('Lỗi kết nối máy chủ: ' + (error.data?.error || error.message || 'Lỗi không xác định'));
        }
    }

    function attachTableTriggers() {
        if (!nodesTableBody) return;

        // Sự kiện cho ảnh thumbnail -> mở modal quản lý PIE
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER).forEach(trigger => {
            const row = trigger.closest('tr');
            if (!row) return;
            const nodeData = {
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: row.dataset.nodeStatus,
                screenshotFilename: row.dataset.screenshotFilename, activityName: row.dataset.activityName,
                pieLogicalName: row.dataset.pieLogicalName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            trigger.onclick = () => { // Gán trực tiếp, hoặc dùng addEventListener và quản lý remove
                if (window.openManagePieConditionsModal) {
                    window.openManagePieConditionsModal(nodeData);
                } else {
                    console.error("Hàm openManagePieConditionsModal chưa được định nghĩa.");
                }
            };
        });

        // Sự kiện cho nút "Tạo PIE Mới"
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER).forEach(button => {
            const row = button.closest('tr');
            if (!row) return;
            const nodeDataForPieDef = { /* ... Lấy data từ row.dataset như trên ... */
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: 'unknown', // Quan trọng: đánh dấu là luồng tạo mới
                screenshotFilename: row.dataset.screenshotFilename, activityName: row.dataset.activityName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            button.onclick = () => {
                if (window.openManagePieConditionsModal) { // Vẫn mở modal chọn conditions trước
                    window.openManagePieConditionsModal(nodeDataForPieDef);
                } else {
                    console.error("Hàm openManagePieConditionsModal chưa được định nghĩa.");
                }
            };
        });

        // Sự kiện cho nút Xóa Node
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN).forEach(button => {
            const row = button.closest('tr');
            if (!row) return;
            button.onclick = () => handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName);
        });

        // Sự kiện cho dropdown Phân loại Node
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT).forEach(select => {
            select.onchange = handleNodeClassificationChange;
        });

        // Kích hoạt lại Bootstrap Tooltips cho các nút mới được render
        var tooltipTriggerList = [].slice.call(nodesTableBody.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    async function fetchAndRenderTableNodes(page = 1, appName = null, statusFilter = null) {
        const currentAppName = appName !== null ? appName : (appNameFilterSelect ? appNameFilterSelect.value : '');
        const currentStatus = statusFilter !== null ? statusFilter : (statusFilterSelect ? statusFilterSelect.value : 'unknown'); // Mặc định là unknown
        const apiUrl = buildApiUrl(page, currentAppName, currentStatus);

        if (!nodesTableBody) { console.error("nodesTableBody không tìm thấy!"); return; }
        nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center py-3"><i class="fas fa-spinner fa-spin me-2"></i>Đang tải dữ liệu Nodes...</td></tr>`;
        if (paginationContainer) paginationContainer.innerHTML = '';

        try {
            const data = await sendApiRequest(apiUrl, 'GET'); // Dùng sendApiRequest

            nodesTableBody.innerHTML = ''; // Xóa nội dung "Đang tải..."
            if (data.nodes && data.nodes.length > 0) {
                data.nodes.forEach(node => {
                    nodesTableBody.appendChild(renderNodeRow(node));
                });
            } else {
                nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-muted fst-italic py-3">Không tìm thấy Node nào khớp với bộ lọc.</td></tr>`;
            }

            if (data.pagination) {
                renderNodePagination(data.pagination, { appName: currentAppName, status: currentStatus });
            }
            attachTableTriggers(); // QUAN TRỌNG: Gắn lại listeners sau khi render xong bảng

        } catch (error) {
            console.error("Lỗi khi tải và render Nodes:", error);
            nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-danger py-3">Lỗi tải dữ liệu: ${error.data?.error || error.message || 'Lỗi không xác định'}</td></tr>`;
            if (paginationContainer) paginationContainer.innerHTML = '';
        }
    }

    // --- Khởi tạo cho Table Handler ---
    if (filterForm) {
        filterForm.addEventListener('submit', function (event) {
            event.preventDefault();
            fetchAndRenderTableNodes(1); // Luôn về trang 1 khi lọc mới
        });
    }

    // Load dữ liệu lần đầu cho bảng
    // Cần đảm bảo hàm này được export hoặc gọi từ main.js
    window.fetchAndRenderTableNodes = fetchAndRenderTableNodes; // Đưa ra global để gọi từ modal khi cần refresh

    // Kiểm tra xem tbody có được render từ server không
    // Nếu không thì fetch, nếu có thì chỉ attach trigger cho pagination của server
    const currentUrlParams = new URLSearchParams(window.location.search);
    const initialPage = parseInt(currentUrlParams.get('page') || '1', 10);
    const initialAppName = currentUrlParams.get('app_name_filter') || (appNameFilterSelect ? appNameFilterSelect.value : '');
    const initialStatus = currentUrlParams.get('filter_status') || (statusFilterSelect ? statusFilterSelect.value : 'unknown');

    if (nodesTableBody && nodesTableBody.children.length > 0 &&
        !(nodesTableBody.firstElementChild && nodesTableBody.firstElementChild.children.length === 1 &&
            nodesTableBody.firstElementChild.firstElementChild.textContent.includes("Không tìm thấy Node nào"))) {
        // Đã có dữ liệu từ server, chỉ cần gắn listener cho pagination hiện tại
        if (paginationContainer) {
            paginationContainer.querySelectorAll('.page-link').forEach(link => {
                if (link.closest('.page-item.disabled')) return;
                // Gắn listener mới, tránh việc gắn nhiều lần nếu chạy lại initTableHandler
                link.addEventListener('click', function handler(e) {
                    e.preventDefault();
                    fetchAndRenderTableNodes(parseInt(this.dataset.page), initialAppName, initialStatus);
                    // Nên có cơ chế remove listener cũ nếu element không được tạo lại hoàn toàn
                });
            });
        }
        attachTableTriggers(); // Gắn trigger cho các nút trong bảng đã render từ server
    } else {
        fetchAndRenderTableNodes(initialPage, initialAppName, initialStatus);
    }
}

// initTableHandler();