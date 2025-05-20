// static/js/admin_node_management/main.js
// Sẽ import các hàm init từ các module khác nếu dùng ES Modules
// import { initManagePieModal } from './modal_manage_pie.js';
// import { initDefineMetadataModal } from './modal_define_metadata.js';
// import { initTableHandler } from './table_handler.js';
// import { initializeAppConfig } from './config.js';

document.addEventListener('DOMContentLoaded', function () {
    // Lấy các giá trị URL API và config từ global scope được nhúng bởi template
    // Giả sử template đã nhúng các giá trị này vào một đối tượng global tên là `templatePageConfig`
    if (typeof templatePageConfig !== 'undefined') {
        initializeAppConfig(templatePageConfig); // Hàm này nằm trong config.js
    } else {
        console.warn("templatePageConfig không được định nghĩa. Các URL API có thể không hoạt động.");
        // Initialize với giá trị rỗng để APP_CONFIG tồn tại
        initializeAppConfig({});
    }


    // Khởi tạo các thành phần
    // Thứ tự quan trọng nếu có sự phụ thuộc DOM hoặc hàm

    // 1. Khởi tạo logic cho modal quản lý PIE conditions
    if (typeof initManagePieModal === "function") {
        initManagePieModal();
    } else {
        console.error("initManagePieModal is not defined. Make sure modal_manage_pie.js is loaded and correct.");
    }

    // 2. Khởi tạo logic cho modal định nghĩa metadata PIE mới
    if (typeof initDefineMetadataModal === "function") {
        initDefineMetadataModal();
    } else {
        console.error("initDefineMetadataModal is not defined. Make sure modal_define_metadata.js is loaded and correct.");
    }

    // 3. Khởi tạo logic cho bảng (filter, pagination, actions)
    // Hàm này cũng sẽ gọi fetchAndRenderTableNodes lần đầu nếu cần
    if (typeof initTableHandler === "function") {
        initTableHandler();
    } else {
        console.error("initTableHandler is not defined. Make sure table_handler.js is loaded and correct.");
    }


    // Các khởi tạo khác nếu có...
    // Ví dụ, logic cho modal xem ảnh gốc (originalImagePreviewModal) nếu vẫn giữ lại
    const originalImagePreviewModalEl = document.getElementById('originalImagePreviewModal');
    if (originalImagePreviewModalEl && typeof bootstrap !== 'undefined') {
        const modalInstance = new bootstrap.Modal(originalImagePreviewModalEl);
        // Gắn listener cho 'show.bs.modal' nếu cần (tương tự code gốc của bạn)
        originalImagePreviewModalEl.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            if (!button || !button.dataset) return;

            const modalImgOrig = document.getElementById('modalScreenshotImageOriginal');
            const modalElementsListOrig = document.getElementById('originalModalElementsList');
            const modalScreenIdDispOrig = document.getElementById('originalModalScreenIdDisplay');
            const modalContainerOrig = document.getElementById('modalScreenshotContainerOriginal');

            const imageUrl = button.dataset.imageUrl; // Lấy từ data-bs-image-url
            const screenId = button.dataset.screenId;   // Lấy từ data-bs-screen-id
            const elementsUrl = button.dataset.elementsUrl; // Lấy từ data-bs-elements-url
            const origW = parseInt(button.dataset.originalWidth);
            const origH = parseInt(button.dataset.originalHeight);

            if (modalScreenIdDispOrig) modalScreenIdDispOrig.textContent = screenId || 'N/A';
            if (modalImgOrig) {
                modalImgOrig.src = imageUrl || '';
                modalImgOrig.style.display = imageUrl ? 'block' : 'none';
            }
            if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-muted small">Đang tải elements...</p>';
            if (modalContainerOrig) modalContainerOrig.querySelectorAll('.element-overlay-displayonly').forEach(ov => ov.remove());

            if (imageUrl && elementsUrl && modalImgOrig) {
                modalImgOrig.onload = function () {
                    fetch(elementsUrl)
                        .then(res => res.json())
                        .then(data => {
                            if (data.success && data.elements) {
                                // Cần hàm drawDisplayOnlyOverlays (tương tự drawInteractiveOverlays nhưng class khác và không có event click)
                                // drawDisplayOnlyOverlays(modalImgOrig, data.elements, origW, origH, modalContainerOrig);
                                console.log("Cần hàm drawDisplayOnlyOverlays cho modal xem ảnh gốc");
                                if (modalElementsListOrig) {
                                    modalElementsListOrig.innerHTML = '';
                                    data.elements.forEach(el => {
                                        const li = document.createElement('li'); li.className = 'list-group-item small';
                                        li.innerHTML = `<strong>ID:</strong> ${el.resource_id || el.element_id || 'N/A'} <br>
                                                    <strong>Text:</strong> ${el.text_content || '--'} <br>
                                                    <strong>Class:</strong> ${el.class_name || 'N/A'}`;
                                        modalElementsListOrig.appendChild(li);
                                    });
                                    if (data.elements.length === 0) modalElementsListOrig.innerHTML = '<p class="text-muted small">Không có elements.</p>';
                                }
                            } else {
                                if (modalElementsListOrig) modalElementsListOrig.innerHTML = `<p class="text-danger small">Lỗi: ${data.error || 'Không lấy được elements.'}</p>`;
                            }
                        })
                        .catch(err => {
                            if (modalElementsListOrig) modalElementsListOrig.innerHTML = `<p class="text-danger small">Lỗi tải elements: ${err.message}</p>`;
                        });
                };
                modalImgOrig.onerror = () => { if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-danger small">Lỗi tải ảnh.</p>'; };
            } else {
                if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-muted small">Không có đủ thông tin để tải ảnh/elements.</p>';
            }
        });
    }

    console.log("Admin Node Management page initialized.");
});