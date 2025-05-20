// static/js/admin_node_management/utils.js
import { APP_CONFIG } from './config.js'; // Đảm bảo APP_CONFIG được export từ config.js

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
        // 'Content-Type' sẽ được đặt dựa trên body, hoặc mặc định là json nếu body là object
        'X-CSRFToken': APP_CONFIG.CSRF_TOKEN
    };

    const config = {
        method: method.toUpperCase(),
        headers: { ...defaultHeaders, ...headers }
    };

    if (body) {
        if (body instanceof FormData) {
            // Không set Content-Type, trình duyệt sẽ tự làm với boundary đúng
            config.body = body;
        } else if (typeof body === 'object') {
            config.headers['Content-Type'] = 'application/json';
            config.body = JSON.stringify(body);
        } else { // string, etc.
            config.headers['Content-Type'] = 'text/plain';
            config.body = body;
        }
    }


    try {
        const response = await fetch(url, config);
        const contentType = response.headers.get("content-type");

        if (!response.ok) {
            let errorData;
            if (contentType && contentType.includes("application/json")) {
                errorData = await response.json();
            } else {
                errorData = { message: await response.text() || response.statusText };
            }
            const error = new Error(errorData.message || errorData.error || `HTTP error! status: ${response.status}`);
            error.response = response;
            error.data = errorData;
            console.error(`API request error to ${url} (Status: ${response.status}):`, error.message, error.data);
            throw error;
        }

        // Xử lý response dựa trên content type
        if (contentType && contentType.includes("application/json")) {
            return await response.json();
        } else {
            return await response.text(); // Trả về text nếu không phải JSON
        }

    } catch (error) {
        // Lỗi đã được log ở trên hoặc là lỗi mạng (fetch failed)
        if (!error.response) { // Lỗi mạng, fetch không thành công
            console.error(`Network error or fetch failed for API request to ${url}:`, error);
        }
        throw error;
    }
}


/**
 * Vẽ các overlay tương tác lên ảnh.
 * @param {HTMLImageElement} imgElement - Element <img> đang hiển thị ảnh.
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

    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 ||
        !displayedImgWidth || !displayedImgHeight || displayedImgWidth <= 0 || displayedImgHeight <= 0) {
        console.warn(`[UTILS] drawInteractiveOverlays: Kích thước không hợp lệ để vẽ overlays. 
            Original (Node): ${nodeOriginalWidth}x${nodeOriginalHeight}, 
            Displayed (Image Element): ${displayedImgWidth}x${displayedImgHeight}`);
        return;
    }

    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;
    console.log(`[UTILS] drawInteractiveOverlays: Scale factors - ScaleX=${scaleX.toFixed(3)}, ScaleY=${scaleY.toFixed(3)}`);

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
        overlay.dataset.elementIndex = index; // Quan trọng: lưu index của element trong rawElementsDataForModal

        const titleText = `ID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nDesc: ${elData.description || '--'}\nClass: ${elData.class_name || 'N/A'}\nBounds: [${el_orig_left},${el_orig_top},${el_orig_right},${el_orig_bottom}]\nClick để chọn/bỏ chọn.`;
        overlay.setAttribute('title', titleText); // Dùng setAttribute cho title nhiều dòng

        const x = el_orig_left * scaleX;
        const y = el_orig_top * scaleY;
        const w = Math.max(5, el_orig_width * scaleX); // Kích thước tối thiểu 5px để dễ click
        const h = Math.max(5, el_orig_height * scaleY);

        overlay.style.left = `${x.toFixed(1)}px`;
        overlay.style.top = `${y.toFixed(1)}px`;
        overlay.style.width = `${w.toFixed(1)}px`;
        overlay.style.height = `${h.toFixed(1)}px`;

        overlay.addEventListener('click', function () {
            // console.log("[UTILS] Overlay clicked! Index:", index); 
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
