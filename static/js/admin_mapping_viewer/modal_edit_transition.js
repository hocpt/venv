// static/js/admin_mapping_viewer/modal_edit_transition.js
import { APP_CONFIG } from './config_mapping.js';
import { sendApiRequest } from './utils_mapping.js';

let modalInstance = null;
let formElement = null;
let saveButton = null;
let errorMessagesDiv = null;
let currentNeo4jEdgeId = null;
let onSaveSuccessCallback = null; // Callback để cập nhật Cytoscape graph

// DOM ID selectors từ APP_CONFIG
const IDS = APP_CONFIG.DOM_ELEMENT_IDS;

/**
 * Khởi tạo modal sửa transition.
 * @param {function} onSaveCb - Callback sẽ được gọi khi lưu thành công, nhận (neo4jEdgeId, updatedData).
 */
let DOM_IDS_MODAL = {}; // Sẽ được gán trong init

function getModalDOMElementsAndInitInstance() {
    // Gán DOM_IDS_MODAL từ APP_CONFIG
    DOM_IDS_MODAL = {
        modal: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal,
        form: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionForm,
        saveBtn: APP_CONFIG.DOM_ELEMENT_IDS.saveTransitionChangesBtn,
        errorMsg: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionErrorMessages,
        neo4jIdInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionNeo4jIdInput,
        sourceNodeInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionSourceNodeInput,
        targetNodeInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionTargetNodeInput,
        actionTypeSelect: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionActionTypeSelect,
        elementIdInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementIdInput,
        identifierTypeInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionIdentifierTypeInput,
        elementTextInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementTextInput,
        macroCodeInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionMacroCodeInput,
        paramsJsonTextarea: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionParamsJsonTextarea,
        statusSelect: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionStatusSelect,
        attemptCountInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionAttemptCountInput,
        successCountInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionSuccessCountInput
    };

    console.log("MODAL_EDIT_TRANSITION: getModalDOMElements - Attempting to get elements with IDS:", JSON.parse(JSON.stringify(DOM_IDS_MODAL)));

    const modalEl = document.getElementById(DOM_IDS_MODAL.modal);
    formElement = document.getElementById(DOM_IDS_MODAL.form);
    saveButton = document.getElementById(DOM_IDS_MODAL.saveBtn);
    errorMessagesDiv = document.getElementById(DOM_IDS_MODAL.errorMsg);

    let allFound = true;
    if (!modalEl) { console.error(`MODAL_EDIT_TRANSITION: Modal element ('${DOM_IDS_MODAL.modal}') not found!`); allFound = false; }
    if (!formElement) { console.error(`MODAL_EDIT_TRANSITION: Form element ('${DOM_IDS_MODAL.form}') not found!`); allFound = false; }
    if (!saveButton) { console.error(`MODAL_EDIT_TRANSITION: Save button ('${DOM_IDS_MODAL.saveBtn}') not found!`); allFound = false; }
    // Kiểm tra các element khác nếu cần thiết cho hoạt động cơ bản của modal
    if (!document.getElementById(DOM_IDS_MODAL.actionTypeSelect)) { console.warn(`MODAL_EDIT_TRANSITION: Dropdown ActionType ('${DOM_IDS_MODAL.actionTypeSelect}') not found.`); }
    if (!document.getElementById(DOM_IDS_MODAL.statusSelect)) { console.warn(`MODAL_EDIT_TRANSITION: Dropdown Status ('${DOM_IDS_MODAL.statusSelect}') not found.`); }


    if (modalEl && allFound) { // Chỉ tạo instance nếu modal và các thành phần cốt lõi tồn tại
        modalInstance = new bootstrap.Modal(modalEl);
        return true;
    }
    return false;
}
export function initEditTransitionModal(onSaveCb) {
    console.log("MODAL_EDIT_TRANSITION: initEditTransitionModal called.");

    if (!getModalDOMElementsAndInitInstance()) {
        console.error("MODAL_EDIT_TRANSITION: CRITICAL - Failed to get essential modal DOM elements or create instance. Modal functionality disabled.");
        return; // Dừng khởi tạo nếu không lấy được các element cơ bản
    }

    onSaveSuccessCallback = onSaveCb;

    if (formElement && saveButton) {
        populateDropdown(DOM_IDS_MODAL.actionTypeSelect, APP_CONFIG.VALID_ACTION_TYPES);
        populateDropdown(DOM_IDS_MODAL.statusSelect, APP_CONFIG.VALID_TRANSITION_STATUSES);
        formElement.addEventListener('submit', handleFormSubmit);
        console.log("MODAL_EDIT_TRANSITION: Form submit listener attached.");
    } else {
        console.warn("MODAL_EDIT_TRANSITION: Form hoặc nút Save không tìm thấy sau khi getModalDOMElements. Form submit sẽ không hoạt động.");
    }
    console.log("MODAL_EDIT_TRANSITION: Initialized (hoặc đã cố gắng khởi tạo).");
}

