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

// Hàm lấy các DOM element một lần khi khởi tạo module
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
        const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === index);
        if (isSelected) listItem.classList.add(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);
        listItem.addEventListener('click', (e) => { e.preventDefault(); handleElementSelectionFromVisualizer(index); });
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
        let attributeOptionsHtml = APP_CONFIG.ELEMENT_ATTRIBUTES_FOR_PIE.map(attr => `<option value="${attr.value}" ${condition.attribute === attr.value ? 'selected' : ''}>${attr.label}</option>`).join('');
        let comparisonOptionsHtml = APP_CONFIG.COMPARISON_TYPES_FOR_PIE.map(comp => `<option value="${comp.value}" ${condition.comparison === comp.value ? 'selected' : ''}>${comp.label}</option>`).join('');
        conditionDiv.innerHTML = `
            <div class="row gx-2 gy-1 align-items-center">
                <div class="col-sm-4"><select class="form-select form-select-sm condition-attribute" data-index="${index}" aria-label="Thuộc tính"><option value="">-- Thuộc tính --</option>${attributeOptionsHtml}</select></div>
                <div class="col-sm-3"><select class="form-select form-select-sm condition-comparison" data-index="${index}" aria-label="So sánh">${comparisonOptionsHtml}</select></div>
                <div class="col-sm-4"><input type="text" class="form-control form-control-sm condition-value" data-index="${index}" value="${condition.value || ''}" placeholder="Giá trị" aria-label="Giá trị" ${condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS' ? 'disabled' : ''}></div>
                <div class="col-sm-1 text-end"><button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-index="${index}" title="Xóa" aria-label="Xóa"><i class="fas fa-times"></i></button></div>
            </div>
            <div class="text-muted xsmall mt-1"><em>${condition.element_identifier_display || 'Thủ công'}</em></div>`;
        selectedConditionsListDiv.appendChild(conditionDiv);
    });
    attachListenersToSelectedConditions();
    updateVisualizerSelections();
}

function attachListenersToSelectedConditions() {
    if (!selectedConditionsListDiv) return;
    selectedConditionsListDiv.querySelectorAll('.condition-attribute').forEach(s => { s.onchange = function () { if (currentSelectedPieConditions[this.dataset.index]) currentSelectedPieConditions[this.dataset.index].attribute = this.value; }; });
    selectedConditionsListDiv.querySelectorAll('.condition-comparison').forEach(s => {
        s.onchange = function () {
            if (currentSelectedPieConditions[this.dataset.index]) {
                currentSelectedPieConditions[this.dataset.index].comparison = this.value;
                const vIn = this.closest('.row').querySelector('.condition-value');
                if (this.value === 'EXISTS' || this.value === 'NOT_EXISTS') { vIn.disabled = true; vIn.value = ''; currentSelectedPieConditions[this.dataset.index].value = ''; }
                else { vIn.disabled = false; }
            }
        };
    });
    selectedConditionsListDiv.querySelectorAll('.condition-value').forEach(i => { i.oninput = function () { if (currentSelectedPieConditions[this.dataset.index]) currentSelectedPieConditions[this.dataset.index].value = this.value.trim(); }; });
    selectedConditionsListDiv.querySelectorAll('.remove-condition-btn').forEach(b => { b.onclick = function () { currentSelectedPieConditions.splice(this.dataset.index, 1); renderSelectedPieConditions(); }; });
}

function handleElementSelectionFromVisualizer(elementOriginalIndex) {
    if (!rawElementsDataForModal || rawElementsDataForModal.length <= elementOriginalIndex || elementOriginalIndex < 0) {
        console.warn("[MODAL_MANAGE_PIE] Invalid element index or rawElementsDataForModal not ready:", elementOriginalIndex);
        return;
    }
    const elementData = rawElementsDataForModal[elementOriginalIndex];
    if (!elementData) {
        console.warn("[MODAL_MANAGE_PIE] No element data found for index:", elementOriginalIndex);
        return;
    }

    const existingConditionIndex = currentSelectedPieConditions.findIndex(cond => cond.internal_element_index === elementOriginalIndex);
    if (existingConditionIndex > -1) {
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
    } else {
        let newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: `Từ Elem: ${(elementData.resource_id || elementData.text_content || elementData.element_id || 'N/A').substring(0, 25)}...`,
            attribute: '', comparison: 'EQUALS', value: ''
        };
        if (elementData.resource_id) { newCondition.attribute = 'resource_id'; newCondition.value = elementData.resource_id; }
        else if (elementData.text_content) { newCondition.attribute = 'text'; newCondition.value = elementData.text_content; }
        else if (elementData.description) { newCondition.attribute = 'description'; newCondition.value = elementData.description; }
        else if (elementData.class_name) { newCondition.attribute = 'class_name'; newCondition.value = elementData.class_name; }
        else { newCondition.element_identifier_display = "Từ Elem (cần cấu hình)"; }
        currentSelectedPieConditions.push(newCondition);
    }
    renderSelectedPieConditions();
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

