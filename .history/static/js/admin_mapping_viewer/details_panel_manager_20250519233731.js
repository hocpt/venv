// static/js/admin_mapping_viewer/details_panel_manager.js
import { APP_CONFIG } from './config_mapping.js';
import { escapeHtml } from './utils_mapping.js'; // Giả sử escapeHtml ở utils
import { openEditTransitionModal } from './modal_edit_transition.js'; // Import hàm mở modal

// DOM Elements của Panel Chi Tiết
let panelTextContentDiv, panelActionsAreaDiv, panelScreenshotAreaDiv,
    panelScreenshotContainer, panelScreenshotImage;

// Hàm lấy các DOM element một lần
function getDetailsPanelDOMElements() {
    const IDS = APP_CONFIG.DOM_ELEMENT_IDS;
    console.log("DETAILS_PANEL: getDetailsPanelDOMElements - Attempting to get elements with IDS:", JSON.parse(JSON.stringify(IDS)));

    panelTextContentDiv = document.getElementById(IDS.detailsPanelTextContent);
    panelActionsAreaDiv = document.getElementById(IDS.detailsPanelActionsArea);
    panelScreenshotAreaDiv = document.getElementById(IDS.detailsPanelScreenshotArea);
    panelScreenshotContainer = document.getElementById(IDS.detailsPanelScreenshotContainer);
    panelScreenshotImage = document.getElementById(IDS.detailsPanelScreenshotImage);

    // Log kết quả của từng getElementById
    console.log(`DETAILS_PANEL: Element '${IDS.detailsPanelTextContent}' found?`, panelTextContentDiv !== null);
    console.log(`DETAILS_PANEL: Element '${IDS.detailsPanelActionsArea}' found?`, panelActionsAreaDiv !== null);
    console.log(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotArea}' found?`, panelScreenshotAreaDiv !== null);
    console.log(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotContainer}' found?`, panelScreenshotContainer !== null);
    console.log(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotImage}' found?`, panelScreenshotImage !== null);
}

/**
 * Khởi tạo Details Panel Manager.
 */
export function initDetailsPanelManager() {
    console.log("DETAILS_PANEL: initDetailsPanelManager called.");
    getDetailsPanelDOMElements();
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotContainer || !panelScreenshotImage) {
        console.error("DETAILS_PANEL: Một hoặc nhiều DOM elements của panel chi tiết không tìm thấy. Kiểm tra ID trong HTML và config_mapping.js DOM_ELEMENT_IDS.");
    } else {
        console.log("DETAILS_PANEL: All required DOM elements for details panel found.");
    }
    console.log("DETAILS_PANEL: Initialized.");
}

/**
 * Hiển thị thông báo mặc định khi không có gì được chọn.
 */
export function showDefaultDetailsMessage() {
    if (panelTextContentDiv) panelTextContentDiv.innerHTML = '<p class="text-muted fst-italic">Nhấp vào một node (màn hình) hoặc cạnh (chuyển tiếp) để xem chi tiết.</p>';
    if (panelActionsAreaDiv) panelActionsAreaDiv.innerHTML = '';
    if (panelScreenshotAreaDiv) panelScreenshotAreaDiv.style.display = 'none';
}

/**
 * Hiển thị chi tiết của một Node (Screen).
 * @param {object} nodeData - Dữ liệu của node từ Cytoscape (node.data()).
 */
