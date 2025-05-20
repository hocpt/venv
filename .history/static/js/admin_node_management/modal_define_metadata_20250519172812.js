// static/js/admin_node_management/modal_define_metadata.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest } from './utils.js';

let defineMetadataModalInstance = null;
// DOM Elements
let modalEl, form, unknownNodeNeo4jIdInput, currentUnknownScreenIdInput, selectedConditionsJsonInput,
    currentUnknownScreenIdDisplay, appNameInput, activityNameInput, logicalNameInput,
    newDefinedScreenIdInput, descriptionInput, conditionsCountDisplay, errorMessagesSpan, saveBtn;

function getDOMElementsMetadata() {
    modalEl = document.getElementById(APP_CONFIG.ELEMENT_IDS.DEFINE_METADATA_MODAL);
    form = document.getElementById(APP_CONFIG.ELEMENT_IDS.DEFINE_METADATA_FORM);
    unknownNodeNeo4jIdInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_NODE_NEO4J_ID_INPUT);
    currentUnknownScreenIdInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_CURRENT_UNKNOWN_SCREEN_ID_INPUT);
    selectedConditionsJsonInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_SELECTED_CONDITIONS_JSON_INPUT);
    currentUnknownScreenIdDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_CURRENT_UNKNOWN_SCREEN_ID_DISPLAY);
    appNameInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_APP_NAME_INPUT);
    activityNameInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_ACTIVITY_NAME_INPUT);
    logicalNameInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_LOGICAL_NAME_INPUT);
    newDefinedScreenIdInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_NEW_DEFINED_SCREEN_ID_INPUT);
    descriptionInput = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_DESCRIPTION_INPUT);
    conditionsCountDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_CONDITIONS_COUNT_DISPLAY);
    errorMessagesSpan = document.getElementById(APP_CONFIG.ELEMENT_IDS.DEFINE_METADATA_ERROR_MESSAGES);
    saveBtn = document.getElementById(APP_CONFIG.ELEMENT_IDS.SAVE_NEW_PIE_DEFINITION_BTN);
}


function openDefineNewPieMetadataModal(nodeDataSource, conditionsToSave) {
    if (!defineMetadataModalInstance) {
        getDOMElementsMetadata(); // Ensure DOM elements are fetched
        if (!modalEl) { console.error("Modal #defineNewPieMetadataModal instance not available for open."); return; }
        defineMetadataModalInstance = new bootstrap.Modal(modalEl);
    }
    if (form) form.reset();
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';
    console.log("[METADATA_MODAL] openDefineNewPieMetadataModal received nodeDataSource:", JSON.stringify(nodeDataSource));
    if (unknownNodeNeo4jIdInput) { // unknownNodeNeo4jIdInput là document.getElementById(APP_CONFIG.ELEMENT_IDS.METADATA_NODE_NEO4J_ID_INPUT)
        const neoId = nodeDataSource.nodeNeo4jId;
        if (neoId !== undefined && neoId !== null && String(neoId).trim() !== "" && String(neoId).toLowerCase() !== "none") {
            unknownNodeNeo4jIdInput.value = neoId;
            console.log(`[METADATA_MODAL] Set metadata_unknownNodeNeo4jId INPUT to: '${neoId}'`);
        } else {
            unknownNodeNeo4jIdInput.value = ''; // Quan trọng: Để trống nếu không hợp lệ
            console.error("[METADATA_MODAL] CRITICAL: nodeNeo4jId is invalid or 'None' string in nodeDataSource!", nodeDataSource);
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi: ID của Node Neo4j gốc không hợp lệ.';
        }
        if (nodeDataSource && nodeDataSource.nodeNeo4jId !== undefined && nodeDataSource.nodeNeo4jId !== null) {
            unknownNodeNeo4jIdInput.value = nodeDataSource.nodeNeo4jId;
            console.log(`[METADATA_MODAL] Set metadata_unknownNodeNeo4jId INPUT to: ${unknownNodeNeo4jIdInput.value}`); // KIỂM TRA GIÁ TRỊ INPUT
        } else {
            unknownNodeNeo4jIdInput.value = '';
            console.error("[METADATA_MODAL] CRITICAL: nodeNeo4jId is MISSING or null/undefined in nodeDataSource!", nodeDataSource);
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi nghiêm trọng: Không thể xác định Node Neo4j gốc.';
        }
    } else {
        console.error("[METADATA_MODAL] Input #metadata_unknownNodeNeo4jId not found in DOM!");
    }
    if (currentUnknownScreenIdInput) currentUnknownScreenIdInput.value = nodeDataSource.currentScreenId || '';
    if (currentUnknownScreenIdDisplay) currentUnknownScreenIdDisplay.textContent = nodeDataSource.currentScreenId || 'N/A';
    if (appNameInput) appNameInput.value = nodeDataSource.appName || '';
    if (activityNameInput) activityNameInput.value = nodeDataSource.activityName || '';
    if (logicalNameInput) logicalNameInput.value = '';
    if (newDefinedScreenIdInput) newDefinedScreenIdInput.value = '';
    if (descriptionInput) descriptionInput.value = '';
    if (selectedConditionsJsonInput) selectedConditionsJsonInput.value = JSON.stringify(conditionsToSave || []);
    if (conditionsCountDisplay) conditionsCountDisplay.textContent = (conditionsToSave || []).length;

    defineMetadataModalInstance.show();
}

