// static/js/admin_node_management/table_handler.js
import { APP_CONFIG } from './config.js'; // Giả sử bạn cần APP_CONFIG
import { sendApiRequest } from './utils.js';
// Không import openManagePieConditionsModal ở đây nếu bạn gọi qua window object

// ... (các hàm con như buildApiUrl, renderNodeRow, renderNodePagination, handleDeleteNode, handleNodeClassificationChange, attachTableTriggers) ...
// ... (Nội dung các hàm này như đã cung cấp ở phản hồi trước)

// ĐÂY LÀ HÀM CHÍNH CẦN EXPORT
export function initTableHandler() { // Thêm từ khóa 'export'
    const nodesTableBody = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODES_TABLE_BODY);
    const filterForm = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODE_FILTER_FORM);
    const appNameFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.APP_NAME_FILTER_SELECT);
    const statusFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.STATUS_FILTER_SELECT);
    const paginationContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.PAGINATION_CONTAINER);

    // --- Hàm renderNodeRow ---
    function renderNodeRow(node) {
        const row = document.createElement('tr');
        // ... (gán các data-* attributes) ...
        row.dataset.nodeNeo4jId = node.id || node.element_id || '';
        row.dataset.currentScreenId = node.screen_id || '';
        // ... (các data attributes khác) ...
        row.dataset.screenshotFullUrl = node.screenshot_full_url || ''; // Quan trọng cho ảnh
        row.dataset.width = node.width || '';
        row.dataset.height = node.height || '';


        const screenElementsUrl = APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id || ''));

        let imgHtml = `<span class="text-muted small ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" style="cursor:pointer; display:inline-block; width:70px; height:70px; border:1px dashed #ccc; text-align:center; line-height:70px;" title="Quản lý PIE Conditions">N/A</span>`;
        if (node.screenshot_full_url) {
            imgHtml = `<img src="${node.screenshot_full_url}" alt="ss_${node.screen_id}" class="node-thumbnail ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" title="Quản lý PIE Conditions">`;
        }
        // ... (Phần còn lại của renderNodeRow như đã cung cấp)
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

    // --- Hàm renderNodePagination ---
    function renderNodePagination(paginationData, currentPageFilters) {
        // ... (Nội dung hàm như đã cung cấp)
        if (!paginationContainer || !paginationData || paginationData.total_pages <= 1) {
            if (paginationContainer) paginationContainer.innerHTML = ''; return;
        }
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
            // Tạo listener mới mỗi lần render pagination
            link.addEventListener('click', function (e) {
                e.preventDefault();
                fetchAndRenderTableNodes(parseInt(this.dataset.page), currentPageFilters.appName, currentPageFilters.status);
            });
        });
    }

    // --- Hàm attachTableTriggers ---
    function attachTableTriggers() {
        if (!nodesTableBody) return;

        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER).forEach(trigger => {
            const row = trigger.closest('tr'); if (!row) return;
            const nodeData = {
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: row.dataset.nodeStatus,
                screenshotFilename: row.dataset.screenshotFilename,
                screenshotFullUrl: row.dataset.screenshotFullUrl, // **THÊM CÁI NÀY**
                activityName: row.dataset.activityName,
                pieLogicalName: row.dataset.pieLogicalName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            trigger.onclick = () => { if (window.openManagePieConditionsModalGlobal) window.openManagePieConditionsModalGlobal(nodeData); };
        });

        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER).forEach(button => {
            const row = button.closest('tr'); if (!row) return;
            const nodeDataForPieDef = {
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: 'unknown',
                screenshotFilename: row.dataset.screenshotFilename,
                screenshotFullUrl: row.dataset.screenshotFullUrl, // **THÊM CÁI NÀY**
                activityName: row.dataset.activityName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            button.onclick = () => { if (window.openManagePieConditionsModalGlobal) window.openManagePieConditionsModalGlobal(nodeDataForPieDef); };
        });

        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN).forEach(button => {
            const row = button.closest('tr'); if (!row) return;
            button.onclick = () => handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName);
        });
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT).forEach(select => {
            select.onchange = handleNodeClassificationChange;
        });

        // Kích hoạt Bootstrap Tooltips
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            var tooltipTriggerList = [].slice.call(nodesTableBody.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                // Xóa tooltip cũ nếu có trước khi tạo mới để tránh lỗi
                var existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
                if (existingTooltip) { existingTooltip.dispose(); }
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }

    // --- Hàm fetchAndRenderTableNodes ---
    async function fetchAndRenderTableNodes(page = 1, appName = null, statusFilter = null) {
        const currentAppNameVal = appName !== null ? appName : (appNameFilterSelect ? appNameFilterSelect.value : '');
        const currentStatusVal = statusFilter !== null ? statusFilter : (statusFilterSelect ? statusFilterSelect.value : 'unknown');
        const apiUrl = buildApiUrl(page, currentAppNameVal, currentStatusVal);

        if (!nodesTableBody) { console.error("Element nodesTableBody không tìm thấy!"); return; }
        nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center py-3"><i class="fas fa-spinner fa-spin me-2"></i>Đang tải dữ liệu Nodes...</td></tr>`;
        if (paginationContainer) paginationContainer.innerHTML = '';

        try {
            const data = await sendApiRequest(apiUrl, 'GET');
            nodesTableBody.innerHTML = '';
            if (data.nodes && data.nodes.length > 0) {
                data.nodes.forEach(node => { nodesTableBody.appendChild(renderNodeRow(node)); });
            } else {
                nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-muted fst-italic py-3">Không tìm thấy Node nào khớp với bộ lọc.</td></tr>`;
            }
            if (data.pagination) {
                renderNodePagination(data.pagination, { appName: currentAppNameVal, status: currentStatusVal });
            }
            attachTableTriggers(); // QUAN TRỌNG: Gắn lại listeners sau khi render xong bảng
        } catch (error) {
            console.error("Lỗi khi tải và render Nodes:", error);
            nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-danger py-3">Lỗi tải dữ liệu: ${error.data?.error || error.message || 'Lỗi không xác định'}</td></tr>`;
        }
    }
    // --- Gán hàm fetchAndRenderTableNodes ra global scope để các module khác có thể gọi refresh ---
    window.fetchAndRenderTableNodes = fetchAndRenderTableNodes;

    // --- Xử lý sự kiện filter và tải dữ liệu lần đầu ---
    if (filterForm) {
        filterForm.addEventListener('submit', function (event) {
            event.preventDefault();
            fetchAndRenderTableNodes(1);
        });
    }

    const currentUrlParams = new URLSearchParams(window.location.search);
    const initialPage = parseInt(currentUrlParams.get('page') || '1', 10);
    const initialAppName = currentUrlParams.get('app_name_filter') || (appNameFilterSelect ? appNameFilterSelect.value : '');
    const initialStatus = currentUrlParams.get('filter_status') || (statusFilterSelect ? statusFilterSelect.value : 'unknown');

    // Kiểm tra xem tbody có được render từ server không
    if (nodesTableBody && nodesTableBody.children.length > 0 &&
        !(nodesTableBody.firstElementChild && nodesTableBody.firstElementChild.children.length === 1 &&
            nodesTableBody.firstElementChild.firstElementChild.textContent.includes("Không tìm thấy Node nào"))) {
        attachTableTriggers(); // Gắn listeners cho các hàng đã render từ server
        if (paginationContainer && paginationContainer.innerHTML.trim() !== '') { // Nếu server đã render pagination
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
    } else { // Nếu tbody trống hoặc chỉ có thông báo "không tìm thấy" -> fetch từ client
        fetchAndRenderTableNodes(initialPage, initialAppName, initialStatus);
    }
}