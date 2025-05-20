// static/js/admin_node_management/modal_manage_pie.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest, drawInteractiveOverlays } from './utils.js';

let managePieModalInstance = null;
let currentManagingNodeData = {}; // Dữ liệu của node đang được quản lý (gốc từ table_handler)
let currentSelectedPieConditions = []; // Danh sách các điều kiện PIE hiện tại đang được xây dựng/sửa
let rawElementsDataForModal = []; // Dữ liệu elements thô lấy từ API cho node hiện tại

// DOM Elements của Modal Quản lý PIE
let modalEl, currentScreenIdDisplay, currentAppNameDisplay, modalLabel,
    imageContainer, screenshotImg, elementTextListDiv, selectedConditionsListDiv,
    addManualConditionBtn, mainActionBtn, errorMessagesSpan;

// Hàm lấy các DOM element một lần để tránh query lặp lại
function getDOMElementsForManagePie() {
    modalEl = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_MODAL);
    currentScreenIdDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_CURRENT_SCREEN_ID);
    currentAppNameDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_CURRENT_APP_NAME);
    modalLabel = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_LABEL);
    imageContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_IMAGE_CONTAINER);
    screenshotImg = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_SCREENSHOT);
    elementTextListDiv = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_ELEMENT_TEXT_LIST);
    selectedConditionsListDiv = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_SELECTED_CONDITIONS_LIST);
    addManualConditionBtn = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_ADD_MANUAL_BTN);
    mainActionBtn = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_MAIN_ACTION_BTN);
    errorMessagesSpan = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_ERROR_MESSAGES);
}

/**
 * Render danh sách text của các elements (cột 2 trong modal).
 * Gắn sự kiện click cho mỗi item để chọn/bỏ chọn element.
 */
function renderElementTextList() {
    if (!elementTextListDiv) return;
    elementTextListDiv.innerHTML = ''; // Xóa nội dung cũ
    if (!rawElementsDataForModal || rawElementsDataForModal.length === 0) {
        elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Không có elements nào được phát hiện trên ảnh.</div>';
        return;
    }

    rawElementsDataForModal.forEach((elData, index) => {
        const listItem = document.createElement('a');
        listItem.href = "#"; // Để có thể click
        listItem.className = 'list-group-item list-group-item-action py-1 px-2 text-break';
        listItem.dataset.elementIndex = index; // Lưu index gốc của element trong rawElementsDataForModal

        // Hiển thị thông tin element
        const idPart = elData.resource_id || elData.element_id || 'Không có ID';
        const textPart = elData.text_content || '';
        const descPart = elData.description || elData.content_description || ''; // Thêm content_description
        const classPart = elData.class_name ? elData.class_name.replace('android.widget.', '') : (elData.element_type ? elData.element_type.replace('android.widget.', '') : '');

        let displayText = `<div class="fw-bold small" title="${idPart}">${idPart.substring(0, 35)}${idPart.length > 35 ? '...' : ''}</div>`;
        if (textPart) displayText += `<div class="text-muted xsmall" title="${textPart}">Text: ${textPart.substring(0, 40)}${textPart.length > 40 ? '...' : ''}</div>`;
        if (descPart) displayText += `<div class="text-muted xsmall" title="${descPart}">Desc: ${descPart.substring(0, 40)}${descPart.length > 40 ? '...' : ''}</div>`;
        if (classPart) displayText += `<div class="text-muted xsmall">Class: ${classPart}</div>`;
        listItem.innerHTML = displayText;
        listItem.title = `ID: ${idPart}\nText: ${textPart}\nDesc: ${descPart}\nClass: ${classPart}\nClick để chọn/bỏ chọn làm điều kiện.`;

        listItem.addEventListener('click', (e) => {
            e.preventDefault();
            console.log("[MODAL_PIE] Text list item clicked. Index:", index);
            // Gọi hàm xử lý lựa chọn, truyền index gốc của element
            handleElementSelectionFromVisualizer(index);
        });
        elementTextListDiv.appendChild(listItem);
    });
    updateVisualizerSelections(); // Cập nhật trạng thái selected cho list items
}

/**
 * Render bảng "Điều kiện Nhận diện PIE Đã Chọn:" (cột 3).
 */
