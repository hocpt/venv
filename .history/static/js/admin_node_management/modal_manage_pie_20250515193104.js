// static/js/admin_node_management/modal_manage_pie.js
// Cần import sendApiRequest, drawInteractiveOverlays từ utils.js nếu dùng ES Modules
// import { sendApiRequest, drawInteractiveOverlays } from './utils.js';
// import { APP_CONFIG } from './config.js'; // Hoặc truy cập window.APP_CONFIG

function initManagePieModal() {
    const modalEl = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_MODAL);
    if (!modalEl) {
        console.error("Modal #managePieConditionsModal không tìm thấy trong DOM.");
        return;
    }
    const modalInstance = new bootstrap.Modal(modalEl);

    // DOM elements của modal
    const currentScreenIdDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_CURRENT_SCREEN_ID);
    const currentAppNameDisplay = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_CURRENT_APP_NAME);
    const modalLabel = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_LABEL);
    const imageContainer = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_IMAGE_CONTAINER);
    const screenshotImg = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_SCREENSHOT);
    const elementTextListDiv = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_ELEMENT_TEXT_LIST);
    const selectedConditionsListDiv = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_SELECTED_CONDITIONS_LIST);
    const addManualConditionBtn = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_ADD_MANUAL_BTN);
    const mainActionBtn = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_MAIN_ACTION_BTN);
    const errorMessagesSpan = document.getElementById(APP_CONFIG.ELEMENT_IDS.MANAGE_PIE_ERROR_MESSAGES);

    let currentManagingNodeData = {}; // Dữ liệu của Node đang được xử lý (screenId, appName, status, etc.)
    let currentSelectedPieConditions = []; // Mảng các object condition đang được tạo/sửa
    let rawElementsDataForModal = []; // Mảng elements gốc từ API cho Node hiện tại

    // --- Hàm render danh sách text elements (Phần 2) ---
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
            listItem.className = 'list-group-item list-group-item-action';
            listItem.dataset.elementIndex = index; // Lưu index để lấy lại elData

            let displayText = `<strong>${elData.resource_id || elData.element_id || 'Element'}</strong>`;
            if (elData.text_content) {
                displayText += `<br><small class="text-muted">Text: ${elData.text_content.substring(0, 40)}${elData.text_content.length > 40 ? '...' : ''}</small>`;
            }
            if (elData.class_name) {
                displayText += `<br><small class="text-muted">Class: ${elData.class_name.replace('android.widget.', '')}</small>`;
            }
            listItem.innerHTML = displayText;

            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === index);
            if (isSelected) {
                listItem.classList.add(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);
            }

            listItem.addEventListener('click', function (e) {
                e.preventDefault();
                handleElementSelectionFromVisualizer(index, this); // Truyền index
            });
            elementTextListDiv.appendChild(listItem);
        });
    }

    // --- Hàm render danh sách conditions đã chọn (Phần 3) ---
    function renderSelectedPieConditions() {
        if (!selectedConditionsListDiv) return;
        selectedConditionsListDiv.innerHTML = '';

        if (currentSelectedPieConditions.length === 0) {
            selectedConditionsListDiv.innerHTML = '<p class="text-muted small p-2 initial-prompt">Click element trên ảnh/list hoặc "Thêm thủ công".</p>';
            updateVisualizerSelections(); // Vẫn cần cập nhật visualizer
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
                    <div class="col-md-4">
                        <select class="form-select form-select-sm condition-attribute" data-index="${index}">
                            <option value="">-- Thuộc tính --</option>
                            ${attributeOptionsHtml}
                        </select>
                    </div>
                    <div class="col-md-3">
                        <select class="form-select form-select-sm condition-comparison" data-index="${index}">
                            ${comparisonOptionsHtml}
                        </select>
                    </div>
                    <div class="col-md-4">
                        <input type="text" class="form-control form-control-sm condition-value" data-index="${index}"
                               value="${condition.value || ''}" placeholder="Giá trị"
                               ${condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS' ? 'disabled' : ''}>
                    </div>
                    <div class="col-md-1 text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-index="${index}" title="Xóa điều kiện này">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
                <div class="text-muted xsmall mt-1"><em>${condition.element_identifier_display || 'Điều kiện thủ công'}</em></div>
            `;
            selectedConditionsListDiv.appendChild(conditionDiv);
        });

        attachListenersToSelectedConditions();
        updateVisualizerSelections(); // Cập nhật lại highlight trên visualizer
    }

    function attachListenersToSelectedConditions() {
        selectedConditionsListDiv.querySelectorAll('.condition-attribute').forEach(select => {
            select.onchange = function () {
                const index = parseInt(this.dataset.index);
                currentSelectedPieConditions[index].attribute = this.value;
            };
        });
        selectedConditionsListDiv.querySelectorAll('.condition-comparison').forEach(select => {
            select.onchange = function () {
                const index = parseInt(this.dataset.index);
                currentSelectedPieConditions[index].comparison = this.value;
                const valueInput = this.closest('.row').querySelector('.condition-value');
                if (this.value === 'EXISTS' || this.value === 'NOT_EXISTS') {
                    valueInput.disabled = true;
                    valueInput.value = '';
                    currentSelectedPieConditions[index].value = '';
                } else {
                    valueInput.disabled = false;
                }
            };
        });
        selectedConditionsListDiv.querySelectorAll('.condition-value').forEach(input => {
            input.oninput = function () {
                const index = parseInt(this.dataset.index);
                currentSelectedPieConditions[index].value = this.value.trim();
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

    // --- Xử lý chọn element từ Visualizer (Ảnh hoặc List Text) ---
    function handleElementSelectionFromVisualizer(elementIndexOrData, clickedDomElement) {
        let elementData;
        let elementOriginalIndex;

        if (typeof elementIndexOrData === 'number') { // Nếu truyền vào là index
            elementOriginalIndex = elementIndexOrData;
            if (rawElementsDataForModal.length <= elementOriginalIndex) return;
            elementData = rawElementsDataForModal[elementOriginalIndex];
        } else { // Nếu truyền vào là object elementData (ví dụ từ overlay đã có data)
            elementData = elementIndexOrData;
            // Tìm index của element này trong rawElementsDataForModal để đồng bộ highlight
            elementOriginalIndex = rawElementsDataForModal.findIndex(el =>
                (el.resource_id && el.resource_id === elementData.resource_id) ||
                (el.element_id && el.element_id === elementData.element_id) ||
                (el.text_content === elementData.text_content && el.class_name === elementData.class_name) // Fallback yếu hơn
            );
        }

        if (!elementData) return;

        const existingConditionIndex = currentSelectedPieConditions.findIndex(cond => cond.internal_element_index === elementOriginalIndex && elementOriginalIndex !== -1);

        if (existingConditionIndex > -1) {
            currentSelectedPieConditions.splice(existingConditionIndex, 1);
        } else {
            let newCondition = {
                internal_element_index: elementOriginalIndex,
                element_identifier_display: `Từ Elem ID: ${elementData.resource_id || elementData.element_id || 'N/A'}`,
                attribute: '',
                comparison: 'EQUALS',
                value: ''
            };
            if (elementData.resource_id) {
                newCondition.attribute = 'resource_id';
                newCondition.value = elementData.resource_id;
            } else if (elementData.text_content) {
                newCondition.attribute = 'text';
                newCondition.value = elementData.text_content;
                newCondition.element_identifier_display = `Từ Elem Text: "${elementData.text_content.substring(0, 15)}..."`;
            } else if (elementData.description) { // Content-desc
                newCondition.attribute = 'description';
                newCondition.value = elementData.description;
                newCondition.element_identifier_display = `Từ Elem Desc: "${elementData.description.substring(0, 15)}..."`;
            } else if (elementData.class_name) {
                newCondition.attribute = 'class_name';
                newCondition.value = elementData.class_name;
                newCondition.element_identifier_display = `Từ Elem Class: ${elementData.class_name}`;
            } else {
                // Không có thuộc tính phù hợp để tự động tạo condition, nhưng vẫn có thể thêm thủ công nếu muốn
                // Hoặc là không thêm gì cả. Hiện tại: không thêm.
                return;
            }
            currentSelectedPieConditions.push(newCondition);
        }
        renderSelectedPieConditions(); // Điều này sẽ gọi updateVisualizerSelections
    }

    // --- Cập nhật highlight trên Visualizer ---
    function updateVisualizerSelections() {
        // Overlays trên ảnh
        imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(overlay => {
            const elIndex = parseInt(overlay.dataset.elementIndex);
            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex);
            if (isSelected) {
                overlay.classList.add(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);
            } else {
                overlay.classList.remove(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);
            }
        });
        // Items trong danh sách text
        elementTextListDiv.querySelectorAll('.list-group-item').forEach(item => {
            const elIndex = parseInt(item.dataset.elementIndex);
            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex);
            if (isSelected) {
                item.classList.add(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);
            } else {
                item.classList.remove(APP_CONFIG.CSS_CLASSES.SELECTED_FOR_PIE);
            }
        });
    }

    // --- Hàm chính để mở và chuẩn bị modal ---
    async function openManagePieConditionsModal(nodeData) {
        currentManagingNodeData = { ...nodeData }; // Sao chép để tránh thay đổi data gốc ngoài ý muốn
        currentSelectedPieConditions = [];
        rawElementsDataForModal = [];
        if (errorMessagesSpan) errorMessagesSpan.textContent = '';

        if (currentScreenIdDisplay) currentScreenIdDisplay.textContent = nodeData.currentScreenId || 'N/A';
        if (currentAppNameDisplay) currentAppNameDisplay.textContent = nodeData.appName || 'N/A';

        // Reset UI
        if (screenshotImg) screenshotImg.src = '';
        if (imageContainer) imageContainer.querySelectorAll('.' + APP_CONFIG.CSS_CLASSES.ELEMENT_OVERLAY_INTERACTIVE).forEach(ov => ov.remove());
        if (elementTextListDiv) elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Đang tải...</p>';

        // Tải ảnh và elements
        let screenshotPath = '';
        if (nodeData.screenshotFilename && nodeData.appName) {
            screenshotPath = `${APP_CONFIG.SCREENSHOTS_BASE_URL}${nodeData.appName}/${nodeData.screenshotFilename}`;
        }

        if (screenshotPath && screenshotImg) {
            screenshotImg.src = screenshotPath;
            screenshotImg.onload = async () => {
                try {
                    const elementsUrl = APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(nodeData.currentScreenId));
                    const elementsJsonResponse = await sendApiRequest(elementsUrl, 'GET'); // Dùng sendApiRequest

                    if (elementsJsonResponse.success && elementsJsonResponse.elements) {
                        rawElementsDataForModal = elementsJsonResponse.elements;
                        // Gọi hàm vẽ overlay đã được truyền selectionHandler
                        drawInteractiveOverlays(screenshotImg, rawElementsDataForModal, nodeData.width, nodeData.height, imageContainer, currentSelectedPieConditions, (elData, clickedOverlay) => {
                            const elIndex = rawElementsDataForModal.findIndex(rawEl =>
                                (rawEl.resource_id && rawEl.resource_id === elData.resource_id) ||
                                (rawEl.element_id && rawEl.element_id === elData.element_id) ||
                                (rawEl.text_content === elData.text_content && rawEl.class_name === elData.class_name)
                            );
                            if (elIndex !== -1) {
                                handleElementSelectionFromVisualizer(elIndex, clickedOverlay);
                            }
                        });
                        renderElementTextList(rawElementsDataForModal);
                    } else {
                        throw new Error(elementsJsonResponse.error || "Không lấy được elements cho modal.");
                    }
                } catch (error) {
                    console.error("Lỗi tải elements cho modal quản lý PIE:", error);
                    if (elementTextListDiv) elementTextListDiv.innerHTML = `<p class="text-danger small p-2">Lỗi tải elements: ${error.message}</p>`;
                }
            };
            screenshotImg.onerror = () => {
                console.error("Lỗi tải ảnh cho modal:", screenshotImg.src);
                if (imageContainer) imageContainer.innerHTML = `<p class="text-danger p-2">Lỗi tải ảnh: ${nodeData.screenshotFilename || 'Không có ảnh'}</p>`;
                if (elementTextListDiv) elementTextListDiv.innerHTML = `<p class="text-muted small p-2">Không có ảnh, không thể hiển thị elements trực quan.</p>`;
            };
        } else {
            if (imageContainer) imageContainer.innerHTML = '<p class="text-muted p-2">Node không có ảnh chụp màn hình.</p>';
            if (elementTextListDiv) elementTextListDiv.innerHTML = '<p class="text-muted small p-2">Không thể hiển thị elements trực quan.</p>';
        }

        // Xử lý nút và tiêu đề dựa trên status
        if (nodeData.nodeStatus === 'defined') {
            if (modalLabel) modalLabel.textContent = `Sửa Điều kiện PIE cho: ${nodeData.pieLogicalName || nodeData.currentScreenId}`;
            if (mainActionBtn) {
                mainActionBtn.textContent = 'Lưu Conditions PIE';
                mainActionBtn.className = 'btn btn-sm btn-primary';
            }
            try {
                const conditionsUrl = `${APP_CONFIG.API_GET_PIE_CONDITIONS_URL}?app_name=${encodeURIComponent(nodeData.appName)}&defined_screen_id=${encodeURIComponent(nodeData.currentScreenId)}`;
                const conditionsJsonResponse = await sendApiRequest(conditionsUrl, 'GET'); // Dùng sendApiRequest

                if (conditionsJsonResponse.success && conditionsJsonResponse.conditions) {
                    // Gán internal_element_index = -1 vì chúng ta chưa link với visualizer ở bước này
                    // Việc link sẽ xảy ra khi updateVisualizerSelections được gọi sau khi rawElementsDataForModal được tải
                    currentSelectedPieConditions = conditionsJsonResponse.conditions.map(c => ({ ...c, internal_element_index: -1, element_identifier_display: `Điều kiện đã lưu` }));
                } else {
                    currentSelectedPieConditions = [];
                    console.warn("Không tải được conditions hiện tại cho PIE defined:", conditionsJsonResponse.message);
                }
            } catch (error) {
                console.error("Lỗi tải conditions hiện tại cho PIE defined:", error);
                currentSelectedPieConditions = [];
                if (errorMessagesSpan) errorMessagesSpan.textContent = 'Lỗi tải conditions hiện tại. Bạn có thể tạo mới từ đầu.';
            }
        } else { // 'unknown' or 'provisional_unknown'
            if (modalLabel) modalLabel.textContent = `Chọn Điều kiện cho PIE Mới (Node: ${nodeData.currentScreenId})`;
            if (mainActionBtn) {
                mainActionBtn.textContent = 'Tiếp tục Định nghĩa PIE';
                mainActionBtn.className = 'btn btn-sm btn-success';
            }
            currentSelectedPieConditions = [];
        }

        renderSelectedPieConditions(); // Render Phần 3 (sẽ tự gọi updateVisualizerSelections)
        modalInstance.show();
    }

    // --- Gắn sự kiện cho nút "Thêm điều kiện thủ công" ---
    if (addManualConditionBtn) {
        addManualConditionBtn.addEventListener('click', function () {
            currentSelectedPieConditions.push({
                attribute: 'text', // Mặc định
                comparison: 'EQUALS', // Mặc định
                value: '',
                internal_element_index: -1, // Đánh dấu là thủ công / chưa link
                element_identifier_display: 'Điều kiện thủ công mới'
            });
            renderSelectedPieConditions();
        });
    }

    // --- Xử lý nút hành động chính của modal ---
    if (mainActionBtn) {
        mainActionBtn.addEventListener('click', async function () {
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xử lý...';
            if (errorMessagesSpan) errorMessagesSpan.textContent = '';

            // Chỉ lấy các trường cần thiết cho backend
            const finalConditionsToSave = currentSelectedPieConditions.map(cond => ({
                attribute: cond.attribute,
                comparison: cond.comparison,
                value: cond.value
            }));

            if (currentManagingNodeData.nodeStatus === 'defined') {
                const definedPieIdToUpdate = currentManagingNodeData.currentScreenId;
                const updateUrl = `${APP_CONFIG.API_UPDATE_PIE_CONDITIONS_BASE_URL}/${encodeURIComponent(definedPieIdToUpdate)}/update_conditions`;

                try {
                    const result = await sendApiRequest(updateUrl, 'POST', {
                        app_name: currentManagingNodeData.appName,
                        new_conditions_list: finalConditionsToSave
                    }); // Dùng sendApiRequest

                    if (result.success) {
                        alert("Cập nhật điều kiện PIE thành công!");
                        modalInstance.hide();
                        // Gọi hàm tải lại bảng từ table_handler.js (nếu đã tách file)
                        if (window.fetchAndRenderTableNodes) window.fetchAndRenderTableNodes(); else location.reload();
                    } else {
                        throw new Error(result.message || "Cập nhật thất bại từ server.");
                    }
                } catch (error) {
                    console.error("Lỗi khi update PIE conditions:", error);
                    if (errorMessagesSpan) errorMessagesSpan.textContent = error.message || 'Lỗi không xác định.';
                } finally {
                    this.disabled = false;
                    this.textContent = 'Lưu Conditions PIE';
                }
            } else { // Node 'unknown' -> chuyển sang modal metadata
                if (finalConditionsToSave.length === 0) {
                    if (errorMessagesSpan) errorMessagesSpan.textContent = 'Vui lòng chọn ít nhất một điều kiện nhận diện.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE';
                    return;
                }
                modalInstance.hide();
                // Gọi hàm mở modal metadata từ modal_define_metadata.js
                if (window.openDefineNewPieMetadataModal) {
                    window.openDefineNewPieMetadataModal(currentManagingNodeData, finalConditionsToSave);
                } else {
                    console.error("Hàm openDefineNewPieMetadataModal không tồn tại.");
                }
                this.disabled = false; // Reset nút sau khi ẩn modal
                this.textContent = 'Tiếp tục Định nghĩa PIE';
            }
        });
    }
    // Export hàm để main.js hoặc table_handler.js có thể gọi (nếu dùng module)
    // Hoặc đặt nó vào global scope (window.openManagePieConditionsModal = openManagePieConditionsModal;)
    window.openManagePieConditionsModal = openManagePieConditionsModal;
}
// Gọi hàm khởi tạo khi DOM sẵn sàng (nếu không dùng main.js riêng)
// initManagePieModal();