export function initDefineMetadataModal() {
    getDOMElementsMetadata();
    if (!modalEl || !form || !saveBtn) {
        console.error("Một hoặc nhiều element của Define Metadata Modal không tìm thấy.");
        return;
    }
    // Gán hàm vào global scope để modal_manage_pie.js có thể gọi
    window.openDefineNewPieMetadataModalGlobal = openDefineNewPieMetadataModal;


    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        if (errorMessagesSpan) errorMessagesSpan.textContent = '';
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang lưu...';
        const unknownNodeIdFromInput = unknownNodeNeo4jIdInput.value;
        console.log("[METADATA_MODAL] Submitting form. Value of unknownNodeNeo4jIdInput FROM INPUT FIELD:", unknownNodeIdFromInput); // KIỂM TRA GIÁ TRỊ LẤY TỪ INPUT
        if (!unknownNodeIdFromInput || unknownNodeIdFromInput.trim() === '') {
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi nghiêm trọng: unknown_node_neo4j_id bị thiếu khi submit. Vui lòng thử lại từ đầu.';
            console.error("[METADATA_MODAL] CRITICAL: unknown_node_neo4j_id input is EMPTY on form submit!");
            // ... (reset nút save, return)
            return;
        }
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
        console.log("[METADATA_MODAL] Payload to be sent:", JSON.stringify(payload)); // KIỂM TRA PAYLOAD
        if (!payload.logical_name || !payload.new_defined_screen_id) {
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Tên Logic và Defined Screen ID là bắt buộc.';
            saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE'; return;
        }
        if (payload.selected_conditions.length === 0) {
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Cần có ít nhất một điều kiện nhận diện.';
            saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE'; return;
        }
        if (!/^[a-z0-9_]+$/.test(payload.new_defined_screen_id)) {
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Defined Screen ID mới chỉ được chứa chữ thường, số, và dấu gạch dưới (_).';
            saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE'; return;
        }

        try {
            const result = await sendApiRequest(APP_CONFIG.API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL, 'POST', payload);
            if (result.success) {
                alert("Định nghĩa PIE mới và cập nhật Node thành công!");
                if (defineMetadataModalInstance) defineMetadataModalInstance.hide();
                if (window.fetchAndRenderTableNodes) window.fetchAndRenderTableNodes(); else location.reload();
            } else { throw new Error(result.message || "Lưu PIE thất bại."); }
        } catch (error) {
            console.error("Lỗi khi lưu PIE definition mới:", error);
            if (errorMessagesSpan) errorMessagesSpan.textContent = error.data?.message || error.message || 'Lỗi không xác định.';
        } finally {
            saveBtn.disabled = false; saveBtn.textContent = 'Lưu Định nghĩa PIE';
        }
    });
}