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
        return `${APP_CONFIG.API_MANAGED_NODES_URL}?${params.toString()}`;
    }

    /**
     * Render một hàng (<tr>) cho một Node.
     * @param {object} node - Dữ liệu của Node từ API.
     * @returns {HTMLTableRowElement | null} Element <tr> đã được tạo, hoặc null nếu node không hợp lệ.
     */
    function renderNodeRow(node) {
        if (!node || typeof node !== 'object' || !node.screen_id) {
            console.error("renderNodeRow: Dữ liệu node không hợp lệ hoặc thiếu screen_id:", node);
            return null;
        }

        const row = document.createElement('tr');
        row.dataset.nodeNeo4jId = node.id || node.element_id || '';
        row.dataset.currentScreenId = node.screen_id; // screen_id là bắt buộc
        row.dataset.appName = node.app_name || '';
        row.dataset.nodeStatus = node.status || 'unknown';
        row.dataset.screenshotFilename = node.screenshot_path || '';
        row.dataset.screenshotFullUrl = node.screenshot_full_url || '';
        row.dataset.activityName = node.activity_name || '';
        row.dataset.pieLogicalName = node.logical_pie_name || '';
        row.dataset.width = node.width || '';
        row.dataset.height = node.height || '';

        const screenElementsPageUrl = node.screen_id ? APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id)) : '#';

        // --- SỬA LỖI RENDER ẢNH THUMBNAIL ---
        let imgHtml = `<span class="text-muted small ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" 
                             style="cursor:pointer; display:inline-block; width:70px; height:100px; border:1px dashed #ccc; text-align:center; line-height:100px; vertical-align:middle;" 
                             title="Quản lý PIE Conditions cho ${node.screen_id}">N/A</span>`;
        if (node.screenshot_full_url) {
            // Sử dụng template literals (dấu `) và ${variable} để chèn giá trị biến
            imgHtml = `<img src="${node.screenshot_full_url}" 
                             alt="Ảnh của ${node.screen_id}" 
                             class="node-thumbnail ${APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER}" 
                             title="Quản lý PIE Conditions cho ${node.screen_id}">`;
        }
        const cellImage = `<td>${imgHtml}</td>`;
        // --- KẾT THÚC SỬA LỖI RENDER ẢNH ---

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
            <td><input type="checkbox" class="node-checkbox" value="${node.screen_id}" aria-label="Chọn node ${node.screen_id}"></td>
            <td><a href="${screenElementsPageUrl}" target="_blank" title="Xem elements của ${node.screen_id}"><code class="small">${(node.screen_id).substring(0, 20)}</code></a></td>
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
        // Đảm bảo APP_CONFIG.API_DELETE_NODE_BASE_URL đã được khởi tạo
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
                fetchAndRenderTableNodes();
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

        if (!APP_CONFIG.API_CLASSIFY_NODE_BASE_URL) {
            console.error("URL API phân loại node chưa được cấu hình.");
            alert("Lỗi cấu hình: Không thể phân loại node.");
            if (statusSpan) { statusSpan.textContent = 'Lỗi CFG!'; }
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

        // Xóa các listener cũ bằng cách clone và replace (đơn giản và hiệu quả cho các element cụ thể)
        // Hoặc sử dụng event delegation trên nodesTableBody nếu muốn tối ưu hơn nữa cho nhiều loại sự kiện.

        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER).forEach(trigger => {
            const newTrigger = trigger.cloneNode(true);
            trigger.parentNode.replaceChild(newTrigger, trigger); // Thay thế element cũ bằng clone để xóa listener

            nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER).forEach(trigger => {
                const newTrigger = trigger.cloneNode(true);
                trigger.parentNode.replaceChild(newTrigger, trigger); // Thay thế element cũ bằng clone để xóa listener

                newTrigger.addEventListener('click', function () { // 'this' ở đây là newTrigger (ảnh hoặc span N/A)
                    const row = this.closest('tr'); // Tìm <tr> cha của newTrigger
                    if (!row) {
                        console.error("[TABLE_HANDLER] Không tìm thấy <tr> cha cho manage-pie-trigger.");
                        return;
                    }

                    // ---- ĐIỂM CẦN KIỂM TRA SỐ 1 ----
                    console.log("[TABLE_HANDLER] MANAGE_PIE_TRIGGER clicked. Reading data from row:", row);
                    console.log("[TABLE_HANDLER] data-node-neo4j-id from row:", row.dataset.nodeNeo4jId);
                    console.log("[TABLE_HANDLER] data-current-screen-id from row:", row.dataset.currentScreenId);
                    // Log thêm các dataset khác nếu cần

                    // Kiểm tra giá trị nodeNeo4jId đọc được
                    const neo4jId = row.dataset.nodeNeo4jId;
                    if (neo4jId === undefined || neo4jId === null || String(neo4jId).trim() === "") {
                        console.error("[TABLE_HANDLER] LỖI QUAN TRỌNG: nodeNeo4jId đọc từ dataset cho MANAGE_PIE_TRIGGER bị rỗng hoặc không xác định!");
                        alert("Lỗi dữ liệu: Không thể lấy ID Neo4j của Node để quản lý PIE.");
                        return;
                    }

                    const nodeData = {
                        nodeNeo4jId: neo4jId, // Sử dụng giá trị đã kiểm tra
                        currentScreenId: row.dataset.currentScreenId,
                        appName: row.dataset.appName,
                        nodeStatus: row.dataset.nodeStatus,
                        screenshotFilename: row.dataset.screenshotFilename,
                        screenshotFullUrl: row.dataset.screenshotFullUrl,
                        activityName: row.dataset.activityName,
                        pieLogicalName: row.dataset.pieLogicalName || '', // Đảm bảo không undefined
                        width: parseInt(row.dataset.width) || null,
                        height: parseInt(row.dataset.height) || null
                    };
                    console.log("[TABLE_HANDLER] nodeData FOR MANAGE_PIE_TRIGGER:", JSON.stringify(nodeData, null, 2));

                    if (window.openManagePieConditionsModalGlobal) {
                        window.openManagePieConditionsModalGlobal(nodeData);
                    } else {
                        console.error("Hàm openManagePieConditionsModalGlobal chưa được định nghĩa.");
                        alert("Lỗi: Chức năng quản lý PIE chưa sẵn sàng.");
                    }
                });
            });
        });
        if (nodesTableBody) {
            nodesTableBody.addEventListener('click', function (event) {
                const targetElement = event.target;

                // Xử lý click cho MANAGE_PIE_TRIGGER (ảnh hoặc span N/A)
                const managePieTrigger = targetElement.closest('.' + APP_CONFIG.CSS_CLASSES.MANAGE_PIE_TRIGGER);
                if (managePieTrigger) {
                    event.preventDefault(); // Ngăn hành vi mặc định nếu là link
                    const row = managePieTrigger.closest('tr');
                    if (!row) {
                        console.error("[TABLE_HANDLER_DLG] Không tìm thấy <tr> cha cho manage-pie-trigger.");
                        return;
                    }
                    console.log("[TABLE_HANDLER_DLG] MANAGE_PIE_TRIGGER clicked. Reading data from row:", row);
                    console.log("[TABLE_HANDLER_DLG] data-node-neo4j-id from row:", row.dataset.nodeNeo4jId);

                    const neo4jId = row.dataset.nodeNeo4jId;
                    if (neo4jId === undefined || neo4jId === null || String(neo4jId).trim() === "") {
                        console.error("[TABLE_HANDLER_DLG] LỖI: nodeNeo4jId đọc từ dataset cho MANAGE_PIE_TRIGGER bị rỗng!");
                        alert("Lỗi dữ liệu: Không thể lấy ID Neo4j của Node để quản lý PIE.");
                        return;
                    }
                    const nodeData = { /* ... (lấy nodeData như code trước đó) ... */
                        nodeNeo4jId: neo4jId,
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
                    return; // Đã xử lý, không cần kiểm tra các trigger khác
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
                    console.log("[TABLE_HANDLER_DLG] DEFINE_NEW_PIE_TRIGGER clicked. Reading data from row:", row);
                    console.log("[TABLE_HANDLER_DLG] data-node-neo4j-id from row:", row.dataset.nodeNeo4jId);

                    const neo4jId = row.dataset.nodeNeo4jId;
                    if (neo4jId === undefined || neo4jId === null || String(neo4jId).trim() === "") {
                        console.error("[TABLE_HANDLER_DLG] LỖI: nodeNeo4jId đọc từ dataset cho DEFINE_NEW_PIE_TRIGGER bị rỗng!");
                        alert("Lỗi dữ liệu: Không thể lấy ID Neo4j của Node để tạo PIE mới.");
                        return;
                    }
                    const nodeDataForPieDef = { /* ... (lấy nodeData như code trước đó) ... */
                        nodeNeo4jId: neo4jId,
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
            });

            // Gắn listener cho việc thay đổi NODE_CLASSIFICATION_SELECT
            nodesTableBody.addEventListener('change', function (event) {
                const targetElement = event.target;
                if (targetElement.classList.contains(APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT)) {
                    handleNodeClassificationChange(event); // Gọi hàm xử lý đã có
                }
            });
        }
        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DEFINE_NEW_PIE_TRIGGER).forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);

            newButton.addEventListener('click', function () { // 'this' ở đây là newButton
                const row = this.closest('tr'); // Tìm <tr> cha của newButton
                if (!row) {
                    console.error("[TABLE_HANDLER] Không tìm thấy <tr> cha cho define-new-pie-trigger.");
                    return;
                }

                // ---- ĐIỂM CẦN KIỂM TRA SỐ 2 ----
                console.log("[TABLE_HANDLER] DEFINE_NEW_PIE_TRIGGER clicked. Reading data from row:", row);
                console.log("[TABLE_HANDLER] data-node-neo4j-id from row:", row.dataset.nodeNeo4jId);
                console.log("[TABLE_HANDLER] data-current-screen-id from row:", row.dataset.currentScreenId);
                // Log thêm các dataset khác nếu cần

                // Kiểm tra giá trị nodeNeo4jId đọc được
                const neo4jId = row.dataset.nodeNeo4jId;
                if (neo4jId === undefined || neo4jId === null || String(neo4jId).trim() === "") {
                    console.error("[TABLE_HANDLER] LỖI QUAN TRỌNG: nodeNeo4jId đọc từ dataset cho DEFINE_NEW_PIE_TRIGGER bị rỗng hoặc không xác định!");
                    alert("Lỗi dữ liệu: Không thể lấy ID Neo4j của Node để tạo PIE mới.");
                    return;
                }

                // nodeStatus sẽ luôn là 'unknown' hoặc 'provisional_unknown' cho luồng này
                // nhưng ta vẫn lấy từ dataset để nhất quán nếu có thay đổi sau này
                const nodeDataForPieDef = {
                    nodeNeo4jId: neo4jId, // Sử dụng giá trị đã kiểm tra
                    currentScreenId: row.dataset.currentScreenId,
                    appName: row.dataset.appName,
                    nodeStatus: row.dataset.nodeStatus, // Lấy status từ row, JS sau đó sẽ xử lý là 'unknown'
                    screenshotFilename: row.dataset.screenshotFilename,
                    screenshotFullUrl: row.dataset.screenshotFullUrl,
                    activityName: row.dataset.activityName,
                    width: parseInt(row.dataset.width) || null,
                    height: parseInt(row.dataset.height) || null,
                    // pieLogicalName không cần thiết vì đang tạo mới
                };
                console.log("[TABLE_HANDLER] nodeData FOR DEFINE_NEW_PIE_TRIGGER:", JSON.stringify(nodeDataForPieDef, null, 2));

                if (window.openManagePieConditionsModalGlobal) {
                    // Luồng tạo PIE mới cho node "unknown" cũng đi qua modal chọn conditions trước
                    window.openManagePieConditionsModalGlobal(nodeDataForPieDef);
                } else {
                    console.error("Hàm openManagePieConditionsModalGlobal chưa được định nghĩa.");
                    alert("Lỗi: Chức năng tạo PIE chưa sẵn sàng.");
                }
            });
        });

        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.DELETE_NODE_BTN).forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            newButton.addEventListener('click', function () {
                const row = this.closest('tr');
                if (!row) return;
                handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName);
            });
        });

        nodesTableBody.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.NODE_CLASSIFICATION_SELECT).forEach(select => {
            const newSelect = select.cloneNode(true);
            select.parentNode.replaceChild(newSelect, select);
            newSelect.value = select.value;
            newSelect.addEventListener('change', handleNodeClassificationChange);
        });

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
        // Đảm bảo APP_CONFIG.API_MANAGED_NODES_URL đã được khởi tạo
        if (!APP_CONFIG.API_MANAGED_NODES_URL) {
            console.error("TABLE_HANDLER: API_MANAGED_NODES_URL is not configured.");
            nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-danger py-3">Lỗi cấu hình: Không thể tải dữ liệu.</td></tr>`;
            return;
        }
        const apiUrl = buildApiUrl(page, currentAppNameVal, currentStatusVal);

        if (!nodesTableBody) { console.error("Element nodesTableBody không tìm thấy!"); return; }

        let colspanValue = 12;
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
    window.fetchAndRenderTableNodesGlobal = fetchAndRenderTableNodes;

    // --- Khởi tạo cho Table Handler ---
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

    if (nodesTableBody && nodesTableBody.children.length > 0 &&
        !(nodesTableBody.firstElementChild && nodesTableBody.firstElementChild.children.length === 1 &&
            nodesTableBody.firstElementChild.firstElementChild.textContent.includes("Không tìm thấy Node nào"))) {
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
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            var serverTooltips = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
            serverTooltips.map(function (el) { return new bootstrap.Tooltip(el) });
        }
    } else {
        fetchAndRenderTableNodes(initialPage, initialAppName, initialStatus);
    }
}
