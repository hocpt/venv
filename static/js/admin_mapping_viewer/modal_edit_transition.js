// static/js/admin_mapping_viewer/modal_edit_transition.js
import { APP_CONFIG } from './config_mapping.js';
import { sendApiRequest } from './utils_mapping.js';

let modalInstance = null;
let formElement = null;
let saveButton = null;
let errorMessagesDiv = null;
let currentNeo4jEdgeId = null;
let onSaveSuccessCallback = null; // Callback để cập nhật Cytoscape graph
let elementIdSelect;
let actionTypeSelect;
let availableMacros = [];
let elementIdContainer, macroCodeContainer, paramsJsonContainer; // Các div cha

let elementIdSelectInput, macroCodeSelect, paramsJsonTextarea;

let currentIsCreatingNewTransition = false;
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
        successCountInput: APP_CONFIG.DOM_ELEMENT_IDS.editTransitionSuccessCountInput,
        savebtn: APP_CONFIG.DOM_ELEMENT_IDS.saveTransitionChangesBtn,



    };
    console.log("MODAL_EDIT_TRANSITION: getModalDOMElements - Attempting to get elements with IDS:", JSON.parse(JSON.stringify(DOM_IDS_MODAL)));
    actionTypeSelect = document.getElementById(DOM_IDS_MODAL.actionTypeSelect);

    // Lấy các div cha
    elementIdContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementIdInput)?.closest('.mb-3'); // ?. an toàn hơn
    macroCodeContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionMacroCodeInput)?.closest('.mb-3');
    paramsJsonContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionParamsJsonTextarea)?.closest('.mb-3');
    saveButton = document.getElementById(DOM_IDS_MODAL.saveBtn);
    // Lấy các input/select/textarea
    elementIdSelectInput = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementIdInput); // Đã là select
    macroCodeSelect = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionMacroCodeInput); // Giờ là select
    paramsJsonTextarea = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionParamsJsonTextarea);

    // Thêm kiểm tra cho các container mới
    if (!elementIdContainer) console.warn("MODAL_EDIT_TRANSITION: Container for Element ID not found.");
    if (!macroCodeContainer) console.warn("MODAL_EDIT_TRANSITION: Container for Macro Code not found.");
    if (!paramsJsonContainer) console.warn("MODAL_EDIT_TRANSITION: Container for Params JSON not found.");
    elementIdSelect = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementIdInput);
    if (!elementIdSelect) {
        console.warn(`MODAL_EDIT_TRANSITION: Dropdown ElementID ('${APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementIdInput}') not found.`);
        // allFound = false; // Bỏ comment nếu đây là element bắt buộc cho modal hoạt động
    }

    console.log("MODAL_EDIT_TRANSITION: getModalDOMElements - Attempting to get elements with IDS:", JSON.parse(JSON.stringify(DOM_IDS_MODAL)));

    const modalEl = document.getElementById(DOM_IDS_MODAL.modal);
    formElement = document.getElementById(DOM_IDS_MODAL.form);
    console.log("MODAL_EDIT_TRANSITION: Attempting to get save button with ID:", DOM_IDS_MODAL.saveBtn);
    saveButton = document.getElementById(DOM_IDS_MODAL.saveBtn);
    console.log("MODAL_EDIT_TRANSITION: saveButton object:", saveButton); // Kiểm tra xem có null không

    console.log("MODAL_EDIT_TRANSITION: Attempting to get error messages div with ID:", DOM_IDS_MODAL.errorMsg);
    errorMessagesDiv = document.getElementById(DOM_IDS_MODAL.errorMsg);
    console.log("MODAL_EDIT_TRANSITION: errorMessagesDiv object:", errorMessagesDiv);

    let allFound = true;
    if (!modalEl) { console.error(`MODAL_EDIT_TRANSITION: Modal element ('${DOM_IDS_MODAL.modal}') not found!`); allFound = false; }
    if (!formElement) { console.error(`MODAL_EDIT_TRANSITION: Form element ('${DOM_IDS_MODAL.form}') not found!`); allFound = false; }
    if (!saveButton) { console.error(`MODAL_EDIT_TRANSITION: Save button ('${DOM_IDS_MODAL.saveBtn}') not found!`); allFound = false; }
    // Kiểm tra các element khác nếu cần thiết cho hoạt động cơ bản của modal
    if (!document.getElementById(DOM_IDS_MODAL.actionTypeSelect)) { console.warn(`MODAL_EDIT_TRANSITION: Dropdown ActionType ('${DOM_IDS_MODAL.actionTypeSelect}') not found.`); }
    if (!document.getElementById(DOM_IDS_MODAL.statusSelect)) { console.warn(`MODAL_EDIT_TRANSITION: Dropdown Status ('${DOM_IDS_MODAL.statusSelect}') not found.`); }
    if (!saveButton) { console.error(`MODAL_EDIT_TRANSITION: Save button ('${DOM_IDS_MODAL.saveBtn}') not found!`); allFound = false; }

    if (modalEl && allFound) { // Chỉ tạo instance nếu modal và các thành phần cốt lõi tồn tại
        modalInstance = new bootstrap.Modal(modalEl);
        return true;
    }

    return false;
}
async function fetchAvailableMacros() {
    if (availableMacros.length > 0) return; // Chỉ fetch một lần
    try {
        const macros = await sendApiRequest('/admin/api/macros/list', 'GET');
        if (macros && Array.isArray(macros)) {
            availableMacros = macros;
            // Populate dropdown macroCodeSelect nếu nó đã được lấy tham chiếu
            if (macroCodeSelect) {
                macroCodeSelect.innerHTML = '<option value="">-- Chọn Macro --</option>';
                availableMacros.forEach(macro => {
                    const option = document.createElement('option');
                    option.value = macro.value;
                    option.textContent = macro.label;
                    macroCodeSelect.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error("MODAL_EDIT_TRANSITION: Lỗi khi tải danh sách macros:", error);
    }
}

function handleActionTypeChange() {
    const selectedActionType = actionTypeSelect ? actionTypeSelect.value : '';

    // Mặc định ẩn tất cả các trường tùy chọn trước
    if (elementIdContainer) elementIdContainer.style.display = 'none';
    if (macroCodeContainer) macroCodeContainer.style.display = 'none';
    if (paramsJsonContainer) paramsJsonContainer.style.display = 'none';
    // Reset giá trị của các trường bị ẩn để tránh gửi dữ liệu không mong muốn
    if (elementIdSelectInput) elementIdSelectInput.value = '';
    if (macroCodeSelect) macroCodeSelect.value = '';
    // if (paramsJsonTextarea) paramsJsonTextarea.value = ''; // Cân nhắc việc reset params

    switch (selectedActionType) {
        case 'click':
        case 'input':
            if (elementIdContainer) elementIdContainer.style.display = 'block';
            // Element ID là bắt buộc cho click/input
            if (paramsJsonContainer && selectedActionType === 'input') { // paramsJson thường cần cho input
                paramsJsonContainer.style.display = 'block';
            } else if (paramsJsonContainer && selectedActionType === 'click') { // paramsJson có thể tùy chọn cho click
                paramsJsonContainer.style.display = 'block'; // Hoặc 'none' nếu click không bao giờ cần params
            }
            break;
        case 'run_macro':
            if (macroCodeContainer) macroCodeContainer.style.display = 'block';
            if (paramsJsonContainer) paramsJsonContainer.style.display = 'block';
            // Element ID có thể tùy chọn cho run_macro
            if (elementIdContainer) elementIdContainer.style.display = 'block';
            break;
        case 'swipe_up':
        case 'swipe_down':
        case 'swipe_left':
        case 'swipe_right':
            // Element ID có thể tùy chọn (nếu swipe trên element)
            if (elementIdContainer) elementIdContainer.style.display = 'block';
            // Params JSON có thể cần cho tọa độ nếu không có element ID
            if (paramsJsonContainer) paramsJsonContainer.style.display = 'block';
            break;
        case 'start_app':
            if (paramsJsonContainer) paramsJsonContainer.style.display = 'block'; // Để nhập package, activity
            break;
        case 'nav_go_back':
            // Thường không cần trường nào khác
            break;
        case 'other':
        case '': // Nếu chưa chọn hoặc chọn "Khác"
            // Có thể hiển thị tất cả các trường hoặc một tập hợp mặc định
            if (elementIdContainer) elementIdContainer.style.display = 'block';
            if (macroCodeContainer) macroCodeContainer.style.display = 'block';
            if (paramsJsonContainer) paramsJsonContainer.style.display = 'block';
            break;
        default:
            console.warn("MODAL_EDIT_TRANSITION: Loại hành động không xác định:", selectedActionType);
            break;
    }
}
export function initEditTransitionModal(onSaveCb) {
    console.log("MODAL_EDIT_TRANSITION: initEditTransitionModal called.");
    const actionTypeSelectEl = document.getElementById(DOM_IDS_MODAL.actionTypeSelect); // Hoặc formElement.elements['action_type']
    const statusSelectEl = document.getElementById(DOM_IDS_MODAL.statusSelect); // Hoặc formElement.elements['status']
    actionTypeSelect = document.getElementById(DOM_IDS_MODAL.actionTypeSelect);
    if (actionTypeSelect) {
        actionTypeSelect.addEventListener('change', handleActionTypeChange);
    } else {
        console.warn("MODAL_EDIT_TRANSITION: ActionType select element not found, cannot attach change listener.");
    }
    fetchAvailableMacros();
    if (actionTypeSelectEl && APP_CONFIG.VALID_ACTION_TYPES && actionTypeSelectEl.options.length <= 1) { // Chỉ populate nếu chưa có options (ngoại trừ option mặc định)
        APP_CONFIG.VALID_ACTION_TYPES.forEach(action => {
            const option = document.createElement('option');
            if (typeof action === 'object' && action.value !== undefined) { // Nếu action là object {value, label}
                option.value = action.value;
                option.textContent = action.label || action.value;
            } else { // Nếu action là string
                option.value = action;
                option.textContent = action;
            }
            actionTypeSelectEl.appendChild(option);
        });
    }
    if (statusSelectEl && APP_CONFIG.VALID_TRANSITION_STATUSES && statusSelectEl.options.length <= 1) {
        APP_CONFIG.VALID_TRANSITION_STATUSES.forEach(status => {
            const option = document.createElement('option');
            if (typeof status === 'object' && status.value !== undefined) {
                option.value = status.value;
                option.textContent = status.label || status.value;
            } else {
                option.value = status;
                option.textContent = status;
            }
            statusSelectEl.appendChild(option);
        });
    }
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
    if (elementIdSelect) { // elementIdSelect đã được gán trong getModalDOMElementsAndInitInstance
        elementIdSelect.addEventListener('change', function () {
            const selectedOption = this.options[this.selectedIndex];
            const elementText = selectedOption.dataset.actualText || ''; // Lấy từ dataset mới
            const identifierType = selectedOption.dataset.identifierType || ''; // Lấy từ dataset mới

            const elementTextInput = formElement.elements['element_text']; // Hoặc document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementTextInput)
            const identifierTypeInput = formElement.elements['identifier_type']; // Hoặc document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionIdentifierTypeInput)

            if (elementTextInput) {
                elementTextInput.value = elementText;
            }
            if (identifierTypeInput) {
                identifierTypeInput.value = identifierType;
            }
        });
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


export function openEditTransitionModal(edgeData, isCreating = false) {
    if (!modalInstance || !formElement) {
        console.error("MODAL_EDIT_TRANSITION: Cannot open modal. Instance or form not initialized.");
        alert("Lỗi: Chức năng sửa transition chưa sẵn sàng (thiếu form).");
        return;
    }
    currentIsCreatingNewTransition = isCreating;
    formElement.elements['identifier_type'].value = edgeData.identifier_type || '';
    formElement.elements['element_text'].value = edgeData.element_text || '';
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
    currentIsCreatingNewTransition = isCreating;

    if (!modalInstance || !formElement) {
        console.error("MODAL_EDIT_TRANSITION: Modal or form not initialized. Cannot open.");
        return;
    }
    if (errorMessagesDiv) errorMessagesDiv.style.display = 'none'; // Đảm bảo errorMessagesDiv đã được khởi tạo
    formElement.reset();

    const modalTitleEl = document.getElementById('editTransitionModalLabel'); // ID của tiêu đề modal
    if (modalTitleEl) {
        modalTitleEl.textContent = currentIsCreatingNewTransition ? 'Tạo Transition Mới' : 'Sửa Transition';
    }

    currentNeo4jEdgeId = currentIsCreatingNewTransition ? null : edgeData.neo4j_edge_id;

    // Điền thông tin vào form
    if (formElement.elements['neo4j_id']) { // Kiểm tra element tồn tại
        formElement.elements['neo4j_id'].value = currentNeo4jEdgeId || '';
    }


    // Điền thông tin vào form
    if (formElement.elements['source_node']) formElement.elements['source_node'].value = edgeData.source || '';

    // Cho phép chọn Target Node nếu là tạo mới
    const targetNodeInput = formElement.elements['target_node'];
    const statusSelectEl = formElement.elements['status'];
    if (statusSelectEl) {
        // Logic populate statusSelectEl nếu cần
        statusSelectEl.value = edgeData.status || (currentIsCreatingNewTransition ? 'provisional' : '');
    }
    // Bạn cần một dropdown/select để chọn Target Node. 
    // Tạm thời vẫn để là input text, nhưng lý tưởng là dropdown các screen_id khác.
    targetNodeInput.readOnly = !isCreating; // Cho phép sửa target nếu tạo mới
    targetNodeInput.value = edgeData.target || '';

    // Populate dropdowns tĩnh (ActionType, Status)
    // (Giữ nguyên logic populateDropdown đã có trong initEditTransitionModal)
    // Chọn giá trị mặc định hoặc giá trị từ edgeData
    formElement.elements['action_type'].value = edgeData.action_type || '';;


    // Populate dropdown Element ID (dựa trên source node)
    if (edgeData.source && elementIdSelectInput) { // elementIdSelectInput là biến module cho <select>
        populateElementIdDropdown(edgeData.source, edgeData.element_id)
            .then(() => {
                if (elementIdSelectInput && elementIdSelectInput.value === edgeData.element_id && elementIdSelectInput.selectedIndex > -1) {
                    const selectedOption = elementIdSelectInput.options[elementIdSelectInput.selectedIndex];
                    if (formElement.elements['element_text']) formElement.elements['element_text'].value = selectedOption.dataset.actualText || '';
                    if (formElement.elements['identifier_type']) formElement.elements['identifier_type'].value = selectedOption.dataset.identifierType || '';
                } else {
                    if (formElement.elements['element_text']) formElement.elements['element_text'].value = edgeData.element_text || '';
                    if (formElement.elements['identifier_type']) formElement.elements['identifier_type'].value = edgeData.identifier_type || '';
                }
            });
    } else if (elementIdSelectInput) {
        elementIdSelectInput.innerHTML = '<option value="">-- Source Node không xác định --</option>';
        elementIdSelectInput.disabled = true;
    }

    // Điền các trường text khác
    if (formElement.elements['identifier_type']) formElement.elements['identifier_type'].value = edgeData.identifier_type || '';
    if (formElement.elements['element_text']) formElement.elements['element_text'].value = edgeData.element_text || '';
    if (formElement.elements['macro_code']) formElement.elements['macro_code'].value = edgeData.macro_code || '';
    if (formElement.elements['params_json_str']) formElement.elements['params_json_str'].value = edgeData.params_json || (isCreating ? '{}' : '');
    if (formElement.elements['attempt_count']) formElement.elements['attempt_count'].value = edgeData.attempt_count !== undefined ? edgeData.attempt_count : (isCreating ? 0 : '');
    if (formElement.elements['success_count']) formElement.elements['success_count'].value = edgeData.success_count !== undefined ? edgeData.success_count : (isCreating ? 0 : '');

    // Gọi handleActionTypeChange để cập nhật UI các trường theo action_type ban đầu (quan trọng)
    handleActionTypeChange();

    // Nếu đang tạo mới và action_type là run_macro, không cần chọn macro_code cụ thể ngay
    // Nhưng nếu đang sửa, và action_type là run_macro, thì phải chọn lại macro_code

    if (!currentIsCreatingNewTransition && macroCodeSelect && actionTypeSelectEl && actionTypeSelectEl.value === 'run_macro') {
        if (macroCodeSelect) macroCodeSelect.value = edgeData.macro_code || '';
    } else if (currentIsCreatingNewTransition && macroCodeSelect) {
        macroCodeSelect.value = ''; // Reset macro code nếu tạo mới
    }
    // Gọi handleActionTypeChange để cập nhật UI các trường theo action_type ban đầu
    handleActionTypeChange();

    // Sau khi handleActionTypeChange đã thiết lập hiển thị đúng cho macroCodeSelect,
    // mới tiến hành set giá trị cho nó.
    if (macroCodeSelect && edgeData.action_type === 'run_macro') {
        // Đảm bảo dropdown macro đã được populate bởi fetchAvailableMacros()
        // Nếu fetchAvailableMacros là async, bạn có thể cần await nó hoặc xử lý promise
        // Tạm thời giả định availableMacros đã có dữ liệu (hoặc sẽ được điền khi fetch xong)
        macroCodeSelect.value = edgeData.macro_code || '';
        if (macroCodeSelect.value !== (edgeData.macro_code || '')) {
            console.warn(`MODAL_EDIT_TRANSITION: Macro code '${edgeData.macro_code}' không tìm thấy trong danh sách.`);
        }
    }
    if (edgeData.source) {
        console.log(`MODAL_EDIT_TRANSITION: Mở modal cho edge, source node: ${edgeData.source}, element_id hiện tại: ${edgeData.element_id}`);
        populateElementIdDropdown(edgeData.source, edgeData.element_id);
    } else {
        if (elementIdSelect) {
            elementIdSelect.innerHTML = '<option value="">-- Source Node không xác định --</option>';
            elementIdSelect.disabled = true;
        }
        console.warn("MODAL_EDIT_TRANSITION: Source Node ID không có trong edgeData, không thể populate element dropdown.");
    }

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
    if (elementIdSelect.selectedIndex > -1) {
        const selectedOption = elementIdSelect.options[elementIdSelect.selectedIndex];
        const elementText = selectedOption.dataset.elementText || edgeData.element_text || ''; // Fallback về edgeData nếu dataset chưa có khi mới load
        const identifierType = selectedOption.dataset.identifierType || edgeData.identifier_type || '';

        if (formElement.elements['element_text']) {
            formElement.elements['element_text'].value = elementText;
        }
        if (formElement.elements['identifier_type']) {
            formElement.elements['identifier_type'].value = identifierType;
        }
    } else { // Nếu không có element nào được chọn (ví dụ: element_id của edge không có trong list)
        if (formElement.elements['element_text']) {
            formElement.elements['element_text'].value = edgeData.element_text || ''; // Giữ giá trị cũ từ edgeData
        }
        if (formElement.elements['identifier_type']) {
            formElement.elements['identifier_type'].value = edgeData.identifier_type || ''; // Giữ giá trị cũ
        }
    }
    console.log("MODAL_EDIT_TRANSITION: Opening modal for edge:", edgeData);
    modalInstance.show();
}
/**
 * Xử lý khi form sửa transition được submit.
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    let apiUrl;
    console.log("MODAL_EDIT_TRANSITION: Inside handleFormSubmit. saveButton:", saveButton, "errorMessagesDiv:", errorMessagesDiv, "currentIsCreatingNewTransition:", currentIsCreatingNewTransition, "currentNeo4jEdgeId:", currentNeo4jEdgeId);
    if (!saveButton || !errorMessagesDiv || (!currentIsCreatingNewTransition && !currentNeo4jEdgeId)) {
        console.error("MODAL_EDIT_TRANSITION: handleFormSubmit - Nút save, error div hoặc currentNeo4jEdgeId bị thiếu.");
        return;
    }

    saveButton.disabled = true;
    saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang lưu...';
    errorMessagesDiv.textContent = '';
    if (errorMessagesDiv) errorMessagesDiv.style.display = 'none';


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



    const sourceNode = formElement.elements['source_node'].value;
    const targetNode = formElement.elements['target_node'].value; // Lấy target node
    const actionType = formElement.elements['action_type'].value;
    const elementId = formElement.elements['element_id'].value;
    const identifierType = formElement.elements['identifier_type'].value;
    const elementText = formElement.elements['element_text'].value;
    const macroCode = formElement.elements['macro_code'].value;
    const status = formElement.elements['status'].value;
    const attemptCount = parseInt(formElement.elements['attempt_count'].value) || 0;
    const successCount = parseInt(formElement.elements['success_count'].value) || 0;

    // Validate targetNode nếu đang tạo mới
    if (currentIsCreatingNewTransition && !targetNode) {
        if (errorMessagesDiv) {
            errorMessagesDiv.textContent = 'Target Node là bắt buộc khi tạo transition mới.';
            errorMessagesDiv.style.display = 'block';
        }
        saveButton.disabled = false; saveButton.textContent = currentIsCreatingNewTransition ? 'Tạo Transition' : 'Lưu Thay Đổi';
        return;
    }

    // Validate JSON params_json_str (giữ nguyên)
    if (paramsJsonForPayload) {
        try { JSON.parse(paramsJsonForPayload); } catch (e) { /* ... báo lỗi ... */ return; }
    } else {
        paramsJsonForPayload = null; // Hoặc "{}" tùy theo backend mong muốn
    }

    const payload = {
        source_node_id: sourceNode, // Đổi tên key để rõ ràng hơn nếu cần
        target_node_id: targetNode,
        action_type: actionType,
        element_id: elementId || null,
        identifier_type: identifierType || null,
        element_text: elementText || null,
        macro_code: macroCode || null,
        params_json_str: paramsJsonForPayload,
        status: status,
        attempt_count: attemptCount,
        success_count: successCount,
        app_name: APP_CONFIG.APP_NAME_FROM_FLASK // Gửi app_name để backend xử lý đúng context
    };
    let httpMethod;

    if (currentIsCreatingNewTransition) {
        apiUrl = `/admin/api/mapping/transition/create`;
        httpMethod = 'POST';
        if (saveButton) saveButton.textContent = 'Đang tạo...'; // Đảm bảo saveButton được kiểm tra
    } else {
        // Đảm bảo APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION tồn tại và currentNeo4jEdgeId có giá trị
        if (!APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION) {
            console.error("MODAL_EDIT_TRANSITION: APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION is not defined!");
            // Xử lý lỗi, ví dụ hiển thị thông báo và return
            if (errorMessagesDiv) errorMessagesDiv.textContent = 'Lỗi cấu hình: URL cập nhật không xác định.';
            if (saveButton) { saveButton.disabled = false; saveButton.textContent = 'Lưu Thay Đổi'; }
            return;
        }
        if (!currentNeo4jEdgeId) { // Kiểm tra currentNeo4jEdgeId khi không phải tạo mới
            console.error("MODAL_EDIT_TRANSITION: currentNeo4jEdgeId is missing for update operation.");
            if (errorMessagesDiv) errorMessagesDiv.textContent = 'Lỗi: Không xác định được ID của transition cần sửa.';
            if (saveButton) { saveButton.disabled = false; saveButton.textContent = 'Lưu Thay Đổi'; }
            return;
        }
        apiUrl = `${APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION}${encodeURIComponent(currentNeo4jEdgeId)}`;
        httpMethod = 'POST'; // Hoặc 'PUT'
        if (saveButton) saveButton.textContent = 'Đang lưu...';
    }
    const paramsJsonTextValue = document.getElementById(DOM_IDS_MODAL.paramsJsonTextarea).value.trim(); // Lấy lại nếu cần cho payload
    let paramsJsonForSend = null;
    if (paramsJsonTextValue) {
        try {
            JSON.parse(paramsJsonTextValue); // Validate
            paramsJsonForSend = paramsJsonTextValue;
        } catch (e) {
            if (errorMessagesDiv) errorMessagesDiv.textContent = 'Lỗi: "Tham Số Hành Động" không phải là JSON hợp lệ.';
            if (saveButton) { saveButton.disabled = false; saveButton.textContent = currentIsCreatingNewTransition ? 'Tạo Transition' : 'Lưu Thay Đổi'; }
            return;
        }
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
    for (const key in updatedProperties) {
        if (updatedProperties[key] === undefined) {
            delete updatedProperties[key];
        }
    }
    try {
        const result = await sendApiRequest(apiUrl, httpMethod, payload);
        if (result.success) {
            console.log(`MODAL_EDIT_TRANSITION: ${currentIsCreatingNewTransition ? 'Tạo' : 'Cập nhật'} transition thành công!`);
            modalInstance.hide();

            // Gọi callback hoặc tải lại đồ thị
            if (typeof onSaveSuccessCallback === 'function' && !currentIsCreatingNewTransition) { // Chỉ gọi cho update
                onSaveSuccessCallback(currentNeo4jEdgeId, payload); // payload ở đây có thể cần điều chỉnh cho khớp với dữ liệu cytoscape mong đợi
            } else if (currentIsCreatingNewTransition) {
                // Nếu tạo mới thành công, cần tải lại toàn bộ đồ thị để thấy cạnh mới
                // Hoặc backend trả về thông tin cạnh mới để thêm vào Cytoscape
                console.log("MODAL_EDIT_TRANSITION: Transition mới đã được tạo. Cần tải lại đồ thị.");
                if (typeof window.refreshCytoscapeGraph === 'function') { // Giả sử có hàm này
                    window.refreshCytoscapeGraph();
                } else {
                    alert("Transition mới đã được tạo. Vui lòng làm mới đồ thị để xem thay đổi.");
                }
            }
        } else {
            if (errorMessagesDiv) {
                errorMessagesDiv.textContent = result.error || result.message || 'Lỗi không xác định từ server.';
                errorMessagesDiv.style.display = 'block';
            }
        }
    } catch (error) {
        console.error("MODAL_EDIT_TRANSITION: Lỗi khi gửi yêu cầu cập nhật transition:", error);
        errorMessagesDiv.textContent = error.data?.message || error.message || 'Lỗi kết nối hoặc xử lý server.';
    } finally {
        saveButton.disabled = false;
        saveButton.textContent = 'Lưu Thay Đổi';
    }
}
async function populateElementIdDropdown(sourceScreenId, currentSelectedElementId) {
    if (!elementIdSelect) {
        console.warn("MODAL_EDIT_TRANSITION: Element ID select element không tìm thấy, không thể populate.");
        return;
    }

    elementIdSelect.innerHTML = '<option value="">-- Đang tải Elements... --</option>';
    elementIdSelect.disabled = true;

    try {
        const currentAppName = APP_CONFIG.APP_NAME_FROM_FLASK;
        let apiUrl = `/admin/api/screen/${sourceScreenId}/elements_for_dropdown`;
        if (currentAppName) {
            apiUrl += `?app_name=${encodeURIComponent(currentAppName)}`;
        }

        const elements = await sendApiRequest(apiUrl, 'GET');
        elementIdSelect.innerHTML = '<option value="">-- Chọn Element --</option>';

        if (elements && elements.length > 0) {
            elements.forEach(element => {
                const option = document.createElement('option');
                option.value = element.value; // element_id
                option.textContent = element.label;
                // Lưu trữ dữ liệu đầy đủ hơn vào dataset
                option.dataset.actualText = element.actual_text || '';
                option.dataset.identifierType = element.identifier_type_from_db || '';
                elementIdSelect.appendChild(option);
            });

            if (currentSelectedElementId) {
                elementIdSelect.value = currentSelectedElementId;
                // Trigger change để cập nhật các trường liên quan ngay khi modal mở và có giá trị được chọn
                if (elementIdSelect.value === currentSelectedElementId) { // Đảm bảo giá trị thực sự được set
                    elementIdSelect.dispatchEvent(new Event('change'));
                } else {
                    console.warn(`MODAL_EDIT_TRANSITION: Element ID '${currentSelectedElementId}' của transition không tìm thấy trong danh sách elements của Source Node '${sourceScreenId}'. Các trường text/type sẽ không được tự động điền.`);
                    // Nếu không tìm thấy, có thể giữ giá trị cũ của edgeData cho các trường text/type
                    const elementTextInput = formElement.elements['element_text'];
                    const identifierTypeInput = formElement.elements['identifier_type'];
                    if (elementTextInput) elementTextInput.value = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionElementTextInput).value || ''; // Giữ giá trị đang hiển thị nếu có
                    if (identifierTypeInput) identifierTypeInput.value = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionIdentifierTypeInput).value || '';
                }
            }
        } else {
            elementIdSelect.innerHTML = '<option value="">-- Không có element nào trên Source Node --</option>';
        }
    } catch (error) {
        console.error("MODAL_EDIT_TRANSITION: Lỗi khi tải hoặc điền elements cho dropdown:", error);
        elementIdSelect.innerHTML = '<option value="">-- Lỗi tải Elements --</option>';
    } finally {
        elementIdSelect.disabled = false;
    }
}