function renderSelectedPieConditions() {
    if (!selectedConditionsListDiv) return;
    selectedConditionsListDiv.innerHTML = ''; // Xóa nội dung cũ

    if (currentSelectedPieConditions.length === 0) {
        selectedConditionsListDiv.innerHTML = '<p class="text-muted small p-2 initial-prompt">Click element trên ảnh/list hoặc "Thêm thủ công" để tạo điều kiện.</p>';
        updateVisualizerSelections(); // Đảm bảo không có gì được highlight trên ảnh/list
        return;
    }

    currentSelectedPieConditions.forEach((condition, arrayIndex) => { // arrayIndex là index trong currentSelectedPieConditions
        const conditionDiv = document.createElement('div');
        conditionDiv.className = `mb-2 p-2 border rounded bg-white shadow-sm ${APP_CONFIG.CSS_CLASSES.CONDITION_ITEM_ROW}`;
        conditionDiv.dataset.conditionArrayIndex = arrayIndex; // Lưu index của condition trong mảng

        let attributeOptionsHtml = APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE.map(attr =>
            `<option value="${attr.value}" ${condition.attribute === attr.value ? 'selected' : ''}>${attr.label}</option>`
        ).join('');
        let comparisonOptionsHtml = APP_CONFIG.COMPARISON_TYPES_FOR_PIE.map(comp =>
            `<option value="${comp.value}" ${condition.comparison === comp.value ? 'selected' : ''}>${comp.label}</option>`
        ).join('');
        const isValueDisabled = condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS';

        conditionDiv.innerHTML = `
            <div class="row gx-2 gy-1 align-items-center">
                <div class="col-sm-4">
                    <select class="form-select form-select-sm condition-attribute" data-condition-array-index="${arrayIndex}" aria-label="Thuộc tính">
                        <option value="">-- Thuộc tính --</option>
                        ${attributeOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-3">
                    <select class="form-select form-select-sm condition-comparison" data-condition-array-index="${arrayIndex}" aria-label="So sánh">
                        ${comparisonOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-4">
                    <input type="text" class="form-control form-control-sm condition-value" 
                           data-condition-array-index="${arrayIndex}" 
                           value="${condition.value || ''}" 
                           placeholder="Giá trị" aria-label="Giá trị"
                           ${isValueDisabled ? 'disabled' : ''}>
                </div>
                <div class="col-sm-1 text-end">
                    <button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-condition-array-index="${arrayIndex}" title="Xóa điều kiện" aria-label="Xóa">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="text-muted xsmall mt-1"><em>Nguồn: ${condition.element_identifier_display || 'Thủ công'}</em></div>`;
        selectedConditionsListDiv.appendChild(conditionDiv);
    });

    attachListenersToSelectedConditions(); // Gắn listener cho các select/input/button vừa tạo
    updateVisualizerSelections(); // Cập nhật highlight trên ảnh và list text
}

/**
 * Gắn các trình xử lý sự kiện cho các input/select/button trong bảng điều kiện.
 */
function attachListenersToSelectedConditions() {
    if (!selectedConditionsListDiv) return;

    selectedConditionsListDiv.querySelectorAll('.condition-attribute').forEach(selectElement => {
        selectElement.addEventListener('change', function () {
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex);
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;

            const newAttributeSelected = this.value;
            currentSelectedPieConditions[conditionArrayIndex].attribute = newAttributeSelected;

            const internalElementIdx = currentSelectedPieConditions[conditionArrayIndex].internal_element_index;
            let newValueForCondition = '';

            if (internalElementIdx !== -1 && internalElementIdx !== undefined && rawElementsDataForModal && rawElementsDataForModal[internalElementIdx]) {
                const originalElementData = rawElementsDataForModal[internalElementIdx];
                switch (newAttributeSelected) {
                    case 'resource_id':
                        newValueForCondition = originalElementData.resource_id || originalElementData.element_id || '';
                        break;
                    case 'text':
                        newValueForCondition = originalElementData.text_content || '';
                        break;
                    case 'description': // Hoặc content_description
                        newValueForCondition = originalElementData.description || originalElementData.content_description || '';
                        break;
                    case 'class_name':
                        newValueForCondition = originalElementData.class_name || originalElementData.element_type || '';
                        break;
                    default:
                        newValueForCondition = originalElementData[newAttributeSelected] || '';
                }
            } else if (currentSelectedPieConditions[conditionArrayIndex].is_manual) {
                // Điều kiện thủ công, giữ nguyên giá trị khi đổi thuộc tính, người dùng tự sửa
                newValueForCondition = currentSelectedPieConditions[conditionArrayIndex].value;
            }

            currentSelectedPieConditions[conditionArrayIndex].value = newValueForCondition;
            const valueInputElement = this.closest('.row').querySelector('.condition-value');
            if (valueInputElement) {
                valueInputElement.value = newValueForCondition;
            }
            console.log(`[MODAL_PIE] Condition idx ${conditionArrayIndex} attribute changed to '${newAttributeSelected}', value set to '${newValueForCondition}'`);
        });
    });

    selectedConditionsListDiv.querySelectorAll('.condition-comparison').forEach(selectElement => {
        selectElement.addEventListener('change', function () {
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex);
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;

            const newComparison = this.value;
            currentSelectedPieConditions[conditionArrayIndex].comparison = newComparison;
            const valueInputElement = this.closest('.row').querySelector('.condition-value');
            if (valueInputElement) {
                if (newComparison === 'EXISTS' || newComparison === 'NOT_EXISTS') {
                    valueInputElement.value = '';
                    valueInputElement.disabled = true;
                    currentSelectedPieConditions[conditionArrayIndex].value = '';
                } else {
                    valueInputElement.disabled = false;
                }
            }
        });
    });

    selectedConditionsListDiv.querySelectorAll('.condition-value').forEach(inputElement => {
        inputElement.addEventListener('input', function () {
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex);
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;
            currentSelectedPieConditions[conditionArrayIndex].value = this.value.trim();
        });
    });

    selectedConditionsListDiv.querySelectorAll('.remove-condition-btn').forEach(buttonElement => {
        buttonElement.addEventListener('click', function () {
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex);
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;
            currentSelectedPieConditions.splice(conditionArrayIndex, 1);
            renderSelectedPieConditions(); // Vẽ lại bảng và cập nhật highlights
        });
    });
}

