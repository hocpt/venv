// static/js/admin_node_management/main.js
import { initializeAppConfig } from './config.js';
import { initManagePieModal } from './modal_manage_pie.js';
import { initDefineMetadataModal } from './modal_define_metadata.js';
import { initTableHandler } from './table_handler.js'; // Giả sử initTableHandler chứa cả fetch lần đầu

document.addEventListener('DOMContentLoaded', function () {
    // Nhận config từ global scope (được nhúng bởi template)
    if (typeof window.templatePageConfig !== 'undefined') {
        initializeAppConfig(window.templatePageConfig);
    } else {
        console.warn("templatePageConfig is not defined. API URLs might be incorrect.");
        initializeAppConfig({}); // Khởi tạo với giá trị rỗng để APP_CONFIG tồn tại
    }

    // Khởi tạo các modules
    initManagePieModal();
    initDefineMetadataModal();
    initTableHandler(); // Hàm này sẽ tự gọi fetchAndRenderTableNodes lần đầu

    // Logic cho modal xem ảnh gốc (nếu vẫn giữ lại)
    const originalImagePreviewModalEl = document.getElementById('originalImagePreviewModal');
    if (originalImagePreviewModalEl && typeof bootstrap !== 'undefined') {
        // const modalInstance = new bootstrap.Modal(originalImagePreviewModalEl); // Không cần new liên tục
        originalImagePreviewModalEl.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            if (!button || !button.dataset) return;

            const modalImgOrig = document.getElementById('modalScreenshotImageOriginal');
            const modalElementsListOrig = document.getElementById('originalModalElementsList');
            const modalScreenIdDispOrig = document.getElementById('originalModalScreenIdDisplay');
            // const modalContainerOrig = document.getElementById('modalScreenshotContainerOriginal');

            const imageUrl = button.dataset.imageUrl || button.dataset.bsImageUrl; // Kiểm tra cả data-bs-
            const screenId = button.dataset.screenId || button.dataset.bsScreenId;
            const elementsUrl = button.dataset.elementsUrl || button.dataset.bsElementsUrl;
            const origW = parseInt(button.dataset.originalWidth || button.dataset.bsOriginalWidth);
            const origH = parseInt(button.dataset.originalHeight || button.dataset.bsOriginalHeight);

            if (modalScreenIdDispOrig) modalScreenIdDispOrig.textContent = screenId || 'N/A';
            if (modalImgOrig) {
                modalImgOrig.src = imageUrl || '';
                modalImgOrig.style.display = imageUrl ? 'block' : 'none';
            }
            if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-muted small">Đang tải elements...</p>';
            // if (modalContainerOrig) modalContainerOrig.querySelectorAll('.element-overlay-displayonly').forEach(ov => ov.remove());

            if (imageUrl && elementsUrl && modalImgOrig) {
                modalImgOrig.onload = function () {
                    fetch(elementsUrl) // Không cần sendApiRequest vì đây là GET đơn giản
                        .then(res => { if (!res.ok) throw new Error("Network response was not ok for elements."); return res.json(); })
                        .then(data => {
                            if (data.success && data.elements) {
                                // console.log("Cần hàm drawDisplayOnlyOverlays cho modal xem ảnh gốc");
                                if (modalElementsListOrig) {
                                    modalElementsListOrig.innerHTML = '';
                                    if (data.elements.length > 0) {
                                        const ul = document.createElement('ul'); ul.className = 'list-group list-group-flush';
                                        data.elements.forEach(el => {
                                            const li = document.createElement('li'); li.className = 'list-group-item list-group-item-sm py-1 px-0';
                                            li.innerHTML = `<strong>ID:</strong> ${el.resource_id || el.element_id || 'N/A'} <br>
                                                        <small><strong>Text:</strong> ${el.text_content || '--'} | 
                                                        <strong>Class:</strong> ${el.class_name ? el.class_name.replace('android.widget.', '') : 'N/A'}</small>`;
                                            ul.appendChild(li);
                                        });
                                        modalElementsListOrig.appendChild(ul);
                                    } else {
                                        modalElementsListOrig.innerHTML = '<p class="text-muted small">Không có elements.</p>';
                                    }
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
                if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-muted small">Thiếu thông tin để tải ảnh/elements.</p>';
            }
        });
    }

    console.log("Admin Node Management page fully initialized via JS modules.");
});