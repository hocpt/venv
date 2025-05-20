// static/js/admin_node_management/modal_manage_pie.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest, drawInteractiveOverlays } from './utils.js';

let managePieModalInstance = null;
let currentManagingNodeData = {};
let currentSelectedPieConditions = [];
let rawElementsDataForModal = [];

// DOM Elements
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
        elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Không có elements nào được phát hiện.</div>';
        return;
    }
    rawElementsDataForModal.forEach((elData, index) => {
        const listItem = document.createElement('a');
        listItem.href = "#";
        listItem.className = 'list-group-item list-group-item-action py-1 px-2 text-break';
        listItem.dataset.elementIndex = index;
        const idPart = elData.resource_id || elData.element_id || 'Không có ID';
        const textPart = elData.text_content || '';
        const descPart = elData.description || '';
        const classPart = elData.class_name ? elData.class_name.replace('android.widget.', '') : '';
        let displayText = `<div class="fw-bold small" title="${idPart}">${idPart.substring(0, 35)}${idPart.length > 35 ? '...' : ''}</div>`;
        if (textPart) displayText += `<div class="text-muted xsmall" title="${textPart}">Text: ${textPart.substring(0, 40)}${textPart.length > 40 ? '...' : ''}</div>`;
        if (descPart) displayText += `<div class="text-muted xsmall" title="${descPart}">Desc: ${descPart.substring(0, 40)}${descPart.length > 40 ? '...' : ''}</div>`;
        if (classPart) displayText += `<div class="text-muted xsmall">Class: ${classPart}</div>`;
        listItem.innerHTML = displayText;
        listItem.title = `ID: ${idPart}\nText: ${textPart}\nDesc: ${descPart}\nClass: ${classPart}\nClick để chọn/bỏ chọn.`;

        listItem.addEventListener('click', (e) => {
            e.preventDefault();
            console.log("[MODAL_PIE] Text list item clicked. Index:", index);
            handleElementSelectionFromVisualizer(index);
        });
        elementTextListDiv.appendChild(listItem);
    });
    updateVisualizerSelections();
}

function renderSelectedPieConditions() {
    if (!selectedConditionsListDiv) return;
    selectedConditionsListDiv.innerHTML = '';
    if (currentSelectedPieConditions.length === 0) {
        selectedConditionsListDiv.innerHTML = '<p class="text-muted small p-2 initial-prompt">Click element trên ảnh/list hoặc "Thêm thủ công".</p>';
        updateVisualizerSelections(); // Gọi để bỏ chọn tất cả trên ảnh
        return;
    }

    currentSelectedPieConditions.forEach((condition, index) => {
        const conditionDiv = document.createElement('div');
        conditionDiv.className = `mb-2 p-2 border rounded bg-white shadow-sm ${APP_CONFIG.CSS_CLASSES.CONDITION_ITEM_ROW}`;
        conditionDiv.dataset.conditionIndex = index; // Lưu index của condition trong mảng

        // Tạo HTML cho select box "Thuộc tính"
        let attributeOptionsHtml = APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE.map(attr =>
            `<option value="${attr.value}" ${condition.attribute === attr.value ? 'selected' : ''}>${attr.label}</option>`
        ).join('');

        // Tạo HTML cho select box "So sánh"
        let comparisonOptionsHtml = APP_CONFIG.COMPARISON_TYPES_FOR_PIE.map(comp =>
            `<option value="${comp.value}" ${condition.comparison === comp.value ? 'selected' : ''}>${comp.label}</option>`
        ).join('');

        // Kiểm tra xem có nên disable input value không
        const isValueDisabled = condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS';

        conditionDiv.innerHTML = `
            <div class="row gx-2 gy-1 align-items-center">
                <div class="col-sm-4">
                    <select class="form-select form-select-sm condition-attribute" data-condition-array-index="${index}" aria-label="Thuộc tính">
                        <option value="">-- Thuộc tính --</option>
                        ${attributeOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-3">
                    <select class="form-select form-select-sm condition-comparison" data-condition-array-index="${index}" aria-label="So sánh">
                        ${comparisonOptionsHtml}
                    </select>
                </div>
                <div class="col-sm-4">
                    <input type="text" class="form-control form-control-sm condition-value" 
                           data-condition-array-index="${index}" 
                           value="${condition.value || ''}" 
                           placeholder="Giá trị" aria-label="Giá trị"
                           ${isValueDisabled ? 'disabled' : ''}>
                </div>
                <div class="col-sm-1 text-end">
                    <button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-condition-array-index="${index}" title="Xóa" aria-label="Xóa">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="text-muted xsmall mt-1"><em>Nguyên gốc: ${condition.element_identifier_display || 'Thủ công'}</em></div>`;
        selectedConditionsListDiv.appendChild(conditionDiv);
    });

    // Gắn listeners sau khi tất cả các div đã được thêm vào DOM
    attachListenersToSelectedConditions();
    updateVisualizerSelections(); // Cập nhật lựa chọn trên ảnh/list text
}

