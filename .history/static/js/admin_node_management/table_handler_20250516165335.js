// static/js/admin_node_management/table_handler.js
import { APP_CONFIG } from './config.js'; // Đảm bảo APP_CONFIG được export từ config.js
import { sendApiRequest } from './utils.js'; // Đảm bảo sendApiRequest được export từ utils.js

// Hàm initTableHandler sẽ được gọi từ main.js
export function initTableHandler() {
    // Lấy các DOM element cần thiết một lần khi khởi tạo
    const nodesTableBody = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODES_TABLE_BODY);
    const filterForm = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODE_FILTER_FORM);
    const appNameFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.APP_NAME_FILTER_SELECT);
    const statusFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.STATUS_FILTER_SELECT);
    const paginationContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.PAGINATION_CONTAINER);

    if (!nodesTableBody || !filterForm || !appNameFilterSelect || !statusFilterSelect || !paginationContainer) {
        console.error("TABLE_HANDLER: Một hoặc nhiều DOM elements chính không tìm thấy. Logic của bảng có thể không hoạt động.");
        return;
    }

    /**
     * Xây dựng URL API để lấy danh sách Node dựa trên filter và phân trang.
     */
    function buildApiUrl(page = 1, appName = null, statusFilter = null) {
        const params = new URLSearchParams();
        params.append('page', page);
        if (appName && appName.trim() !== '') {
            params.append('app_name_filter', appName);
        }
        if (statusFilter && statusFilter.trim() !== '') {
            params.append('filter_status', statusFilter);
        }
        // Đảm bảo APP_CONFIG.API_MANAGED_NODES_URL đã được khởi tạo đúng trong main.js từ templatePageConfig
        return `${APP_CONFIG.API_MANAGED_NODES_URL}?${params.toString()}`;
    }

    /**
     * Render một hàng (<tr>) cho một Node.
     * @param {object} node - Dữ liệu của Node từ API.
     * @returns {HTMLTableRowElement} Element <tr> đã được tạo.
     */
    function renderNodeRow(node) {
        const row = document.createElement('tr');
        // Gán các data-* attributes quan trọng vào thẻ <tr> để dễ truy cập khi xử lý sự kiện
        row.dataset.nodeNeo4jId = node.id || node.element_id || '';
        row.dataset.currentScreenId = node.screen_id || '';
        row.dataset.appName = node.app_name || '';
        row.dataset.nodeStatus = node.status || 'unknown';
        row.dataset.screenshotFilename = node.screenshot_path || ''; // Chỉ tên file từ Neo4j
        row.dataset.screenshotFullUrl = node.screenshot_full_url || ''; // URL đầy đủ từ API backend
        row.dataset.activityName = node.activity_name || '';
        row.dataset.pieLogicalName = node.logical_pie_name || '';
        row.dataset.width = node.width || '';
        row.dataset.height = node.height || '';

        const screenElementsPageUrl = APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id || ''));

        // --- SỬA LỖI RENDER ẢNH THUMBNAIL ---
        let imgHtml = `<span class="text-muted small ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" 
                             style="cursor:pointer; display:inline-block; width:70px; height:100px; border:1px dashed #ccc; text-align:center; line-height:100px; vertical-align:middle;" 
                             title="Quản lý PIE Conditions cho ${node.screen_id}">N/A</span>`;
        if (node.screenshot_full_url) {
            imgHtml = `<img src="${node.screenshot_full_url}" 
                             alt="Ảnh của ${node.screen_id || 'node'}" 
                             class="node-thumbnail ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" 
                             title="Quản lý PIE Conditions cho ${node.screen_id}">`;
        }
        const cellImage = `<td>${imgHtml}</td>`;
        // --- KẾT THÚC SỬA LỖI RENDER ẢNH ---

        let logicalNameHtml = `<em class="text-muted small">Chưa có PIE</em>`;
        if (node.logical_pie_name && node.logical_pie_name !== "PIE Def không tìm thấy" && node.logical_pie_name !== "Lỗi lấy PIE Def") {
            logicalNameHtml = `<span title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}${node.logical_pie_name.length > 25 ? '...' : ''}</span>`;
        } else if (node.logical_pie_name) { // Hiển thị lỗi nếu có
            logicalNameHtml = `<em class="text-danger small" title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}${node.logical_pie_name.length > 25 ? '...' : ''}</em>`;
        }

        let statusClass = 'bg-secondary';
        if (node.status === 'defined') statusClass = 'bg-success';
        else if (node.status === 'provisional_unknown') statusClass = 'bg-warning text-dark';
        else if (node.status === 'merged_to_defined') statusClass = 'bg-info text-dark';

        const classificationsOpts = [
            { v: "", l: "-- Chưa --" }, { v: "login_screen", l: "Login" }, { v: "profile_screen", l: "Profile" },
            { v: "feed_screen", l: "Feed/Home" }, { v: "settings_screen", l: "Settings" },
            { v: "popup_dialog", l: "Popup" }, { v: "item_list", l: "Item List" },
            { v: "item_detail", l: "Item Detail" }, { v: "other", l: "Khác" }
        ];
        let classificationSelectHtml = `<select class="form-select form-select-sm ${APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT}" data-current-screen-id="${node.screen_id}" data-app-name="${node.app_name}" aria-label="Phân loại Node">`;
        classificationsOpts.forEach(opt => {
            classificationSelectHtml += `<option value="${opt.v}" ${node.node_classification == opt.v ? 'selected' : ''}>${opt.l}</option>`;
        });
        classificationSelectHtml += `</select><span class="classification-status small ms-1"></span>`;

        let actionButtonsHtml = `<div class="action-button-row mb-1">
                                    <a href="${screenElementsPageUrl}" target="_blank" class="btn btn-xs btn-outline-info view-elements-btn me-1" title="Xem Elements (Trang riêng)" data-bs-toggle="tooltip"><i class="fas fa-search-plus"></i> Elements</a>
                                    <button type="button" class="btn btn-xs btn-outline-danger ${APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN}" title="Xóa Node" data-bs-toggle="tooltip"><i class="fas fa-trash-alt"></i> Xóa</button>
                                 </div>`;
        if (node.status === 'unknown' || node.status === 'provisional_unknown') {
            actionButtonsHtml += `<div class="action-button-row">
                                    <button type="button" class="btn btn-xs btn-outline-success ${APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER}" title="Tạo PIE Mới cho Node này" data-bs-toggle="tooltip"><i class="fas fa-plus-circle"></i> Tạo PIE Mới</button>
                                 </div>`;
        }

        row.innerHTML = `
            <td><input type="checkbox" class="node-checkbox" value="${node.screen_id || ''}" aria-label="Chọn node ${node.screen_id}"></td>
            <td><a href="${screenElementsPageUrl}" target="_blank" title="Xem elements của ${node.screen_id || ''}"><code class="small">${(node.screen_id || 'N/A').substring(0, 20)}</code></a></td>
            <td><code class="small">${node.app_name || 'N/A'}</code></td>
            <td><code class="small" title="${node.activity_name || ''}">${(node.activity_name || 'N/A').substring(0, 20)}</code></td>
            ${cellImage}
            <td>${logicalNameHtml}</td>
            <td><span class="badge ${statusClass}">${node.status || 'N/A'}</span></td>
            <td>${classificationSelectHtml}</td>
            <td class="text-center">${node.actual_element_count_rel ?? node.defined_element_count ?? 0}</td>
            <td class="text-center">${node.incoming_transitions_count || 0} / ${node.outgoing_transitions_count || 0}</td>
            <td class="small text-nowrap">${node.last_seen ? new Date(node.last_seen).toLocaleDateString('vi-VN') : 'N/A'}</td>
            <td class="action-buttons text-nowrap">${actionButtonsHtml}</td>
        `;
        return row;
    }

    function renderNodePagination(paginationData, currentPageFilters) {
        if (!paginationContainer || !paginationData || paginationData.total_pages <= 1) {
            if (paginationContainer) paginationContainer.innerHTML = '';
            return;
        }
        let html = '<ul class="pagination pagination-sm justify-content-center">';
        html += `<li class="page-item ${paginationData.has_prev ? '' : 'disabled'}"><a class="page-link" href="#" data-page="${paginationData.prev_num || 1}" aria-label="Previous">&laquo;</a></li>`;
        const windowSize = 2;
        let startPage = Math.max(1, paginationData.page - windowSize);
        let endPage = Math.min(paginationData.total_pages, paginationData.page + windowSize);

        if (startPage > 1) {
            html += `<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>`;
            if (startPage > 2) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        for (let i = startPage; i <= endPage; i++) {
            html += `<li class="page-item ${i === paginationData.page ? 'active' : ''}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
        }
        if (endPage < paginationData.total_pages) {
            if (endPage < paginationData.total_pages - 1) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
            html += `<li class="page-item"><a class="page-link" href="#" data-page="${paginationData.total_pages}">${paginationData.total_pages}</a></li>`;
        }
        html += `<li class="page-item ${paginationData.has_next ? '' : 'disabled'}"><a class="page-link" href="#" data-page="${paginationData.next_num || paginationData.total_pages}" aria-label="Next">&raquo;</a></li>`;
        html += '</ul>';
        paginationContainer.innerHTML = html;

        paginationContainer.querySelectorAll('.page-link').forEach(link => {
            if (link.closest('.page-item.disabled')) return;
            // Xóa listener cũ bằng cách clone và replace để tránh gắn nhiều lần
            const newLink = link.cloneNode(true);
            link.parentNode.replaceChild(newLink, link);
            newLink.addEventListener('click', function (e) {
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
                fetchAndRenderTableNodes(); // Tải lại bảng
            } else {
                throw new Error(result.error || result.message || "Xóa Node thất bại từ server.");
            }
        } catch (error) {
            console.error('Lỗi Fetch khi xóa Node:', error);
            alert('Lỗi máy chủ khi xóa Node: ' + (error.data?.error || error.message || 'Lỗi không xác định'));
        }
    }

    async function handleNodeClassificationChange(event) {
        const selectElement = event.target;
        const screenId = selectElement.dataset.currentScreenId;
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
                    throw new Error(result.error || result.message || "Lỗi cập nhật phân loại từ server.");
                }
                setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000);
            }
        } catch (error) {
            if (statusSpan) {
                statusSpan.textContent = 'Lỗi mạng!'; statusSpan.className = 'classification-status small ms-1 text-danger';
                setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000);
            }
            console.error('Lỗi Fetch khi phân loại Node:', error);
            alert('Lỗi máy chủ khi phân loại Node: ' + (error.data?.error || error.message || 'Lỗi không xác định'));
        }
    }

    function attachTableTriggers() {
        if (!nodesTableBody) {
            console.warn("TABLE_HANDLER: nodesTableBody không tìm thấy, không thể gắn triggers.");
            return;
        }

        // Sử dụng event delegation cho hiệu suất tốt hơn và không cần gắn lại nhiều lần
        // Tuy nhiên, để giữ code gần với cấu trúc hiện tại, chúng ta sẽ xóa và gắn lại
        // Hoặc tốt hơn là clone và replace cho các nút/select cụ thể.

        // Gắn sự kiện cho ảnh thumbnail -> mở modal quản lý PIE
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER).forEach(trigger => {
            const newTrigger = trigger.cloneNode(true); // Clone để xóa listener cũ
            trigger.parentNode.replaceChild(newTrigger, trigger);

            newTrigger.addEventListener('click', function () {
                const row = this.closest('tr');
                if (!row) return;
                const nodeData = {
                    nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                    appName: row.dataset.appName, nodeStatus: row.dataset.nodeStatus,
                    screenshotFilename: row.dataset.screenshotFilename,
                    screenshotFullUrl: row.dataset.screenshotFullUrl,
                    activityName: row.dataset.activityName,
                    pieLogicalName: row.dataset.pieLogicalName,
                    width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
                };
                if (window.openManagePieConditionsModalGlobal) {
                    window.openManagePieConditionsModalGlobal(nodeData);
                } else {
                    console.error("Hàm openManagePieConditionsModalGlobal chưa được định nghĩa.");
                    alert("Lỗi: Chức năng quản lý PIE chưa sẵn sàng.");
                }
            });
        });

        // Gắn sự kiện cho nút "Tạo PIE Mới"
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER).forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);

            newButton.addEventListener('click', function () {
                const row = this.closest('tr');
                if (!row) return;
                const nodeDataForPieDef = {
                    nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                    appName: row.dataset.appName, nodeStatus: 'unknown',
                    screenshotFilename: row.dataset.screenshotFilename,
                    screenshotFullUrl: row.dataset.screenshotFullUrl,
                    activityName: row.dataset.activityName,
                    width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
                };
                if (window.openManagePieConditionsModalGlobal) {
                    window.openManagePieConditionsModalGlobal(nodeDataForPieDef);
                } else {
                    console.error("Hàm openManagePieConditionsModalGlobal chưa được định nghĩa.");
                    alert("Lỗi: Chức năng tạo PIE chưa sẵn sàng.");
                }
            });
        });

        // Gắn sự kiện cho nút Xóa Node
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN).forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            newButton.addEventListener('click', function () {
                const row = this.closest('tr');
                if (!row) return;
                handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName);
            });
        });

        // Gắn sự kiện cho dropdown Phân loại Node
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT).forEach(select => {
            const newSelect = select.cloneNode(true); // Clone để giữ lại options
            select.parentNode.replaceChild(newSelect, select);
            newSelect.value = select.value; // Giữ lại giá trị đã chọn nếu có
            newSelect.addEventListener('change', handleNodeClassificationChange);
        });

        // Kích hoạt lại Bootstrap Tooltips
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            var tooltipTriggerList = [].slice.call(nodesTableBody.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.forEach(function (tooltipTriggerEl) {
                var existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
                if (existingTooltip) { existingTooltip.dispose(); }
                new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }

    async function fetchAndRenderTableNodes(page = 1, appName = null, statusFilter = null) {
        const currentAppNameVal = appName !== null ? appName : (appNameFilterSelect ? appNameFilterSelect.value : '');
        const currentStatusVal = statusFilter !== null ? statusFilter : (statusFilterSelect ? statusFilterSelect.value : 'unknown');
        const apiUrl = buildApiUrl(page, currentAppNameVal, currentStatusVal);

        if (!nodesTableBody) { console.error("Element nodesTableBody không tìm thấy!"); return; }

        // Hiển thị loading
        let colspanValue = 12; // Số cột trong bảng của bạn
        const headerCells = document.querySelectorAll('#nodesTable thead th');
        if (headerCells.length > 0) {
            colspanValue = headerCells.length;
        }
        nodesTableBody.innerHTML = `<tr><td colspan="${colspanValue}" class="text-center py-3"><i class="fas fa-spinner fa-spin me-2"></i>Đang tải dữ liệu Nodes...</td></tr>`;
        if (paginationContainer) paginationContainer.innerHTML = '';

        try {
            const data = await sendApiRequest(apiUrl, 'GET');
            nodesTableBody.innerHTML = '';
            if (data.nodes && data.nodes.length > 0) {
                data.nodes.forEach(node => {
                    const rowElement = renderNodeRow(node);
                    if (rowElement) nodesTableBody.appendChild(rowElement);
                });
            } else {
                nodesTableBody.innerHTML = `<tr><td colspan="${colspanValue}" class="text-center text-muted fst-italic py-3">Không tìm thấy Node nào khớp với bộ lọc.</td></tr>`;
            }
            if (data.pagination) {
                renderNodePagination(data.pagination, { appName: currentAppNameVal, status: currentStatusVal });
            }
            attachTableTriggers(); // QUAN TRỌNG: Gắn lại listeners sau khi render xong bảng
        } catch (error) {
            console.error("Lỗi khi tải và render Nodes:", error);
            nodesTableBody.innerHTML = `<tr><td colspan="${colspanValue}" class="text-center text-danger py-3">Lỗi tải dữ liệu: ${error.data?.error || error.message || 'Lỗi không xác định'}</td></tr>`;
        }
    }
    // --- Gán hàm fetchAndRenderTableNodes ra global scope để các module khác có thể gọi refresh ---
    window.fetchAndRenderTableNodesGlobal = fetchAndRenderTableNodes;

    // --- Khởi tạo cho Table Handler ---
    if (filterForm) {
        filterForm.addEventListener('submit', function (event) {
            event.preventDefault();
            fetchAndRenderTableNodes(1);
        });
    }

    // Load dữ liệu lần đầu
    const currentUrlParams = new URLSearchParams(window.location.search);
    const initialPage = parseInt(currentUrlParams.get('page') || '1', 10);
    const initialAppName = currentUrlParams.get('app_name_filter') || (appNameFilterSelect ? appNameFilterSelect.value : '');
    const initialStatus = currentUrlParams.get('filter_status') || (statusFilterSelect ? statusFilterSelect.value : 'unknown');

    // Kiểm tra xem tbody có được render từ server không
    if (nodesTableBody && nodesTableBody.children.length > 0 &&
        !(nodesTableBody.firstElementChild && nodesTableBody.firstElementChild.children.length === 1 &&
            nodesTableBody.firstElementChild.firstElementChild.textContent.includes("Không tìm thấy Node nào"))) {
        // Đã có dữ liệu từ server, chỉ cần attach listener cho các element hiện có
        attachTableTriggers();
        if (paginationContainer && paginationContainer.innerHTML.trim() !== '') {
            paginationContainer.querySelectorAll('.page-link').forEach(link => {
                if (link.closest('.page-item.disabled')) return;
                const newLink = link.cloneNode(true);
                link.parentNode.replaceChild(newLink, link);
                newLink.addEventListener('click', function (e) {
                    e.preventDefault();
                    const pageNum = parseInt(this.dataset.page, 10);
                    const appName = appNameFilterSelect ? appNameFilterSelect.value : '';
                    const status = statusFilterSelect ? statusFilterSelect.value : 'unknown';
                    fetchAndRenderTableNodes(pageNum, appName, status);
                });
            });
        }
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) { // Kích hoạt tooltip cho server-rendered elements
            var serverTooltips = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
            serverTooltips.map(function (el) { return new bootstrap.Tooltip(el) });
        }
    } else {
        // Nếu tbody trống hoặc chỉ có thông báo "không tìm thấy", thì fetch từ client
        fetchAndRenderTableNodes(initialPage, initialAppName, initialStatus);
    }
}
