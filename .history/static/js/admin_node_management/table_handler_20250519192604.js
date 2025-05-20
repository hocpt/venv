// static/js/admin_node_management/table_handler.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest } from './utils.js';

export function initTableHandler() {
    const nodesTableBody = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODES_TABLE_BODY);
    const filterForm = document.getElementById(APP_CONFIG.ELEMENT_IDS.NODE_FILTER_FORM);
    const appNameFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.APP_NAME_FILTER_SELECT);
    const statusFilterSelect = document.getElementById(APP_CONFIG.ELEMENT_IDS.STATUS_FILTER_SELECT);
    const paginationContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.PAGINATION_CONTAINER);

    if (!nodesTableBody || !filterForm || !appNameFilterSelect || !statusFilterSelect || !paginationContainer) {
        console.error("TABLE_HANDLER: Một hoặc nhiều DOM elements chính không tìm thấy. Logic của bảng có thể không hoạt động.");
        return;
    }

    function buildApiUrl(page = 1, appName = null, statusFilter = null) {
        const params = new URLSearchParams();
        params.append('page', page);
        if (appName && appName.trim() !== '') {
            params.append('app_name_filter', appName);
        }
        if (statusFilter && statusFilter.trim() !== '' && statusFilter !== 'all') { // Không gửi filter_status nếu là 'all'
            params.append('filter_status', statusFilter);
        }
        return `${APP_CONFIG.API_MANAGED_NODES_URL}?${params.toString()}`;
    }

    function renderNodeRow(node) {
        if (!node || typeof node !== 'object' || !node.screen_id) {
            console.error("renderNodeRow: Dữ liệu node không hợp lệ hoặc thiếu screen_id:", node);
            return null;
        }

        const row = document.createElement('tr');
        // Sử dụng key từ backend Python (ví dụ: 'neo4j_id_for_html')
        row.dataset.nodeNeo4jId = node.neo4j_id_for_html || ''; // QUAN TRỌNG: Đảm bảo key này đúng
        row.dataset.currentScreenId = node.screen_id;
        row.dataset.appName = node.app_name || '';
        row.dataset.nodeStatus = node.status || 'unknown';
        row.dataset.screenshotFilename = node.screenshot_path || '';
        row.dataset.screenshotFullUrl = node.screenshot_full_url || '';
        row.dataset.activityName = node.activity_name || '';
        row.dataset.pieLogicalName = node.logical_pie_name || '';
        row.dataset.width = node.width || '';
        row.dataset.height = node.height || '';

        const screenElementsPageUrl = node.screen_id ? APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id)) : '#';

        let imgHtml = `<span class="text-muted small ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" 
                             style="cursor:pointer; display:inline-block; width:70px; height:100px; border:1px dashed #ccc; text-align:center; line-height:100px; vertical-align:middle;" 
                             title="Quản lý PIE Conditions cho ${node.screen_id}">N/A</span>`;
        if (node.screenshot_full_url) {
            imgHtml = `<img src="${node.screenshot_full_url}" 
                             alt="Ảnh của ${node.screen_id}" 
                             class="node-thumbnail ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" 
                             title="Quản lý PIE Conditions cho ${node.screen_id}">`;
        }
        const cellImage = `<td>${imgHtml}</td>`;

        let logicalNameHtml = `<em class="text-muted small">Chưa có PIE</em>`;
        if (node.logical_pie_name && node.logical_pie_name !== "PIE Def không tìm thấy" && node.logical_pie_name !== "Lỗi lấy PIE Def") {
            logicalNameHtml = `<span title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}${node.logical_pie_name.length > 25 ? '...' : ''}</span>`;
        } else if (node.logical_pie_name) {
            logicalNameHtml = `<em class="text-danger small" title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}${node.logical_pie_name.length > 25 ? '...' : ''}</em>`;
        }

        let statusClass = 'bg-secondary';
        if (node.status === 'defined') statusClass = 'bg-success';
        else if (node.status === 'provisional_unknown') statusClass = 'bg-warning text-dark';
        else if (node.status === 'merged_to_defined') statusClass = 'bg-info text-dark';
        else if (node.status === 'defined_from_unknown') statusClass = 'bg-primary';


        const classificationsOpts = [
            { v: "", l: "-- Chưa --" }, { v: "login_screen", l: "Login" }, { v: "profile_screen", l: "Profile" },
            { v: "feed_screen", l: "Feed/Home" }, { v: "settings_screen", l: "Settings" },
            { v: "popup_dialog", l: "Popup" }, { v: "item_list", l: "Item List" },
            { v: "item_detail", l: "Item Detail" }, { v: "other", l: "Khác" }
        ];
        let classificationSelectHtml = `<select class="form-select form-select-sm ${APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT}" data-current-screen-id="${node.screen_id}" data-app-name="${node.app_name || ''}" aria-label="Phân loại Node">`;
        classificationsOpts.forEach(opt => {
            classificationSelectHtml += `<option value="${opt.v}" ${node.node_classification == opt.v ? 'selected' : ''}>${opt.l}</option>`;
        });
        classificationSelectHtml += `</select><span class="classification-status small ms-1"></span>`;

        let actionButtonsHtml = `<div class="action-button-row mb-1">
                                    <a href="${screenElementsPageUrl}" target="_blank" class="btn btn-xs btn-outline-info view-elements-btn me-1" title="Xem Elements (Trang riêng)" data-bs-toggle="tooltip"><i class="fas fa-search-plus"></i> Elements</a>
                                    <button type="button" class="btn btn-xs btn-outline-danger ${APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN}" title="Xóa Node" data-bs-toggle="tooltip"><i class="fas fa-trash-alt"></i> Xóa</button>
                                 </div>`;

        const isUnknownStatus = node.status === 'unknown' || node.status === 'provisional_unknown';
        if (isUnknownStatus) {
            actionButtonsHtml += `<div class="action-button-row">
                                    <button type="button" class="btn btn-xs btn-outline-success ${APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER}" title="Tạo PIE Mới cho Node này" data-bs-toggle="tooltip"><i class="fas fa-plus-circle"></i> Tạo PIE Mới</button>
                                 </div>`;
        }

        // Sử dụng các trường _iso đã được chuyển đổi từ backend
        const lastSeenDisplay = node.last_seen_iso ? node.last_seen_iso.split('T')[0] : 'N/A';

        row.innerHTML = `
            <td><input type="checkbox" class="node-checkbox" value="${node.screen_id}" aria-label="Chọn node ${node.screen_id}"></td>
            <td><a href="${screenElementsPageUrl}" target="_blank" title="Xem elements của ${node.screen_id}"><code class="small">${(node.screen_id || 'N/A').substring(0, 20)}</code></a></td>
            <td><code class="small">${node.app_name || 'N/A'}</code></td>
            <td><code class="small" title="${node.activity_name || ''}">${(node.activity_name || 'N/A').substring(0, 20)}</code></td>
            ${cellImage}
            <td>${logicalNameHtml}</td>
            <td><span class="badge ${statusClass}">${node.status || 'N/A'}</span></td>
            <td>${classificationSelectHtml}</td>
            <td class="text-center">${node.actual_element_count_rel ?? node.defined_element_count ?? 0}</td>
            <td class="text-center">${node.incoming_transitions_count || 0} / ${node.outgoing_transitions_count || 0}</td>
            <td class="small text-nowrap">${lastSeenDisplay}</td>
            <td class="action-buttons text-nowrap">${actionButtonsHtml}</td>
        `;
        return row;
    }

    function renderNodePagination(paginationData, currentPageFilters) {
        // ... (code render pagination như cũ) ...
        if (!paginationContainer || !paginationData || paginationData.total_pages <= 1) {
            if (paginationContainer) paginationContainer.innerHTML = '';
            return;
        }
        let html = '<ul class="pagination pagination-sm justify-content-center">';
        // Logic tạo HTML cho pagination (giữ nguyên hoặc cải thiện nếu cần)
        html += `<li class="page-item ${paginationData.has_prev ? '' : 'disabled'}"><a class="page-link page-nav-btn" href="#" data-page="${paginationData.prev_num || 1}" aria-label="Previous">&laquo;</a></li>`;
        const windowSize = 2;
        let startPage = Math.max(1, paginationData.page - windowSize);
        let endPage = Math.min(paginationData.total_pages, paginationData.page + windowSize);

        if (startPage > 1) {
            html += `<li class="page-item"><a class="page-link page-nav-btn" href="#" data-page="1">1</a></li>`;
            if (startPage > 2) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        for (let i = startPage; i <= endPage; i++) {
            html += `<li class="page-item ${i === paginationData.page ? 'active' : ''}"><a class="page-link page-nav-btn" href="#" data-page="${i}">${i}</a></li>`;
        }
        if (endPage < paginationData.total_pages) {
            if (endPage < paginationData.total_pages - 1) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
            html += `<li class="page-item"><a class="page-link page-nav-btn" href="#" data-page="${paginationData.total_pages}">${paginationData.total_pages}</a></li>`;
        }
        html += `<li class="page-item ${paginationData.has_next ? '' : 'disabled'}"><a class="page-link page-nav-btn" href="#" data-page="${paginationData.next_num || paginationData.total_pages}" aria-label="Next">&raquo;</a></li>`;
        html += '</ul>';
        paginationContainer.innerHTML = html;
    }

    async function handleDeleteNode(screenId, appName) {
        // ... (code handleDeleteNode như cũ) ...
        if (!confirm(`Bạn có chắc chắn muốn xóa Node '${screenId}' của app '${appName}' không? Hành động này không thể hoàn tác.`)) {
            return;
        }
        if (!APP_CONFIG.API_DELETE_NODE_BASE_URL) {
            console.error("URL API xóa node chưa được cấu hình.");
            alert("Lỗi cấu hình: Không thể xóa node.");
            return;
        }
        const deleteUrl = APP_CONFIG.API_DELETE_NODE_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(screenId));
        try {
            const result = await sendApiRequest(deleteUrl, 'POST', { app_name: appName });
            if (result.success) {
                alert(result.message || 'Xóa Node thành công!');
                fetchAndRenderTableNodes( // Gọi lại để làm mới bảng
                    parseInt(paginationContainer.querySelector('.page-item.active .page-link')?.dataset.page || '1'),
                    appNameFilterSelect.value,
                    statusFilterSelect.value
                );
            } else {
                throw new Error(result.error || result.message || "Xóa Node thất bại từ server.");
            }
        } catch (error) {
            console.error('Lỗi Fetch khi xóa Node:', error);
            alert('Lỗi máy chủ khi xóa Node: ' + (error.data?.error || error.message || 'Lỗi không xác định'));
        }
    }

    async function handleNodeClassificationChange(selectElement) { // Thay event bằng selectElement
        // const selectElement = event.target; // Không cần nữa nếu truyền trực tiếp
        const screenId = selectElement.dataset.currentScreenId;
        const appName = selectElement.dataset.appName;
        const newClassification = selectElement.value;
        const statusSpan = selectElement.closest('td').querySelector('.classification-status');

        if (statusSpan) { statusSpan.textContent = 'Đang lưu...'; statusSpan.className = 'classification-status small ms-1 text-muted'; }

        if (!APP_CONFIG.API_CLASSIFY_NODE_BASE_URL) {
            // ... (xử lý lỗi config)
            return;
        }
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
            // ... (xử lý lỗi)
        }
    }

    /**
     * Hàm này chỉ dùng để khởi tạo lại các thư viện bên thứ 3 như Bootstrap Tooltips
     * sau khi bảng được vẽ lại. Các sự kiện click chính đã được xử lý bằng event delegation.
     */
    function reinitializeThirdPartyLibraries() {
        console.log("[TABLE_HANDLER] Reinitializing third-party libraries (e.g., Tooltips).");
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip && nodesTableBody) {
            const existingTooltips = nodesTableBody.querySelectorAll('[data-bs-toggle="tooltip"]');
            existingTooltips.forEach(el => {
                const tooltipInstance = bootstrap.Tooltip.getInstance(el);
                if (tooltipInstance) {
                    tooltipInstance.dispose();
                }
            });
            const tooltipTriggerList = [].slice.call(nodesTableBody.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }

    // --- GẮN SỰ KIỆN MỘT LẦN BẰNG EVENT DELEGATION ---
    if (nodesTableBody) {
        nodesTableBody.addEventListener('click', function (event) {
            const targetElement = event.target;

            // Xử lý click cho MANAGE_PIE_TRIGGER (ảnh hoặc span N/A)
            const managePieTrigger = targetElement.closest('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER);
            if (managePieTrigger) {
                event.preventDefault();
                const row = managePieTrigger.closest('tr');
                if (!row) {
                    console.error("[TABLE_HANDLER_DLG] Không tìm thấy <tr> cha cho manage-pie-trigger.");
                    return;
                }
                console.log("[TABLE_HANDLER_DLG] MANAGE_PIE_TRIGGER clicked. Reading data from row:", row);
                const neo4jId = row.dataset.nodeNeo4jId; // Đọc từ data attribute
                console.log("[TABLE_HANDLER_DLG] data-node-neo4j-id from row:", neo4jId, "(Type:", typeof neo4jId, ")");


                if (neo4jId === undefined || neo4jId === null || String(neo4jId).trim() === "" || String(neo4jId).toLowerCase() === "none") {
                    console.error("[TABLE_HANDLER_DLG] LỖI: nodeNeo4jId đọc từ dataset cho MANAGE_PIE_TRIGGER bị rỗng, 'None' hoặc không xác định!");
                    alert("Lỗi dữ liệu: Không thể lấy ID Neo4j của Node để quản lý PIE. Giá trị nhận được: '" + neo4jId + "'");
                    return;
                }
                const nodeData = {
                    nodeNeo4jId: neo4jId, // Sử dụng giá trị đã đọc và kiểm tra
                    currentScreenId: row.dataset.currentScreenId,
                    appName: row.dataset.appName,
                    nodeStatus: row.dataset.nodeStatus,
                    screenshotFilename: row.dataset.screenshotFilename,
                    screenshotFullUrl: row.dataset.screenshotFullUrl,
                    activityName: row.dataset.activityName,
                    pieLogicalName: row.dataset.pieLogicalName || '',
                    width: parseInt(row.dataset.width) || null,
                    height: parseInt(row.dataset.height) || null
                };
                console.log("[TABLE_HANDLER_DLG] nodeData FOR MANAGE_PIE_TRIGGER:", JSON.stringify(nodeData, null, 2));
                if (window.openManagePieConditionsModalGlobal) {
                    window.openManagePieConditionsModalGlobal(nodeData);
                } else { console.error("Hàm openManagePieConditionsModalGlobal không tồn tại."); }
                return;
            }

            // Xử lý click cho DEFINE_NEW_PIE_TRIGGER (nút "Tạo PIE Mới")
            const definePieTrigger = targetElement.closest('.' + APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER);
            if (definePieTrigger) {
                event.preventDefault();
                const row = definePieTrigger.closest('tr');
                if (!row) {
                    console.error("[TABLE_HANDLER_DLG] Không tìm thấy <tr> cha cho define-new-pie-trigger.");
                    return;
                }
                const neo4jId = row.dataset.nodeNeo4jId; // Đọc từ data attribute
                console.log("[TABLE_HANDLER_DLG] DEFINE_NEW_PIE_TRIGGER clicked. data-node-neo4j-id from row:", neo4jId, "(Type:", typeof neo4jId, ")");

                if (neo4jId === undefined || neo4jId === null || String(neo4jId).trim() === "" || String(neo4jId).toLowerCase() === "none") {
                    console.error("[TABLE_HANDLER_DLG] LỖI: nodeNeo4jId đọc từ dataset cho DEFINE_NEW_PIE_TRIGGER bị rỗng, 'None' hoặc không xác định!");
                    alert("Lỗi dữ liệu: Không thể lấy ID Neo4j của Node để tạo PIE mới. Giá trị nhận được: '" + neo4jId + "'");
                    return;
                }
                const nodeDataForPieDef = {
                    nodeNeo4jId: neo4jId, // Sử dụng giá trị đã đọc và kiểm tra
                    currentScreenId: row.dataset.currentScreenId,
                    appName: row.dataset.appName,
                    nodeStatus: row.dataset.nodeStatus,
                    screenshotFilename: row.dataset.screenshotFilename,
                    screenshotFullUrl: row.dataset.screenshotFullUrl,
                    activityName: row.dataset.activityName,
                    width: parseInt(row.dataset.width) || null,
                    height: parseInt(row.dataset.height) || null
                };
                console.log("[TABLE_HANDLER_DLG] nodeData FOR DEFINE_NEW_PIE_TRIGGER:", JSON.stringify(nodeDataForPieDef, null, 2));
                if (window.openManagePieConditionsModalGlobal) {
                    window.openManagePieConditionsModalGlobal(nodeDataForPieDef);
                } else { console.error("Hàm openManagePieConditionsModalGlobal không tồn tại."); }
                return;
            }

            // Xử lý click cho DELETE_NODE_BTN
            const deleteNodeBtn = targetElement.closest('.' + APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN);
            if (deleteNodeBtn) {
                event.preventDefault();
                const row = deleteNodeBtn.closest('tr');
                if (!row) return;
                handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName);
                return;
            }

            // Xử lý click cho nút phân trang
            const pageNavButton = targetElement.closest('.page-link.page-nav-btn');
            if (pageNavButton && !pageNavButton.closest('.page-item.disabled')) {
                event.preventDefault();
                const pageNum = parseInt(pageNavButton.dataset.page, 10);
                const appName = appNameFilterSelect ? appNameFilterSelect.value : '';
                const status = statusFilterSelect ? statusFilterSelect.value : 'all'; // Mặc định là 'all' nếu không có
                fetchAndRenderTableNodes(pageNum, appName, status);
                return;
            }
        });

        // Gắn listener cho việc thay đổi NODE_CLASSIFICATION_SELECT
        nodesTableBody.addEventListener('change', function (event) {
            const targetElement = event.target;
            if (targetElement.classList.contains(APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT)) {
                handleNodeClassificationChange(targetElement); // Truyền trực tiếp selectElement
            }
        });
    }


    async function fetchAndRenderTableNodes(page = 1, appName = null, statusFilter = null) {
        const currentAppNameVal = appName !== null ? appName : (appNameFilterSelect ? appNameFilterSelect.value : '');
        const currentStatusVal = statusFilter !== null ? statusFilter : (statusFilterSelect ? statusFilterSelect.value : 'all'); // Mặc định là 'all'

        if (!APP_CONFIG.API_MANAGED_NODES_URL) {
            console.error("TABLE_HANDLER: API_MANAGED_NODES_URL is not configured.");
            if (nodesTableBody) nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-danger py-3">Lỗi cấu hình: Không thể tải dữ liệu.</td></tr>`;
            return;
        }
        const apiUrl = buildApiUrl(page, currentAppNameVal, currentStatusVal);
        console.log("[TABLE_HANDLER] Fetching nodes from:", apiUrl);


        if (!nodesTableBody) { console.error("Element nodesTableBody không tìm thấy!"); return; }

        let colspanValue = 12; // Giá trị mặc định
        const headerCells = document.querySelectorAll('#nodesTable thead th');
        if (headerCells.length > 0) {
            colspanValue = headerCells.length;
        }
        nodesTableBody.innerHTML = `<tr><td colspan="${colspanValue}" class="text-center py-3"><i class="fas fa-spinner fa-spin me-2"></i>Đang tải dữ liệu Nodes...</td></tr>`;
        if (paginationContainer) paginationContainer.innerHTML = '';

        try {
            const data = await sendApiRequest(apiUrl, 'GET');
            console.log("[TABLE_HANDLER] Data received from API:", data);
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
            reinitializeThirdPartyLibraries(); // Gọi để khởi tạo lại tooltips
        } catch (error) {
            console.error("Lỗi khi tải và render Nodes:", error);
            let errorMsg = 'Lỗi không xác định';
            if (error.data && error.data.error) errorMsg = error.data.error;
            else if (error.message) errorMsg = error.message;
            if (nodesTableBody) nodesTableBody.innerHTML = `<tr><td colspan="${colspanValue}" class="text-center text-danger py-3">Lỗi tải dữ liệu: ${errorMsg}</td></tr>`;
        }
    }
    window.fetchAndRenderTableNodesGlobal = fetchAndRenderTableNodes; // Gán vào window để gọi từ nơi khác nếu cần

    // --- Khởi tạo cho Table Handler ---
    if (filterForm) {
        filterForm.addEventListener('submit', function (event) {
            event.preventDefault();
            fetchAndRenderTableNodes(1, appNameFilterSelect.value, statusFilterSelect.value);
        });
    }

    // Lấy tham số từ URL để fetch lần đầu (nếu có)
    const currentUrlParams = new URLSearchParams(window.location.search);
    const initialPage = parseInt(currentUrlParams.get('page') || '1', 10);
    const initialAppName = currentUrlParams.get('app_name_filter') || (appNameFilterSelect ? appNameFilterSelect.value : '');
    const initialStatus = currentUrlParams.get('filter_status') || (statusFilterSelect ? statusFilterSelect.value : 'all'); // Mặc định 'all'

    // Chỉ fetchAndRenderTableNodes nếu bảng rỗng hoặc không có dữ liệu từ server-side rendering
    // Điều này tránh việc gọi API 2 lần không cần thiết nếu bảng đã được render bởi Flask.
    // Tuy nhiên, với cách tiếp cận SPA-like này, chúng ta thường sẽ fetch khi JS load.
    fetchAndRenderTableNodes(initialPage, initialAppName, initialStatus);
}