export function displayNodeDetails(nodeData) {
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotImage || !panelScreenshotContainer) {
        console.error("DETAILS_PANEL: Không thể hiển thị chi tiết Node, thiếu DOM elements.");
        return;
    }
    console.log("DETAILS_PANEL: Displaying Node Details:", nodeData);

    // Xóa các nút hành động cũ và ảnh cũ
    panelActionsAreaDiv.innerHTML = '';
    panelScreenshotAreaDiv.style.display = 'none';
    panelScreenshotImage.src = '';
    panelScreenshotImage.style.display = 'none';
    panelScreenshotContainer.querySelectorAll('.element-overlay, p.text-danger, p.text-muted, p.text-warning').forEach(el => el.remove());

    let textDetailsHtml = `<h5>Chi tiết Node (Màn hình)</h5>
        <ul class="list-group list-group-flush">
          <li class="list-group-item"><strong>ID:</strong> <code>${escapeHtml(nodeData.id)}</code></li>
          <li class="list-group-item"><strong>Nhãn:</strong> ${escapeHtml(nodeData.label || nodeData.id)}</li>
          <li class="list-group-item"><strong>Activity:</strong> ${escapeHtml(nodeData.activity || 'N/A')}</li>
          <li class="list-group-item"><strong>Trạng thái:</strong> <span class="badge bg-info">${escapeHtml(nodeData.status || 'N/A')}</span></li>
          <li class="list-group-item"><strong>Số Element (ước tính):</strong> ${nodeData.element_count !== undefined ? nodeData.element_count : 'N/A'}</li>
          <li class="list-group-item"><strong>Kích thước gốc (W x H):</strong> ${escapeHtml(nodeData.original_width || '?')} x ${escapeHtml(nodeData.original_height || '?')}</li>
        </ul>`;
    panelTextContentDiv.innerHTML = textDetailsHtml;

    // Thêm nút "Xem/Phân loại Elements"
    const screenIdForLink = nodeData.id;
    if (screenIdForLink && APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS) {
        const elementPageUrl = APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS.replace('PLACEHOLDER', encodeURIComponent(screenIdForLink));
        panelActionsAreaDiv.innerHTML = `<div class="mt-3"><a href="${elementPageUrl}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="fas fa-search me-1"></i> Xem/Phân loại Elements (Trang riêng)</a></div>`;
    }

    // Xử lý hiển thị ảnh và overlays
    console.log("DETAILS_PANEL: Kiểm tra hiển thị ảnh. URL:", nodeData.screenshot_url, "Original Width:", nodeData.original_width, "Original Height:", nodeData.original_height);
    if (nodeData.screenshot_url &&
        typeof nodeData.original_width === 'number' && nodeData.original_width > 0 &&
        typeof nodeData.original_height === 'number' && nodeData.original_height > 0) {

        panelScreenshotAreaDiv.style.display = 'block';
        panelScreenshotContainer.innerHTML = ''; // Xóa overlay cũ, giữ lại thẻ img nếu đã append

        panelScreenshotImage.onload = null; panelScreenshotImage.onerror = null;
        panelScreenshotImage.src = "";
        panelScreenshotImage.alt = `Ảnh chụp màn hình cho ${nodeData.id}`;
        panelScreenshotImage.style.display = 'block';
        panelScreenshotImage.dataset.screenId = nodeData.id;
        panelScreenshotContainer.appendChild(panelScreenshotImage); // Đảm bảo img nằm trong container

        const loadingMsg = document.createElement('p');
        loadingMsg.className = 'text-muted small fst-italic mt-1';
        loadingMsg.textContent = 'Đang tải ảnh...';
        panelScreenshotContainer.appendChild(loadingMsg);

        const onImageLoadSuccess = () => {
            if (!panelScreenshotImage) return;
            console.log(`DETAILS_PANEL: Ảnh ${nodeData.id} đã tải. Natural W/H: ${panelScreenshotImage.naturalWidth}x${panelScreenshotImage.naturalHeight}. Client W/H: ${panelScreenshotImage.clientWidth}x${panelScreenshotImage.clientHeight}`);
            if (loadingMsg) loadingMsg.textContent = 'Đang tải elements...';

            let retryCount = 0; const MAX_RETRIES = 25; const RETRY_INTERVAL = 120;
            function checkSizeAndFetchElements() {
                if (!panelScreenshotImage || !panelScreenshotContainer || !panelScreenshotContainer.contains(panelScreenshotImage)) {
                    console.warn("DETAILS_PANEL: Thẻ img không còn trong container. Dừng.");
                    if (loadingMsg) loadingMsg.remove();
                    return;
                }
                if (panelScreenshotImage.clientWidth > 0 && panelScreenshotImage.clientHeight > 0) {
                    console.log(`DETAILS_PANEL: Kích thước client của ảnh ${nodeData.id} hợp lệ. Đang tìm nạp elements...`);
                    if (loadingMsg) loadingMsg.remove();

                    const elementsApiUrl = APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS.replace('PLACEHOLDER', encodeURIComponent(nodeData.id));
                    fetch(elementsApiUrl) // Dùng fetch đơn giản vì không cần CSRF cho GET này (thường là vậy)
                        .then(response => {
                            if (!response.ok) return response.json().then(err => { throw new Error(err.error || `Lỗi HTTP ${response.status}`) });
                            return response.json();
                        })
                        .then(data => {
                            if (data.success && data.elements) {
                                drawScreenOverlays(panelScreenshotImage, data.elements, nodeData.original_width, nodeData.original_height);
                            } else {
                                const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                                errorMsgP.textContent = `(Lỗi tải elements: ${data.error || 'Không thể lấy dữ liệu.'})`;
                                panelScreenshotContainer.appendChild(errorMsgP);
                            }
                        })
                        .catch(error => {
                            console.error(`DETAILS_PANEL: Lỗi fetch elements cho ${nodeData.id}:`, error);
                            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                            errorMsgP.textContent = `(Lỗi fetch elements: ${error.message})`;
                            panelScreenshotContainer.appendChild(errorMsgP);
                        });
                } else if (retryCount < MAX_RETRIES) {
                    retryCount++;
                    setTimeout(checkSizeAndFetchElements, RETRY_INTERVAL);
                } else {
                    // ... (xử lý lỗi không lấy được kích thước)
                    if (loadingMsg) loadingMsg.textContent = '(Lỗi: Không xác định được kích thước ảnh.)';
                }
            }
            checkSizeAndFetchElements();
        };
        const onImageLoadError = () => { /* ... (xử lý lỗi tải ảnh như cũ) ... */
            if (loadingMsg) loadingMsg.remove();
            console.error("DETAILS_PANEL: Lỗi tải ảnh cho node " + nodeData.id + ". URL: " + nodeData.screenshot_url);
            if (panelScreenshotImage) panelScreenshotImage.alt = `Lỗi tải ảnh cho ${nodeData.id}`;
            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1'; errorMsgP.textContent = '(Lỗi tải ảnh. Kiểm tra URL và file trên server.)';
            if (panelScreenshotContainer) panelScreenshotContainer.appendChild(errorMsgP);
        };

        panelScreenshotImage.onload = onImageLoadSuccess;
        panelScreenshotImage.onerror = onImageLoadError;
        panelScreenshotImage.src = nodeData.screenshot_url;
        if (panelScreenshotImage.complete && panelScreenshotImage.naturalWidth > 0 && panelScreenshotImage.src === nodeData.screenshot_url) {
            onImageLoadSuccess();
        } else if (panelScreenshotImage.complete && panelScreenshotImage.naturalWidth === 0) {
            onImageLoadError();
        }
    } else {
        // ... (xử lý khi không có ảnh hoặc thiếu kích thước như cũ) ...
        if (panelScreenshotAreaDiv) panelScreenshotAreaDiv.style.display = 'none';
        let reason = [];
        if (!nodeData.screenshot_url) reason.push("không có URL ảnh chụp");
        if (typeof nodeData.original_width !== 'number' || nodeData.original_width <= 0) reason.push("thiếu kích thước rộng gốc");
        if (typeof nodeData.original_height !== 'number' || nodeData.original_height <= 0) reason.push("thiếu kích thước cao gốc");
        const reasonText = reason.length > 0 ? reason.join(' và ') : 'Không rõ lý do';
        const reasonP = document.createElement('p');
        reasonP.className = 'text-muted mt-2 text-center small fst-italic';
        reasonP.textContent = `(Không thể hiển thị ảnh/elements. Lý do: ${reasonText})`;
        if (panelTextContentDiv) panelTextContentDiv.appendChild(reasonP);
    }
}