function attachListenersToSelectedConditions() {
    if (!selectedConditionsListDiv) return;

    selectedConditionsListDiv.querySelectorAll('.condition-attribute').forEach(selectElement => {
        selectElement.addEventListener('change', function () {
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex); // Lấy index của condition trong mảng
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;

            const newAttributeSelected = this.value;
            currentSelectedPieConditions[conditionArrayIndex].attribute = newAttributeSelected;

            // Lấy internal_element_index để tìm element gốc
            const internalElementIdx = currentSelectedPieConditions[conditionArrayIndex].internal_element_index;
            let newValueForCondition = ''; // Giá trị mặc định nếu không tìm thấy

            if (internalElementIdx !== -1 && internalElementIdx !== undefined && rawElementsDataForModal && rawElementsDataForModal[internalElementIdx]) {
                const originalElementData = rawElementsDataForModal[internalElementIdx];
                // Lấy giá trị mới từ originalElementData dựa trên newAttributeSelected
                switch (newAttributeSelected) {
                    case 'resource_id':
                        newValueForCondition = originalElementData.resource_id || originalElementData.element_id || '';
                        break;
                    case 'text':
                        newValueForCondition = originalElementData.text_content || '';
                        break;
                    case 'description':
                        newValueForCondition = originalElementData.description || '';
                        break;
                    case 'class_name':
                        newValueForCondition = originalElementData.class_name || originalElementData.element_type || '';
                        break;
                    // Thêm các case khác cho các thuộc tính bạn có trong APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE
                    default:
                        // Nếu thuộc tính không được xử lý đặc biệt, thử lấy trực tiếp từ originalElementData
                        newValueForCondition = originalElementData[newAttributeSelected] || '';
                }
            } else if (currentSelectedPieConditions[conditionArrayIndex].internal_element_index === -1) {
                // Đây là điều kiện thủ công, không thay đổi giá trị khi đổi thuộc tính, giữ giá trị cũ
                newValueForCondition = currentSelectedPieConditions[conditionArrayIndex].value;
                console.log("[MODAL_PIE] Manual condition, attribute changed, value kept:", newValueForCondition);
            }


            currentSelectedPieConditions[conditionArrayIndex].value = newValueForCondition;

            // Cập nhật input value trên UI
            const valueInputElement = this.closest('.row').querySelector('.condition-value');
            if (valueInputElement) {
                valueInputElement.value = newValueForCondition;
            }
            console.log(`[MODAL_PIE] Condition at index ${conditionArrayIndex} attribute changed to '${newAttributeSelected}', value set to '${newValueForCondition}'`);
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
                    valueInputElement.value = ''; // Xóa giá trị
                    valueInputElement.disabled = true;
                    currentSelectedPieConditions[conditionArrayIndex].value = ''; // Cập nhật trong mảng data
                } else {
                    valueInputElement.disabled = false;
                    // Giữ lại giá trị cũ nếu có, hoặc người dùng sẽ tự nhập
                }
            }
            console.log(`[MODAL_PIE] Condition at index ${conditionArrayIndex} comparison changed to '${newComparison}'`);
        });
    });

    selectedConditionsListDiv.querySelectorAll('.condition-value').forEach(inputElement => {
        inputElement.addEventListener('input', function () { // 'input' event tốt hơn 'oninput'
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex);
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;

            currentSelectedPieConditions[conditionArrayIndex].value = this.value.trim();
            // console.log(`[MODAL_PIE] Condition at index ${conditionArrayIndex} value changed to '${this.value.trim()}'`);
        });
    });

    selectedConditionsListDiv.querySelectorAll('.remove-condition-btn').forEach(buttonElement => {
        buttonElement.addEventListener('click', function () {
            const conditionArrayIndex = parseInt(this.dataset.conditionArrayIndex);
            if (isNaN(conditionArrayIndex) || !currentSelectedPieConditions[conditionArrayIndex]) return;

            console.log(`[MODAL_PIE] Removing condition at index ${conditionArrayIndex}`);
            currentSelectedPieConditions.splice(conditionArrayIndex, 1);
            renderSelectedPieConditions(); // Vẽ lại toàn bộ bảng điều kiện
        });
    });
}

