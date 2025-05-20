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
            // console.log("[MODAL_PIE] Text list item clicked. Index:", index);
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
    // console.log("[MODAL_PIE] Element data for selection:", JSON.parse(JSON.stringify(elementData)));

    const existingConditionIndex = currentSelectedPieConditions.findIndex(cond => cond.internal_element_index === elementOriginalIndex);

    if (existingConditionIndex > -1) {
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
        console.log("[MODAL_PIE] Condition removed for element index:", elementOriginalIndex);
    } else {
        let newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: `Từ Elem: ${(elementData.resource_id || elementData.text_content || elementData.element_id || 'N/A').substring(0, 25)}...`,
            attribute: '',
            comparison: 'EQUALS',
            value: ''
        };
        if (elementData.resource_id) { newCondition.attribute = 'resource_id'; newCondition.value = elementData.resource_id; }
        else if (elementData.text_content) { newCondition.attribute = 'text'; newCondition.value = elementData.text_content; }
        else if (elementData.description) { newCondition.attribute = 'description'; newCondition.value = elementData.description; }
        else if (elementData.class_name) { newCondition.attribute = 'class_name'; newCondition.value = elementData.class_name; }
        else { newCondition.element_identifier_display = "Từ Elem (cần cấu hình thuộc tính)"; }
        currentSelectedPieConditions.push(newCondition);
        console.log("[MODAL_PIE] New condition added:", JSON.parse(JSON.stringify(newCondition)));
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
    // console.log("[MODAL_PIE] Visualizer selections updated.");
}

async function processImageAndElementsWhenReady() {
    if (!screenshotImg || !imageContainer || !elementTextListDiv || !currentManagingNodeData) {
        console.error("[MODAL_PIE] processImageAndElementsWhenReady: Thiếu DOM elements hoặc data.");
        return;
    }
    console.log("[MODAL_PIE] processImageAndElementsWhenReady: Bắt đầu xử lý.");

    if (screenshotImg.style.display !== 'block') screenshotImg.style.display = 'block';
    await new Promise(resolve => setTimeout(resolve, 100)); // Tăng thời gian chờ một chút

    console.log(`    Image natural dimensions: ${screenshotImg.naturalWidth}x${screenshotImg.naturalHeight}`);
    console.log(`    Image client dimensions (initial check): ${screenshotImg.clientWidth}x${screenshotImg.clientHeight}`);

    if (screenshotImg.naturalWidth === 0 || screenshotImg.naturalHeight === 0) { /* ... xử lý ảnh lỗi ... */ return; }

    let displayedWidth = screenshotImg.clientWidth;
    let displayedHeight = screenshotImg.clientHeight;
    let usingFallbackDimensions = false;

    if (displayedWidth === 0 || displayedHeight === 0) {
        console.warn("[MODAL_PIE] clientWidth/Height là 0. Thử đợi với vòng lặp setTimeout.");
        await new Promise((resolve) => {
            let attempts = 0; const maxAttempts = 60; const interval = 50; // ~3 giây
            function checkDimLoop() {
                displayedWidth = screenshotImg.clientWidth; displayedHeight = screenshotImg.clientHeight;
                // console.log(`[MODAL_PIE] Wait Loop Attempt ${attempts + 1}: Client dimensions: ${displayedWidth}x${displayedHeight}`);
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
            } else { /* ... báo lỗi không thể xác định kích thước ... */ return; }
        }
    }

    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang tải elements...</div>';
    try {
        const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(currentManagingNodeData.currentScreenId));
        const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

        if (elementsJsonResponse.success && elementsJsonResponse.elements) {
            rawElementsDataForModal = elementsJsonResponse.elements; // Gán dữ liệu elements gốc
            const nodeOriginalWidth = currentManagingNodeData.width;
            const nodeOriginalHeight = currentManagingNodeData.height;

            if (rawElementsDataForModal.length > 0 && nodeOriginalWidth && nodeOriginalHeight) {
                drawInteractiveOverlays(
                    screenshotImg,
                    rawElementsDataForModal, // Truyền mảng elements gốc
                    nodeOriginalWidth,
                    nodeOriginalHeight,
                    imageContainer,
                    handleElementSelectionFromVisualizer // Truyền thẳng hàm xử lý (nó nhận index)
                );
                if (usingFallbackDimensions && imageContainer && !imageContainer.querySelector('.fallback-warning-message')) {
                    // ... (thêm cảnh báo fallback)
                }
            } else if (!nodeOriginalWidth || !nodeOriginalHeight) {
                console.warn("[MODAL_PIE] Thiếu width/height gốc của Node. Overlays có thể không chính xác.");
            }
            renderElementTextList(); // Render danh sách text elements SAU KHI rawElementsDataForModal được gán
        } else { throw new Error(elementsJsonResponse.error || "Không lấy được elements."); }
    } catch (error) {
        console.error("[MODAL_PIE] Lỗi tải elements hoặc vẽ overlays:", error);
        if (elementTextListDiv) elementTextListDiv.innerHTML = `<div class="list-group-item text-danger small">Lỗi tải elements: ${error.message}</div>`;
    }
    updateVisualizerSelections(); // Cập nhật highlight dựa trên conditions đã có (nếu sửa PIE)
}

async function openModalWithData(nodeData) {
    if (!modalEl) getDOMElementsForManagePie();
    if (!managePieModalInstance && modalEl) managePieModalInstance = new bootstrap.Modal(modalEl);
    if (!managePieModalInstance) { console.error("Không thể khởi tạo modal instance."); return; }

    currentManagingNodeData = { ...nodeData };
    currentSelectedPieConditions = [];
    rawElementsDataForModal = []; // QUAN TRỌNG: Reset ở đây
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
            console.log("[MODAL_PIE] Modal shown, ảnh đã onload nhưng có vẻ là ảnh lỗi (naturalWidth=0).");
        } else if (screenshotImg && screenshotImg.src && screenshotImg.complete && screenshotImg.naturalWidth > 0) {
            console.log("[MODAL_PIE] Modal shown, ảnh đã onload và hợp lệ. Bắt đầu processImageAndElementsWhenReady.");
            imageHasLoadedSuccessfully = true;
            processImageAndElementsWhenReady();
        } else {
            console.log("[MODAL_PIE] Modal shown, không có ảnh hợp lệ để xử lý.");
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
                imageHasLoadedSuccessfully = false;
                console.error("[MODAL_PIE] Ảnh onload nhưng naturalWidth/Height là 0. Ảnh không hợp lệ.");
                if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2 text-center">Ảnh tải về không hợp lệ (kích thước 0x0 sau onload).</p>`;
                if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Ảnh không hợp lệ.</div>';
                return;
            }
            if (modalEl && modalEl.classList.contains('show')) {
                console.log("[MODAL_PIE] Ảnh onload, modal đã shown. Bắt đầu processImageAndElementsWhenReady (từ onload).");
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

                if (managePieModalInstance) managePieModalInstance.hide();

                if (window.openDefineNewPieMetadataModalGlobal) {

                    window.openDefineNewPieMetadataModalGlobal(currentManagingNodeData, finalConditionsToSave);

                } else { console.error("Hàm openDefineNewPieMetadataModalGlobal không tồn tại."); }

                this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';

            }

        });

    }


}
