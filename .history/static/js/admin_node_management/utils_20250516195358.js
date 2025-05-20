// static/js/admin_node_management/utils.js
import { APP_CONFIG } from './config.js';

export async function sendApiRequest(url, method = 'GET', body = null, headers = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json',
        'X-CSRFToken': APP_CONFIG.CSRF_TOKEN
    };
    const config = {
        method: method.toUpperCase(),
        headers: { ...defaultHeaders, ...headers }
    };
    if (body && (method.toUpperCase() === 'POST' || method.toUpperCase() === 'PUT')) {
        config.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(url, config);
        // Thử parse JSON trước, nếu lỗi thì lấy text
        let responseData;
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            responseData = await response.json();
        } else {
            responseData = await response.text(); // Lấy text nếu không phải JSON
            // Nếu là text và response không ok, tạo object lỗi để nhất quán
            if (!response.ok) throw new Error(responseData || `HTTP error! status: ${response.status}`);
            return responseData; // Trả về text nếu thành công và không phải JSON
        }

        if (!response.ok) {
            const error = new Error(responseData.message || responseData.error || response.statusText || `HTTP error! status: ${response.status}`);
            error.response = response;
            error.data = responseData;
            throw error;
        }
        return responseData;
    } catch (error) {
        console.error(`API request error to ${url}:`, error.message, error.data || error);
        throw error;
    }
}

export function drawInteractiveOverlays(
    imgElement,
    elementsData,
    nodeOriginalWidth,
    nodeOriginalHeight,
    containerElement,
    selectionHandler // Hàm callback khi một element được click, sẽ nhận elementIndex
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
        console.warn(`[UTILS] drawInteractiveOverlays: Kích thước không hợp lệ để vẽ. 
            Original: ${nodeOriginalWidth}x${nodeOriginalHeight}, 
            Displayed: ${displayedImgWidth}x${displayedImgHeight}`);
        return;
    }

    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;
    // console.log(`[UTILS] drawInteractiveOverlays: ScaleX=${scaleX.toFixed(3)}, ScaleY=${scaleY.toFixed(3)}`);

    if (!elementsData || !elementsData.length) {
        // console.log("[UTILS] drawInteractiveOverlays: Không có element data để vẽ.");
        return;
    }

    elementsData.forEach((elData, index) => { // index ở đây là elementOriginalIndex
        if (!elData || (!elData.element_id && !elData.resource_id) || !elData.bounds) {
            // console.warn("[UTILS] drawInteractiveOverlays: Bỏ qua element do thiếu data:", elData);
            return;
        }

        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds;
        if (bounds && typeof bounds === 'object' && bounds.left !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10); el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10); const el_orig_bottom = parseInt(bounds.bottom, 10);
                if ([el_orig_left, el_orig_top, el_orig_right, el_orig_bottom].some(isNaN)) throw new Error("NaN in bounds");
                el_orig_width = el_orig_right - el_orig_left; el_orig_height = el_orig_bottom - el_orig_top;
                if (el_orig_width <= 0 || el_orig_height <= 0) el_orig_width = undefined;
            } catch (e) { el_orig_width = undefined; }
        }
        if (el_orig_width === undefined) {
            // console.warn("[UTILS] drawInteractiveOverlays: Bounds không hợp lệ cho element:", elData);
            return;
        }

        const overlay = document.createElement('div');
        overlay.className = APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE;
        overlay.dataset.elementIndex = index; // Quan trọng: lưu index của element trong rawElementsDataForModal
        overlay.title = `ID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nClass: ${elData.class_name || 'N/A'}\nDesc: ${elData.description || '--'}\nClick để chọn/bỏ chọn.`;

        const x = el_orig_left * scaleX;
        const y = el_orig_top * scaleY;
        const w = Math.max(5, el_orig_width * scaleX); // Kích thước tối thiểu 5px
        const h = Math.max(5, el_orig_height * scaleY);

        overlay.style.left = `${x.toFixed(1)}px`;
        overlay.style.top = `${y.toFixed(1)}px`;
        overlay.style.width = `${w.toFixed(1)}px`;
        overlay.style.height = `${h.toFixed(1)}px`;

        overlay.addEventListener('click', function () {
            console.log("[UTILS] Overlay clicked! Index:", index); // Log khi click
            if (typeof selectionHandler === 'function') {
                selectionHandler(index); // Gọi selectionHandler với elementOriginalIndex
            } else {
                console.error("[UTILS] selectionHandler is not a function for overlay click!");
            }
        });
        containerElement.appendChild(overlay);
    });
    // console.log(`[UTILS] drawInteractiveOverlays: Đã vẽ ${containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).length} overlays.`);
}
