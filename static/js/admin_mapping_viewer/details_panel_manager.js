// static/js/admin_mapping_viewer/details_panel_manager.js
import { APP_CONFIG } from './config_mapping.js';
import { escapeHtml, sendApiRequest as sendApiRequestFromUtils } from './utils_mapping.js';  // Giả sử escapeHtml ở utils
import { openEditTransitionModal } from './modal_edit_transition.js'; // Import hàm mở modal

// DOM Elements của Panel Chi Tiết
let panelTextContentDiv, panelActionsAreaDiv, panelScreenshotAreaDiv,
    panelScreenshotContainer, panelScreenshotImage;

// Hàm lấy các DOM element một lần
function getAndCheckDetailsPanelDOMElements() {
    const IDS = APP_CONFIG.DOM_ELEMENT_IDS;
    let allFound = true;

    panelTextContentDiv = document.getElementById(IDS.detailsPanelTextContent);
    if (!panelTextContentDiv) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelTextContent}' not found.`); allFound = false; }

    panelActionsAreaDiv = document.getElementById(IDS.detailsPanelActionsArea);
    if (!panelActionsAreaDiv) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelActionsArea}' not found.`); allFound = false; }

    panelScreenshotAreaDiv = document.getElementById(IDS.detailsPanelScreenshotArea);
    if (!panelScreenshotAreaDiv) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotArea}' not found.`); allFound = false; }

    panelScreenshotContainer = document.getElementById(IDS.detailsPanelScreenshotContainer);
    if (!panelScreenshotContainer) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotContainer}' not found.`); allFound = false; }

    panelScreenshotImage = document.getElementById(IDS.detailsPanelScreenshotImage);
    if (!panelScreenshotImage) { console.warn(`DETAILS_PANEL: Element '${IDS.detailsPanelScreenshotImage}' not found.`); allFound = false; }

    return allFound;
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
    if (!panelTextContentDiv && !getAndCheckDetailsPanelDOMElements()) return; // Thử lấy lại nếu chưa có

    if (panelTextContentDiv) panelTextContentDiv.innerHTML = '<p class="text-muted fst-italic">Nhấp vào một node (màn hình) hoặc cạnh (chuyển tiếp) để xem chi tiết.</p>';
    if (panelActionsAreaDiv) panelActionsAreaDiv.innerHTML = '';
    if (panelScreenshotAreaDiv) panelScreenshotAreaDiv.style.display = 'none';
}