/**
 * Xử lý khi một element được chọn từ ảnh (overlay) hoặc từ danh sách text.
 * @param {number} elementOriginalIndex - Index của element trong mảng rawElementsDataForModal.
 */
function handleElementSelectionFromVisualizer(elementOriginalIndex) {
    console.log(`[MODAL_PIE] handleElementSelectionFromVisualizer called with originalIndex: ${elementOriginalIndex}`);

    if (rawElementsDataForModal === null || rawElementsDataForModal.length === 0 || elementOriginalIndex < 0 || elementOriginalIndex >= rawElementsDataForModal.length) {
        console.warn("[MODAL_PIE] Invalid elementOriginalIndex or rawElementsDataForModal is empty/null.");
        return;
    }

    const elementData = rawElementsDataForModal[elementOriginalIndex];
    if (!elementData) {
        console.warn("[MODAL_PIE] No element data found for index:", elementOriginalIndex);
        return;
    }
    console.log("[MODAL_PIE] Selected elementData:", JSON.stringify(elementData));

    // Chỉ toggle nếu điều kiện đó được tạo từ click (không phải thủ công)
    const existingConditionIndex = currentSelectedPieConditions.findIndex(
        cond => cond.internal_element_index === elementOriginalIndex && !cond.is_manual
    );

    if (existingConditionIndex > -1) {
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
        console.log("[MODAL_PIE] Condition removed for element index:", elementOriginalIndex);
    } else {
        let defaultAttribute = '';
        let defaultValue = '';
        let displayIdentifier = `Từ Elem Index ${elementOriginalIndex}`;

        // ---- START: ƯU TIÊN RESOURCE_ID LÀM MẶC ĐỊNH ----
        if (elementData.resource_id && typeof elementData.resource_id === 'string' && elementData.resource_id.trim() !== '') {
            defaultAttribute = 'resource_id';
            defaultValue = elementData.resource_id;
            displayIdentifier = `ResID: ${elementData.resource_id.substring(0, 25)}...`;
        } else if (elementData.element_id && typeof elementData.element_id === 'string' && elementData.element_id.includes(':id/')) {
            defaultAttribute = 'resource_id';
            defaultValue = elementData.element_id;
            displayIdentifier = `ElemID: ${elementData.element_id.substring(0, 25)}...`;
        } else if (elementData.text_content && typeof elementData.text_content === 'string' && elementData.text_content.trim() !== '') {
            defaultAttribute = 'text';
            defaultValue = elementData.text_content;
            displayIdentifier = `Text: ${elementData.text_content.substring(0, 25)}...`;
        } else if (elementData.description && typeof elementData.description === 'string' && elementData.description.trim() !== '') {
            defaultAttribute = 'description';
            defaultValue = elementData.description;
            displayIdentifier = `Desc: ${elementData.description.substring(0, 25)}...`;
        } else if (elementData.content_description && typeof elementData.content_description === 'string' && elementData.content_description.trim() !== '') { // Thêm content_description
            defaultAttribute = 'description'; // Vẫn map vào 'description' attribute
            defaultValue = elementData.content_description;
            displayIdentifier = `ContDesc: ${elementData.content_description.substring(0, 25)}...`;
        } else if (elementData.class_name && typeof elementData.class_name === 'string' && elementData.class_name.trim() !== '') {
            defaultAttribute = 'class_name';
            defaultValue = elementData.class_name;
            displayIdentifier = `Class: ${elementData.class_name.substring(0, 25)}...`;
        } else if (elementData.element_type && typeof elementData.element_type === 'string' && elementData.element_type.trim() !== '') { // Fallback cho element_type nếu class_name không có
            defaultAttribute = 'class_name'; // Vẫn map vào 'class_name' attribute
            defaultValue = elementData.element_type;
            displayIdentifier = `Type: ${elementData.element_type.substring(0, 25)}...`;
        }
        else {
            if (APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE && APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE.length > 0) {
                defaultAttribute = APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE[0].value; // Lấy thuộc tính đầu tiên trong config
                defaultValue = elementData[defaultAttribute] || ''; // Thử lấy giá trị tương ứng
            } else {
                defaultAttribute = 'text'; // Fallback cuối cùng
                defaultValue = '';
            }
            displayIdentifier = `Elem Index ${elementOriginalIndex} (Cần cấu hình lại)`;
        }
        // ---- END: ƯU TIÊN RESOURCE_ID ----

        const newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: displayIdentifier,
            attribute: defaultAttribute,
            comparison: 'EQUALS',
            value: defaultValue,
            is_manual: false // Đánh dấu không phải thủ công
        };
        currentSelectedPieConditions.push(newCondition);
        console.log("[MODAL_PIE] New condition added:", JSON.stringify(newCondition));
    }
    renderSelectedPieConditions(); // Cập nhật bảng điều kiện và gọi updateVisualizerSelections bên trong
}

