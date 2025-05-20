// static/js/admin_node_management/utils.js

/**
 * Gửi AJAX request (dùng Fetch API)
 * @param {string} url URL của API
 * @param {string} method Phương thức HTTP (GET, POST, PUT, DELETE)
 * @param {object} [body=null] Body của request (cho POST, PUT)
 * @param {object} [headers={}] Headers tùy chỉnh
 * @returns {Promise<object>} Promise giải quyết với dữ liệu JSON từ server
 */
async function sendApiRequest(url, method = 'GET', body = null, headers = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json',
        'X-CSRFToken': APP_CONFIG.CSRF_TOKEN // Giả sử APP_CONFIG.CSRF_TOKEN đã được set
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
            // Ném lỗi với thông điệp từ server nếu có, nếu không dùng statusText
            const error = new Error(responseData.message || responseData.error || response.statusText || `HTTP error! status: ${response.status}`);
            error.response = response; // Gắn response vào lỗi để xử lý thêm nếu cần
            error.data = responseData;
            throw error;
        }
        return responseData;
    } catch (error) {
        console.error(`Lỗi API request đến ${url}:`, error);
        throw error; // Ném lại lỗi để hàm gọi xử lý
    }
}


/**
 * Hàm vẽ các overlay tương tác lên ảnh.
 * @param {HTMLImageElement} imgElement - Element <img> đang hiển thị ảnh.
 * @param {Array<object>} elementsData - Mảng dữ liệu các elements từ API.
 * @param {number} nodeOriginalWidth - Chiều rộng gốc của màn hình.
 * @param {number} nodeOriginalHeight - Chiều cao gốc của màn hình.
 * @param {HTMLElement} containerElement - Container div chứa ảnh và các overlays.
 * @param {Array<object>} currentSelectedConditions - Danh sách conditions hiện tại để highlight.
 * @param {function} selectionHandler - Hàm callback khi một element được click. (elementData, domOverlay)
 */
function drawInteractiveOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight, containerElement, currentSelectedConditions, selectionHandler) {
    if (!containerElement) { console.error("drawInteractiveOverlays: containerElement is null!"); return; }
    containerElement.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 || displayedImgWidth === 0 || displayedImgHeight === 0) {
        console.warn(`Kích thước không hợp lệ để vẽ overlay. Gốc: ${nodeOriginalWidth}x${nodeOriginalHeight}, Hiển thị: ${displayedImgWidth}x${displayedImgHeight}`);
        // Có thể thêm thông báo lỗi vào containerElement
        return;
    }

    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;

    if (!elementsData || !elementsData.length) {
        // console.log("Không có element data để vẽ overlays.");
        return;
    }

    elementsData.forEach((elData, index) => {
        // Cần element_id hoặc resource_id để định danh, và bounds để vẽ
        if (!elData || (!elData.element_id && !elData.resource_id) || !elData.bounds) return;

        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds;

        if (bounds && typeof bounds === 'object' && bounds.left !== undefined && bounds.top !== undefined && bounds.right !== undefined && bounds.bottom !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10);
                el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10);
                const el_orig_bottom = parseInt(bounds.bottom, 10);
                if (isNaN(el_orig_left) || isNaN(el_orig_top) || isNaN(el_orig_right) || isNaN(el_orig_bottom)) throw new Error("NaN in bounds");
                el_orig_width = el_orig_right - el_orig_left;
                el_orig_height = el_orig_bottom - el_orig_top;
                if (el_orig_width <= 0 || el_orig_height <= 0) { el_orig_width = undefined; }
            } catch (e) { el_orig_width = undefined; }
        }

        if (el_orig_width === undefined) { // Fallback nếu bounds không hợp lệ
            // console.warn("Bounds không hợp lệ cho element:", elData);
            // Có thể thử fallback bằng coordinates và default size nếu có, nhưng hiện tại chỉ bỏ qua
            return;
        }

        const x_on_image = el_orig_left * scaleX;
        const y_on_image = el_orig_top * scaleY;
        let width_on_image = el_orig_width * scaleX;
        let height_on_image = el_orig_height * scaleY;

        width_on_image = Math.max(width_on_image, 5); // Kích thước tối thiểu để click
        height_on_image = Math.max(height_on_image, 5);

        const overlay = document.createElement('div');
        overlay.className = APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE;
        overlay.dataset.elementIndex = index; // Lưu index để lấy lại data gốc từ mảng rawElementsDataForModal
        overlay.title = `Click để chọn/bỏ chọn\nID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nClass: ${elData.class_name || 'N/A'}`;
        overlay.style.left = `${x_on_image.toFixed(1)}px`;
        overlay.style.top = `${y_on_image.toFixed(1)}px`;
        overlay.style.width = `${width_on_image.toFixed(1)}px`;
        overlay.style.height = `${height_on_image.toFixed(1)}px`;

        // Kiểm tra xem element này có trong currentSelectedPieConditions không
        // (Logic kiểm tra selection sẽ nằm trong module modal_manage_pie.js khi nó gọi hàm này)
        // Tạm thời không highlight ở đây, để module gọi tự quản lý class 'selected-for-pie'

        overlay.addEventListener('click', function () {
            if (typeof selectionHandler === 'function') {
                selectionHandler(elData, this); // Truyền elData gốc và DOM element của overlay
            }
        });
        containerElement.appendChild(overlay);
    });
}

// Nếu dùng ES Modules:
// export { sendApiRequest, drawInteractiveOverlays };