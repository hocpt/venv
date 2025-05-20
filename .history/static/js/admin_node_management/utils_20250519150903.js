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
        const responseData = await response.json();
        if (!response.ok) {
            const error = new Error(responseData.message || responseData.error || response.statusText || `HTTP error! status: ${response.status}`);
            error.response = response;
            error.data = responseData;
            throw error;
        }
        return responseData;
    } catch (error) {
        console.error(`API request error to ${url}:`, error.message, error.data || '');
        throw error;
    }
}

export function drawInteractiveOverlays(
    imgElement,
    elementsData,
    nodeOriginalWidth,
    nodeOriginalHeight,
    containerElement,
    selectionHandler
) {
    if (!containerElement || !imgElement) {
        console.error("[UTILS] drawInteractiveOverlays: containerElement hoặc imgElement is null!");
        return;
    }
    containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

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
    console.log(`[UTILS] drawInteractiveOverlays: Image displayed: ${displayedImgWidth}x${displayedImgHeight}, Original: ${nodeOriginalWidth}x${nodeOriginalHeight}, ScaleX=${scaleX.toFixed(4)}, ScaleY=${scaleY.toFixed(4)}`);

    if (!elementsData || !elementsData.length) {
        console.log("[UTILS] drawInteractiveOverlays: Không có element data để vẽ.");
        return;
    }

    elementsData.forEach((elData, index) => {
        if (!elData || !elData.bounds ||
            (typeof elData.bounds.left !== 'number' || typeof elData.bounds.top !== 'number' ||
                typeof elData.bounds.right !== 'number' || typeof elData.bounds.bottom !== 'number')) {
            return;
        }

        let el_orig_left = elData.bounds.left;
        let el_orig_top = elData.bounds.top;
        let el_orig_right = elData.bounds.right;
        let el_orig_bottom = elData.bounds.bottom;

        let el_orig_width = el_orig_right - el_orig_left;
        let el_orig_height = el_orig_bottom - el_orig_top;

        if (el_orig_width <= 0 || el_orig_height <= 0) return;

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
            // console.log("[UTILS] Overlay clicked! Element Index from dataset:", this.dataset.elementIndex, "(original index:", index, ")"); 
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