function handleElementSelectionFromVisualizer(elementOriginalIndex) {
    console.log(`[MODAL_PIE] handleElementSelectionFromVisualizer called with originalIndex: ${elementOriginalIndex}`);
    if (!rawElementsDataForModal || rawElementsDataForModal.length === 0 || elementOriginalIndex < 0 || elementOriginalIndex >= rawElementsDataForModal.length) {
        console.warn("[MODAL_PIE] Invalid index or rawElementsDataForModal is empty.", elementOriginalIndex, rawElementsDataForModal);
        return;
    }
    const elementData = rawElementsDataForModal[elementOriginalIndex];
    if (!elementData) {
        console.warn("[MODAL_PIE] No element data found for index:", elementOriginalIndex);
        return;
    }
    console.log("[MODAL_PIE] Selected elementData:", JSON.stringify(elementData));

    const existingConditionIndex = currentSelectedPieConditions.findIndex(
        cond => cond.internal_element_index === elementOriginalIndex
    );

    if (existingConditionIndex > -1) {
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
        console.log("[MODAL_PIE] Condition removed for element index:", elementOriginalIndex);
    } else {
        let defaultAttribute = '';
        let defaultValue = '';
        let displayIdentifier = `Elem Index ${elementOriginalIndex}`;

        // ---- START: ƯU TIÊN RESOURCE_ID ----
        if (elementData.resource_id && typeof elementData.resource_id === 'string' && elementData.resource_id.trim() !== '') {
            defaultAttribute = 'resource_id'; // Đặt resource_id làm thuộc tính mặc định
            defaultValue = elementData.resource_id;
            displayIdentifier = `ResID: ${elementData.resource_id.substring(0, 20)}...`;
        } else if (elementData.element_id && typeof elementData.element_id === 'string' && elementData.element_id.includes(':id/')) { // Heuristic cho resource-id
            defaultAttribute = 'resource_id'; // Vẫn coi là resource_id nếu có dạng com.app:id/
            defaultValue = elementData.element_id;
            displayIdentifier = `ElemID: ${elementData.element_id.substring(0, 20)}...`;
        } else if (elementData.text_content && typeof elementData.text_content === 'string' && elementData.text_content.trim() !== '') {
            defaultAttribute = 'text';
            defaultValue = elementData.text_content;
            displayIdentifier = `Text: ${elementData.text_content.substring(0, 20)}...`;
        } else if (elementData.description && typeof elementData.description === 'string' && elementData.description.trim() !== '') {
            defaultAttribute = 'description';
            defaultValue = elementData.description;
            displayIdentifier = `Desc: ${elementData.description.substring(0, 20)}...`;
        } else if (elementData.class_name && typeof elementData.class_name === 'string' && elementData.class_name.trim() !== '') {
            defaultAttribute = 'class_name';
            defaultValue = elementData.class_name;
            displayIdentifier = `Class: ${elementData.class_name.substring(0, 20)}...`;
        } else {
            // Fallback nếu không có thuộc tính nào phù hợp, hoặc bạn muốn một mặc định khác
            // Lấy thuộc tính đầu tiên trong danh sách APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE làm mặc định
            if (APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE && APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE.length > 0) {
                defaultAttribute = APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE[0].value;
            } else {
                defaultAttribute = 'text'; // Mặc định cuối cùng nếu config rỗng
            }
            // Giá trị sẽ để trống để người dùng tự điền hoặc chọn lại thuộc tính
            defaultValue = '';
            displayIdentifier = `Elem Index ${elementOriginalIndex} (Cần cấu hình)`;
        }
        // ---- END: ƯU TIÊN RESOURCE_ID ----

        const newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: displayIdentifier,
            attribute: defaultAttribute, // Sử dụng thuộc tính mặc định đã xác định
            comparison: 'EQUALS',
            value: defaultValue       // Sử dụng giá trị mặc định đã xác định
        };
        currentSelectedPieConditions.push(newCondition);
        console.log("[MODAL_PIE] New condition added:", JSON.stringify(newCondition));
    }

    console.log("[MODAL_PIE] currentSelectedPieConditions after update:", JSON.stringify(currentSelectedPieConditions));
    renderSelectedPieConditions();
    updateVisualizerSelections();
}