/**
 * Cập nhật trạng thái 'selected' (highlight) cho các overlays trên ảnh và các item trong danh sách text.
 * Dựa trên các điều kiện trong currentSelectedPieConditions.
 */
function updateVisualizerSelections() {
    console.log("[MODAL_PIE] Updating visualizer selections. Conditions count:", currentSelectedPieConditions.length);
    // Lấy tất cả các internal_element_index từ các điều kiện không phải thủ công
    const selectedElementIndices = new Set(
        currentSelectedPieConditions
            .filter(cond => !cond.is_manual && cond.internal_element_index !== -1 && cond.internal_element_index !== undefined)
            .map(cond => cond.internal_element_index)
    );
    console.log("[MODAL_PIE] Indices of elements to be highlighted:", Array.from(selectedElementIndices));


    // Cập nhật overlays trên ảnh
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(overlay => {
            const elIndex = parseInt(overlay.dataset.elementIndex);
            if (!isNaN(elIndex)) {
                const isSelected = selectedElementIndices.has(elIndex);
                overlay.classList.toggle(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE, isSelected);
                // console.log(`[MODAL_PIE] Overlay index ${elIndex} selected: ${isSelected}`);
            }
        });
    } else {
        console.warn("[MODAL_PIE] imageContainer not found for updating overlay selections.");
    }

    // Cập nhật items trong danh sách text
    if (elementTextListDiv) {
        elementTextListDiv.querySelectorAll('.list-group-item[data-element-index]').forEach(item => {
            const elIndex = parseInt(item.dataset.elementIndex);
            if (!isNaN(elIndex)) {
                const isSelected = selectedElementIndices.has(elIndex);
                item.classList.toggle(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE, isSelected); // Dùng class từ config
                item.classList.toggle('active', isSelected); // Có thể dùng thêm class 'active' của Bootstrap
                // console.log(`[MODAL_PIE] Text list item index ${elIndex} selected: ${isSelected}`);
            }
        });
    } else {
        console.warn("[MODAL_PIE] elementTextListDiv not found for updating list item selections.");
    }
}


/**
 * Xử lý ảnh và elements khi ảnh đã sẵn sàng và modal đã hiển thị.
 */
