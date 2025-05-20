// static/js/admin_node_management/modal_define_metadata.js
// Cần import sendApiRequest từ utils.js nếu dùng ES Modules
// import { sendApiRequest } from './utils.js';
// import { APP_CONFIG } from './config.js'; // Hoặc truy cập window.APP_CONFIG

function initDefineMetadataModal() {
    const modalEl = document.getElementById(APP_CONFIG.ELEMENT_IDS.DEFINE_METADATA_MODAL);
    if (!modalEl) {
        console.error("Modal #defineNewPieMetadataModal không tìm thấy.");
        return;
    }
    const modalInstance = new bootstrap.Modal(modalEl);
    const form = document.getElementById(APP_CONFIG.ELEMENT_IDS.DEFINE_METADATA_FORM);

    const unknownNodeNeo4jIdInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_NODE_NEO4J_ID_INPUT);
    const currentUnknownScreenIdInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_CURRENT_UNKNOWN_SCREEN_ID_INPUT);
    const selectedConditionsJsonInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_SELECTED_CONDITIONS_JSON_INPUT);
    const currentUnknownScreenIdDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_CURRENT_UNKNOWN_SCREEN_ID_DISPLAY);
    const appNameInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_APP_NAME_INPUT);
    const activityNameInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_ACTIVITY_NAME_INPUT);
    const logicalNameInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_LOGICAL_NAME_INPUT);
    const newDefinedScreenIdInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_NEW_DEFINED_SCREEN_ID_INPUT);
    const descriptionInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_DESCRIPTION_INPUT);
    const conditionsCountDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_CONDITIONS_COUNT_DISPLAY);
    const errorMessagesSpan = document.getElementById(APP_CONFIG.ELEMENT_IDS.DEFINE_METADATA_ERROR_MESSAGES);
    const saveBtn = document.getElementById(APP_CONFIG.ELEMENT_IDS.SAVE_NEW_PIE_DEFINITION_BTN);

    function openDefineNewPieMetadataModal(nodeDataSource, conditionsToSave) {
        if (!modalInstance) return;
        if (form) form.reset(); // Reset form trước
        if (errorMessagesSpan) errorMessagesSpan.textContent = '';

        if (unknownNodeNeo4jIdInput) unknownNodeNeo4jIdInput.value = nodeDataSource.nodeNeo4jId || '';
        if (currentUnknownScreenIdInput) currentUnknownScreenIdInput.value = nodeDataSource.currentScreenId || '';
        if (currentUnknownScreenIdDisplay) currentUnknownScreenIdDisplay.textContent = nodeDataSource.currentScreenId || 'N/A';

        if (appNameInput) appNameInput.value = nodeDataSource.appName || '';
        if (activityNameInput) activityNameInput.value = nodeDataSource.activityName || '';

        // Các trường này người dùng sẽ nhập
        if (logicalNameInput) logicalNameInput.value = '';
        if (newDefinedScreenIdInput) newDefinedScreenIdInput.value = '';
        if (descriptionInput) descriptionInput.value = '';

        if (selectedConditionsJsonInput) selectedConditionsJsonInput.value = JSON.stringify(conditionsToSave || []);
        if (conditionsCountDisplay) conditionsCountDisplay.textContent = (conditionsToSave || []).length;

        modalInstance.show();
    }

    if (form && saveBtn) {
        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            if (errorMessagesSpan) errorMessagesSpan.textContent = '';
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang lưu...';

            const payload = {
                unknown_node_neo4j_id: unknownNodeNeo4jIdInput.value,
                current_unknown_screen_id: currentUnknownScreenIdInput.value,
                app_name: appNameInput.value,
                activity_name: activityNameInput.value || null,
                logical_name: logicalNameInput.value.trim(),
                new_defined_screen_id: newDefinedScreenIdInput.value.trim(),
                selected_conditions: JSON.parse(selectedConditionsJsonInput.value || '[]'),
                description: descriptionInput.value.trim() || null
            };

            if (!payload.logical_name || !payload.new_defined_screen_id) {
                if (errorMessagesSpan) errorMessagesSpan.textContent = 'Tên Logic và Defined Screen ID là bắt buộc.';
                saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE';
                return;
            }
            if (payload.selected_conditions.length === 0) {
                if (errorMessagesSpan) errorMessagesSpan.textContent = 'Cần có ít nhất một điều kiện nhận diện đã được chọn.';
                saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE';
                return;
            }
            // Validate new_defined_screen_id format (chỉ chữ thường, số, gạch dưới)
            if (!/^[a-z0-9_]+$/.test(payload.new_defined_screen_id)) {
                if (errorMessagesSpan) errorMessagesSpan.textContent = 'Defined Screen ID mới chỉ được chứa chữ thường, số, và dấu gạch dưới (_).';
                saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE';
                return;
            }


            try {
                const result = await sendApiRequest(APP_CONFIG.API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL, 'POST', payload); // Dùng sendApiRequest

                if (result.success) {
                    alert("Định nghĩa PIE mới và cập nhật Node thành công!");
                    modalInstance.hide();
                    // Gọi hàm tải lại bảng từ table_handler.js
                    if (window.fetchAndRenderTableNodes) window.fetchAndRenderTableNodes(); else location.reload();
                } else {
                    // Lỗi từ server đã được throw bởi sendApiRequest nếu response.ok là false
                    throw new Error(result.message || "Lưu PIE thất bại từ server.");
                }
            } catch (error) {
                console.error("Lỗi khi lưu PIE definition mới:", error);
                if (errorMessagesSpan) errorMessagesSpan.textContent = error.data ? (error.data.message || error.data.error || error.message) : error.message;

            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = 'Lưu Định nghĩa PIE';
            }
        });
    }
    // Export hàm để module khác gọi
    window.openDefineNewPieMetadataModal = openDefineNewPieMetadataModal;
}
// initDefineMetadataModal();