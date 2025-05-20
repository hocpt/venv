// static/js/admin_mapping_viewer/details_panel_manager.js
import { APP_CONFIG } from './config_mapping.js';
import { escapeHtml } from './utils_mapping.js';
import { openEditTransitionModal } from './modal_edit_transition.js';

let panelTextContentDiv, panelActionsAreaDiv, panelScreenshotAreaDiv,
    panelScreenshotContainer, panelScreenshotImage;

function getDetailsPanelDOMElements() {
    const IDS = APP_CONFIG.DOM_ELEMENT_IDS;
    panelTextContentDiv = document.getElementById(IDS.detailsPanelTextContent);
    panelActionsAreaDiv = document.getElementById(IDS.detailsPanelActionsArea);
    panelScreenshotAreaDiv = document.getElementById(IDS.detailsPanelScreenshotArea);
    panelScreenshotContainer = document.getElementById(IDS.detailsPanelScreenshotContainer);
    panelScreenshotImage = document.getElementById(IDS.detailsPanelScreenshotImage);

    // Log kết quả của từng getElementById
    // console.log(`DETAILS_PANEL: Element '${IDS.detailsPanelTextContent}' found?`, panelTextContentDiv !== null);
    // ... (các log khác nếu cần)
}

export function initDetailsPanelManager() {
    console.log("DETAILS_PANEL: initDetailsPanelManager called.");
    getDetailsPanelDOMElements();
    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotContainer || !panelScreenshotImage) {
        console.warn("DETAILS_PANEL: Một hoặc nhiều DOM elements của panel chi tiết không tìm thấy khi init. Chức năng có thể bị ảnh hưởng nếu các elements này không được render sau đó.");
    } else {
        console.log("DETAILS_PANEL: All required DOM elements for details panel found at init.");
    }
    // console.log("DETAILS_PANEL: Initialized."); // Di chuyển xuống dưới sau khi kiểm tra
}

export function showDefaultDetailsMessage() {
    // Gọi lại getDetailsPanelDOMElements phòng trường hợp init chạy trước khi DOM sẵn sàng hoàn toàn
    if (!panelTextContentDiv) getDetailsPanelDOMElements();

    if (panelTextContentDiv) panelTextContentDiv.innerHTML = '<p class="text-muted fst-italic">Nhấp vào một node (màn hình) hoặc cạnh (chuyển tiếp) để xem chi tiết.</p>';
    if (panelActionsAreaDiv) panelActionsAreaDiv.innerHTML = '';
    if (panelScreenshotAreaDiv) panelScreenshotAreaDiv.style.display = 'none';
}