export function displayNodeDetails(nodeData) {
    if (!panelTextContentDiv && !getAndCheckDetailsPanelDOMElements()) {
        console.error("DETAILS_PANEL: displayNodeDetails - Không thể hiển thị chi tiết Node, thiếu DOM elements chính.");
        return;
    }
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotImage || !panelScreenshotContainer) {
        console.error("DETAILS_PANEL: displayNodeDetails - Vẫn thiếu một số DOM elements cần thiết.");
        return;
    }

    console.log("DETAILS_PANEL: Displaying Node Details for nodeData:", JSON.parse(JSON.stringify(nodeData)));

    panelActionsAreaDiv.innerHTML = '';
    panelScreenshotAreaDiv.style.display = 'none';
    panelScreenshotImage.src = '';
    panelScreenshotImage.style.display = 'none';
    panelScreenshotContainer.innerHTML = '';

    let textDetailsHtml = `<h5>Chi tiết Node (Màn hình)</h5> <ul class="list-group list-group-flush"> <li class="list-group-item"><strong>ID (Screen):</strong> <code>${escapeHtml(nodeData.id)}</code></li> <li class="list-group-item"><strong>Nhãn (Label):</strong> ${escapeHtml(nodeData.label || nodeData.id)}</li> <li class="list-group-item"><strong>App Name:</strong> <code>${escapeHtml(nodeData.app_name || 'N/A')}</code></li> <li class="list-group-item"><strong>Activity:</strong> ${escapeHtml(nodeData.activity || 'N/A')}</li> <li class="list-group-item"><strong>Trạng thái:</strong> <span class="badge bg-info">${escapeHtml(nodeData.status || 'N/A')}</span></li> <li class="list-group-item"><strong>Số Element (ước tính):</strong> ${nodeData.element_count !== undefined ? nodeData.element_count : 'N/A'}</li> <li class="list-group-item"><strong>Kích thước gốc (W x H):</strong> ${escapeHtml(nodeData.original_width || '?')} x ${escapeHtml(nodeData.original_height || '?')}</li> </ul>`;
    panelTextContentDiv.innerHTML = textDetailsHtml;

    const screenIdForLink = nodeData.id;
    if (screenIdForLink && APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS && APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS.includes('__SCREEN_ID_PLACEHOLDER__')) {
        const elementPageUrl = APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS.replace('__SCREEN_ID_PLACEHOLDER__', encodeURIComponent(screenIdForLink));
        panelActionsAreaDiv.innerHTML = `<div class="mt-3"><a href="${elementPageUrl}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="fas fa-search me-1"></i> Xem/Phân loại Elements (Trang riêng)</a></div>`;
    } else {
        console.warn("DETAILS_PANEL: Không thể tạo link 'Xem Elements'. URL_FOR_ADMIN_SCREEN_ELEMENTS:", APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS, "screenIdForLink:", screenIdForLink);
    }

    console.log("DETAILS_PANEL: Bắt đầu xử lý ảnh. URL ảnh:", nodeData.screenshot_url,
        "Original Width:", nodeData.original_width,
        "Original Height:", nodeData.original_height);

    if (nodeData.screenshot_url &&
        typeof nodeData.original_width === 'number' && nodeData.original_width > 0 &&
        typeof nodeData.original_height === 'number' && nodeData.original_height > 0) {

        panelScreenshotAreaDiv.style.display = 'block';
        panelScreenshotContainer.appendChild(panelScreenshotImage);

        panelScreenshotImage.onload = null;
        panelScreenshotImage.onerror = null;
        panelScreenshotImage.src = "";
        panelScreenshotImage.alt = `Ảnh chụp màn hình cho ${nodeData.id}`;
        panelScreenshotImage.style.display = 'block';
        panelScreenshotImage.dataset.screenId = nodeData.id;

        const loadingMsg = document.createElement('p');
        loadingMsg.className = 'text-muted small fst-italic mt-1 loading-image-text';
        loadingMsg.textContent = 'Đang tải ảnh...';
        panelScreenshotContainer.appendChild(loadingMsg);

        const onImageLoadSuccess = () => {
            if (!panelScreenshotImage) return;
            console.log(`DETAILS_PANEL: Ảnh ${nodeData.id} đã tải. Natural W/H: ${panelScreenshotImage.naturalWidth}x${panelScreenshotImage.naturalHeight}. Client W/H (sau onload): ${panelScreenshotImage.clientWidth}x${panelScreenshotImage.clientHeight}`);

            const existingLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
            if (existingLoadingMsg) existingLoadingMsg.textContent = 'Đang tải elements...';

            let retryCount = 0;
            const MAX_RETRIES = 30;
            const RETRY_INTERVAL = 150;

            function checkSizeAndFetchElements() {
                if (!panelScreenshotImage || !panelScreenshotContainer || !panelScreenshotContainer.contains(panelScreenshotImage)) {
                    if (existingLoadingMsg) existingLoadingMsg.remove();
                    return;
                }
                // Log kích thước client mỗi lần kiểm tra
                console.log(`DETAILS_PANEL: checkSizeAttempt ${retryCount + 1} - Client W/H: ${panelScreenshotImage.clientWidth}x${panelScreenshotImage.clientHeight}`);

                if (panelScreenshotImage.clientWidth > 0 && panelScreenshotImage.clientHeight > 0) {
                    console.log(`DETAILS_PANEL: Kích thước client của ảnh ${nodeData.id} hợp lệ. Bắt đầu tìm nạp elements...`);
                    const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
                    if (currentLoadingMsg) currentLoadingMsg.remove();

                    const baseUrlForElements = APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS;
                    const screenIdToFetch = nodeData.id;

                    console.log("DETAILS_PANEL: DEBUG - Base URL for elements from APP_CONFIG:", baseUrlForElements);
                    console.log("DETAILS_PANEL: DEBUG - screenIdToFetch for elements:", screenIdToFetch);

                    if (!baseUrlForElements || typeof baseUrlForElements !== 'string' || !baseUrlForElements.includes('__SCREEN_ID_PLACEHOLDER__')) {
                        console.error("DETAILS_PANEL: Lỗi cấu hình API_BASE_URLS.SCREEN_ELEMENTS! Không chứa '__SCREEN_ID_PLACEHOLDER__' hoặc không hợp lệ. URL hiện tại:", baseUrlForElements);
                        const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                        errorMsgP.textContent = `(Lỗi cấu hình URL API elements. Không thể tải.)`;
                        panelScreenshotContainer.appendChild(errorMsgP);
                        return;
                    }
                    if (!screenIdToFetch) {
                        console.error("DETAILS_PANEL: screenIdToFetch (nodeData.id) bị thiếu, không thể fetch elements.");
                        const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                        errorMsgP.textContent = `(Lỗi: Thiếu ID của node để tải elements.)`;
                        panelScreenshotContainer.appendChild(errorMsgP);
                        return;
                    }

                    const elementsApiUrl = baseUrlForElements.replace('__SCREEN_ID_PLACEHOLDER__', encodeURIComponent(screenIdToFetch));
                    console.log("DETAILS_PANEL: Final constructed elementsApiUrl:", elementsApiUrl);

                    sendApiRequestFromUtils(elementsApiUrl, 'GET')
                        .then(data => {
                            console.log("DETAILS_PANEL: Dữ liệu elements nhận được từ API:", JSON.parse(JSON.stringify(data)));
                            if (data.success && Array.isArray(data.elements)) {
                                if (data.elements.length > 0) {
                                    console.log("DETAILS_PANEL: Element đầu tiên:", JSON.stringify(data.elements[0]));
                                } else {
                                    console.log("DETAILS_PANEL: API trả về danh sách elements rỗng cho node " + screenIdToFetch);
                                }
                                drawScreenOverlays(panelScreenshotImage, data.elements, nodeData.original_width, nodeData.original_height);
                            } else {
                                const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                                errorMsgP.textContent = `(Lỗi tải elements: ${data.error || data.message || 'Dữ liệu elements không hợp lệ.'})`;
                                panelScreenshotContainer.appendChild(errorMsgP);
                            }
                        })
                        .catch(error => {
                            console.error(`DETAILS_PANEL: Lỗi fetch elements cho ${nodeData.id} từ URL ${elementsApiUrl}:`, error);
                            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                            errorMsgP.textContent = `(Lỗi fetch elements: ${error.message}. URL đã gọi: ${elementsApiUrl})`;
                            panelScreenshotContainer.appendChild(errorMsgP);
                        });
                } else if (retryCount < MAX_RETRIES) {
                    retryCount++;
                    console.warn(`DETAILS_PANEL: Ảnh ${nodeData.id} clientWidth/Height vẫn là 0. Thử lại (${retryCount}/${MAX_RETRIES})...`);
                    const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
                    if (currentLoadingMsg) currentLoadingMsg.textContent = `Đang chờ render ảnh (${retryCount})...`;
                    setTimeout(checkSizeAndFetchElements, RETRY_INTERVAL);
                } else {
                    console.error(`DETAILS_PANEL: Vẫn không lấy được kích thước client của ảnh ${nodeData.id} sau ${MAX_RETRIES} lần thử.`);
                    const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
                    if (currentLoadingMsg) currentLoadingMsg.remove();
                    const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                    errorMsgP.textContent = '(Lỗi: Không xác định được kích thước ảnh sau nhiều lần thử.)';
                    panelScreenshotContainer.appendChild(errorMsgP);
                }
            }
            // Bắt đầu vòng lặp kiểm tra kích thước ngay sau khi ảnh onload thành công
            // hoặc đợi một frame để trình duyệt có thời gian tính toán kích thước client
            requestAnimationFrame(checkSizeAndFetchElements);
        };
        const onImageLoadError = () => {
            const currentLoadingMsg = panelScreenshotContainer.querySelector('.loading-image-text');
            if (currentLoadingMsg) currentLoadingMsg.remove();
            console.error("DETAILS_PANEL: Lỗi tải ảnh cho node " + nodeData.id + ". URL: " + nodeData.screenshot_url);
            if (panelScreenshotImage) panelScreenshotImage.alt = `Lỗi tải ảnh cho ${nodeData.id}`;
            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
            errorMsgP.textContent = '(Lỗi tải ảnh. Kiểm tra URL và file trên server.)';
            panelScreenshotContainer.appendChild(errorMsgP);
        };

        panelScreenshotImage.onload = onImageLoadSuccess;
        panelScreenshotImage.onerror = onImageLoadError;
        panelScreenshotImage.src = nodeData.screenshot_url;

        // Xử lý trường hợp ảnh đã được cache và complete ngay lập tức
        if (panelScreenshotImage.complete) {
            console.log("DETAILS_PANEL: Ảnh đã 'complete'. Natural W/H:", panelScreenshotImage.naturalWidth, panelScreenshotImage.naturalHeight);
            if (panelScreenshotImage.naturalWidth > 0 && panelScreenshotImage.src === nodeData.screenshot_url) {
                // Kích hoạt onload handler nếu ảnh đã load xong từ cache
                // Đôi khi trình duyệt không tự kích hoạt lại onload cho ảnh cache
                onImageLoadSuccess();
            } else if (panelScreenshotImage.naturalWidth === 0 && panelScreenshotImage.src === nodeData.screenshot_url) {
                // Ảnh complete nhưng lỗi (ví dụ URL sai, file không tồn tại)
                console.error("DETAILS_PANEL: Ảnh đã complete nhưng naturalWidth là 0 (ảnh lỗi).");
                onImageLoadError();
            }
        }
    } else {
        panelScreenshotAreaDiv.style.display = 'none';
        let reason = [];
        if (!nodeData.screenshot_url) reason.push("không có URL ảnh chụp");
        if (typeof nodeData.original_width !== 'number' || nodeData.original_width <= 0) reason.push("thiếu hoặc không hợp lệ kích thước rộng gốc");
        if (typeof nodeData.original_height !== 'number' || nodeData.original_height <= 0) reason.push("thiếu hoặc không hợp lệ kích thước cao gốc");

        const reasonText = reason.length > 0 ? reason.join(' và ') : 'Không rõ lý do';
        console.warn(`DETAILS_PANEL: Không hiển thị ảnh và elements cho node ${nodeData.id} vì: ${reasonText}`);

        const reasonP = document.createElement('p');
        reasonP.className = 'text-muted mt-2 text-center small fst-italic';
        reasonP.textContent = `(Không có ảnh chụp hoặc thiếu thông tin kích thước gốc, không thể hiển thị elements. Lý do: ${reasonText})`;
        panelTextContentDiv.appendChild(reasonP);
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
        console.error("DETAILS_PANEL (drawScreenOverlays): panelScreenshotContainer is null.");
        return;
    }
    panelScreenshotContainer.querySelectorAll('.element-overlay').forEach(el => el.remove());
    panelScreenshotContainer.querySelectorAll('.overlay-dimension-error-dsp, .text-warning, .text-muted.small.fst-italic.mt-1').forEach(el => {
        if (!el.classList.contains('loading-image-text')) {
            el.remove();
        }
    });

    const containerWidth = imgElement.parentElement.clientWidth; // Kích thước của panelScreenshotContainer
    const containerHeight = imgElement.parentElement.clientHeight; // Kích thước của panelScreenshotContainer

    const naturalWidth = imgElement.naturalWidth;
    const naturalHeight = imgElement.naturalHeight;

    if (naturalWidth === 0 || naturalHeight === 0) {
        console.warn("DETAILS_PANEL (drawScreenOverlays): Ảnh có kích thước gốc bằng 0, không thể vẽ overlay.");
        return;
    }

    const imageAspectRatio = naturalWidth / naturalHeight;
    // Sử dụng clientWidth/Height của thẻ img, vì object-fit:contain sẽ điều chỉnh kích thước hiển thị bên trong nó
    const displayBoxWidth = imgElement.clientWidth;
    const displayBoxHeight = imgElement.clientHeight;
    const displayBoxAspectRatio = displayBoxWidth / displayBoxHeight;

    let renderedImgWidth, renderedImgHeight, offsetX = 0, offsetY = 0;

    if (imageAspectRatio > displayBoxAspectRatio) {
        // Ảnh rộng hơn display box -> chiều rộng ảnh render = chiều rộng display box, chiều cao tính theo tỷ lệ
        renderedImgWidth = displayBoxWidth;
        renderedImgHeight = displayBoxWidth / imageAspectRatio;
        offsetY = (displayBoxHeight - renderedImgHeight) / 2; // Khoảng trống trên dưới
    } else {
        // Ảnh cao hơn display box (hoặc vừa khít) -> chiều cao ảnh render = chiều cao display box, chiều rộng tính theo tỷ lệ
        renderedImgHeight = displayBoxHeight;
        renderedImgWidth = displayBoxHeight * imageAspectRatio;
        offsetX = (displayBoxWidth - renderedImgWidth) / 2; // Khoảng trống trái phải
    }

    console.log(`DETAILS_PANEL (drawScreenOverlays): Image natural: ${naturalWidth}x${naturalHeight} (AR: ${imageAspectRatio.toFixed(3)})`);
    console.log(`DETAILS_PANEL (drawScreenOverlays): Img tag client: ${displayBoxWidth}x${displayBoxHeight} (AR: ${displayBoxAspectRatio.toFixed(3)})`);
    console.log(`DETAILS_PANEL (drawScreenOverlays): Rendered image inside tag: ${renderedImgWidth.toFixed(1)}x${renderedImgHeight.toFixed(1)}. Offset: X=${offsetX.toFixed(1)}, Y=${offsetY.toFixed(1)}`);


    if (renderedImgWidth === 0 || renderedImgHeight === 0) {
        console.warn(`DETAILS_PANEL (drawScreenOverlays): Kích thước ảnh render bằng 0, không thể vẽ overlay.`);
        return;
    }

    // Tỷ lệ scale dựa trên kích thước ảnh GỐC của screenshot (nodeOriginalWidth/Height)
    // và kích thước ảnh được RENDER THỰC TẾ trên màn hình (renderedImgWidth/Height)
    const scaleX = renderedImgWidth / nodeOriginalWidth;
    const scaleY = renderedImgHeight / nodeOriginalHeight;
    console.log(`DETAILS_PANEL (drawScreenOverlays): Final Scaling: X=${scaleX.toFixed(3)}, Y=${scaleY.toFixed(3)} (based on rendered image size)`);

    if (!elementsData || !Array.isArray(elementsData) || elementsData.length === 0) {
        console.info("DETAILS_PANEL (drawScreenOverlays): No valid elementsData to draw.");
        // ... (thêm thông báo nếu cần)
        return;
    }

    let drawnCount = 0;
    elementsData.forEach((elData, index) => {
        console.log(`DETAILS_PANEL (drawScreenOverlays): Processing element ${index}:`, JSON.stringify(elData).substring(0, 150));
        if (!elData) {
            console.warn(`DETAILS_PANEL (drawScreenOverlays): Element data at index ${index} is null/undefined.`);
            return;
        }
        const elIdentifier = elData.element_id || elData.resource_id || `generated_overlay_id_${index}`;
        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds;

        if (bounds && typeof bounds === 'object' &&
            bounds.left !== undefined && bounds.top !== undefined &&
            bounds.right !== undefined && bounds.bottom !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10);
                el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10);
                const el_orig_bottom = parseInt(bounds.bottom, 10);
                if ([el_orig_left, el_orig_top, el_orig_right, el_orig_bottom].some(isNaN)) {
                    el_orig_width = undefined;
                } else {
                    el_orig_width = el_orig_right - el_orig_left;
                    el_orig_height = el_orig_bottom - el_orig_top;
                    if (el_orig_width <= 0 || el_orig_height <= 0) {
                        el_orig_width = undefined;
                    }
                }
            } catch (e) { el_orig_width = undefined; }
        } else { el_orig_width = undefined; }

        if (el_orig_width === undefined) {
            let coord_x_val = elData.coordinate_x; let coord_y_val = elData.coordinate_y;
            if (elData.coordinates && typeof elData.coordinates === 'object' && elData.coordinates.x !== undefined) { coord_x_val = elData.coordinates.x; coord_y_val = elData.coordinates.y; }
            if (coord_x_val !== undefined && coord_y_val !== undefined) {
                try {
                    const coord_x = parseInt(coord_x_val, 10);
                    const coord_y = parseInt(coord_y_val, 10);
                    if (isNaN(coord_x) || isNaN(coord_y)) throw new Error("NaN in coordinates");
                    const defaultSizeKey = elData.element_type || elData.class_name || 'default';
                    const defaultSize = APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY[defaultSizeKey] || APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY['default'];
                    el_orig_width = defaultSize.width;
                    el_orig_height = defaultSize.height;
                    el_orig_left = coord_x - (el_orig_width / 2);
                    el_orig_top = coord_y - (el_orig_height / 2);
                } catch (e) {
                    console.warn(`DETAILS_PANEL (drawScreenOverlays): Error in fallback for element ${elIdentifier}:`, e, elData);
                    return;
                }
            } else {
                console.warn(`DETAILS_PANEL (drawScreenOverlays): Element ${elIdentifier} has no valid bounds or coordinates. Skipping.`);
                return;
            }
        }
        console.log(`DETAILS_PANEL (drawScreenOverlays): Element ${elIdentifier} - Original Coords: L${el_orig_left}, T${el_orig_top}, W${el_orig_width}, H${el_orig_height}`);

        const x = (el_orig_left * scaleX) + offsetX;
        const y = (el_orig_top * scaleY) + offsetY;
        const w = Math.max(3, el_orig_width * scaleX);
        const h = Math.max(3, el_orig_height * scaleY);

        console.log(`DETAILS_PANEL (drawScreenOverlays): Element ${elIdentifier} - Final Pos: L${x.toFixed(1)}, T${y.toFixed(1)}, W${w.toFixed(1)}, H${h.toFixed(1)}`);

        const overlay = document.createElement('div');
        overlay.className = 'element-overlay';
        overlay.title = `ID: ${elIdentifier}\nType: ${elData.element_type || elData.class_name || 'N/A'}\nText: ${elData.text_content || '--'}`;
        overlay.style.left = `${x.toFixed(1)}px`;
        overlay.style.top = `${y.toFixed(1)}px`;
        overlay.style.width = `${w.toFixed(1)}px`;
        overlay.style.height = `${h.toFixed(1)}px`;

        const elementType = elData.element_type || elData.class_name || '';
        if (elementType.toLowerCase().includes('button')) {
            overlay.classList.add('element-overlay-button');
        }

        panelScreenshotContainer.appendChild(overlay);
        drawnCount++;
    });
    console.log(`DETAILS_PANEL (drawScreenOverlays): Drawn ${drawnCount} overlays for screen ${imgElement.dataset.screenId}.`);
    if (drawnCount === 0 && elementsData.length > 0) {
        console.warn("DETAILS_PANEL (drawScreenOverlays): Có dữ liệu elements nhưng không vẽ được overlay nào. Kiểm tra logic tính toán tọa độ/kích thước.");
        const noOverlayMsg = document.createElement('p');
        noOverlayMsg.className = 'text-warning small fst-italic mt-1';
        noOverlayMsg.textContent = '(Có elements nhưng không thể vẽ overlay. Kiểm tra console log.)';
        panelScreenshotContainer.appendChild(noOverlayMsg);
    }
}
