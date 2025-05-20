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

    // Bỏ currentSelectedConditions khỏi tham số ở đây, việc highlight sẽ do updateVisualizerSelections làm

    selectionHandler // Hàm callback khi một element được click, sẽ nhận elementIndex

) {

    if (!containerElement) { console.error("drawInteractiveOverlays: containerElement is null!"); return; }

    containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());


    const displayedImgWidth = imgElement.clientWidth;

    const displayedImgHeight = imgElement.clientHeight;


    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 ||

        !displayedImgWidth || !displayedImgHeight || displayedImgWidth <= 0 || displayedImgHeight <= 0) { // Thêm kiểm tra displayedImg

        console.warn(`drawInteractiveOverlays: Kích thước không hợp lệ. Gốc: ${nodeOriginalWidth}x${nodeOriginalHeight}, Hiển thị: ${displayedWidth}x${displayedHeight}`);

        return;

    }


    const scaleX = displayedImgWidth / nodeOriginalWidth;

    const scaleY = displayedImgHeight / nodeOriginalHeight;


    if (!elementsData || !elementsData.length) return;


    elementsData.forEach((elData, index) => { // index ở đây là elementOriginalIndex

        // ... (logic tính toán el_orig_left, el_orig_top, el_orig_width, el_orig_height như cũ) ...

        if (!elData || (!elData.element_id && !elData.resource_id) || !elData.bounds) return;


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

        if (el_orig_width === undefined) { /* Fallback logic hoặc return */ return; }



        const overlay = document.createElement('div');

        overlay.className = APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE;

        overlay.dataset.elementIndex = index; // Quan trọng: lưu index của element trong rawElementsDataForModal

        overlay.title = `ID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nClass: ${elData.class_name || 'N/A'}\nDesc: ${elData.description || '--'}`;

        overlay.style.left = `${(el_orig_left * scaleX).toFixed(1)}px`;

        overlay.style.top = `${(el_orig_top * scaleY).toFixed(1)}px`;

        overlay.style.width = `${Math.max(5, el_orig_width * scaleX).toFixed(1)}px`;

        overlay.style.height = `${Math.max(5, el_orig_height * scaleY).toFixed(1)}px`;



        // Việc thêm class 'selected-for-pie' sẽ do updateVisualizerSelections() quản lý sau khi

        // currentSelectedPieConditions được cập nhật.


        overlay.addEventListener('click', function () {

            if (typeof selectionHandler === 'function') {

                // Gọi selectionHandler với elementOriginalIndex (chính là `index` ở đây)

                selectionHandler(index);

            }

        });

        containerElement.appendChild(overlay);

    });

}