async function processImageAndElementsWhenReady() {
    if (!screenshotImg || !imageContainer || !elementTextListDiv || !currentManagingNodeData) {
        console.error("[MODAL_PIE] processImageAndElementsWhenReady: Thiếu DOM elements hoặc data.");
        return;
    }
    console.log("[MODAL_PIE] processImageAndElementsWhenReady: Bắt đầu xử lý ảnh và elements.");

    if (screenshotImg.style.display !== 'block') screenshotImg.style.display = 'block';
    await new Promise(resolve => requestAnimationFrame(resolve)); // Đợi frame để render

    console.log(`    Image natural dimensions: ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
    console.log(`    Image client dimensions (initial check): ${screenshotImg.clientWidth}x${screenshotImg.clientHeight}`);

    if (screenshotImg.naturalWidth === 0 || screenshotImg.naturalHeight === 0) {
        console.error("[MODAL_PIE] Ảnh không hợp lệ (kích thước gốc bằng 0).");
        if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2 text-center">Ảnh tải về không hợp lệ.</p>`;
        return;
    }

    let displayedWidth = screenshotImg.clientWidth;
    let displayedHeight = screenshotImg.clientHeight;

    // ... (Logic đợi kích thước ảnh và fallback như trước, có thể giữ nguyên) ...
    if (displayedWidth === 0 || displayedHeight === 0) {
        console.warn("[MODAL_PIE] clientWidth/Height là 0. Thử đợi với vòng lặp setTimeout.");
        await new Promise((resolve) => {
            let attempts = 0; const maxAttempts = 60; const interval = 50;
            function checkDimLoop() {
                displayedWidth = screenshotImg.clientWidth; displayedHeight = screenshotImg.clientHeight;
                if ((displayedWidth > 0 && displayedHeight > 0) || attempts >= maxAttempts) {
                    resolve();
                } else { attempts++; setTimeout(checkDimLoop, interval); }
            }
            checkDimLoop();
        });
        displayedWidth = screenshotImg.clientWidth; displayedHeight = screenshotImg.clientHeight;
        if (displayedWidth === 0 || displayedHeight === 0) {
            // ... (xử lý lỗi không lấy được kích thước)
            console.error("[MODAL_PIE] Không thể xác định kích thước ảnh hiển thị.");
            if (imageContainer && !imageContainer.querySelector('.dimension-error-message')) {
                const errorMsgEl = document.createElement('p');
                errorMsgEl.className = 'text-danger small fst-italic p-1 text-center dimension-error-message';
                errorMsgEl.textContent = 'Lỗi: Không thể xác định kích thước ảnh để hiển thị elements.';
                imageContainer.appendChild(errorMsgEl);
            }
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-danger small">Lỗi hiển thị kích thước ảnh.</div>';
            return;
        }
    }


    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang tải elements...</div>';
    try {
        const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(currentManagingNodeData.currentScreenId));
        const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

        if (elementsJsonResponse.success && Array.isArray(elementsJsonResponse.elements)) {
            rawElementsDataForModal = elementsJsonResponse.elements;
            const nodeOriginalWidth = parseInt(currentManagingNodeData.width, 10);
            const nodeOriginalHeight = parseInt(currentManagingNodeData.height, 10);

            if (rawElementsDataForModal.length > 0 && nodeOriginalWidth > 0 && nodeOriginalHeight > 0) {
                drawInteractiveOverlays(
                    screenshotImg, rawElementsDataForModal, nodeOriginalWidth, nodeOriginalHeight,
                    imageContainer, // Container để vẽ overlay
                    handleElementSelectionFromVisualizer // Callback khi overlay được click
                );
            } else if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0) {
                console.warn("[MODAL_PIE] Thiếu width/height gốc của Node. Overlays có thể không chính xác.");
            }
            renderElementTextList(); // Render danh sách text elements
        } else {
            rawElementsDataForModal = [];
            throw new Error(elementsJsonResponse.error || "Không lấy được elements hoặc dữ liệu không phải array.");
        }
    } catch (error) {
        console.error("[MODAL_PIE] Lỗi tải elements hoặc vẽ overlays:", error);
        if (elementTextListDiv) elementTextListDiv.innerHTML = `<div class="list-group-item text-danger small">Lỗi tải elements: ${error.message}</div>`;
        rawElementsDataForModal = [];
    }
    // Gọi updateVisualizerSelections ở cuối, sau khi cả overlays và list text đã được render
    // và currentSelectedPieConditions (nếu có từ việc load PIE cũ) đã được thiết lập.
    updateVisualizerSelections();
}

/**
 * Mở modal và điền dữ liệu cho node được chọn.
 * @param {object} nodeData - Dữ liệu của node từ table_handler.js.
 */
