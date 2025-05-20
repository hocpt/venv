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

export function drawInteractiveOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight, containerElement, currentSelectedConditions, selectionHandler) {
    if (!containerElement) { console.error("drawInteractiveOverlays: containerElement is null!"); return; }
    containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 || displayedImgWidth === 0 || displayedImgHeight === 0) {
        console.warn(`Invalid dimensions for overlay. Original: ${nodeOriginalWidth}x${nodeOriginalHeight}, Displayed: ${displayedImgWidth}x${displayedImgHeight}`);
        return;
    }

    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;

    if (!elementsData || !elementsData.length) return;

    elementsData.forEach((elData, index) => {
        if (!elData || (!elData.element_id && !elData.resource_id && !elData.text_content && !elData.class_name && !elData.bounds && !(elData.coordinates && elData.coordinates.x !== undefined))) {
            console.warn("Skipping element due to insufficient data for overlay:", elData);
            return;
        }

        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds;

        if (bounds && typeof bounds === 'object' && bounds.left !== undefined && bounds.top !== undefined && bounds.right !== undefined && bounds.bottom !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10); el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10); const el_orig_bottom = parseInt(bounds.bottom, 10);
                if ([el_orig_left, el_orig_top, el_orig_right, el_orig_bottom].some(isNaN)) throw new Error("NaN in bounds");
                el_orig_width = el_orig_right - el_orig_left; el_orig_height = el_orig_bottom - el_orig_top;
                if (el_orig_width <= 0 || el_orig_height <= 0) el_orig_width = undefined;
            } catch (e) { el_orig_width = undefined; }
        }

        if (el_orig_width === undefined) { // Fallback if bounds invalid or not present
            let coord_x_val = elData.coordinate_x; let coord_y_val = elData.coordinate_y;
            if (elData.coordinates && typeof elData.coordinates === 'object') {
                coord_x_val = elData.coordinates.x; coord_y_val = elData.coordinates.y;
            }
            if (coord_x_val !== undefined && coord_y_val !== undefined) {
                try {
                    const coord_x = parseInt(coord_x_val, 10); const coord_y = parseInt(coord_y_val, 10);
                    if (isNaN(coord_x) || isNaN(coord_y)) throw new Error("NaN in coordinates");
                    const defaultSize = APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY[elData.class_name || 'default'] || APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY['default'];
                    el_orig_width = defaultSize.width; el_orig_height = defaultSize.height;
                    el_orig_left = coord_x - (el_orig_width / 2); el_orig_top = coord_y - (el_orig_height / 2);
                } catch (e) { console.warn("Error in fallback bounds calculation:", elData, e); return; }
            } else { return; }
        }

        const overlay = document.createElement('div');
        overlay.className = APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE;
        overlay.dataset.elementIndex = index;
        overlay.title = `ID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nClass: ${elData.class_name || 'N/A'}\nDesc: ${elData.description || '--'}`;
        overlay.style.left = `${(el_orig_left * scaleX).toFixed(1)}px`;
        overlay.style.top = `${(el_orig_top * scaleY).toFixed(1)}px`;
        overlay.style.width = `${Math.max(5, el_orig_width * scaleX).toFixed(1)}px`;
        overlay.style.height = `${Math.max(5, el_orig_height * scaleY).toFixed(1)}px`;

        // Highlighting logic will be managed by updateVisualizerSelections called from modal_manage_pie.js

        overlay.addEventListener('click', function () {
            if (typeof selectionHandler === 'function') {
                selectionHandler(index, this); // Pass index and the DOM element
            }
        });
        containerElement.appendChild(overlay);
    });
}