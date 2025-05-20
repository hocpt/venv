// static/js/admin_node_management/modal_manage_pie.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest, drawInteractiveOverlays } from './utils.js';

let managePieModalInstance = null;
let currentManagingNodeData = {}; // Dữ liệu của Node đang được xử lý
let currentSelectedPieConditions = []; // Mảng các object condition đang được tạo/sửa
let rawElementsDataForModal = []; // Mảng elements gốc từ API cho Node hiện tại

// DOM Elements cho modal này (sẽ được gán trong init)
let modalEl, currentScreenIdDisplay, currentAppNameDisplay, modalLabel,
    imageContainer, screenshotImg, elementTextListDiv, selectedConditionsListDiv,
    addManualConditionBtn, mainActionBtn, errorMessagesSpan;

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

function renderElementTextList() {
    if (!elementTextListDiv) return;
    elementTextListDiv.innerHTML = '';
    if (!rawElementsDataForModal || rawElementsDataForModal.length === 0) {
        elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Không có elements nào được phát hiện trên ảnh này.</p>';
        return;
    }

    rawElementsDataForModal.forEach((elData, index) => {
        const listItem = document.createElement('a');
        listItem.href = "#";
        listItem.className = 'list-group-item list-group-item-action py-1 px-2';
        listItem.dataset.elementIndex = index;

        let idPart = elData.resource_id || elData.element_id || 'Không có ID';
        let textPart = elData.text_content || '';
        let descPart = elData.description || '';
        let classPart = elData.class_name ? elData.class_name.replace('android.widget.', '') : '';

        let displayText = `<div class="fw-bold small text-truncate" title="${idPart}">${idPart}</div>`;
        if (textPart) displayText += `<div class="text-muted xsmall text-truncate" title="${textPart}">Text: ${textPart}</div>`;
        if (descPart) displayText += `<div class="text-muted xsmall text-truncate" title="${descPart}">Desc: ${descPart}</div>`;
        if (classPart) displayText += `<div class="text-muted xsmall">Class: ${classPart}</div>`;

        listItem.innerHTML = displayText;
        listItem.title = `ID: ${idPart}\nText: ${textPart}\nDesc: ${descPart}\nClass: ${classPart}\nClick để chọn/bỏ chọn.`;

        const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === index);
        if (isSelected) listItem.classList.add(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);

        listItem.addEventListener('click', function (e) {
            e.preventDefault();
            handleElementSelectionFromVisualizer(index, this);
        });
        elementTextListDiv.appendChild(listItem);
    });
}

function renderSelectedPieConditions() {
    if (!selectedConditionsListDiv) return;
    selectedConditionsListDiv.innerHTML = '';

    if (currentSelectedPieConditions.length === 0) {
        selectedConditionsListDiv.innerHTML = '<p class="text-muted small p-2 initial-prompt">Click element trên ảnh/list hoặc "Thêm thủ công" để tạo điều kiện.</p>';
        updateVisualizerSelections();
        return;
    }

    currentSelectedPieConditions.forEach((condition, index) => {
        const conditionDiv = document.createElement('div');
        conditionDiv.className = `mb-2 p-2 border rounded bg-white shadow-sm ${APP_CONFIG.CSS_CLASSES.CONDITION_ITEM_ROW}`;
        conditionDiv.dataset.conditionIndex = index;

        let attributeOptionsHtml = APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE.map(attr =>
            `<option value="${attr.value}" ${condition.attribute === attr.value ? 'selected' : ''}>${attr.label}</option>`
        ).join('');
        let comparisonOptionsHtml = APP_CONFIG.COMPARISON_TYPES_FOR_PIE.map(comp =>
            `<option value="${comp.value}" ${condition.comparison === comp.value ? 'selected' : ''}>${comp.label}</option>`
        ).join('');

        conditionDiv.innerHTML = `
            <div class="row gx-2 gy-1 align-items-center">
                <div class="col-sm-4">
                    <select class="form-select form-select-sm condition-attribute" data-index="${index}" aria-label="Thuộc tính element">
                        <option value="">-- Thuộc tính --</option>
                        ${attributeOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-3">
                    <select class="form-select form-select-sm condition-comparison" data-index="${index}" aria-label="Loại so sánh">
                        ${comparisonOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-4">
                    <input type="text" class="form-control form-control-sm condition-value" data-index="${index}"
                           value="${condition.value || ''}" placeholder="Giá trị so sánh"
                           aria-label="Giá trị so sánh"
                           ${condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS' ? 'disabled' : ''}>
                </div>
                <div class="col-sm-1 text-end">
                    <button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-index="${index}" title="Xóa điều kiện này" aria-label="Xóa điều kiện">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="text-muted xsmall mt-1"><em>${condition.element_identifier_display || 'Điều kiện nhập thủ công'}</em></div>
        `;
        selectedConditionsListDiv.appendChild(conditionDiv);
    });
    attachListenersToSelectedConditions();
    updateVisualizerSelections();
}

