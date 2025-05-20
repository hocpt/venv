// static/js/admin_node_management/utils.js
import { APP_CONFIG } from './config.js';

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
            config.body = body;
        } else if (typeof body === 'object' && body !== null) {
            config.headers['Content-Type'] = 'application/json';
            config.body = JSON.stringify(body);
        } else if (typeof body === 'string') {
            config.headers['Content-Type'] = 'text/plain';
            config.body = body;
        }
    }

    try {
        const response = await fetch(url, config);
        const contentType = response.headers.get("content-type");
        let responseData;

        if (!response.ok) {
            let errorPayload = { message: `Lỗi HTTP: ${response.status} ${response.statusText}`, status: response.status };
            if (contentType && contentType.includes("application/json")) {
                try { const errJson = await response.json(); errorPayload.message = errJson.message || errJson.error || errorPayload.message; errorPayload.data = errJson; } catch (e) { /* Bỏ qua */ }
            } else { try { errorPayload.message = await response.text() || errorPayload.message; } catch (e) { /* Bỏ qua */ } }
            const error = new Error(errorPayload.message);
            error.response = response; error.data = errorPayload.data || { server_message: errorPayload.message };
            console.error(`API request error to ${url} (Status: ${response.status}):`, error.message, error.data);
            throw error;
        }

        if (contentType && contentType.includes("application/json")) {
            responseData = await response.json();
        } else {
            responseData = await response.text();
        }
        return responseData;
    } catch (error) {
        if (!error.response) console.error(`Network error or fetch failed for API request to ${url}:`, error);
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
    // console.log(`[UTILS] drawInteractiveOverlays: ScaleX=${scaleX.toFixed(3)}, ScaleY=${scaleY.toFixed(3)}`);

    if (!elementsData || !elementsData.length) {
        // console.log("[UTILS] drawInteractiveOverlays: Không có element data để vẽ.");
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
            // console.log("[UTILS] Overlay clicked! Element Index:", index); 
            if (typeof selectionHandler === 'function') {
                selectionHandler(index); // CHỈ TRUYỀN INDEX
            } else {
                console.error("[UTILS] selectionHandler is not a function for overlay click!");
            }
        });
        containerElement.appendChild(overlay);
    });
    // console.log(`[UTILS] drawInteractiveOverlays: Đã vẽ ${containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).length} overlays.`);
}
