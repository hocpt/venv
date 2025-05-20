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
function getModalDOMElements() {
    console.log("MODAL_EDIT_TRANSITION: getModalDOMElements - Attempting to get elements with IDS:", JSON.parse(JSON.stringify(IDS)));

    const modalEl = document.getElementById(IDS.editTransitionModal);
    formElement = document.getElementById(IDS.editTransitionForm);
    saveButton = document.getElementById(IDS.saveTransitionChangesBtn);
    errorMessagesDiv = document.getElementById(IDS.editTransitionErrorMessages);

    // Log kết quả
    console.log(`MODAL_EDIT_TRANSITION: Element '${IDS.editTransitionModal}' found?`, modalEl !== null);
    console.log(`MODAL_EDIT_TRANSITION: Element '${IDS.editTransitionForm}' found?`, formElement !== null);
    console.log(`MODAL_EDIT_TRANSITION: Element '${IDS.saveTransitionChangesBtn}' found?`, saveButton !== null);
    console.log(`MODAL_EDIT_TRANSITION: Element '${IDS.editTransitionErrorMessages}' found?`, errorMessagesDiv !== null);

    // Kiểm tra các select box
    console.log(`MODAL_EDIT_TRANSITION: Element '${IDS.editTransitionActionTypeSelect}' found?`, document.getElementById(IDS.editTransitionActionTypeSelect) !== null);
    console.log(`MODAL_EDIT_TRANSITION: Element '${IDS.editTransitionStatusSelect}' found?`, document.getElementById(IDS.editTransitionStatusSelect) !== null);

    return modalEl; // Trả về modalEl để init có thể tạo instance
}
export function initEditTransitionModal(onSaveCb) {
    console.log("MODAL_EDIT_TRANSITION: initEditTransitionModal called.");
    const modalEl = getModalDOMElements(); // Gọi hàm để lấy và log các DOM elements

    if (!modalEl) { // Nếu modal chính không tìm thấy, không thể tiếp tục
        console.error("MODAL_EDIT_TRANSITION: CRITICAL - Modal element (ID: '" + IDS.editTransitionModal + "') not found. Modal functionality will be disabled.");
        return; // Dừng khởi tạo nếu modal chính không có
    }
    modalInstance = new bootstrap.Modal(modalEl);

    onSaveSuccessCallback = onSaveCb;

    // Chỉ populate dropdown và gắn listener cho form nếu form và nút save tồn tại
    if (formElement && saveButton) {
        populateDropdown(IDS.editTransitionActionTypeSelect, APP_CONFIG.VALID_ACTION_TYPES);
        populateDropdown(IDS.editTransitionStatusSelect, APP_CONFIG.VALID_TRANSITION_STATUSES);
        formElement.addEventListener('submit', handleFormSubmit);
        console.log("MODAL_EDIT_TRANSITION: Form submit listener attached.");
    } else {
        console.error("MODAL_EDIT_TRANSITION: Form (ID: '" + IDS.editTransitionForm + "') hoặc nút Save (ID: '" + IDS.saveTransitionChangesBtn + "') không tìm thấy. Form submit sẽ không hoạt động.");
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

/**
 * Mở modal và điền dữ liệu của transition.
 * @param {object} edgeData - Dữ liệu của cạnh từ Cytoscape (edge.data()).
 */
export function openEditTransitionModal(edgeData) {
    if (!modalInstance || !formElement) {
        console.error("MODAL_EDIT_TRANSITION: Modal hoặc form chưa được khởi tạo đúng cách.");
        alert("Lỗi: Chức năng sửa transition chưa sẵn sàng.");
        return;
    }
    if (errorMessagesDiv) errorMessagesDiv.textContent = '';
    formElement.reset();

    currentNeo4jEdgeId = edgeData.neo4j_edge_id;
    document.getElementById(IDS.editTransitionNeo4jIdInput).value = currentNeo4jEdgeId || '';
    document.getElementById(IDS.editTransitionSourceNodeInput).value = edgeData.source || '';
    document.getElementById(IDS.editTransitionTargetNodeInput).value = edgeData.target || '';

    // Sử dụng populateDropdown để set giá trị selected cho dropdowns
    populateDropdown(IDS.editTransitionActionTypeSelect, APP_CONFIG.VALID_ACTION_TYPES, edgeData.action_type || '');
    populateDropdown(IDS.editTransitionStatusSelect, APP_CONFIG.VALID_TRANSITION_STATUSES, edgeData.status || 'provisional');

    document.getElementById(IDS.editTransitionElementIdInput).value = edgeData.element_id || '';
    document.getElementById(IDS.editTransitionIdentifierTypeInput).value = edgeData.identifier_type || '';
    document.getElementById(IDS.editTransitionElementTextInput).value = edgeData.element_text || '';
    document.getElementById(IDS.editTransitionMacroCodeInput).value = edgeData.macro_code || '';

    let paramsJsonString = edgeData.params_json || ''; // params_json từ Cytoscape
    try {
        if (paramsJsonString) {
            const parsedJson = JSON.parse(paramsJsonString);
            paramsJsonString = JSON.stringify(parsedJson, null, 2); // Format cho đẹp
        }
    } catch (e) {
        console.warn("MODAL_EDIT_TRANSITION: params_json không hợp lệ, hiển thị dạng thô:", paramsJsonString, e);
    }
    document.getElementById(IDS.editTransitionParamsJsonTextarea).value = paramsJsonString;

    document.getElementById(IDS.editTransitionAttemptCountInput).value = edgeData.attempt_count !== undefined ? edgeData.attempt_count : 0;
    document.getElementById(IDS.editTransitionSuccessCountInput).value = edgeData.success_count !== undefined ? edgeData.success_count : 0;

    console.log("MODAL_EDIT_TRANSITION: Opening modal for edge:", edgeData);
    modalInstance.show();
}

/**
 * Xử lý khi form sửa transition được submit.
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    if (!saveButton || !errorMessagesDiv || !currentNeo4jEdgeId) return;

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