async function attemptDrawOverlays() {
    if (!screenshotImg || !imageContainer || !elementTextListDiv) {
        console.error("[MODAL_MANAGE_PIE] attemptDrawOverlays: Critical DOM elements missing.");
        return;
    }

    // Đảm bảo ảnh được hiển thị
    if (screenshotImg.style.display !== 'block') {
        screenshotImg.style.display = 'block';
    }

    // Sử dụng một promise để đợi kích thước ảnh ổn định
    const waitForImageDimensions = (imgElement, timeout = 2000) => {
        return new Promise((resolve, reject) => {
            let attempts = 0;
            const maxAttempts = Math.ceil(timeout / 50); // Thử mỗi 50ms

            const check = () => {
                if (imgElement.clientWidth > 0 && imgElement.clientHeight > 0) {
                    console.log(`[MODAL_MANAGE_PIE] Image dimensions ready: ${imgElement.clientWidth}x${imgElement.clientHeight} after ${attempts} attempts.`);
                    resolve({ width: imgElement.clientWidth, height: imgElement.clientHeight });
                } else if (attempts < maxAttempts) {
                    attempts++;
                    // console.log(`[MODAL_MANAGE_PIE] Waiting for image dimensions... Attempt ${attempts}`);
                    setTimeout(check, 50); // Thử lại sau một khoảng ngắn
                } else {
                    console.error(`[MODAL_MANAGE_PIE] Timeout waiting for image dimensions. clientWidth/Height still 0. Natural: ${imgElement.naturalWidth}x${imgElement.naturalHeight}`);
                    reject(new Error("Timeout waiting for image dimensions."));
                }
            };
            check();
        });
    };

    try {
        // Đợi cho đến khi ảnh có kích thước client hợp lệ
        await waitForImageDimensions(screenshotImg);

        console.log("[MODAL_MANAGE_PIE] Image dimensions are valid. Loading elements and drawing overlays.");
        if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Ảnh đã hiển thị, đang tải elements...</div>';

        const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(currentManagingNodeData.currentScreenId));
        const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

        if (elementsJsonResponse.success && elementsJsonResponse.elements) {
            rawElementsDataForModal = elementsJsonResponse.elements;
            const nodeOriginalWidth = currentManagingNodeData.width;
            const nodeOriginalHeight = currentManagingNodeData.height;

            if (rawElementsDataForModal.length > 0 && nodeOriginalWidth && nodeOriginalHeight) {
                drawInteractiveOverlays( // utils.js
                    screenshotImg, rawElementsDataForModal, nodeOriginalWidth, nodeOriginalHeight,
                    imageContainer,
                    (elementIndex) => { // selectionHandler for drawInteractiveOverlays
                        handleElementSelectionFromVisualizer(elementIndex);
                    }
                );
            } else if (!nodeOriginalWidth || !nodeOriginalHeight) {
                console.warn("Modal: Thiếu width/height gốc của Node. Overlays có thể không chính xác.");
                if (imageContainer && !imageContainer.querySelector('.overlay-dimension-error')) {
                    const errorMsgEl = document.createElement('p');
                    errorMsgEl.className = 'text-warning small fst-italic p-1 text-center overlay-dimension-error';
                    errorMsgEl.textContent = '(Lưu ý: Thiếu kích thước gốc từ Node, overlay có thể không chính xác.)';
                    imageContainer.appendChild(errorMsgEl);
                }
            }
            renderElementTextList();
        } else { throw new Error(elementsJsonResponse.error || "Không lấy được elements."); }
    } catch (error) {
        console.error("[MODAL_MANAGE_PIE] Error in attemptDrawOverlays:", error);
        if (elementTextListDiv) elementTextListDiv.innerHTML = `<div class="list-group-item text-danger small">Lỗi xử lý ảnh/elements: ${error.message}</div>`;
        if (imageContainer && !imageContainer.querySelector('.overlay-dimension-error')) {
            const errorMsgEl = document.createElement('p');
            errorMsgEl.className = 'text-danger small fst-italic p-1 text-center overlay-dimension-error';
            errorMsgEl.textContent = 'Lỗi hiển thị elements trên ảnh.';
            imageContainer.appendChild(errorMsgEl);
        }
    }
    updateVisualizerSelections(); // Cập nhật highlight dựa trên conditions đã có
}