/**
 * Hiển thị chi tiết của một Cạnh (Transition).
 * @param {object} edgeData - Dữ liệu của cạnh từ Cytoscape (edge.data()).
 */
export function displayEdgeDetails(edgeData) {
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv) {
        console.error("DETAILS_PANEL: Không thể hiển thị chi tiết Edge, thiếu DOM elements.");
        return;
    }
    console.log("DETAILS_PANEL: Displaying Edge Details:", edgeData);

    panelScreenshotAreaDiv.style.display = 'none'; // Ẩn khu vực ảnh
    panelActionsAreaDiv.innerHTML = ''; // Xóa các nút hành động cũ

    // Hiển thị thông tin chi tiết của cạnh
    let edgeDetailsHtml = `<h5>Chi tiết Cạnh (Transition)</h5><ul class="list-group list-group-flush">`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>ID (Cytoscape):</strong> <code>${escapeHtml(edgeData.id)}</code></li>`; // edgeData.id là ID của Cytoscape
    if (edgeData.neo4j_edge_id) edgeDetailsHtml += `<li class="list-group-item"><strong>ID (Neo4j):</strong> <code>${escapeHtml(edgeData.neo4j_edge_id)}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Nguồn:</strong> <code>${escapeHtml(edgeData.source)}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Đích:</strong> <code>${escapeHtml(edgeData.target)}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Loại H.Động:</strong> ${escapeHtml(edgeData.action_type || 'N/A')}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Macro Code:</strong> <code>${escapeHtml(edgeData.macro_code || 'N/A')}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Element ID (tương tác):</strong> <code>${escapeHtml(edgeData.element_id || 'N/A')}</code></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Loại ID (element):</strong> ${escapeHtml(edgeData.identifier_type || 'N/A')}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Element Text:</strong> ${escapeHtml(edgeData.element_text || '--')}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Trạng thái Cạnh:</strong> <span class="badge bg-secondary">${escapeHtml(edgeData.status || 'N/A')}</span></li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Lần thử:</strong> ${edgeData.attempt_count !== undefined ? edgeData.attempt_count : 'N/A'}</li>`;
    edgeDetailsHtml += `<li class="list-group-item"><strong>Thành công:</strong> ${edgeData.success_count !== undefined ? edgeData.success_count : 'N/A'}</li>`;
    if (edgeData.params_json) {
        try {
            const paramsObj = JSON.parse(edgeData.params_json);
            const formattedParams = JSON.stringify(paramsObj, null, 2);
            edgeDetailsHtml += `<li class="list-group-item"><strong>Params (JSON):</strong> <pre><code style="white-space: pre-wrap; word-break: break-all;">${escapeHtml(formattedParams)}</code></pre></li>`;
        } catch (e) {
            edgeDetailsHtml += `<li class="list-group-item"><strong>Params (Raw):</strong> <pre><code>${escapeHtml(edgeData.params_json)}</code></pre></li>`;
        }
    } else {
        edgeDetailsHtml += `<li class="list-group-item"><strong>Params:</strong> N/A</li>`;
    }
    edgeDetailsHtml += `</ul>`;
    panelTextContentDiv.innerHTML = edgeDetailsHtml;

    // Tạo và thêm nút "Sửa Transition"
    if (edgeData.neo4j_edge_id) { // Chỉ thêm nút nếu có neo4j_edge_id
        const editButton = document.createElement('button');
        editButton.type = 'button';
        editButton.className = 'btn btn-sm btn-outline-warning mt-2';
        editButton.innerHTML = '<i class="fas fa-edit me-1"></i> Sửa Transition';
        editButton.addEventListener('click', function () {
            console.log("DETAILS_PANEL: Nút 'Sửa Transition' được click. Data:", edgeData);
            openEditTransitionModal(edgeData); // Gọi hàm đã import
        });
        panelActionsAreaDiv.appendChild(editButton);
        console.log("DETAILS_PANEL: Đã thêm nút 'Sửa Transition'.");
    } else {
        console.warn("DETAILS_PANEL: Không thể thêm nút 'Sửa Transition' vì thiếu neo4j_edge_id.");
    }
}

/**
 * Vẽ các overlay của elements lên ảnh.
 * (Đây là hàm drawMapScreenOverlays đã sửa từ lần trước, đảm bảo nó dùng defaultSizesForOverlay từ APP_CONFIG)
 */
function drawScreenOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight) {
    if (!panelScreenshotContainer) {
        console.error("DETAILS_PANEL: panelScreenshotContainer is null, cannot draw overlays.");
        return;
    }
    panelScreenshotContainer.querySelectorAll('.element-overlay').forEach(el => el.remove()); // Chỉ xóa overlay, không xóa ảnh hay loading msg

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 || displayedImgWidth === 0 || displayedImgHeight === 0) {
        console.warn(`DETAILS_PANEL: Kích thước không hợp lệ để vẽ overlay. Gốc: ${nodeOriginalWidth}x${nodeOriginalHeight}, Hiển thị: ${displayedImgWidth}x${displayedImgHeight}`);
        return;
    }
    const overallScaleX = displayedImgWidth / nodeOriginalWidth;
    const overallScaleY = displayedImgHeight / nodeOriginalHeight;

    if (!elementsData || !elementsData.length) return;

    elementsData.forEach(elData => {
        if (!elData || !elData.element_id) return;
        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        // ... (logic tính toán el_orig_left, top, width, height từ elData.bounds hoặc elData.coordinate_x/y và APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY)
        // Ví dụ (cần điều chỉnh cho chính xác):
        if (elData.bounds_left !== undefined) { // Giả sử có bounds
            el_orig_left = parseFloat(elData.bounds_left); el_orig_top = parseFloat(elData.bounds_top);
            el_orig_width = parseFloat(elData.bounds_right) - el_orig_left; el_orig_height = parseFloat(elData.bounds_bottom) - el_orig_top;
        } else if (elData.coordinate_x !== undefined) { // Fallback cho coordinates
            const defaultSize = APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY[elData.element_type || 'default'] || APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY['default'];
            el_orig_width = defaultSize.width; el_orig_height = defaultSize.height;
            el_orig_left = parseFloat(elData.coordinate_x) - (el_orig_width / 2);
            el_orig_top = parseFloat(elData.coordinate_y) - (el_orig_height / 2);
        } else { return; } // Bỏ qua nếu không có thông tin

        if (isNaN(el_orig_left) || isNaN(el_orig_top) || isNaN(el_orig_width) || isNaN(el_orig_height) || el_orig_width <= 0 || el_orig_height <= 0) {
            return; // Bỏ qua nếu kích thước không hợp lệ
        }
        // ... (phần còn lại của việc tạo và append overlay như cũ)
        let x = el_orig_left * overallScaleX; let y = el_orig_top * overallScaleY;
        let w = el_orig_width * overallScaleX; let h = el_orig_height * overallScaleY;
        w = Math.max(w, 3); h = Math.max(h, 3);

        const overlay = document.createElement('div');
        overlay.className = 'element-overlay';
        overlay.title = `ID: ${elData.element_id}\nType: ${elData.element_type || 'N/A'}`;
        overlay.style.cssText = `left:${x}px; top:${y}px; width:${w}px; height:${h}px;`;
        if ((elData.element_type || '').toLowerCase().includes('button')) {
            overlay.classList.add('element-overlay-button');
        }
        panelScreenshotContainer.appendChild(overlay);
    });
}
