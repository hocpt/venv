// static/js/admin_node_management/modal_manage_pie.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest, drawInteractiveOverlays } from './utils.js';

let managePieModalInstance = null;
let currentManagingNodeData = {};
let currentSelectedPieConditions = [];
let rawElementsDataForModal = [];

// DOM Elements for this modal
let modalEl, currentScreenIdDisplay, currentAppNameDisplay, modalLabel,
    imageContainer, screenshotImg, elementTextListDiv, selectedConditionsListDiv,
    addManualConditionBtn, mainActionBtn, errorMessagesSpan;

function getDOMElements() {
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
        elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Không có elements nào được phát hiện.</p>';
        return;
    }

    rawElementsDataForModal.forEach((elData, index) => {
        const listItem = document.createElement('a');
        listItem.href = "#";
        listItem.className = 'list-group-item list-group-item-action py-1 px-2'; // Reduced padding
        listItem.dataset.elementIndex = index;

        let idPart = elData.resource_id || elData.element_id || 'No ID';
        let textPart = elData.text_content || '';
        let descPart = elData.description || ''; // content-description
        let classPart = elData.class_name ? elData.class_name.replace('android.widget.', '') : '';

        let displayText = `<div class="fw-bold small">${idPart.substring(0, 30)}</div>`;
        if (textPart) displayText += `<div class="text-muted xsmall">Text: ${textPart.substring(0, 35)}${textPart.length > 35 ? '...' : ''}</div>`;
        if (descPart) displayText += `<div class="text-muted xsmall">Desc: ${descPart.substring(0, 35)}${descPart.length > 35 ? '...' : ''}</div>`;
        if (classPart) displayText += `<div class="text-muted xsmall">Class: ${classPart}</div>`;

        listItem.innerHTML = displayText;
        listItem.title = `ID: ${idPart}\nText: ${textPart}\nDesc: ${descPart}\nClass: ${classPart}`;

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
        selectedConditionsListDiv.innerHTML = '<p class="text-muted small p-2 initial-prompt">Click element trên ảnh/list hoặc "Thêm thủ công".</p>';
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
                    <select class="form-select form-select-sm condition-attribute" data-index="${index}">
                        <option value="">-- Thuộc tính --</option>
                        ${attributeOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-3">
                    <select class="form-select form-select-sm condition-comparison" data-index="${index}">
                        ${comparisonOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-4">
                    <input type="text" class="form-control form-control-sm condition-value" data-index="${index}"
                           value="${condition.value || ''}" placeholder="Giá trị"
                           ${condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS' ? 'disabled' : ''}>
                </div>
                <div class="col-sm-1 text-end">
                    <button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-index="${index}" title="Xóa">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="text-muted xsmall mt-1"><em>${condition.element_identifier_display || 'Điều kiện thủ công'}</em></div>
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
                    currentSelectedPieConditions[index].value = '';
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
    if (rawElementsDataForModal.length <= elementOriginalIndex || elementOriginalIndex < 0) return;
    const elementData = rawElementsDataForModal[elementOriginalIndex];
    if (!elementData) return;

    const existingConditionIndex = currentSelectedPieConditions.findIndex(cond => cond.internal_element_index === elementOriginalIndex);

    if (existingConditionIndex > -1) {
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
    } else {
        let newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: `Elem: ${(elementData.resource_id || elementData.element_id || '').substring(0, 15)}...`,
            attribute: '', comparison: 'EQUALS', value: ''
        };
        if (elementData.resource_id) {
            newCondition.attribute = 'resource_id'; newCondition.value = elementData.resource_id;
        } else if (elementData.text_content) {
            newCondition.attribute = 'text'; newCondition.value = elementData.text_content;
        } else if (elementData.description) {
            newCondition.attribute = 'description'; newCondition.value = elementData.description;
        } else if (elementData.class_name) {
            newCondition.attribute = 'class_name'; newCondition.value = elementData.class_name;
        } else { return; }
        currentSelectedPieConditions.push(newCondition);
    }
    renderSelectedPieConditions(); // This will call updateVisualizerSelections
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

export async function openManagePieConditionsModal(nodeData) {
    if (!modalInstance) {
        console.error("Modal #managePieConditionsModal instance not available.");
        getDOMElements(); // Try to get them again
        if (!modalEl) return;
        managePieModalInstance = new bootstrap.Modal(modalEl); // Re-init if first time failed
        if (!managePieModalInstance) return;
    }

    currentManagingNodeData = { ...nodeData };
    currentSelectedPieConditions = [];
    rawElementsDataForModal = [];
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';

    if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
    if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';
    if (screenshotImg) screenshotImg.src = APP_CONFIG.SCREENSHOTS_BASE_URL + 'placeholder_loading.gif'; // Placeholder
    if (imageContainer) imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());
    if (elementTextListDiv) elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Đang tải elements...</p>';
    renderSelectedPieConditions(); // Render Phần 3 (sẽ trống ban đầu)


    // Load screenshot
    let screenshotPath = '';
    if (nodeData.screenshotFilename && nodeData.appName) {
        screenshotPath = `${APP_CONFIG.SCREENSHOTS_BASE_URL}${nodeData.appName}/${nodeData.screenshotFilename}`;
    }

    const screenshotPromise = new Promise((resolve, reject) => {
        if (screenshotPath && screenshotImg) {
            screenshotImg.src = screenshotPath;
            screenshotImg.onload = () => resolve();
            screenshotImg.onerror = () => {
                console.error("Lỗi tải ảnh:", screenshotPath);
                if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2">Lỗi tải ảnh: ${nodeData.screenshotFilename || 'Không có ảnh'}</p>`;
                reject(new Error("Lỗi tải ảnh screenshot."));
            };
        } else {
            if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2">Node không có ảnh.</p>';
            resolve(); // Resolve if no image to load, so element loading can proceed if desired
        }
    });

    try {
        await screenshotPromise; // Wait for image to load or fail gracefully

        // Load elements only if screenshot loaded (or if we decide to load them anyway)
        if (screenshotImg.src && !screenshotImg.src.includes('placeholder_loading.gif')) { // Check if image actually loaded
            const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(nodeData.currentScreenId));
            const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

            if (elementsJsonResponse.success && elementsJsonResponse.elements) {
                rawElementsDataForModal = elementsJsonResponse.elements;
                drawInteractiveOverlays(screenshotImg, rawElementsDataForModal, nodeData.width, nodeData.height, imageContainer, currentSelectedPieConditions, handleElementSelectionFromVisualizer);
                renderElementTextList(); // Render text list after overlays are ready
            } else {
                throw new Error(elementsJsonResponse.error || "Không lấy được elements.");
            }
        } else if (!screenshotPath) {
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Không có ảnh, không thể hiển thị elements trực quan.</p>';
        }
    } catch (error) {
        console.error("Lỗi tải ảnh/elements cho modal quản lý PIE:", error);
        if (elementTextListDiv) elementTextListDiv.innerHTML = `<p class="text-danger small p-2">Lỗi: ${error.message}</p>`;
    }


    // Load existing conditions if node is 'defined'
    if (nodeData.nodeStatus === 'defined') {
        if (modalLabel) modalLabel.textContent = `Sửa Điều kiện PIE cho: ${nodeData.pieLogicalName || nodeData.currentScreenId}`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Lưu Conditions PIE'; mainActionBtn.className = 'btn btn-sm btn-primary'; }

        try {
            const conditionsUrl = `${APP_CONFIG.API_GET_PIE_CONDITIONS_URL}?app_name=${encodeURIComponent(nodeData.appName)}&defined_screen_id=${encodeURIComponent(nodeData.currentScreenId)}`;
            const conditionsJsonResponse = await sendApiRequest(conditionsUrl, 'GET');
            if (conditionsJsonResponse.success && conditionsJsonResponse.conditions) {
                currentSelectedPieConditions = conditionsJsonResponse.conditions.map(c => ({ ...c, internal_element_index: -1, element_identifier_display: "Điều kiện đã lưu" }));
            } else { currentSelectedPieConditions = []; console.warn("Không tải được conditions hiện tại:", conditionsJsonResponse.message); }
        } catch (error) {
            console.error("Lỗi tải conditions:", error); currentSelectedPieConditions = [];
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi tải conditions. Có thể tạo mới.';
        }
    } else { // 'unknown'
        if (modalLabel) modalLabel.textContent = `Chọn Điều kiện cho PIE Mới (Node: ${nodeData.currentScreenId})`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Tiếp tục Định nghĩa PIE'; mainActionBtn.className = 'btn btn-sm btn-success'; }
        currentSelectedPieConditions = [];
    }

    renderSelectedPieConditions(); // Render Phần 3 (sẽ gọi updateVisualizerSelections)
    modalInstance.show();
}

export function initManagePieModal() {
    getDOMElements(); // Lấy các element 1 lần
    if (!modalEl) return; // Nếu modal chính không có thì không làm gì cả

    if (addManualConditionBtn) {
        addManualConditionBtn.addEventListener('click', function () {
            currentSelectedPieConditions.push({
                attribute: '', comparison: 'EQUALS', value: '',
                internal_element_index: -1, // Đánh dấu là thủ công
                element_identifier_display: 'Điều kiện thủ công mới'
            });
            renderSelectedPieConditions();
        });
    }

    if (mainActionBtn) {
        mainActionBtn.addEventListener('click', async function () {
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xử lý...';
            if (errorMessagesSpan) errorMessagesSpan.textContent = '';

            const finalConditionsToSave = currentSelectedPieConditions.map(cond => ({
                attribute: cond.attribute,
                comparison: cond.comparison,
                value: cond.value
            })).filter(c => c.attribute && c.comparison); // Lọc bỏ condition chưa hoàn chỉnh

            if (currentManagingNodeData.nodeStatus === 'defined') {
                const definedPieIdToUpdate = currentManagingNodeData.currentScreenId;
                const updateUrl = `${APP_CONFIG.API_UPDATE_PIE_CONDITIONS_BASE_URL}/${encodeURIComponent(definedPieIdToUpdate)}/update_conditions`;
                try {
                    const result = await sendApiRequest(updateUrl, 'POST', {
                        app_name: currentManagingNodeData.appName,
                        new_conditions_list: finalConditionsToSave
                    });
                    if (result.success) {
                        alert("Cập nhật điều kiện PIE thành công!");
                        if (managePieModalInstance) managePieModalInstance.hide();
                        if (window.fetchAndRenderTableNodes) window.fetchAndRenderTableNodes(); else location.reload();
                    } else { throw new Error(result.message || "Lỗi từ server."); }
                } catch (error) {
                    console.error("Lỗi khi update PIE conditions:", error);
                    if (errorMessagesSpan) errorMessagesSpan.textContent = error.data?.message || error.message || 'Lỗi không xác định.';
                } finally {
                    this.disabled = false; this.textContent = 'Lưu Conditions PIE';
                }
            } else { // Node 'unknown' -> chuyển sang modal metadata
                if (finalConditionsToSave.length === 0) {
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Vui lòng chọn ít nhất một điều kiện nhận diện.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }
                if (managePieModalInstance) managePieModalInstance.hide();
                if (window.openDefineNewPieMetadataModalGlobal) { // Đổi tên để tránh xung đột
                    window.openDefineNewPieMetadataModalGlobal(currentManagingNodeData, finalConditionsToSave);
                } else { console.error("Hàm openDefineNewPieMetadataModalGlobal không tồn tại."); }
                this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
            }
        });
    }
}