// static/js/admin_node_management/utils.js
import { APP_CONFIG } from './config.js';

/**
 * Gửi AJAX request (dùng Fetch API) một cách nhất quán.
 * @param {string} url - URL của API.
 * @param {string} [method='GET'] - Phương thức HTTP.
 * @param {object} [body=null] - Body của request cho POST/PUT.
 * @param {object} [headers={}] - Headers tùy chỉnh.
 * @returns {Promise<object|string>} Promise giải quyết với dữ liệu JSON hoặc text từ server.
 */
export async function sendApiRequest(url, method = 'GET', body = null, headers = {}) {
    const defaultHeaders = {
        'X-CSRFToken': APP_CONFIG.CSRF_TOKEN
    };

    const config = {
        method: method.toUpperCase(),
        headers: { ...defaultHeaders, ...headers }
    };

    if (body) {
        if (body instanceof FormData) {
            // Để trình duyệt tự set Content-Type cho FormData
            config.body = body;
        } else if (typeof body === 'object' && body !== null) { // Kiểm tra body là object và không null
            config.headers['Content-Type'] = 'application/json';
            config.body = JSON.stringify(body);
        } else if (typeof body === 'string') {
            config.headers['Content-Type'] = 'text/plain'; // Hoặc application/x-www-form-urlencoded nếu là query string
            config.body = body;
        } else {
            console.warn("sendApiRequest: Kiểu body không được hỗ trợ hoặc body là null/undefined:", body);
        }
    }

    try {
        const response = await fetch(url, config);
        const contentType = response.headers.get("content-type");
        let responseData;

        if (!response.ok) { // Xử lý lỗi HTTP trước
            let errorPayload = { message: `Lỗi HTTP: ${response.status} ${response.statusText}`, status: response.status };
            if (contentType && contentType.includes("application/json")) {
                try {
                    const errJson = await response.json();
                    errorPayload.message = errJson.message || errJson.error || errorPayload.message;
                    errorPayload.data = errJson;
                } catch (e) { /* Bỏ qua nếu không parse được JSON lỗi */ }
            } else {
                try {
                    errorPayload.message = await response.text() || errorPayload.message;
                } catch (e) { /* Bỏ qua */ }
            }
            const error = new Error(errorPayload.message);
            error.response = response; // Gắn response vào lỗi
            error.data = errorPayload.data || { server_message: errorPayload.message }; // Gắn data lỗi (nếu có)
            console.error(`API request error to ${url} (Status: ${response.status}):`, error.message, error.data);
            throw error;
        }

        // Xử lý response thành công
        if (contentType && contentType.includes("application/json")) {
            responseData = await response.json();
        } else {
            responseData = await response.text();
        }
        return responseData;

    } catch (error) {
        // Lỗi đã được log ở trên hoặc là lỗi mạng (fetch failed)
        if (!error.response) {
            console.error(`Network error or fetch failed for API request to ${url}:`, error);
        }
        // Ném lại lỗi để hàm gọi có thể bắt và xử lý
        throw error;
    }
}


/**
 * Vẽ các overlay tương tác lên ảnh.
 * @param {HTMLImageElement} imgElement - Element <img> đang hiển thị ảnh (phải có clientWidth/Height > 0).
 * @param {Array<object>} elementsData - Mảng dữ liệu các elements từ API.
 * @param {number} nodeOriginalWidth - Chiều rộng gốc của màn hình (từ Neo4j).
 * @param {number} nodeOriginalHeight - Chiều cao gốc của màn hình (từ Neo4j).
 * @param {HTMLElement} containerElement - Container div chứa ảnh và các overlays.
 * @param {function} selectionHandler - Hàm callback khi một element được click, sẽ nhận elementIndex.
 */
export function drawInteractiveOverlays(
    imgElement,
    elementsData,
    nodeOriginalWidth,
    nodeOriginalHeight,
    containerElement,
    selectionHandler
) {
    if (!containerElement) {
        console.error("[UTILS] drawInteractiveOverlays: containerElement is null!");
        return;
    }
    // Xóa các overlay cũ trước khi vẽ mới
    containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

    // Kiểm tra kỹ các kích thước
    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0) {
        console.warn(`[UTILS] drawInteractiveOverlays: Kích thước gốc của Node không hợp lệ: ${nodeOriginalWidth}x${nodeOriginalHeight}`);
        return;
    }
    if (!displayedImgWidth || !displayedImgHeight || displayedImgWidth <= 0 || displayedImgHeight <= 0) {
        console.warn(`[UTILS] drawInteractiveOverlays: Kích thước hiển thị của ảnh không hợp lệ: ${displayedImgWidth}x${displayedImgHeight}. Overlays sẽ không được vẽ.`);
        return;
    }

    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;
    console.log(`[UTILS] drawInteractiveOverlays: Image displayed: ${displayedImgWidth}x${displayedImgHeight}, Original: ${nodeOriginalWidth}x${nodeOriginalHeight}, ScaleX=${scaleX.toFixed(3)}, ScaleY=${scaleY.toFixed(3)}`);

    if (!elementsData || !elementsData.length) {
        console.log("[UTILS] drawInteractiveOverlays: Không có element data để vẽ.");
        return;
    }

    elementsData.forEach((elData, index) => {
        if (!elData || !elData.bounds ||
            (typeof elData.bounds.left !== 'number' || typeof elData.bounds.top !== 'number' ||
                typeof elData.bounds.right !== 'number' || typeof elData.bounds.bottom !== 'number')) {
            // console.warn("[UTILS] drawInteractiveOverlays: Bỏ qua element do thiếu bounds hợp lệ:", elData);
            return;
        }

        let el_orig_left = elData.bounds.left;
        let el_orig_top = elData.bounds.top;
        let el_orig_right = elData.bounds.right;
        let el_orig_bottom = elData.bounds.bottom;

        let el_orig_width = el_orig_right - el_orig_left;
        let el_orig_height = el_orig_bottom - el_orig_top;

        if (el_orig_width <= 0 || el_orig_height <= 0) {
            // console.warn("[UTILS] drawInteractiveOverlays: Kích thước element không hợp lệ (<=0) cho:", elData);
            return;
        }

        const overlay = document.createElement('div');
        overlay.className = APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE;
        overlay.dataset.elementIndex = index;

        const titleText = `ID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nDesc: ${elData.description || '--'}\nClass: ${elData.class_name || 'N/A'}\nBounds: [${el_orig_left},${el_orig_top},${el_orig_right},${el_orig_bottom}]\nClick để chọn/bỏ chọn.`;
        overlay.setAttribute('title', titleText);

        const x = el_orig_left * scaleX;
        const y = el_orig_top * scaleY;
        const w = Math.max(5, el_orig_width * scaleX);
        const h = Math.max(5, el_orig_height * scaleY);

        overlay.style.left = `${x.toFixed(1)}px`;
        overlay.style.top = `${y.toFixed(1)}px`;
        overlay.style.width = `${w.toFixed(1)}px`;
        overlay.style.height = `${h.toFixed(1)}px`;

        overlay.addEventListener('click', function () {
            console.log("[UTILS] Overlay clicked! Element Index:", index);
            if (typeof selectionHandler === 'function') {
                selectionHandler(index); // Gọi selectionHandler với elementOriginalIndex
            } else {
                console.error("[UTILS] selectionHandler is not a function for overlay click!");
            }
        });
        containerElement.appendChild(overlay);
    });
    console.log(`[UTILS] drawInteractiveOverlays: Đã vẽ ${containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).length} overlays.`);
}