function attachListenersToSelectedConditions() {
    if (!selectedConditionsListDiv) return;
    selectedConditionsListDiv.querySelectorAll('.condition-attribute').forEach(select => {
        select.onchange = function () {
            const index = parseInt(this.dataset.index);
            if (currentSelectedPieConditions[index]) currentSelectedPieConditions[index].attribute = this.value;
        };
    });
    selectedConditionsListDiv.querySelectorAll('.condition-comparison').forEach(select => {
        select.onchange = function () {
            const index = parseInt(this.dataset.index);
            if (currentSelectedPieConditions[index]) {
                currentSelectedPieConditions[index].comparison = this.value;
                const valueInput = this.closest('.row').querySelector('.condition-value');
                if (this.value === 'EXISTS' || this.value === 'NOT_EXISTS') {
                    valueInput.disabled = true; valueInput.value = '';
                    currentSelectedPieConditions[index].value = ''; // Set value to empty for EXISTS/NOT_EXISTS
                } else {
                    valueInput.disabled = false;
                }
            }
        };
    });
    selectedConditionsListDiv.querySelectorAll('.condition-value').forEach(input => {
        input.oninput = function () {
            const index = parseInt(this.dataset.index);
            if (currentSelectedPieConditions[index]) currentSelectedPieConditions[index].value = this.value.trim();
        };
    });
    selectedConditionsListDiv.querySelectorAll('.remove-condition-btn').forEach(button => {
        button.onclick = function () {
            const index = parseInt(this.dataset.index);
            currentSelectedPieConditions.splice(index, 1);
            renderSelectedPieConditions();
        };
    });
}

function handleElementSelectionFromVisualizer(elementOriginalIndex, clickedDomElement) {
    if (rawElementsDataForModal.length <= elementOriginalIndex || elementOriginalIndex < 0) {
        console.warn("Invalid element index for selection:", elementOriginalIndex);
        return;
    }
    const elementData = rawElementsDataForModal[elementOriginalIndex];
    if (!elementData) {
        console.warn("No element data found for index:", elementOriginalIndex);
        return;
    }

    const existingConditionIndex = currentSelectedPieConditions.findIndex(cond => cond.internal_element_index === elementOriginalIndex);

    if (existingConditionIndex > -1) { // Element đã được chọn -> bỏ chọn
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
    } else { // Element chưa được chọn -> chọn mới
        let newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: `Từ Elem: ${(elementData.resource_id || elementData.text_content || elementData.element_id || 'N/A').substring(0, 20)}...`,
            attribute: '', // Sẽ được tự động gợi ý
            comparison: 'EQUALS',
            value: ''
        };

        if (elementData.resource_id) {
            newCondition.attribute = 'resource_id';
            newCondition.value = elementData.resource_id;
        } else if (elementData.text_content) {
            newCondition.attribute = 'text';
            newCondition.value = elementData.text_content;
        } else if (elementData.description) { // Ưu tiên content-desc nếu không có text
            newCondition.attribute = 'description';
            newCondition.value = elementData.description;
        } else if (elementData.class_name) {
            newCondition.attribute = 'class_name';
            newCondition.value = elementData.class_name;
        } else {
            // Nếu không có thuộc tính nào phù hợp, vẫn thêm condition rỗng để người dùng tự điền
            console.warn("Element không có thuộc tính phù hợp (resource_id, text, description, class_name) để tự động tạo condition:", elementData);
            // Hoặc có thể alert và không thêm:
            // alert("Element này không có thuộc tính phù hợp để tự động tạo điều kiện."); return;
        }
        currentSelectedPieConditions.push(newCondition);
    }
    renderSelectedPieConditions(); // Điều này sẽ tự động gọi updateVisualizerSelections
}

function updateVisualizerSelections() {
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(overlay => {
            const elIndex = parseInt(overlay.dataset.elementIndex);
            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex);
            overlay.classList.toggle(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE, isSelected);
        });
    }
    if (elementTextListDiv) {
        elementTextListDiv.querySelectorAll('.list-group-item').forEach(item => {
            const elIndex = parseInt(item.dataset.elementIndex);
            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex);
            item.classList.toggle(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE, isSelected);
        });
    }
}