async function openModalWithData(nodeData) {
    if (!modalEl) getDOMElementsForManagePie(); // Lấy DOM elements nếu chưa có
    if (!managePieModalInstance && modalEl) managePieModalInstance = new bootstrap.Modal(modalEl);
    if (!managePieModalInstance) { console.error("Không thể khởi tạo modal instance cho #managePieConditionsModal."); return; }

    console.log("[MODAL_PIE] openModalWithData received nodeData:", JSON.stringify(nodeData, null, 2));
    currentManagingNodeData = { ...nodeData }; // Sao chép dữ liệu node
    currentSelectedPieConditions = []; // Reset danh sách điều kiện hiện tại
    rawElementsDataForModal = [];    // Reset danh sách elements thô

    // Reset UI của modal
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';
    if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
    if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';
    if (screenshotImg) { screenshotImg.src = ''; screenshotImg.style.display = 'none'; }
    if (imageContainer) {
        imageContainer.querySelectorAll(`.${APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE}, p, .dimension-error-message, .fallback-warning-message, .overlay-dimension-error`).forEach(el => el.remove());
    }
    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang chuẩn bị...</div>';

    renderSelectedPieConditions(); // Hiển thị bảng điều kiện rỗng ban đầu

    const screenshotUrlToLoad = currentManagingNodeData.screenshotFullUrl;
    let imageHasLoadedSuccessfully = false;

    const modalShownHandler = () => {
        console.log("[MODAL_PIE] Sự kiện 'shown.bs.modal' được kích hoạt.");
        if (imageHasLoadedSuccessfully) {
            processImageAndElementsWhenReady();
        } else if (screenshotImg && screenshotImg.src && !screenshotImg.complete) {
            console.log("[MODAL_PIE] Modal shown, ảnh có thể chưa onload hoàn toàn. Đợi onload event của ảnh.");
        } else if (screenshotImg && screenshotImg.src && screenshotImg.complete && screenshotImg.naturalWidth === 0) {
            console.log("[MODAL_PIE] Modal shown, ảnh đã onload nhưng có vẻ là ảnh lỗi (naturalWidth=0).");
        } else if (screenshotImg && screenshotImg.src && screenshotImg.complete && screenshotImg.naturalWidth > 0) {
            imageHasLoadedSuccessfully = true;
            processImageAndElementsWhenReady();
        } else {
            console.log("[MODAL_PIE] Modal shown, không có ảnh hợp lệ để xử lý.");
        }
    };

    if (modalEl) {
        modalEl.removeEventListener('shown.bs.modal', modalShownHandler); // Xóa listener cũ nếu có
        modalEl.addEventListener('shown.bs.modal', modalShownHandler, { once: true });
    }

    if (screenshotUrlToLoad && screenshotImg) {
        screenshotImg.onload = () => {
            screenshotImg.style.display = 'block';
            console.log("[MODAL_PIE] Sự kiện 'onload' của ảnh được kích hoạt:", screenshotImg.src);
            console.log(`    Kích thước gốc (natural): ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
            if (screenshotImg.naturalWidth > 0 && screenshotImg.naturalHeight > 0) {
                imageHasLoadedSuccessfully = true;
            } else {
                imageHasLoadedSuccessfully = false;
                console.error("[MODAL_PIE] Ảnh onload nhưng naturalWidth/Height là 0.");
                if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2 text-center">Ảnh tải về không hợp lệ (kích thước 0x0).</p>`;
                if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Ảnh không hợp lệ.</div>';
                return;
            }

            if (modalEl && modalEl.classList.contains('show')) { // Nếu modal đã hiển thị
                processImageAndElementsWhenReady();
            }
        };
        screenshotImg.onerror = () => {
            imageHasLoadedSuccessfully = false;
            console.error("[MODAL_PIE] Lỗi tải ảnh:", screenshotImg.src);
            const filenameForError = currentManagingNodeData.screenshotFilename || 'không rõ';
            const errorMessageHTML = `<p class="text-danger p-2 text-center">Lỗi tải ảnh: ${filenameForError}.<br><small>URL: ${screenshotImg.src || 'N/A'}</small></p>`;
            if (imageContainer) imageContainer.innerHTML = errorMessageHTML;
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Lỗi tải ảnh.</div>';
        };
        screenshotImg.src = screenshotUrlToLoad; // Bắt đầu tải ảnh
    } else {
        if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2 text-center">Node không có URL ảnh.</p>';
        if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Không có ảnh.</div>';
    }

    // Tải conditions cũ nếu node 'defined'
    const nodeStatusToHandle = String(currentManagingNodeData.nodeStatus || '').toLowerCase();
    const definedStatuses = ['defined', 'defined_from_unknown', 'merged_to_defined'];

    if (definedStatuses.includes(nodeStatusToHandle)) {
        if (modalLabel) modalLabel.textContent = `Sửa Điều kiện PIE cho: ${currentManagingNodeData.pieLogicalName || currentManagingNodeData.currentScreenId}`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Lưu Conditions PIE'; mainActionBtn.className = 'btn btn-sm btn-primary'; }

        try {
            const conditionsUrl = `${APP_CONFIG.API_GET_PIE_CONDITIONS_URL}?app_name=${encodeURIComponent(currentManagingNodeData.appName)}&defined_screen_id=${encodeURIComponent(currentManagingNodeData.currentScreenId)}`;
            const conditionsJsonResponse = await sendApiRequest(conditionsUrl, 'GET');

            if (conditionsJsonResponse.success && Array.isArray(conditionsJsonResponse.conditions)) {
                currentSelectedPieConditions = conditionsJsonResponse.conditions.map(c => ({
                    ...c,
                    internal_element_index: -1, // Điều kiện đã lưu không trỏ trực tiếp đến index trên ảnh hiện tại
                    element_identifier_display: c.element_identifier_display || "Điều kiện đã lưu từ DB",
                    is_manual: c.is_manual === undefined ? true : c.is_manual // Giả định là manual nếu không có cờ
                }));
                console.log(`[MODAL_PIE] Đã tải ${currentSelectedPieConditions.length} điều kiện PIE đã lưu.`);
            } else {
                currentSelectedPieConditions = [];
                const apiMessage = conditionsJsonResponse.message || "Không tải được conditions hoặc không có conditions nào.";
                console.warn(`[MODAL_PIE] Khi tải conditions cho node defined: ${apiMessage}`);
                if (conditionsJsonResponse.success === false && conditionsJsonResponse.message && !conditionsJsonResponse.message.toLowerCase().includes("không tìm thấy định nghĩa pie")) {
                    if (errorMessagesSpan) errorMessagesSpan.textContent = apiMessage;
                }
            }
        } catch (error) {
            console.error("[MODAL_PIE] Lỗi khi gọi API tải PIE conditions cho node defined:", error);
            currentSelectedPieConditions = [];
            const errorMessageToShow = error.data?.message || error.message || 'Lỗi không xác định khi tải conditions.';
            if (errorMessagesSpan) errorMessagesSpan.textContent = errorMessageToShow;
        }
    } else { // Node 'unknown'
        if (modalLabel) modalLabel.textContent = `Chọn Điều kiện cho PIE Mới (Node: ${currentManagingNodeData.currentScreenId})`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Tiếp tục Định nghĩa PIE'; mainActionBtn.className = 'btn btn-sm btn-success'; }
        currentSelectedPieConditions = [];
    }

    renderSelectedPieConditions(); // Vẽ lại bảng điều kiện (có thể rỗng hoặc có dữ liệu đã tải)
    // Hàm này cũng sẽ gọi updateVisualizerSelections()
    if (managePieModalInstance) managePieModalInstance.show();
}