export function displayNodeDetails(nodeData) {
    // Gọi lại getDetailsPanelDOMElements để đảm bảo các biến DOM được cập nhật
    if (!panelTextContentDiv) getDetailsPanelDOMElements();

    if (!panelTextContentDiv || !panelActionsAreaDiv || !panelScreenshotAreaDiv || !panelScreenshotImage || !panelScreenshotContainer) {
        console.error("DETAILS_PANEL: Không thể hiển thị chi tiết Node, thiếu DOM elements.");
        return;
    }
    console.log("DETAILS_PANEL: Displaying Node Details:", JSON.parse(JSON.stringify(nodeData)));

    panelActionsAreaDiv.innerHTML = '';
    panelScreenshotAreaDiv.style.display = 'none';
    panelScreenshotImage.src = '';
    panelScreenshotImage.style.display = 'none';
    panelScreenshotContainer.innerHTML = ''; // Xóa hết con, bao gồm cả img cũ nếu có

    let textDetailsHtml = `<h5>Chi tiết Node (Màn hình)</h5>
        <ul class="list-group list-group-flush">
          <li class="list-group-item"><strong>ID (Screen):</strong> <code>${escapeHtml(nodeData.id)}</code></li>
          <li class="list-group-item"><strong>Nhãn:</strong> ${escapeHtml(nodeData.label || nodeData.id)}</li>
          <li class="list-group-item"><strong>App Name:</strong> <code>${escapeHtml(nodeData.app_name || 'N/A')}</code></li>
          <li class="list-group-item"><strong>Activity:</strong> ${escapeHtml(nodeData.activity || 'N/A')}</li>
          <li class="list-group-item"><strong>Trạng thái:</strong> <span class="badge bg-info">${escapeHtml(nodeData.status || 'N/A')}</span></li>
          <li class="list-group-item"><strong>Số Element (ước tính):</strong> ${nodeData.element_count !== undefined ? nodeData.element_count : 'N/A'}</li>
          <li class="list-group-item"><strong>Kích thước gốc (W x H):</strong> ${escapeHtml(nodeData.original_width || '?')} x ${escapeHtml(nodeData.original_height || '?')}</li>
        </ul>`;
    panelTextContentDiv.innerHTML = textDetailsHtml;

    const screenIdForLink = nodeData.id;
    if (screenIdForLink && APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS) {
        const elementPageUrl = APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS.replace('PLACEHOLDER', encodeURIComponent(screenIdForLink));
        panelActionsAreaDiv.innerHTML = `<div class="mt-3"><a href="${elementPageUrl}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="fas fa-search me-1"></i> Xem/Phân loại Elements (Trang riêng)</a></div>`;
    }

    console.log("DETAILS_PANEL: Kiểm tra hiển thị ảnh. URL:", nodeData.screenshot_url, "Original Width:", nodeData.original_width, "Original Height:", nodeData.original_height);
    if (nodeData.screenshot_url &&
        typeof nodeData.original_width === 'number' && nodeData.original_width > 0 &&
        typeof nodeData.original_height === 'number' && nodeData.original_height > 0) {

        panelScreenshotAreaDiv.style.display = 'block';
        // panelScreenshotContainer.innerHTML = ''; // Đã xóa ở trên

        // Gắn lại thẻ img vào container vì có thể đã bị xóa bởi innerHTML = '' ở trên
        panelScreenshotContainer.appendChild(panelScreenshotImage);

        panelScreenshotImage.onload = null; panelScreenshotImage.onerror = null;
        panelScreenshotImage.src = "";
        panelScreenshotImage.alt = `Ảnh chụp màn hình cho ${nodeData.id}`;
        panelScreenshotImage.style.display = 'block';
        panelScreenshotImage.dataset.screenId = nodeData.id;

        const loadingMsg = document.createElement('p');
        loadingMsg.className = 'text-muted small fst-italic mt-1';
        loadingMsg.textContent = 'Đang tải ảnh...';
        panelScreenshotContainer.appendChild(loadingMsg);

        const onImageLoadSuccess = () => {
            // ... (code onImageLoadSuccess như trước) ...
            if (!panelScreenshotImage) return;
            console.log(`DETAILS_PANEL: Ảnh ${nodeData.id} đã tải. Natural W/H: ${panelScreenshotImage.naturalWidth}x${panelScreenshotImage.naturalHeight}. Client W/H: ${panelScreenshotImage.clientWidth}x${panelScreenshotImage.clientHeight}`);
            if (loadingMsg) loadingMsg.textContent = 'Đang tải elements...';

            let retryCount = 0; const MAX_RETRIES = 25; const RETRY_INTERVAL = 120;
            function checkSizeAndFetchElements() {
                if (!panelScreenshotImage || !panelScreenshotContainer || !panelScreenshotContainer.contains(panelScreenshotImage)) {
                    console.warn("DETAILS_PANEL: Thẻ img không còn trong container. Dừng fetch elements.");
                    if (loadingMsg) loadingMsg.remove();
                    return;
                }
                if (panelScreenshotImage.clientWidth > 0 && panelScreenshotImage.clientHeight > 0) {
                    console.log(`DETAILS_PANEL: Kích thước client của ảnh ${nodeData.id} hợp lệ. Đang tìm nạp elements...`);
                    if (loadingMsg) loadingMsg.remove();

                    // ---- DEBUG URL API ELEMENTS ----
                    console.log("DETAILS_PANEL: APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS:", APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS);
                    console.log("DETAILS_PANEL: nodeData.id for replacing PLACEHOLDER:", nodeData.id);

                    if (!nodeData.id) {
                        console.error("DETAILS_PANEL: nodeData.id is missing, cannot fetch elements.");
                        const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                        errorMsgP.textContent = `(Lỗi: Thiếu ID của node để tải elements.)`;
                        panelScreenshotContainer.appendChild(errorMsgP);
                        return;
                    }

                    const elementsApiUrl = APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS.replace('PLACEHOLDER', encodeURIComponent(nodeData.id));
                    console.log("DETAILS_PANEL: Final constructed elementsApiUrl:", elementsApiUrl);
                    // ---- KẾT THÚC DEBUG URL ----

                    fetch(elementsApiUrl)
                        .then(response => {
                            if (!response.ok) { // Kiểm tra response.ok
                                console.error(`DETAILS_PANEL: Lỗi HTTP ${response.status} khi fetch elements từ ${elementsApiUrl}`);
                                // Cố gắng parse JSON nếu là lỗi server có body JSON
                                return response.text().then(text => { // Lấy text để xem response là gì
                                    let errorDetail = `Lỗi HTTP ${response.status} (${response.statusText})`;
                                    try {
                                        const errJson = JSON.parse(text);
                                        errorDetail = errJson.error || errJson.message || errorDetail;
                                    } catch (e) {
                                        // Nếu không phải JSON, có thể là trang HTML lỗi
                                        if (text.toLowerCase().includes("<!doctype html>")) {
                                            errorDetail += ". Server trả về HTML.";
                                        } else {
                                            errorDetail += ". Phản hồi không phải JSON.";
                                        }
                                        console.log("DETAILS_PANEL: Response text when not OK and not JSON:", text.substring(0, 200));
                                    }
                                    throw new Error(errorDetail);
                                });
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.success && data.elements) {
                                drawScreenOverlays(panelScreenshotImage, data.elements, nodeData.original_width, nodeData.original_height);
                            } else {
                                const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                                errorMsgP.textContent = `(Lỗi tải elements: ${data.error || data.message || 'Không thể lấy dữ liệu.'})`;
                                panelScreenshotContainer.appendChild(errorMsgP);
                            }
                        })
                        .catch(error => { // Bắt lỗi từ throw new Error hoặc lỗi mạng
                            console.error(`DETAILS_PANEL: Lỗi fetch elements cho ${nodeData.id}:`, error);
                            const errorMsgP = document.createElement('p'); errorMsgP.className = 'text-danger small fst-italic mt-1';
                            errorMsgP.textContent = `(Lỗi fetch elements: ${error.message})`;
                            panelScreenshotContainer.appendChild(errorMsgP);
                        });
                } else if (retryCount < MAX_RETRIES) {
                    retryCount++;
                    setTimeout(checkSizeAndFetchElements, RETRY_INTERVAL);
                } else {
                    if (loadingMsg) loadingMsg.textContent = '(Lỗi: Không xác định được kích thước ảnh.)';
                }
            }
            checkSizeAndFetchElements();
        };
        const onImageLoadError = () => { /* ... */ };

        panelScreenshotImage.onload = onImageLoadSuccess;
        panelScreenshotImage.onerror = onImageLoadError;
        panelScreenshotImage.src = nodeData.screenshot_url;
        if (panelScreenshotImage.complete && panelScreenshotImage.naturalWidth > 0 && panelScreenshotImage.src === nodeData.screenshot_url) {
            onImageLoadSuccess();
        } else if (panelScreenshotImage.complete && panelScreenshotImage.naturalWidth === 0) {
            onImageLoadError();
        }
    } else {
        // ... (xử lý khi không có ảnh hoặc thiếu kích thước)
    }
}

// ... (displayEdgeDetails và drawScreenOverlays như cũ) ...
