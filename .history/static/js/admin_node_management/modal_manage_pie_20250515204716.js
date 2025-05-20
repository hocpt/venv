// static/js/admin_node_management/modal_manage_pie.js
import { APP_CONFIG } from './config.js';
import { sendApiRequest, drawInteractiveOverlays } from './utils.js';

// Khai báo biến ở phạm vi module để lưu trữ instance và trạng thái
let managePieModalInstance = null;
let currentManagingNodeData = {}; // Dữ liệu của Node đang được xử lý
let currentSelectedPieConditions = []; // Mảng các object condition đang được tạo/sửa
let rawElementsDataForModal = []; // Mảng elements gốc từ API cho Node hiện tại

// DOM Elements cho modal này (sẽ được gán trong initManagePieModal)
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

        listItem.addEventListener('click', function (e) {
            e.preventDefault();
            handleElementSelectionFromVisualizer(index); // Chỉ cần truyền index
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

function handleElementSelectionFromVisualizer(elementOriginalIndex) {
    // clickedDomElementContext không còn cần thiết nếu chỉ dựa vào index
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

    if (existingConditionIndex > -1) {
        currentSelectedPieConditions.splice(existingConditionIndex, 1);
    } else {
        let newCondition = {
            internal_element_index: elementOriginalIndex,
            element_identifier_display: `Từ Elem: ${(elementData.resource_id || elementData.text_content || elementData.element_id || 'N/A').substring(0, 25)}...`,
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
        } else {
            // Gán tạm một thuộc tính nếu không có gì rõ ràng, để người dùng tự sửa
            newCondition.attribute = 'xpath'; // Hoặc một thuộc tính khác
            newCondition.element_identifier_display = `Từ Elem (cần cấu hình thuộc tính)`;
            console.warn("Element không có thuộc tính ưu tiên, tạo condition rỗng:", elementData);
        }
        currentSelectedPieConditions.push(newCondition);
    }
    renderSelectedPieConditions();
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

// Hàm này sẽ được gọi từ table_handler.js qua window.openManagePieConditionsModalGlobal
async function openModal(nodeData) {
    if (!modalEl) { // Kiểm tra lại modalEl phòng trường hợp init chưa chạy hoặc lỗi
        console.error("Modal #managePieConditionsModal element not found. Attempting to re-init.");
        getDOMElementsForManagePie(); // Thử lấy lại
        if (!modalEl) {
            alert("Lỗi giao diện: Modal quản lý PIE không thể khởi tạo.");
            return;
        }
        managePieModalInstance = new bootstrap.Modal(modalEl); // Khởi tạo nếu chưa có
    }
    if (!managePieModalInstance) { // Nếu vẫn không có instance
        console.error("Không thể tạo Bootstrap Modal instance cho #managePieConditionsModal.");
        alert("Lỗi giao diện: Không thể mở modal quản lý PIE.");
        return;
    }

    currentManagingNodeData = { ...nodeData };
    currentSelectedPieConditions = [];
    rawElementsDataForModal = [];
    if (errorMessagesSpan) errorMessagesSpan.textContent = '';

    if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
    if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';

    if (screenshotImg) { screenshotImg.src = ''; screenshotImg.style.display = 'none'; }
    if (imageContainer) {
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());
        const existingMessages = imageContainer.querySelectorAll('p.text-danger, p.text-warning, p.text-muted');
        existingMessages.forEach(p => p.remove());
    }
    if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang chuẩn bị...</div>';

    // Phải gọi renderSelectedPieConditions để reset Phần 3 và cập nhật visualizer (bỏ hết highlight)
    renderSelectedPieConditions();

    // SỬ DỤNG screenshotFullUrl đã được backend tạo
    const screenshotUrlToLoad = currentManagingNodeData.screenshotFullUrl;

    if (screenshotUrlToLoad && screenshotImg) {
        screenshotImg.src = screenshotUrlToLoad;
        screenshotImg.style.display = 'block';

        screenshotImg.onload = async () => {
            console.log("Modal image loaded successfully:", screenshotImg.src);
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Đang tải elements...</div>';

            try {
                const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(nodeData.currentScreenId));
                const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET');

                if (elementsJsonResponse.success && elementsJsonResponse.elements) {
                    rawElementsDataForModal = elementsJsonResponse.elements;
                    const nodeWidth = currentManagingNodeData.width;
                    const nodeHeight = currentManagingNodeData.height;

                    if (screenshotImg.clientWidth > 0 && screenshotImg.clientHeight > 0) { // Đảm bảo ảnh đã render kích thước
                        if (nodeWidth && nodeHeight) {
                            drawInteractiveOverlays(
                                screenshotImg,
                                rawElementsDataForModal,
                                nodeWidth,
                                nodeHeight,
                                imageContainer,
                                currentSelectedPieConditions,
                                (elDataFromOverlay, clickedOverlayDOM) => { // selectionHandler
                                    // Tìm index của elDataFromOverlay trong rawElementsDataForModal
                                    // Vì elDataFromOverlay chính là một phần tử của rawElementsDataForModal
                                    const originalIndex = rawElementsDataForModal.indexOf(elDataFromOverlay);
                                    if (originalIndex !== -1) {
                                        handleElementSelectionFromVisualizer(originalIndex); // Chỉ cần index
                                    } else {
                                        console.warn("Không tìm thấy element gốc cho overlay được click", elDataFromOverlay);
                                    }
                                }
                            );
                        } else {
                            console.warn("Modal: Thiếu width/height gốc của Node, overlay có thể không chính xác.");
                            if (imageContainer && imageContainer.innerHTML.indexOf('Lỗi tải ảnh') === -1) {
                                const errorMsgEl = document.createElement('p');
                                errorMsgEl.className = 'text-warning small fst-italic p-1 text-center';
                                errorMsgEl.textContent = '(Lưu ý: Không có kích thước gốc từ Node, overlay có thể không hiển thị hoặc không chính xác.)';
                                imageContainer.appendChild(errorMsgEl);
                            }
                        }
                    } else {
                        console.warn("Modal image clientWidth/Height is 0, cannot draw overlays yet.");
                    }
                    renderElementTextList(); // Render danh sách text elements
                } else {
                    throw new Error(elementsJsonResponse.error || "Không lấy được elements cho modal.");
                }
            } catch (error) {
                console.error("Lỗi tải elements cho modal:", error);
                if (elementTextListDiv) elementTextListDiv.innerHTML = `<div class="list-group-item text-danger small">Lỗi tải elements: ${error.message}</div>`;
            }
        };
        screenshotImg.onerror = () => {
            console.error("Modal manage PIE: Lỗi tải ảnh từ URL:", screenshotImg.src);
            const filenameForError = currentManagingNodeData.screenshotFilename || 'tên file không xác định';
            const errorMessageHTML = `<p class="text-danger p-2 text-center">Lỗi tải ảnh: ${filenameForError}.<br><small>URL: ${screenshotImg.src || 'Không có URL'}</small></p>`;
            if (imageContainer) imageContainer.innerHTML = errorMessageHTML;
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Lỗi tải ảnh, không thể hiển thị elements.</div>';
        };
    } else {
        if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2 text-center">Node không có thông tin ảnh (URL không có).</p>';
        if (elementTextListDiv) elementTextListDiv.innerHTML = '<div class="list-group-item text-muted small">Không thể hiển thị elements trực quan.</div>';
    }

    // Tải conditions cũ nếu node 'defined'
    if (nodeData.nodeStatus === 'defined') {
        if (modalLabel) modalLabel.textContent = `Sửa Điều kiện PIE cho: ${nodeData.pieLogicalName || nodeData.currentScreenId}`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Lưu Conditions PIE'; mainActionBtn.className = 'btn btn-sm btn-primary'; }

        try {
            const conditionsUrl = `${APP_CONFIG.API_GET_PIE_CONDITIONS_URL}?app_name=${encodeURIComponent(nodeData.appName)}&defined_screen_id=${encodeURIComponent(nodeData.currentScreenId)}`;
            const conditionsJsonResponse = await sendApiRequest(conditionsUrl, 'GET');
            if (conditionsJsonResponse.success && conditionsJsonResponse.conditions) {
                currentSelectedPieConditions = conditionsJsonResponse.conditions.map(c => ({
                    ...c,
                    internal_element_index: -1, // Khởi tạo, sẽ được cập nhật nếu khớp
                    element_identifier_display: "Điều kiện đã lưu"
                }));
            } else {
                currentSelectedPieConditions = [];
                console.warn("Không tải được conditions hiện tại cho PIE (defined):", conditionsJsonResponse.message);
            }
        } catch (error) {
            console.error("Lỗi tải conditions cho PIE (defined):", error);
            currentSelectedPieConditions = [];
            if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi tải conditions hiện tại. Bạn có thể tạo mới từ đầu.';
        }
    } else { // 'unknown' hoặc 'provisional_unknown'
        if (modalLabel) modalLabel.textContent = `Chọn Điều kiện cho PIE Mới (Node: ${nodeData.currentScreenId})`;
        if (mainActionBtn) { mainActionBtn.textContent = 'Tiếp tục Định nghĩa PIE'; mainActionBtn.className = 'btn btn-sm btn-success'; }
        currentSelectedPieConditions = [];
    }

    renderSelectedPieConditions(); // Render Phần 3 và cập nhật visualizer
    if (managePieModalInstance) managePieModalInstance.show(); else console.error("managePieModalInstance is null when trying to show.");
}


export function initManagePieModal() {
    getDOMElementsForManagePie();
    if (!modalEl) {
        console.warn("Modal #managePieConditionsModal không được tìm thấy trong DOM khi initManagePieModal.");
        return;
    }
    // Khởi tạo Bootstrap modal instance nếu chưa có
    if (!managePieModalInstance) {
        managePieModalInstance = new bootstrap.Modal(modalEl);
    }

    // Gán hàm mở modal vào global scope để các module khác gọi
    window.openManagePieConditionsModalGlobal = openModal;

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


            if (finalConditionsToSave.some(c => !c.attribute || !c.comparison || ((c.comparison !== 'EXISTS' && c.comparison !== 'NOT_EXISTS') && !c.value))) {
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
                    }); // sendApiRequest đã bao gồm CSRF
                    if (result.success) {
                        alert("Cập nhật điều kiện PIE thành công!");
                        if (managePieModalInstance) managePieModalInstance.hide();
                        if (window.fetchAndRenderTableNodes) window.fetchAndRenderTableNodes(); else location.reload();
                    } else { throw new Error(result.message || "Lỗi từ server khi cập nhật."); }
                } catch (error) {
                    console.error("Lỗi khi update PIE conditions:", error);
                    if (errorMessagesSpan) errorMessagesSpan.textContent = error.data?.message || error.message || 'Lỗi không xác định.';
                } finally {
                    this.disabled = false; this.textContent = 'Lưu Conditions PIE';
                }
            } else { // Node 'unknown' -> chuyển sang modal metadata
                if (finalConditionsToSave.length === 0) {
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Vui lòng chọn ít nhất một điều kiện nhận diện hợp lệ.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }
                if (managePieModalInstance) managePieModalInstance.hide();
                // Gọi hàm global để mở modal metadata
                if (window.openDefineNewPieMetadataModalGlobal) {
                    window.openDefineNewPieMetadataModalGlobal(currentManagingNodeData, finalConditionsToSave);
                } else { console.error("Hàm openDefineNewPieMetadataModalGlobal không tồn tại."); }
                this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
            }
        });
    }
}