/**
 * Khởi tạo modal quản lý PIE conditions.
 */
export function initManagePieModal() {
    getDOMElementsForManagePie(); // Lấy các DOM element cần thiết
    if (!modalEl) {
        console.warn("Modal #managePieConditionsModal không được tìm thấy trong DOM khi initManagePieModal.");
        return;
    }
    if (!managePieModalInstance) { // Tạo instance modal nếu chưa có
        managePieModalInstance = new bootstrap.Modal(modalEl);
    }

    // Gán hàm mở modal vào global scope để table_handler.js có thể gọi
    window.openManagePieConditionsModalGlobal = openModalWithData;

    // Sự kiện cho nút "Thêm điều kiện thủ công"
    if (addManualConditionBtn) {
        addManualConditionBtn.addEventListener('click', function () {
            console.log("[MODAL_PIE] Add manual condition clicked.");
            currentSelectedPieConditions.push({
                attribute: '',
                comparison: 'EQUALS',
                value: '',
                internal_element_index: -1, // Đánh dấu không trỏ đến element cụ thể trên ảnh
                element_identifier_display: 'Điều kiện thủ công mới',
                is_manual: true // Đánh dấu đây là điều kiện thủ công
            });
            renderSelectedPieConditions(); // Vẽ lại bảng điều kiện
        });
    }

    // Sự kiện cho nút hành động chính (Lưu Conditions / Tiếp tục Định nghĩa PIE)
    if (mainActionBtn) {
        mainActionBtn.addEventListener('click', async function () {
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xử lý...';
            if (errorMessagesSpan) errorMessagesSpan.textContent = '';

            const finalConditionsToSave = currentSelectedPieConditions.map(cond => ({
                attribute: cond.attribute,
                comparison: cond.comparison,
                value: cond.value
                // Không cần gửi internal_element_index hay element_identifier_display lên server
            })).filter(c => c.attribute && c.comparison && (c.comparison === 'EXISTS' || c.comparison === 'NOT_EXISTS' || (c.value !== undefined && c.value !== null && String(c.value).trim() !== '')));

            // Kiểm tra xem có điều kiện nào chưa hoàn chỉnh không
            if (currentSelectedPieConditions.some(c => !c.attribute || !c.comparison || ((c.comparison !== 'EXISTS' && c.comparison !== 'NOT_EXISTS') && (c.value === undefined || c.value === null || String(c.value).trim() === '')))) {
                if (errorMessagesSpan) errorMessagesSpan.textContent = 'Một số điều kiện chưa hoàn chỉnh (thiếu Thuộc tính, So sánh hoặc Giá trị). Vui lòng kiểm tra lại.';
                this.disabled = false;
                this.innerHTML = (currentManagingNodeData.nodeStatus === 'defined' || currentManagingNodeData.nodeStatus === 'defined_from_unknown' || currentManagingNodeData.nodeStatus === 'merged_to_defined' ? 'Lưu Conditions PIE' : 'Tiếp tục Định nghĩa PIE');
                return;
            }

            const nodeStatusToHandleOnClick = String(currentManagingNodeData.nodeStatus || '').toLowerCase();
            const definedStatusesOnClick = ['defined', 'defined_from_unknown', 'merged_to_defined'];

            if (definedStatusesOnClick.includes(nodeStatusToHandleOnClick)) { // Node "defined", đang sửa conditions
                const definedPieIdToUpdate = currentManagingNodeData.currentScreenId; // screen_id của node defined chính là defined_screen_id
                const updateUrl = `${APP_CONFIG.API_UPDATE_PIE_CONDITIONS_BASE_URL}/${encodeURIComponent(definedPieIdToUpdate)}/update_conditions`;
                console.log(`[MODAL_PIE] Updating conditions for defined PIE. URL: ${updateUrl}, Payload:`, finalConditionsToSave);
                try {
                    const result = await sendApiRequest(updateUrl, 'POST', {
                        app_name: currentManagingNodeData.appName,
                        new_conditions_list: finalConditionsToSave // Gửi danh sách đã lọc
                    });
                    if (result.success) {
                        alert("Cập nhật điều kiện PIE thành công!");
                        if (managePieModalInstance) managePieModalInstance.hide();
                        if (window.fetchAndRenderTableNodesGlobal) window.fetchAndRenderTableNodesGlobal();
                        else { console.warn("fetchAndRenderTableNodesGlobal không tồn tại, thử reload trang."); location.reload(); }
                    } else {
                        throw new Error(result.message || result.error || "Lỗi từ server khi cập nhật điều kiện PIE.");
                    }
                } catch (error) {
                    console.error("[MODAL_PIE] Lỗi khi update PIE conditions:", error);
                    const errorMsgToShow = error.data?.message || error.message || 'Lỗi không xác định khi cập nhật.';
                    if (errorMessagesSpan) errorMessagesSpan.textContent = errorMsgToShow;
                } finally {
                    this.disabled = false;
                    this.textContent = 'Lưu Conditions PIE';
                }
            } else { // Node 'unknown', đang tạo PIE mới -> chuyển sang modal metadata
                if (finalConditionsToSave.length === 0) { // Vẫn cần ít nhất 1 điều kiện
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Vui lòng chọn ít nhất một điều kiện nhận diện hợp lệ để tiếp tục.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }
                console.log("[MODAL_PIE] Conditions selected for new PIE. Proceeding to metadata modal. Data:", currentManagingNodeData, "Conditions:", finalConditionsToSave);
                if (managePieModalInstance) managePieModalInstance.hide();
                if (window.openDefineNewPieMetadataModalGlobal) {
                    window.openDefineNewPieMetadataModalGlobal(currentManagingNodeData, finalConditionsToSave);
                } else {
                    console.error("Hàm openDefineNewPieMetadataModalGlobal không tồn tại.");
                    alert("Lỗi: Không thể mở form định nghĩa metadata.");
                }
                // Reset nút này vì nó thuộc về modal đã ẩn
                this.disabled = false;
                this.textContent = 'Tiếp tục Định nghĩa PIE';
            }
        });
    }
}