function updateVisualizerSelections() {
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(overlay => {
            const elIndex = parseInt(overlay.dataset.elementIndex);
            overlay.classList.toggle(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE, currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex));
        });
    }
    if (elementTextListDiv) {
        elementTextListDiv.querySelectorAll('.list-group-item').forEach(item => {
            const elIndex = parseInt(item.dataset.elementIndex);
            item.classList.toggle(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE, currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex));
        });
    }
}

async function processImageAndElementsWhenReady() {
    if (!screenshotImg || !imageContainer || !elementTextListDiv || !currentManagingNodeData) {
        console.error("[MODAL_PIE] processImageAndElementsWhenReady: Thiếu DOM elements hoặc data.");
        return;
    }
    console.log("[MODAL_PIE] processImageAndElementsWhenReady: Bắt đầu xử lý.");

    if (screenshotImg.style.display !== 'block') screenshotImg.style.display = 'block';
    // Đợi một frame để trình duyệt có thể tính toán kích thước sau khi display=block
    await new Promise(resolve => requestAnimationFrame(resolve));

    console.log(`    Image natural dimensions: ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
    console.log(`    Image client dimensions (initial check): ${screenshotImg.clientWidth}x${screenshotImg.clientHeight}`);

    if (screenshotImg.naturalWidth === 0 || screenshotImg.naturalHeight === 0) {
        console.error("[MODAL_PIE] Ảnh không hợp lệ (kích thước gốc bằng 0).");
        if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2 text-center">Ảnh tải về không hợp lệ.</p>`;
        return;
    }

    let displayedWidth = screenshotImg.clientWidth;
    let displayedHeight = screenshotImg.clientHeight;
    let usingFallbackDimensions = false;

    if (displayedWidth === 0 || displayedHeight === 0) {
        console.warn("[MODAL_PIE] clientWidth/Height là 0. Thử đợi với vòng lặp setTimeout.");
        await new Promise((resolve) => {
            let attempts = 0; const maxAttempts = 60; const interval = 50; // ~3 giây
            function checkDimLoop() {
                displayedWidth = screenshotImg.clientWidth; displayedHeight = screenshotImg.clientHeight;
                console.log(`[MODAL_PIE] Wait Loop Attempt ${attempts + 1}: Client dimensions: ${displayedWidth}x${displayedHeight}`);
                if ((displayedWidth > 0 && displayedHeight > 0) || attempts >= maxAttempts) {
                    resolve();
                } else { attempts++; setTimeout(checkDimLoop, interval); }
            }
            checkDimLoop();
        });
        displayedWidth = screenshotImg.clientWidth; displayedHeight = screenshotImg.clientHeight;
        if (displayedWidth === 0 || displayedHeight === 0) {
            console.error("[MODAL_PIE] clientWidth/Height vẫn là 0 sau khi đợi. Thử fallback.");
            const cW = imageContainer.clientWidth; const cH = imageContainer.clientHeight;
            if (cW > 0 && cH > 0 && screenshotImg.naturalWidth > 0 && screenshotImg.naturalHeight > 0) {
                const imgAspect = screenshotImg.naturalWidth / screenshotImg.naturalHeight;
                const cAspect = cW / cH;
                if (imgAspect > cAspect) { displayedWidth = cW; displayedHeight = cW / imgAspect; }
                else { displayedHeight = cH; displayedWidth = cH * imgAspect; }
                usingFallbackDimensions = true;
                console.warn(`[MODAL_PIE] Fallback dimensions calculated: ${Math.floor(displayedWidth)}x${Math.floor(displayedHeight)}`);
            } else {
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
    }

    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang tải elements...</div>';
    try {
        const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(currentManagingNodeData.currentScreenId));
        const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

        if (elementsJsonResponse.success && elementsJsonResponse.elements) {
            rawElementsDataForModal = elementsJsonResponse.elements;
            const nodeOriginalWidth = currentManagingNodeData.width;
            const nodeOriginalHeight = currentManagingNodeData.height;

            if (rawElementsDataForModal.length > 0 && nodeOriginalWidth && nodeOriginalHeight) {
                drawInteractiveOverlays(
                    screenshotImg, rawElementsDataForModal, nodeOriginalWidth, nodeOriginalHeight,
                    imageContainer,
                    handleElementSelectionFromVisualizer
                );
                if (usingFallbackDimensions && imageContainer && !imageContainer.querySelector('.fallback-warning-message')) {
                    const warnMsgEl = document.createElement('p');
                    warnMsgEl.className = 'text-warning small fst-italic p-1 text-center fallback-warning-message';
                    warnMsgEl.textContent = '(Lưu ý: Overlay có thể không hoàn toàn chính xác do kích thước ảnh được ước lượng.)';
                    imageContainer.appendChild(warnMsgEl);
                }
            } else if (!nodeOriginalWidth || !nodeOriginalHeight) {
                console.warn("[MODAL_PIE] Thiếu width/height gốc của Node. Overlays có thể không chính xác.");
            }
            renderElementTextList();
        } else { throw new Error(elementsJsonResponse.error || "Không lấy được elements."); }
    } catch (error) {
        console.error("[MODAL_PIE] Lỗi tải elements hoặc vẽ overlays:", error);
        if (elementTextListDiv) elementTextListDiv.innerHTML = `<div class="list-group-item text-danger small">Lỗi tải elements: ${error.message}</div>`;
    }
    updateVisualizerSelections();
}

async function openModalWithData(nodeData) {
    if (!modalEl) getDOMElementsForManagePie();
    if (!managePieModalInstance && modalEl) managePieModalInstance = new bootstrap.Modal(modalEl);
    if (!managePieModalInstance) { console.error("Không thể khởi tạo modal instance."); return; }
    console.log("[MODAL_PIE] openModalWithData received nodeData:", JSON.stringify(nodeData)); // DEBUG

    currentManagingNodeData = { ...nodeData };
    console.log("[MODAL_PIE] currentManagingNodeData set to:", JSON.stringify(currentManagingNodeData)); // DEBUG
    currentSelectedPieConditions = [];
    rawElementsDataForModal = [];
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';
    if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
    if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';

    if (screenshotImg) { screenshotImg.src = ''; screenshotImg.style.display = 'none'; }
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE + ', p.text-danger, p.text-warning, p.text-muted, .overlay-dimension-error, .dimension-error-message, .fallback-warning-message').forEach(el => el.remove());
    }
    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang chuẩn bị...</div>';
    renderSelectedPieConditions();

    const screenshotUrlToLoad = currentManagingNodeData.screenshotFullUrl;
    let imageHasLoadedSuccessfully = false;

    const modalShownHandler = () => {
        console.log("[MODAL_PIE] Sự kiện 'shown.bs.modal' được kích hoạt.");
        if (imageHasLoadedSuccessfully) {
            console.log("[MODAL_PIE] Ảnh đã onload thành công, modal đã shown. Bắt đầu processImageAndElementsWhenReady.");
            processImageAndElementsWhenReady();
        } else if (screenshotImg && screenshotImg.src && !screenshotImg.complete) {
            console.log("[MODAL_PIE] Modal shown, nhưng ảnh có thể chưa onload hoàn toàn. Đợi onload event của ảnh.");
        } else if (screenshotImg && screenshotImg.src && screenshotImg.complete && screenshotImg.naturalWidth === 0) {
            console.log("[MODAL_PIE] Modal shown, ảnh đã onload nhưng có vẻ là ảnh lỗi (naturalWidth=0). onerror nên đã xử lý.");
        } else if (screenshotImg && screenshotImg.src && screenshotImg.complete && screenshotImg.naturalWidth > 0) {
            // Trường hợp hiếm: onload đã chạy, modal mới shown, ảnh hợp lệ
            console.log("[MODAL_PIE] Modal shown, ảnh đã onload và hợp lệ. Bắt đầu processImageAndElementsWhenReady.");
            imageHasLoadedSuccessfully = true; // Đảm bảo cờ này đúng
            processImageAndElementsWhenReady();
        } else {
            console.log("[MODAL_PIE] Modal shown, không có ảnh hợp lệ để xử lý (src có thể rỗng hoặc lỗi trước đó).");
        }
    };

    if (modalEl) {
        modalEl.removeEventListener('shown.bs.modal', modalShownHandler);
        modalEl.addEventListener('shown.bs.modal', modalShownHandler, { once: true });
    }

    if (screenshotUrlToLoad && screenshotImg) {
        screenshotImg.src = screenshotUrlToLoad;
        screenshotImg.onload = () => {
            screenshotImg.style.display = 'block';
            console.log("[MODAL_PIE] Sự kiện 'onload' của ảnh được kích hoạt:", screenshotImg.src);
            console.log(`    Kích thước gốc (natural): ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
            if (screenshotImg.naturalWidth > 0 && screenshotImg.naturalHeight > 0) {
                imageHasLoadedSuccessfully = true;
            } else {
                imageHasLoadedSuccessfully = false; // Ảnh lỗi
                console.error("[MODAL_PIE] Ảnh onload nhưng naturalWidth/Height là 0. Ảnh không hợp lệ.");
                // Xử lý lỗi hiển thị ở đây nếu onerror không bắt được
                if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2 text-center">Ảnh tải về không hợp lệ (kích thước 0x0 sau onload).</p>`;
                if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Ảnh không hợp lệ.</div>';
                return; // Không tiếp tục nếu ảnh lỗi
            }

            if (modalEl && modalEl.classList.contains('show')) {
                console.log("[MODAL_PIE] Ảnh onload, modal đã shown. Bắt đầu processImageAndElementsWhenReady (từ onload).");
                processImageAndElementsWhenReady();
            } else {
                console.log("[MODAL_PIE] Ảnh onload, nhưng modal có thể chưa 'shown'. Đợi 'shown.bs.modal'.");
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
    } else {
        if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2 text-center">Node không có URL ảnh.</p>';
        if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Không có ảnh.</div>';
    }

    // Tải conditions cũ nếu node 'defined'
    if (nodeData.nodeStatus === 'defined') {
        if (modalLabel) modalLabel.textContent = `Sửa Điều kiện PIE cho: ${nodeData.pieLogicalName || nodeData.currentScreenId}`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Lưu Conditions PIE'; mainActionBtn.className = 'btn btn-sm btn-primary'; }
        try {
            const conditionsUrl = `${APP_CONFIG.API_GET_PIE_CONDITIONS_URL}?app_name=${encodeURIComponent(nodeData.appName)}&defined_screen_id=${encodeURIComponent(nodeData.currentScreenId)}`;
            const conditionsJsonResponse = await sendApiRequest(conditionsUrl, 'GET');
            if (conditionsJsonResponse.success && conditionsJsonResponse.conditions) {
                currentSelectedPieConditions = conditionsJsonResponse.conditions.map(c => ({ ...c, internal_element_index: -1, element_identifier_display: "Điều kiện đã lưu" }));
            } else { currentSelectedPieConditions = []; console.warn("Không tải được conditions:", conditionsJsonResponse.message); }
        } catch (error) {
            console.error("Lỗi tải conditions:", error); currentSelectedPieConditions = [];
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi tải conditions. Tạo mới nếu cần.';
        }
    } else {
        if (modalLabel) modalLabel.textContent = `Chọn Điều kiện cho PIE Mới (Node: ${nodeData.currentScreenId})`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Tiếp tục Định nghĩa PIE'; mainActionBtn.className = 'btn btn-sm btn-success'; }
        currentSelectedPieConditions = [];
    }

    renderSelectedPieConditions();
    if (managePieModalInstance) managePieModalInstance.show();
}

export function initManagePieModal() {
    getDOMElementsForManagePie();
    if (!modalEl) {
        console.warn("Modal #managePieConditionsModal không được tìm thấy trong DOM khi initManagePieModal.");
        return;
    }
    if (!managePieModalInstance) {
        managePieModalInstance = new bootstrap.Modal(modalEl);
    }
    window.openManagePieConditionsModalGlobal = openModalWithData;

    if (addManualConditionBtn) {
        addManualConditionBtn.addEventListener('click', function () {
            console.log("[MODAL_PIE] Add manual condition clicked.");
            currentSelectedPieConditions.push({
                attribute: '', comparison: 'EQUALS', value: '',
                internal_element_index: -1,
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
            })).filter(c => c.attribute && c.comparison && (c.comparison === 'EXISTS' || c.comparison === 'NOT_EXISTS' || (c.value !== undefined && c.value !== null && c.value.trim() !== '')));

            if (finalConditionsToSave.some(c => !c.attribute || !c.comparison || ((c.comparison !== 'EXISTS' && c.comparison !== 'NOT_EXISTS') && (c.value === undefined || c.value === null || c.value.trim() === '')))) {
                if (errorMessagesSpan) errorMessagesSpan.textContent = 'Một số điều kiện chưa hoàn chỉnh (thiếu Thuộc tính, So sánh hoặc Giá trị).';
                this.disabled = false; this.innerHTML = (currentManagingNodeData.nodeStatus === 'defined' ? 'Lưu Conditions PIE' : 'Tiếp tục Định nghĩa PIE');
                return;
            }

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
                        if (window.fetchAndRenderTableNodesGlobal) window.fetchAndRenderTableNodesGlobal(); else location.reload();
                    } else { throw new Error(result.message || "Lỗi từ server khi cập nhật."); }
                } catch (error) {
                    console.error("Lỗi khi update PIE conditions:", error);
                    if (errorMessagesSpan) errorMessagesSpan.textContent = error.data?.message || error.message || 'Lỗi không xác định.';
                } finally {
                    this.disabled = false; this.textContent = 'Lưu Conditions PIE';
                }
            } else { // Node 'unknown'
                if (finalConditionsToSave.length === 0) {
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Vui lòng chọn ít nhất một điều kiện nhận diện hợp lệ.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }

                // ---- DEBUG POINT 1: Kiểm tra currentManagingNodeData ----
                console.log("[MODAL_PIE -> METADATA] TRƯỚC KHI GỌI openDefineNewPieMetadataModalGlobal");
                console.log("[MODAL_PIE -> METADATA] currentManagingNodeData:", JSON.stringify(currentManagingNodeData, null, 2));
                console.log("[MODAL_PIE -> METADATA] finalConditionsToSave:", JSON.stringify(finalConditionsToSave, null, 2));


                // Kiểm tra các giá trị quan trọng trong currentManagingNodeData
                if (!currentManagingNodeData || !currentManagingNodeData.nodeNeo4jId || String(currentManagingNodeData.nodeNeo4jId).trim() === '') {
                    console.error("[MODAL_PIE -> METADATA] LỖI NGHIÊM TRỌNG: nodeNeo4jId bị thiếu hoặc rỗng trong currentManagingNodeData!");
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi dữ liệu: Không tìm thấy ID của Node Neo4j. Không thể tiếp tục.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return; // Dừng lại nếu thiếu thông tin quan trọng
                }
                if (!currentManagingNodeData.currentScreenId || String(currentManagingNodeData.currentScreenId).trim() === '') {
                    console.error("[MODAL_PIE -> METADATA] LỖI NGHIÊM TRỌNG: currentScreenId bị thiếu hoặc rỗng trong currentManagingNodeData!");
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi dữ liệu: Không tìm thấy Screen ID hiện tại của Node. Không thể tiếp tục.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }
                if (!currentManagingNodeData.appName || String(currentManagingNodeData.appName).trim() === '') {
                    console.error("[MODAL_PIE -> METADATA] LỖI NGHIÊM TRỌNG: appName bị thiếu hoặc rỗng trong currentManagingNodeData!");
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi dữ liệu: Không tìm thấy App Name của Node. Không thể tiếp tục.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }


                if (managePieModalInstance) {
                    console.log("[MODAL_PIE -> METADATA] Đang ẩn modal PIE conditions...");
                    managePieModalInstance.hide(); // Ẩn modal hiện tại trước khi mở modal mới
                }

                if (typeof window.openDefineNewPieMetadataModalGlobal === 'function') {
                    console.log("[MODAL_PIE -> METADATA] Đang gọi window.openDefineNewPieMetadataModalGlobal...");
                    try {
                        window.openDefineNewPieMetadataModalGlobal(currentManagingNodeData, finalConditionsToSave);
                        console.log("[MODAL_PIE -> METADATA] Đã gọi window.openDefineNewPieMetadataModalGlobal thành công.");
                    } catch (e) {
                        console.error("[MODAL_PIE -> METADATA] Lỗi khi gọi window.openDefineNewPieMetadataModalGlobal:", e);
                        if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi mở form định nghĩa metadata.';
                    }
                } else {
                    console.error("[MODAL_PIE -> METADATA] Lỗi: Hàm window.openDefineNewPieMetadataModalGlobal không tồn tại hoặc không phải là hàm!");
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi cấu hình: Không tìm thấy hàm mở form metadata.';
                }

                // Reset nút sau khi đã gọi (hoặc cố gắng gọi) modal kia
                this.disabled = false;
                this.textContent = 'Tiếp tục Định nghĩa PIE';
            }
        });
    }
}
