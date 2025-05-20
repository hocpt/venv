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

export function drawInteractiveOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight, containerElement, selectionHandler) { // Thêm selectionHandler
    if (!containerElement) { console.error("drawInteractiveOverlays: containerElement is null!"); return; }
    containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 || displayedImgWidth === 0 || displayedImgHeight === 0) {
        console.warn(`[UtilsJS] Invalid dimensions for overlay. Original: ${nodeOriginalWidth}x${nodeOriginalHeight}, Displayed: ${displayedImgWidth}x${displayedImgHeight}`);
        // Hiển thị thông báo lỗi trực tiếp trên container nếu kích thước không hợp lệ
        if (!containerElement.querySelector('.overlay-dimension-error')) {
            const errorMsgEl = document.createElement('p');
            errorMsgEl.className = 'text-danger small fst-italic p-1 text-center overlay-dimension-error';
            errorMsgEl.textContent = `Lỗi kích thước overlay: Gốc ${nodeOriginalWidth}x${nodeOriginalHeight}, Hiển thị ${displayedImgWidth}x${displayedImgHeight}. Không thể vẽ elements.`;
            containerElement.appendChild(errorMsgEl);
        }
        return;
    } else {
        // Xóa thông báo lỗi nếu có và kích thước đã hợp lệ
        const existingError = containerElement.querySelector('.overlay-dimension-error');
        if (existingError) existingError.remove();
    }


    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;
    console.log(`[UtilsJS] Scaling for overlays: scaleX=${scaleX.toFixed(3)}, scaleY=${scaleY.toFixed(3)}`);


    if (!elementsData || !elementsData.length) {
        console.info("[UtilsJS] No elementsData provided to drawInteractiveOverlays.");
        return;
    }

    elementsData.forEach((elData, index) => {
        // Thêm console.log để kiểm tra dữ liệu của từng element
        // console.log(`[UtilsJS] Processing element at index ${index}:`, JSON.stringify(elData).substring(0,150));

        if (!elData || (!elData.element_id && !elData.resource_id && !elData.text_content && !elData.class_name && !elData.bounds && !(elData.coordinates && elData.coordinates.x !== undefined))) {
            console.warn("[UtilsJS] Skipping element due to insufficient data for overlay:", elData);
            return;
        }

        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds; // Giả sử bounds là {left, top, right, bottom}

        // Ưu tiên bounds nếu có và hợp lệ
        if (bounds && typeof bounds === 'object' &&
            bounds.left !== undefined && bounds.top !== undefined &&
            bounds.right !== undefined && bounds.bottom !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10);
                el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10);
                const el_orig_bottom = parseInt(bounds.bottom, 10);

                if ([el_orig_left, el_orig_top, el_orig_right, el_orig_bottom].some(isNaN)) {
                    // console.warn(`[UtilsJS] NaN found in bounds for element index ${index}. Trying coordinates. Bounds:`, bounds);
                    el_orig_width = undefined; // Đánh dấu để thử fallback
                } else {
                    el_orig_width = el_orig_right - el_orig_left;
                    el_orig_height = el_orig_bottom - el_orig_top;
                    if (el_orig_width <= 0 || el_orig_height <= 0) {
                        // console.warn(`[UtilsJS] Invalid width/height from bounds for element index ${index}. Trying coordinates. W: ${el_orig_width}, H: ${el_orig_height}`);
                        el_orig_width = undefined; // Đánh dấu để thử fallback
                    }
                }
            } catch (e) {
                // console.warn(`[UtilsJS] Error parsing bounds for element index ${index}:`, e, `Bounds:`, bounds, `Trying coordinates.`);
                el_orig_width = undefined; // Đánh dấu để thử fallback
            }
        } else {
            // console.log(`[UtilsJS] Bounds not fully defined for element index ${index}. Trying coordinates. Bounds:`, bounds);
            el_orig_width = undefined; // Không có bounds hợp lệ, chuẩn bị fallback
        }


        // Fallback sử dụng coordinates và kích thước mặc định nếu bounds không hợp lệ hoặc thiếu
        if (el_orig_width === undefined) {
            let coord_x_val, coord_y_val;

            // Ưu tiên elData.coordinate_x/y trực tiếp nếu có (từ get_elements_for_screen của graph_db.py)
            if (elData.coordinate_x !== undefined && elData.coordinate_y !== undefined) {
                coord_x_val = elData.coordinate_x;
                coord_y_val = elData.coordinate_y;
            }
            // Nếu không, thử elData.coordinates là một object {x, y}
            else if (elData.coordinates && typeof elData.coordinates === 'object' &&
                elData.coordinates.x !== undefined && elData.coordinates.y !== undefined) {
                coord_x_val = elData.coordinates.x;
                coord_y_val = elData.coordinates.y;
            }

            if (coord_x_val !== undefined && coord_y_val !== undefined) {
                try {
                    const coord_x = parseInt(coord_x_val, 10);
                    const coord_y = parseInt(coord_y_val, 10);
                    if (isNaN(coord_x) || isNaN(coord_y)) throw new Error("NaN in coordinates");

                    const defaultSizeKey = elData.class_name || elData.element_type || 'default';
                    const defaultSize = APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY[defaultSizeKey] || APP_CONFIG.DEFAULT_SIZES_FOR_OVERLAY['default'];

                    el_orig_width = defaultSize.width;
                    el_orig_height = defaultSize.height;
                    el_orig_left = coord_x - (el_orig_width / 2); // Giả sử coordinate là tâm
                    el_orig_top = coord_y - (el_orig_height / 2); // Giả sử coordinate là tâm
                    // console.log(`[UtilsJS] Element index ${index} using fallback dimensions: L=${el_orig_left}, T=${el_orig_top}, W=${el_orig_width}, H=${el_orig_height}`);

                } catch (e) {
                    console.warn(`[UtilsJS] Error in fallback bounds calculation for element index ${index}:`, elData, e);
                    return; // Bỏ qua element này nếu không thể tính toán
                }
            } else {
                // console.warn(`[UtilsJS] Element index ${index} has neither valid bounds nor coordinates. Skipping.`);
                return; // Bỏ qua element này nếu không có thông tin tọa độ/bounds
            }
        }
        // console.log(`[UtilsJS] Final original dimensions for element index ${index}: L=${el_orig_left}, T=${el_orig_top}, W=${el_orig_width}, H=${el_orig_height}`);

        const overlay = document.createElement('div');
        overlay.className = APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE; // Đảm bảo class đúng
        overlay.dataset.elementIndex = index; // Lưu index gốc của element trong elementsData

        // Tạo title cho overlay để dễ debug
        let titleText = `Index: ${index}\n`;
        if (elData.resource_id) titleText += `ResID: ${elData.resource_id}\n`;
        if (elData.element_id) titleText += `ElemID: ${elData.element_id}\n`; // element_id có thể khác resource_id
        if (elData.text_content) titleText += `Text: ${elData.text_content.substring(0, 50)}\n`;
        if (elData.class_name) titleText += `Class: ${elData.class_name}\n`;
        if (elData.description) titleText += `Desc: ${elData.description.substring(0, 50)}\n`;
        titleText += `Bounds: [L:${el_orig_left}, T:${el_orig_top}, W:${el_orig_width}, H:${el_orig_height}]`;
        overlay.title = titleText;

        overlay.style.left = `${(el_orig_left * scaleX).toFixed(1)}px`;
        overlay.style.top = `${(el_orig_top * scaleY).toFixed(1)}px`;
        overlay.style.width = `${Math.max(5, el_orig_width * scaleX).toFixed(1)}px`; // Kích thước tối thiểu
        overlay.style.height = `${Math.max(5, el_orig_height * scaleY).toFixed(1)}px`; // Kích thước tối thiểu

        // Gắn sự kiện click
        overlay.addEventListener('click', function (event) {
            event.stopPropagation(); // Ngăn sự kiện click nổi bọt lên các element cha (như ảnh)
            console.log(`[UtilsJS] Overlay clicked! Original element index from dataset: ${this.dataset.elementIndex}`);
            if (typeof selectionHandler === 'function') {
                // Truyền index gốc của element trong mảng elementsData
                selectionHandler(parseInt(this.dataset.elementIndex)); // Chỉ truyền index
            }
        });
        containerElement.appendChild(overlay);
    });
    // console.log("[UtilsJS] Finished drawing overlays.");
}