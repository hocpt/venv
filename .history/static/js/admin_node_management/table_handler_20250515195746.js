// static/js/admin_node_management/table_handler.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest } from './utils.js';
// import { openManagePieConditionsModal } from './modal_manage_pie.js'; // Sẽ gọi qua window

export function initTableHandler() {
    const nodesTableBody = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODES_TABLE_BODY);
    const filterForm = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODE_FILTER_FORM);
    const appNameFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.APP_NAME_FILTER_SELECT);
    const statusFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.STATUS_FILTER_SELECT);
    const paginationContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.PAGINATION_CONTAINER);

    function buildApiUrl(page = 1, appName = null, statusFilter = null) {
        const params = new URLSearchParams();
        params.append('page', page);
        if (appName) params.append('app_name_filter', appName);
        if (statusFilter) params.append('filter_status', statusFilter);
        return `${APP_CONFIG.API_MANAGED_NODES_URL}?${params.toString()}`;
    }

    function renderNodeRow(node) {
        const row = document.createElement('tr');
        row.dataset.nodeNeo4jId = node.id || node.element_id || '';
        row.dataset.currentScreenId = node.screen_id || '';
        row.dataset.appName = node.app_name || '';
        row.dataset.nodeStatus = node.status || 'unknown';
        row.dataset.screenshotFilename = node.screenshot_path || '';
        row.dataset.activityName = node.activity_name || '';
        row.dataset.pieLogicalName = node.logical_pie_name || '';
        row.dataset.width = node.width || '';
        row.dataset.height = node.height || '';
        row.dataset.screenshotFullUrl = node.screenshot_full_url || '';
        const screenElementsUrl = APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id || ''));

        let imgHtml = `<span class="text-muted small ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" style="cursor:pointer; display:inline-block; width:70px; height:70px; border:1px dashed #ccc; text-align:center; line-height:70px;" title="Quản lý PIE Conditions">N/A</span>`;
        if (node.screenshot_full_url) {
            imgHtml = `<img src="${node.screenshot_full_url}" alt="ss_${node.screen_id}" class="node-thumbnail ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" title="Quản lý PIE Conditions">`;
        }

        let logicalNameHtml = `<em class="text-muted small">Chưa có PIE</em>`;
        if (node.logical_pie_name && node.logical_pie_name !== "PIE Def không tìm thấy" && node.logical_pie_name !== "Lỗi lấy PIE Def") {
            logicalNameHtml = `<span title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}</span>`;
        } else if (node.logical_pie_name) {
            logicalNameHtml = `<em class="text-danger small" title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}</em>`;
        }

        let statusClass = 'bg-secondary';
        if (node.status === 'defined') statusClass = 'bg-success';
        else if (node.status === 'provisional_unknown') statusClass = 'bg-warning text-dark';

        const classificationsOpts = [{ v: "", l: "-- Chưa --" }, { v: "login_screen", l: "Login" }, { v: "profile_screen", l: "Profile" }, { v: "feed_screen", l: "Feed/Home" }, { v: "settings_screen", l: "Settings" }, { v: "popup_dialog", l: "Popup" }, { v: "item_list", l: "Item List" }, { v: "item_detail", l: "Item Detail" }, { v: "other", l: "Khác" }];
        let classificationSelectHtml = `<select class="form-select form-select-sm ${APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT}" data-current-screen-id="${node.screen_id}" data-app-name="${node.app_name}">`;
        classificationsOpts.forEach(opt => {
            classificationSelectHtml += `<option value="${opt.v}" ${node.node_classification == opt.v ? 'selected' : ''}>${opt.l}</option>`;
        });
        classificationSelectHtml += `</select><span class="classification-status small ms-1"></span>`;

        let actionButtonsHtml = `<div class="action-button-row mb-1">
                                    <a href="${screenElementsUrl}" target="_blank" class="btn btn-xs btn-outline-info view-elements-btn me-1" title="Xem Elements (Trang riêng)" data-bs-toggle="tooltip"><i class="fas fa-search-plus"></i> Elements</a>
                                    <button type="button" class="btn btn-xs btn-outline-danger ${APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN}" title="Xóa Node" data-bs-toggle="tooltip"><i class="fas fa-trash-alt"></i> Xóa</button>
                                 </div>`;
        if (node.status === 'unknown' || node.status === 'provisional_unknown') {
            actionButtonsHtml += `<div class="action-button-row">
                                    <button type="button" class="btn btn-xs btn-outline-success ${APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER}" title="Tạo PIE Mới cho Node này" data-bs-toggle="tooltip"><i class="fas fa-plus-circle"></i> Tạo PIE Mới</button>
                                 </div>`;
        }
        row.innerHTML = `
            <td><input type="checkbox" class="node-checkbox" value="${node.screen_id || ''}"></td>
            <td><a href="${screenElementsUrl}" target="_blank"><code class="small">${(node.screen_id || 'N/A').substring(0, 20)}</code></a></td>
            <td><code class="small">${node.app_name || 'N/A'}</code></td>
            <td><code class="small" title="${node.activity_name || ''}">${(node.activity_name || 'N/A').substring(0, 20)}</code></td>
            <td>${imgHtml}</td>
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
            if (paginationContainer) paginationContainer.innerHTML = ''; return;
        }
        // ... (Logic render pagination giữ nguyên như trong file HTML, chỉ cần đảm bảo nó dùng đúng class và data-page)
        let html = '<ul class="pagination pagination-sm justify-content-center">';
        html += `<li class="page-item ${paginationData.has_prev ? '' : 'disabled'}"><a class="page-link" href="#" data-page="${paginationData.prev_num || 1}">&laquo;</a></li>`;
        const window = 2;
        let start = Math.max(1, paginationData.page - window);
        let end = Math.min(paginationData.total_pages, paginationData.page + window);
        if (start > 1) { html += `<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>`; if (start > 2) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`; }
        for (let i = start; i <= end; i++) { html += `<li class="page-item ${i === paginationData.page ? 'active' : ''}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`; }
        if (end < paginationData.total_pages) { if (end < paginationData.total_pages - 1) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`; html += `<li class="page-item"><a class="page-link" href="#" data-page="${paginationData.total_pages}">${paginationData.total_pages}</a></li>`; }
        html += `<li class="page-item ${paginationData.has_next ? '' : 'disabled'}"><a class="page-link" href="#" data-page="${paginationData.next_num || paginationData.total_pages}">&raquo;</a></li>`;
        html += '</ul>';
        paginationContainer.innerHTML = html;
        paginationContainer.querySelectorAll('.page-link').forEach(link => {
            if (link.closest('.page-item.disabled')) return;
            link.addEventListener('click', function (e) {
                e.preventDefault();
                fetchAndRenderTableNodes(parseInt(this.dataset.page), currentPageFilters.appName, currentPageFilters.status);
            });
        });
    }

    async function handleDeleteNode(screenId, appName) {
        if (!confirm(`Bạn chắc chắn muốn xóa Node '${screenId}' của app '${appName}' không?`)) return;
        const deleteUrl = APP_CONFIG.API_DELETE_NODE_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(screenId));
        try {
            const result = await sendApiRequest(deleteUrl, 'POST', { app_name: appName });
            if (result.success) {
                alert(result.message || 'Xóa Node thành công!');
                fetchAndRenderTableNodes(); // Tải lại bảng
            } else { throw new Error(result.error || result.message || "Xóa thất bại."); }
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
            const result = await sendApiRequest(classifyUrl, 'POST', { app_name: appName, node_classification: newClassification });
            if (statusSpan) {
                if (result.success) { statusSpan.textContent = 'Đã lưu!'; statusSpan.className = 'classification-status small ms-1 text-success'; }
                else { statusSpan.textContent = 'Lỗi!'; statusSpan.className = 'classification-status small ms-1 text-danger'; throw new Error(result.error || "Lỗi cập nhật."); }
                setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000);
            }
        } catch (error) {
            if (statusSpan) { statusSpan.textContent = 'Lỗi mạng!'; statusSpan.className = 'classification-status small ms-1 text-danger'; setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000); }
            console.error('Lỗi Fetch khi phân loại Node:', error);
            alert('Lỗi máy chủ: ' + (error.data?.error || error.message || 'Lỗi không xác định'));
        }
    }

    function attachTableTriggers() {
        if (!nodesTableBody) return;
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER).forEach(trigger => {
            const row = trigger.closest('tr'); if (!row) return;
            const nodeData = { /* ... Lấy data từ row.dataset ... */
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: row.dataset.nodeStatus,
                screenshotFullUrl: row.dataset.screenshotFullUrl,
                screenshotFilename: row.dataset.screenshotFilename, activityName: row.dataset.activityName,
                pieLogicalName: row.dataset.pieLogicalName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            trigger.onclick = () => { if (window.openManagePieConditionsModal) window.openManagePieConditionsModal(nodeData); };
        });
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER).forEach(button => {
            const row = button.closest('tr'); if (!row) return;
            const nodeDataForPieDef = { /* ... Lấy data, nodeStatus='unknown' ... */
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: 'unknown',
                screenshotFilename: row.dataset.screenshotFilename, activityName: row.dataset.activityName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            button.onclick = () => { if (window.openManagePieConditionsModal) window.openManagePieConditionsModal(nodeDataForPieDef); };
        });
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN).forEach(button => {
            const row = button.closest('tr'); if (!row) return;
            button.onclick = () => handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName);
        });
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT).forEach(select => {
            select.onchange = handleNodeClassificationChange;
        });
        var tooltipTriggerList = [].slice.call(nodesTableBody.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) { return new bootstrap.Tooltip(tooltipTriggerEl); });
    }

    async function fetchAndRenderTableNodes(page = 1, appName = null, statusFilter = null) {
        const currentAppNameVal = appName !== null ? appName : (appNameFilterSelect ? appNameFilterSelect.value : '');
        const currentStatusVal = statusFilter !== null ? statusFilter : (statusFilterSelect ? statusFilterSelect.value : 'unknown');
        const apiUrl = buildApiUrl(page, currentAppNameVal, currentStatusVal);

        if (!nodesTableBody) { console.error("nodesTableBody không tìm thấy!"); return; }
        nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center py-3"><i class="fas fa-spinner fa-spin me-2"></i>Đang tải...</td></tr>`;
        if (paginationContainer) paginationContainer.innerHTML = '';

        try {
            const data = await sendApiRequest(apiUrl, 'GET');
            nodesTableBody.innerHTML = '';
            if (data.nodes && data.nodes.length > 0) {
                data.nodes.forEach(node => { nodesTableBody.appendChild(renderNodeRow(node)); });
            } else {
                nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-muted fst-italic py-3">Không tìm thấy Node nào.</td></tr>`;
            }
            if (data.pagination) {
                renderNodePagination(data.pagination, { appName: currentAppNameVal, status: currentStatusVal });
            }
            attachTableTriggers();
        } catch (error) {
            console.error("Lỗi khi tải và render Nodes:", error);
            nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-danger py-3">Lỗi: ${error.data?.error || error.message || 'Lỗi không xác định'}</td></tr>`;
        }
    }
    window.fetchAndRenderTableNodes = fetchAndRenderTableNodes; // Expose to global

    // --- Khởi tạo cho Table Handler ---
    if (filterForm) {
        filterForm.addEventListener('submit', function (event) {
            event.preventDefault();
            fetchAndRenderTableNodes(1);
        });
    }
}