/**
 * Điền options vào một select element.
 */
function populateDropdown(selectElementId, optionsArray, selectedValue = null) {
    const selectElement = document.getElementById(selectElementId);
    if (!selectElement) {
        console.warn(`MODAL_EDIT_TRANSITION: Dropdown element #${selectElementId} not found.`);
        return;
    }
    selectElement.innerHTML = ''; // Xóa options cũ
    optionsArray.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value;
        option.textContent = opt.label;
        if (selectedValue && opt.value === selectedValue) {
            option.selected = true;
        }
        selectElement.appendChild(option);
    });
}


export function openEditTransitionModal(edgeData) {
    if (!modalInstance || !formElement) {
        console.error("MODAL_EDIT_TRANSITION: Cannot open modal. Instance or form not initialized.");
        alert("Lỗi: Chức năng sửa transition chưa sẵn sàng (thiếu form).");
        return;
    }
    if (errorMessagesDiv) errorMessagesDiv.textContent = '';
    formElement.reset();

    currentNeo4jEdgeId = edgeData.neo4j_edge_id;
    // Sử dụng DOM_IDS_MODAL đã được gán
    document.getElementById(DOM_IDS_MODAL.neo4jIdInput).value = currentNeo4jEdgeId || '';
    document.getElementById(DOM_IDS_MODAL.sourceNodeInput).value = edgeData.source || '';
    document.getElementById(DOM_IDS_MODAL.targetNodeInput).value = edgeData.target || '';

    populateDropdown(DOM_IDS_MODAL.actionTypeSelect, APP_CONFIG.VALID_ACTION_TYPES, edgeData.action_type || '');
    populateDropdown(DOM_IDS_MODAL.statusSelect, APP_CONFIG.VALID_TRANSITION_STATUSES, edgeData.status || 'provisional');

    document.getElementById(DOM_IDS_MODAL.elementIdInput).value = edgeData.element_id || '';
    document.getElementById(DOM_IDS_MODAL.identifierTypeInput).value = edgeData.identifier_type || '';
    document.getElementById(DOM_IDS_MODAL.elementTextInput).value = edgeData.element_text || '';
    document.getElementById(DOM_IDS_MODAL.macroCodeInput).value = edgeData.macro_code || '';

    let paramsJsonString = edgeData.params_json || '';
    try {
        if (paramsJsonString) {
            const parsedJson = JSON.parse(paramsJsonString);
            paramsJsonString = JSON.stringify(parsedJson, null, 2);
        }
    } catch (e) {
        console.warn("MODAL_EDIT_TRANSITION: params_json không hợp lệ, hiển thị dạng thô:", paramsJsonString, e);
    }
    document.getElementById(DOM_IDS_MODAL.paramsJsonTextarea).value = paramsJsonString;

    document.getElementById(DOM_IDS_MODAL.attemptCountInput).value = edgeData.attempt_count !== undefined ? edgeData.attempt_count : 0;
    document.getElementById(DOM_IDS_MODAL.successCountInput).value = edgeData.success_count !== undefined ? edgeData.success_count : 0;

    console.log("MODAL_EDIT_TRANSITION: Opening modal for edge:", edgeData);
    modalInstance.show();
}
/**
 * Xử lý khi form sửa transition được submit.
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    if (!saveButton || !errorMessagesDiv || !currentNeo4jEdgeId) {
        console.error("MODAL_EDIT_TRANSITION: handleFormSubmit - Nút save, error div hoặc currentNeo4jEdgeId bị thiếu.");
        return;
    }

    saveButton.disabled = true;
    saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang lưu...';
    errorMessagesDiv.textContent = '';

    let paramsJsonForPayload = document.getElementById(IDS.editTransitionParamsJsonTextarea).value.trim();
    if (paramsJsonForPayload) {
        try {
            JSON.parse(paramsJsonForPayload); // Chỉ validate
        } catch (e) {
            errorMessagesDiv.textContent = 'Lỗi: "Tham Số Hành Động" không phải là JSON hợp lệ.';
            saveButton.disabled = false; saveButton.textContent = 'Lưu Thay Đổi';
            return;
        }
    } else {
        paramsJsonForPayload = null;
    }

    const updatedProperties = {
        action_type: document.getElementById(IDS.editTransitionActionTypeSelect).value,
        element_id: document.getElementById(IDS.editTransitionElementIdInput).value.trim() || null,
        identifier_type: document.getElementById(IDS.editTransitionIdentifierTypeInput).value.trim() || null,
        element_text: document.getElementById(IDS.editTransitionElementTextInput).value.trim() || null,
        macro_code: document.getElementById(IDS.editTransitionMacroCodeInput).value.trim() || null,
        params_json_str: paramsJsonForPayload,
        status: document.getElementById(IDS.editTransitionStatusSelect).value,
        attempt_count: parseInt(document.getElementById(IDS.editTransitionAttemptCountInput).value) || 0,
        success_count: parseInt(document.getElementById(IDS.editTransitionSuccessCountInput).value) || 0,
        action_type: document.getElementById(DOM_IDS_MODAL.actionTypeSelect).value,
        element_id: document.getElementById(DOM_IDS_MODAL.elementIdInput).value.trim() || null,
        // ... lấy các giá trị khác từ input sử dụng DOM_IDS_MODAL ...
        params_json_str: paramsJsonForPayload,
        status: document.getElementById(DOM_IDS_MODAL.statusSelect).value,
    };

    // Loại bỏ các giá trị null không cần thiết nếu backend không muốn nhận
    // Object.keys(updatedProperties).forEach(key => {
    //     if (updatedProperties[key] === null && 
    //         !['params_json_str', 'element_id', 'identifier_type', 'element_text', 'macro_code'].includes(key)) {
    //         delete updatedProperties[key];
    //     }
    // });

    const apiUrl = `${APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION}${encodeURIComponent(currentNeo4jEdgeId)}`;
    console.log("MODAL_EDIT_TRANSITION: Updating transition. URL:", apiUrl, "Payload:", updatedProperties);

    try {
        const result = await sendApiRequest(apiUrl, 'POST', updatedProperties);
        if (result.success) {
            alert('Cập nhật transition thành công!');
            modalInstance.hide();
            if (typeof onSaveSuccessCallback === 'function') {
                // Truyền ID và dữ liệu đã cập nhật để cytoscape_manager xử lý
                onSaveSuccessCallback(currentNeo4jEdgeId, updatedProperties);
            }
        } else {
            errorMessagesDiv.textContent = result.error || result.message || 'Lỗi không xác định từ server.';
        }
    } catch (error) {
        console.error("MODAL_EDIT_TRANSITION: Lỗi khi gửi yêu cầu cập nhật transition:", error);
        errorMessagesDiv.textContent = error.data?.message || error.message || 'Lỗi kết nối hoặc xử lý server.';
    } finally {
        saveButton.disabled = false;
        saveButton.textContent = 'Lưu Thay Đổi';
    }
}