// Hàm được gọi khi modal được hiển thị hoàn toàn (sự kiện 'shown.bs.modal')
function onModalShown() {
    console.log("[MODAL_MANAGE_PIE] 'shown.bs.modal' event triggered.");
    if (screenshotImg && screenshotImg.naturalWidth > 0 && screenshotImg.naturalHeight > 0) {
        console.log(`[MODAL_MANAGE_PIE] Image natural dimensions (on 'shown'): ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
        attemptDrawOverlays(); // Bắt đầu quá trình kiểm tra kích thước và vẽ
    } else if (screenshotImg && screenshotImg.src) { // Ảnh có src nhưng naturalWidth=0 (có thể đang tải hoặc lỗi)
        console.warn(`[MODAL_MANAGE_PIE] Image naturalWidth is 0 on 'shown.bs.modal', but src is set. Waiting for onload to potentially re-trigger.`);
        // Nếu onload chưa chạy, nó sẽ set display:block và có thể gọi lại attemptDrawOverlays nếu cần.
        // Nếu onload đã chạy và naturalWidth=0, đó là lỗi ảnh.
    } else {
        console.log("[MODAL_MANAGE_PIE] No valid image src or natural dimensions on 'shown.bs.modal'.");
    }
}

async function openModalWithData(nodeData) {
    if (!modalEl) getDOMElementsForManagePie();
    if (!managePieModalInstance && modalEl) managePieModalInstance = new bootstrap.Modal(modalEl);
    if (!managePieModalInstance) { console.error("Không thể khởi tạo modal."); return; }

    currentManagingNodeData = { ...nodeData };
    currentSelectedPieConditions = [];
    rawElementsDataForModal = [];
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';
    if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
    if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';

    if (screenshotImg) { screenshotImg.src = ''; screenshotImg.style.display = 'none'; }
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE + ', p.text-danger, p.text-warning, p.text-muted, .overlay-dimension-error').forEach(el => el.remove());
    }
    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang chuẩn bị...</div>';
    renderSelectedPieConditions();

    const screenshotUrlToLoad = currentManagingNodeData.screenshotFullUrl;

    if (modalEl) {
        modalEl.removeEventListener('shown.bs.modal', onModalShown); // Xóa listener cũ
        modalEl.addEventListener('shown.bs.modal', onModalShown, { once: true }); // Gắn mới
    }

    if (screenshotUrlToLoad && screenshotImg) {
        screenshotImg.src = screenshotUrlToLoad;

        screenshotImg.onload = () => {
            screenshotImg.style.display = 'block';
            console.log("[MODAL_MANAGE_PIE] Image data loaded (onload event):", screenshotImg.src);
            console.log(`[MODAL_MANAGE_PIE] Natural dimensions (onload): ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
            // Nếu modal đã hiển thị, thử vẽ luôn. Nếu chưa, 'shown.bs.modal' sẽ xử lý.
            if (modalEl && modalEl.classList.contains('show')) {
                console.log("[MODAL_MANAGE_PIE] Modal is already shown, attempting to draw overlays from onload.");
                attemptDrawOverlays();
            }
        };
        screenshotImg.onerror = () => {
            console.error("[MODAL_MANAGE_PIE] Error loading image:", screenshotImg.src);
            const filenameForError = currentManagingNodeData.screenshotFilename || 'không rõ tên file';
            const errorMessageHTML = `<p class="text-danger p-2 text-center">Lỗi tải ảnh: ${filenameForError}.<br><small>URL: ${screenshotImg.src || 'Không có URL'}</small></p>`;
            if (imageContainer) imageContainer.innerHTML = errorMessageHTML;
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Lỗi tải ảnh, không thể hiển thị elements.</div>';
        };
    } else {
        if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2 text-center">Node không có thông tin ảnh (URL không có).</p>';
        if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Không thể hiển thị elements trực quan.</div>';
    }

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
        console.warn("Modal #managePieConditionsModal không tìm thấy trong DOM khi initManagePieModal.");
        return;
    }
    if (!managePieModalInstance) {
        managePieModalInstance = new bootstrap.Modal(modalEl);
    }
    window.openManagePieConditionsModalGlobal = openModalWithData;

    if (addManualConditionBtn) {
        addManualConditionBtn.addEventListener('click', function () {
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
                if (managePieModalInstance) managePieModalInstance.hide();
                if (window.openDefineNewPieMetadataModalGlobal) {
                    window.openDefineNewPieMetadataModalGlobal(currentManagingNodeData, finalConditionsToSave);
                } else { console.error("Hàm openDefineNewPieMetadataModalGlobal không tồn tại."); }
                this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
            }
        });
    }
}