// Hàm này sẽ được export và gọi từ table_handler.js (hoặc main.js)
// thông qua window.openManagePieConditionsModalGlobal
async function openModal(nodeData) {
    if (!managePieModalInstance) {
        console.error("Modal #managePieConditionsModal instance not available for opening.");
        getDOMElementsForManagePie(); // Thử lấy lại DOM elements
        if (!modalEl) return;
        managePieModalInstance = new bootstrap.Modal(modalEl);
        if (!managePieModalInstance) { console.error("Không thể khởi tạo instance cho #managePieConditionsModal"); return; }
    }

    currentManagingNodeData = { ...nodeData };
    currentSelectedPieConditions = [];
    rawElementsDataForModal = [];
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';

    if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
    if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';

    // Reset UI trước khi tải mới
    if (screenshotImg) {
        screenshotImg.src = ''; // Xóa ảnh cũ
        screenshotImg.style.display = 'none'; // Ẩn đi
    }
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());
        // Xóa các thông báo lỗi cũ trong imageContainer
        const errorP = imageContainer.querySelector('p.text-danger');
        if (errorP) errorP.remove();
    }
    if (elementTextListDiv) elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Đang chuẩn bị dữ liệu...</p>';
    renderSelectedPieConditions(); // Render Phần 3 (sẽ trống ban đầu)


    const screenshotUrlFromData = currentManagingNodeData.screenshotFullUrl;

    if (screenshotUrlFromData && screenshotImg) {
        screenshotImg.src = screenshotUrlFromData;
        screenshotImg.style.display = 'block'; // Hiện img để nó bắt đầu tải

        screenshotImg.onload = async () => {
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Đang tải elements...</p>';
            try {
                const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(nodeData.currentScreenId));
                const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

                if (elementsJsonResponse.success && elementsJsonResponse.elements) {
                    rawElementsDataForModal = elementsJsonResponse.elements;
                    const nodeWidth = currentManagingNodeData.width;
                    const nodeHeight = currentManagingNodeData.height;

                    if (rawElementsDataForModal.length > 0 && nodeWidth && nodeHeight) {
                        drawInteractiveOverlays(screenshotImg, rawElementsDataForModal, nodeWidth, nodeHeight, imageContainer, currentSelectedPieConditions, handleElementSelectionFromVisualizer);
                    } else if (!nodeWidth || !nodeHeight) {
                        console.warn("Modal: Thiếu width/height gốc của Node, không thể vẽ overlay chính xác.");
                        if (imageContainer) {
                            const existingError = imageContainer.querySelector('.overlay-dimension-error');
                            if (existingError) existingError.remove();
                            const errorMsgEl = document.createElement('p');
                            errorMsgEl.className = 'text-warning small fst-italic p-1 overlay-dimension-error';
                            errorMsgEl.textContent = '(Lưu ý: Không có kích thước gốc, overlay có thể không chính xác.)';
                            imageContainer.appendChild(errorMsgEl);
                        }
                    }
                    renderElementTextList();
                } else {
                    throw new Error(elementsJsonResponse.error || "Không lấy được elements.");
                }
            } catch (error) {
                console.error("Lỗi tải elements cho modal:", error);
                if (elementTextListDiv) elementTextListDiv.innerHTML = `<p class="text-danger small p-2">Lỗi tải elements: ${error.message}</p>`;
            }
        };
        screenshotImg.onerror = () => {
            console.error("Modal manage PIE: Lỗi tải ảnh từ URL:", screenshotImg.src);
            const filenameForError = currentManagingNodeData.screenshotFilename || 'tên file không xác định';
            const errorMessage = `Lỗi tải ảnh: ${filenameForError}.<br><small>URL thử: ${screenshotImg.src || 'Không có URL'}</small>`;
            if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2">${errorMessage}</p>`;
            if (elementTextListDiv) elementTextListDiv.innerHTML = `<p class="text-muted small p-2">Lỗi tải ảnh, không thể hiển thị elements.</p>`;
        };
    } else {
        if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2">Node không có thông tin ảnh (URL không có).</p>';
        if (elementTextListDiv) elementTextListDiv.innerHTML = `<p class="text-muted small p-2">Không thể hiển thị elements trực quan.</p>';
    }
    }
    
}