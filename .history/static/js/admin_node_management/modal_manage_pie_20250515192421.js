// ===================================================================================
// DOMContentLoaded - KHỞI TẠO CHÍNH
// ===================================================================================
document.addEventListener('DOMContentLoaded', function () {
    // --- Elements của bảng chính và bộ lọc ---
    const nodesTableBody = document.getElementById('nodesTableBody');
    const filterForm = document.getElementById('nodeFilterForm');
    const appNameFilterSelect = document.getElementById('app_name_filter_select_node');
    const statusFilterSelect = document.getElementById('filter_status_select');
    const paginationContainer = document.getElementById('nodeManagementPagination');

    // --- Modal: #managePieConditionsModal ---
    const managePieModalEl = document.getElementById('managePieConditionsModal');
    const managePieModalInstance = managePieModalEl ? new bootstrap.Modal(managePieModalEl) : null;
    const managePie_currentScreenIdDisplay = document.getElementById('managePie_currentScreenIdDisplay');
    const managePie_currentAppNameDisplay = document.getElementById('managePie_currentAppNameDisplay');
    const managePie_modalLabel = document.getElementById('managePieConditionsModalLabel');

    const pieCondImageContainer = document.getElementById('pieConditionsImageContainer');
    const pieCondScreenshot = document.getElementById('pieConditionsScreenshot');
    const pieCondElementTextList = document.getElementById('pieConditionsElementTextList');
    const pieCondSelectedConditionsList = document.getElementById('pieConditionsSelectedConditionsList');
    const pieCond_addManualConditionBtn = document.getElementById('pieConditions_addManualConditionBtn');
    const managePie_mainActionBtn = document.getElementById('managePieConditions_mainActionBtn');
    const managePie_errorMessages = document.getElementById('managePieConditions_errorMessages');

    let currentManagingNodeData = {};
    let currentSelectedPieConditions = [];
    let rawElementsDataForModal = []; // Lưu trữ elements gốc lấy từ API cho modal hiện tại


    // --- Modal: #defineNewPieMetadataModal ---
    const defineMetadataModalEl = document.getElementById('defineNewPieMetadataModal');
    const defineMetadataModalInstance = defineMetadataModalEl ? new bootstrap.Modal(defineMetadataModalEl) : null;
    const defineMetadataForm = document.getElementById('defineNewPieMetadataForm');
    const metadata_unknownNodeNeo4jIdInput = document.getElementById('metadata_unknownNodeNeo4jId');
    const metadata_currentUnknownScreenIdInput = document.getElementById('metadata_currentUnknownScreenId');
    const metadata_selectedConditionsJsonInput = document.getElementById('metadata_selectedConditionsJson');
    const metadata_currentUnknownScreenIdDisplay = document.getElementById('metadata_currentUnknownScreenIdDisplay');
    const metadata_appNameInput = document.getElementById('metadata_appName');
    const metadata_activityNameInput = document.getElementById('metadata_activityName');
    const metadata_logicalNameInput = document.getElementById('metadata_logicalName');
    const metadata_newDefinedScreenIdInput = document.getElementById('metadata_newDefinedScreenId');
    const metadata_descriptionInput = document.getElementById('metadata_description');
    const metadata_conditionsCountDisplay = document.getElementById('metadata_conditionsCountDisplay');
    const defineMetadata_errorMessages = document.getElementById('defineMetadata_errorMessages');
    const saveNewPieDefinitionBtn = document.getElementById('saveNewPieDefinitionBtn');

    // =======================================================================
    // === LOGIC CHO MODAL #managePieConditionsModal (QUẢN LÝ CONDITIONS) ===
    // =======================================================================


    function renderElementTextList(elementsData) {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
        if (!pieCondElementTextList) return;
        pieCondElementTextList.innerHTML = '';
        if (!elementsData || elementsData.length === 0) {
            pieCondElementTextList.innerHTML = '<p class="text-muted small p-2">Không có elements.</p>'; return;
        }
        elementsData.forEach((elData, index) => {
            const listItem = document.createElement('a');
            listItem.href = "#";
            listItem.className = 'list-group-item list-group-item-action';
            listItem.dataset.elementIndex = index;
            let displayText = `<strong>${elData.resource_id || elData.element_id || 'Element'}</strong>`;
            if (elData.text_content) displayText += `<br><small class="text-muted">Text: ${elData.text_content.substring(0, 50)}...</small>`;
            if (elData.class_name) displayText += `<br><small class="text-muted">Class: ${elData.class_name.replace('android.widget.', '')}</small>`;
            listItem.innerHTML = displayText;

            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === index);
            if (isSelected) listItem.classList.add('selected-for-pie');

            listItem.addEventListener('click', function (e) { e.preventDefault(); handleElementSelectionFromVisualizer(index, this); });
            pieCondElementTextList.appendChild(listItem);
        });
    }

    function renderSelectedPieConditions() {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
        if (!pieCondSelectedConditionsList) return;
        pieCondSelectedConditionsList.innerHTML = '';
        if (currentSelectedPieConditions.length === 0) {
            pieCondSelectedConditionsList.innerHTML = '<p class="text-muted small p-2 initial-prompt">Chọn element để thêm điều kiện.</p>'; return;
        }
        currentSelectedPieConditions.forEach((condition, index) => {
            const conditionDiv = document.createElement('div');
            conditionDiv.className = 'mb-2 p-2 border rounded bg-white shadow-sm condition-item-row';
            conditionDiv.dataset.conditionIndex = index;
            let attributeOptionsHtml = ELEMENT_ATTRIBUTES_FOR_PIE.map(attr => `<option value="${attr.value}" ${condition.attribute === attr.value ? 'selected' : ''}>${attr.label}</option>`).join('');
            let comparisonOptionsHtml = COMPARISON_TYPES_FOR_PIE.map(comp => `<option value="${comp.value}" ${condition.comparison === comp.value ? 'selected' : ''}>${comp.label}</option>`).join('');
            conditionDiv.innerHTML = `
                    <div class="row gx-2 gy-1 align-items-center">
                        <div class="col-md-4"><select class="form-select form-select-sm condition-attribute" data-index="${index}">${attributeOptionsHtml}</select></div>
                        <div class="col-md-3"><select class="form-select form-select-sm condition-comparison" data-index="${index}">${comparisonOptionsHtml}</select></div>
                        <div class="col-md-4"><input type="text" class="form-control form-control-sm condition-value" data-index="${index}" value="${condition.value || ''}" placeholder="Giá trị" ${condition.comparison === 'EXISTS' || condition.comparison === 'NOT_EXISTS' ? 'disabled' : ''}></div>
                        <div class="col-md-1 text-end"><button type="button" class="btn btn-sm btn-outline-danger remove-condition-btn" data-index="${index}" title="Xóa"><i class="fas fa-times"></i></button></div>
                    </div>
                    <div class="text-muted xsmall mt-1">Từ Element: ${condition.element_identifier_display || 'Thủ công'}</div>`;
            pieCondSelectedConditionsList.appendChild(conditionDiv);
        });
        attachListenersToSelectedConditions();
        updateVisualizerSelections();
    }

    function attachListenersToSelectedConditions() {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
        document.querySelectorAll('#pieConditionsSelectedConditionsList .condition-attribute').forEach(s => s.onchange = function () { currentSelectedPieConditions[this.dataset.index].attribute = this.value; });
        document.querySelectorAll('#pieConditionsSelectedConditionsList .condition-comparison').forEach(s => s.onchange = function () {
            currentSelectedPieConditions[this.dataset.index].comparison = this.value;
            const vInput = this.closest('.row').querySelector('.condition-value');
            if (this.value === 'EXISTS' || this.value === 'NOT_EXISTS') { vInput.disabled = true; vInput.value = ''; currentSelectedPieConditions[this.dataset.index].value = ''; }
            else { vInput.disabled = false; }
        });
        document.querySelectorAll('#pieConditionsSelectedConditionsList .condition-value').forEach(i => i.oninput = function () { currentSelectedPieConditions[this.dataset.index].value = this.value.trim(); });
        document.querySelectorAll('#pieConditionsSelectedConditionsList .remove-condition-btn').forEach(b => b.onclick = function () { currentSelectedPieConditions.splice(this.dataset.index, 1); renderSelectedPieConditions(); });
    }

    function handleElementSelectionFromVisualizer(elementIndex, clickedDomElement) {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
        if (rawElementsDataForModal.length <= elementIndex) return;
        const elementData = rawElementsDataForModal[elementIndex];

        const existingConditionFind = currentSelectedPieConditions.find(cond => cond.internal_element_index === elementIndex);

        if (existingConditionFind) { // Bỏ chọn
            currentSelectedPieConditions = currentSelectedPieConditions.filter(cond => cond.internal_element_index !== elementIndex);
        } else { // Chọn mới
            let newCondition = {
                internal_element_index: elementIndex, // Để link lại với visualizer
                element_identifier_display: `${elementData.resource_id || elementData.element_id || 'Element'} (${elementData.text_content ? elementData.text_content.substring(0, 15) + '...' : (elementData.class_name || '')})`,
                attribute: '', comparison: 'EQUALS', value: ''
            };
            if (elementData.resource_id) { newCondition.attribute = 'resource_id'; newCondition.value = elementData.resource_id; }
            else if (elementData.text_content) { newCondition.attribute = 'text'; newCondition.value = elementData.text_content; }
            else if (elementData.class_name) { newCondition.attribute = 'class_name'; newCondition.value = elementData.class_name; }
            else { return; } // Không có gì để tạo condition
            currentSelectedPieConditions.push(newCondition);
        }
        renderSelectedPieConditions(); // Cập nhật Phần 3 và gọi updateVisualizerSelections() từ trong đó
    }

    function updateVisualizerSelections() {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
        document.querySelectorAll('#pieConditionsImageContainer .element-overlay-interactive, #pieConditionsElementTextList .list-group-item').forEach(visEl => {
            const elIndex = parseInt(visEl.dataset.elementIndex);
            const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === elIndex);
            if (isSelected) visEl.classList.add('selected-for-pie');
            else visEl.classList.remove('selected-for-pie');
        });
    }

    async function openManagePieConditionsModal(nodeData) {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
        if (!managePieModalInstance) return;
        currentManagingNodeData = nodeData; currentSelectedPieConditions = []; rawElementsDataForModal = [];
        if (managePie_errorMessages) managePie_errorMessages.textContent = '';
        if (managePie_currentScreenIdDisplay) managePie_currentScreenIdDisplay.textContent = nodeData.currentScreenId;
        if (managePie_currentAppNameDisplay) managePie_currentAppNameDisplay.textContent = nodeData.appName;

        if (pieCondScreenshot) pieCondScreenshot.src = '';
        if (pieCondImageContainer) pieCondImageContainer.querySelectorAll('.element-overlay-interactive').forEach(ov => ov.remove());
        if (pieCondElementTextList) pieCondElementTextList.innerHTML = '<p class="text-muted small p-2">Đang tải...</p>';

        let screenshotLoadPromise = new Promise((resolve, reject) => {
            if (nodeData.screenshotFilename && pieCondScreenshot) {
                pieCondScreenshot.src = `${SCREENSHOTS_BASE_URL}${nodeData.appName}/${nodeData.screenshotFilename}`;
                pieCondScreenshot.onload = resolve;
                pieCondScreenshot.onerror = () => reject(new Error("Lỗi tải ảnh screenshot."));
            } else { resolve(); /* Không có ảnh để tải */ }
        });

        try {
            await screenshotLoadPromise;
            const elementsUrl = API_SCREEN_ELEMENTS_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(nodeData.currentScreenId));
            const elementsResponse = await fetch(elementsUrl);
            if (!elementsResponse.ok) throw new Error(`Lỗi HTTP ${elementsResponse.status} khi lấy elements.`);
            const elementsJson = await elementsResponse.json();
            if (elementsJson.success && elementsJson.elements) {
                rawElementsDataForModal = elementsJson.elements;
                drawInteractiveOverlays(pieCondScreenshot, rawElementsDataForModal, nodeData.width, nodeData.height, pieCondImageContainer);
                renderElementTextList(rawElementsDataForModal);
            } else { throw new Error(elementsJson.error || "Không lấy được elements."); }
        } catch (error) {
            console.error("Lỗi tải ảnh/elements cho modal:", error);
            if (pieCondElementTextList) pieCondElementTextList.innerHTML = `<p class="text-danger small p-2">Lỗi: ${error.message}</p>`;
        }

        if (nodeData.nodeStatus === 'defined') {
            if (managePie_modalLabel) managePie_modalLabel.textContent = `Sửa Điều kiện PIE cho: ${nodeData.pieLogicalName || nodeData.currentScreenId}`;
            if (managePie_mainActionBtn) { managePie_mainActionBtn.textContent = 'Lưu Conditions PIE'; managePie_mainActionBtn.className = 'btn btn-sm btn-primary'; }
            try {
                const conditionsUrl = `${API_GET_PIE_CONDITIONS_URL}?app_name=${encodeURIComponent(nodeData.appName)}&defined_screen_id=${encodeURIComponent(nodeData.currentScreenId)}`;
                const conditionsResponse = await fetch(conditionsUrl);
                if (!conditionsResponse.ok) throw new Error(`Lỗi HTTP ${conditionsResponse.status} khi lấy conditions.`);
                const conditionsJson = await conditionsResponse.json();
                if (conditionsJson.success && conditionsJson.conditions) {
                    currentSelectedPieConditions = conditionsJson.conditions.map(c => ({ ...c, internal_element_index: -1 })); // -1 vì chưa link với visualizer
                } else { currentSelectedPieConditions = []; }
            } catch (error) { console.error("Lỗi tải conditions:", error); currentSelectedPieConditions = []; if (managePie_errorMessages) managePie_errorMessages.textContent = 'Lỗi tải conditions. Có thể tạo mới.'; }
        } else {
            if (managePie_modalLabel) managePie_modalLabel.textContent = `Chọn Điều kiện cho PIE Mới (Node: ${nodeData.currentScreenId})`;
            if (managePie_mainActionBtn) { managePie_mainActionBtn.textContent = 'Tiếp tục Định nghĩa PIE'; managePie_mainActionBtn.className = 'btn btn-sm btn-success'; }
            currentSelectedPieConditions = [];
        }
        renderSelectedPieConditions();
        managePieModalInstance.show();
    }

    if (pieCond_addManualConditionBtn) {
        pieCond_addManualConditionBtn.addEventListener('click', function () {
            currentSelectedPieConditions.push({ attribute: 'text', comparison: 'EQUALS', value: '', internal_element_index: -1, element_identifier_display: 'Thủ công' });
            renderSelectedPieConditions();
        });
    }

    if (managePie_mainActionBtn) {
        managePie_mainActionBtn.addEventListener('click', async function () {
            // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
            this.disabled = true; this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ...';
            if (managePie_errorMessages) managePie_errorMessages.textContent = '';
            const finalConditionsToSave = currentSelectedPieConditions.map(cond => ({
                attribute: cond.attribute, comparison: cond.comparison, value: cond.value
            })); // Chỉ lấy 3 trường chính

            if (currentManagingNodeData.nodeStatus === 'defined') {
                const updateUrl = `${API_UPDATE_PIE_CONDITIONS_BASE_URL}/${encodeURIComponent(currentManagingNodeData.currentScreenId)}/update_conditions`;
                try {
                    const response = await fetch(updateUrl, {
                        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
                        body: JSON.stringify({ app_name: currentManagingNodeData.appName, new_conditions_list: finalConditionsToSave })
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.message || `Lỗi HTTP ${response.status}`);
                    if (result.success) { alert("Cập nhật thành công!"); managePieModalInstance.hide(); fetchAndRenderNodes(); }
                    else { throw new Error(result.message || "Lỗi từ server."); }
                } catch (error) { console.error("Lỗi update PIE:", error); if (managePie_errorMessages) managePie_errorMessages.textContent = error.message; }
                finally { this.disabled = false; this.textContent = 'Lưu Conditions PIE'; }
            } else { // Node 'unknown'
                if (finalConditionsToSave.length === 0) {
                    if (managePie_errorMessages) managePie_errorMessages.textContent = 'Cần chọn ít nhất một điều kiện.';
                    this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE'; return;
                }
                managePieModalInstance.hide();
                openDefineNewPieMetadataModal(currentManagingNodeData, finalConditionsToSave);
                this.disabled = false; this.textContent = 'Tiếp tục Định nghĩa PIE'; // Reset nút sau khi ẩn modal
            }
        });
    }

    // =======================================================================
    // === LOGIC CHO MODAL #defineNewPieMetadataModal (METADATA PIE MỚI) ===
    // =======================================================================
    function openDefineNewPieMetadataModal(nodeDataSource, conditionsToSave) {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_define_pie_metadata.js)
        if (!defineMetadataModalInstance) return;
        if (defineMetadata_errorMessages) defineMetadata_errorMessages.textContent = '';
        if (metadata_unknownNodeNeo4jIdInput) metadata_unknownNodeNeo4jIdInput.value = nodeDataSource.nodeNeo4jId;
        if (metadata_currentUnknownScreenIdInput) metadata_currentUnknownScreenIdInput.value = nodeDataSource.currentScreenId;
        if (metadata_currentUnknownScreenIdDisplay) metadata_currentUnknownScreenIdDisplay.textContent = nodeDataSource.currentScreenId;
        if (metadata_appNameInput) metadata_appNameInput.value = nodeDataSource.appName;
        if (metadata_activityNameInput) metadata_activityNameInput.value = nodeDataSource.activityName || '';
        if (metadata_logicalNameInput) metadata_logicalNameInput.value = '';
        if (metadata_newDefinedScreenIdInput) metadata_newDefinedScreenIdInput.value = '';
        if (metadata_descriptionInput) metadata_descriptionInput.value = '';
        if (metadata_selectedConditionsJsonInput) metadata_selectedConditionsJsonInput.value = JSON.stringify(conditionsToSave);
        if (metadata_conditionsCountDisplay) metadata_conditionsCountDisplay.textContent = conditionsToSave.length;
        defineMetadataModalInstance.show();
    }

    if (defineMetadataForm) {
        defineMetadataForm.addEventListener('submit', async function (event) {
            // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_define_pie_metadata.js)
            event.preventDefault();
            if (defineMetadata_errorMessages) defineMetadata_errorMessages.textContent = '';
            if (saveNewPieDefinitionBtn) { saveNewPieDefinitionBtn.disabled = true; saveNewPieDefinitionBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ...'; }
            const payload = {
                unknown_node_neo4j_id: metadata_unknownNodeNeo4jIdInput.value,
                current_unknown_screen_id: metadata_currentUnknownScreenIdInput.value,
                app_name: metadata_appNameInput.value,
                activity_name: metadata_activityNameInput.value || null,
                logical_name: metadata_logicalNameInput.value.trim(),
                new_defined_screen_id: metadata_newDefinedScreenIdInput.value.trim(),
                selected_conditions: JSON.parse(metadata_selectedConditionsJsonInput.value || '[]'),
                description: metadata_descriptionInput.value.trim() || null
            };
            if (!payload.logical_name || !payload.new_defined_screen_id || payload.selected_conditions.length === 0) {
                if (defineMetadata_errorMessages) defineMetadata_errorMessages.textContent = 'Tên Logic, Defined ID và Conditions là bắt buộc.';
                if (saveNewPieDefinitionBtn) { saveNewPieDefinitionBtn.disabled = false; saveNewPieDefinitionBtn.textContent = 'Lưu Định nghĩa PIE'; }
                return;
            }
            try {
                const response = await fetch(API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN }, body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.message || `Lỗi HTTP ${response.status}`);
                if (result.success) { alert("Định nghĩa PIE mới thành công!"); defineMetadataModalInstance.hide(); fetchAndRenderNodes(); }
                else { throw new Error(result.message || "Lưu PIE thất bại."); }
            } catch (error) { console.error("Lỗi lưu PIE mới:", error); if (defineMetadata_errorMessages) defineMetadata_errorMessages.textContent = error.message; }
            finally { if (saveNewPieDefinitionBtn) { saveNewPieDefinitionBtn.disabled = false; saveNewPieDefinitionBtn.textContent = 'Lưu Định nghĩa PIE'; } }
        });
    }

    // =============================================================
    // === LOGIC CHO BẢNG (FILTER, PAGINATION, ACTIONS) ===
    // =============================================================
    function attachTableTriggers() {
        // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/table_handler.js)
        // Gắn sự kiện cho ảnh thumbnail
        document.querySelectorAll('.manage-pie-trigger').forEach(trigger => {
            const row = trigger.closest('tr');
            const nodeData = {
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: row.dataset.nodeStatus,
                screenshotFilename: row.dataset.screenshotFilename, activityName: row.dataset.activityName,
                pieLogicalName: row.dataset.pieLogicalName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            // Xóa listener cũ nếu có thể (để tránh gắn nhiều lần nếu không cloneNode)
            trigger.onclick = null;
            trigger.addEventListener('click', function () { openManagePieConditionsModal(nodeData); });
        });

        // Gắn sự kiện cho nút "Tạo PIE Mới"
        document.querySelectorAll('.define-new-pie-metadata-trigger').forEach(button => {
            const row = button.closest('tr');
            const nodeDataForPieDef = {
                nodeNeo4jId: row.dataset.nodeNeo4jId, currentScreenId: row.dataset.currentScreenId,
                appName: row.dataset.appName, nodeStatus: 'unknown',
                screenshotFilename: row.dataset.screenshotFilename, activityName: row.dataset.activityName,
                width: parseInt(row.dataset.width) || null, height: parseInt(row.dataset.height) || null
            };
            button.onclick = null;
            button.addEventListener('click', function () { openManagePieConditionsModal(nodeDataForPieDef); });
        });

        // Gắn sự kiện cho nút Xóa Node
        document.querySelectorAll('.delete-node-btn').forEach(button => {
            const row = button.closest('tr');
            button.onclick = null; // Xóa listener cũ
            button.addEventListener('click', function () { handleDeleteNode(row.dataset.currentScreenId, row.dataset.appName); });
        });

        // Gắn sự kiện cho dropdown Phân loại Node
        document.querySelectorAll('.node-classification-select').forEach(select => {
            select.onchange = null; // Xóa listener cũ
            select.addEventListener('change', handleNodeClassificationChange);
        });

        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
        tooltipTriggerList.map(function (tooltipTriggerEl) { return new bootstrap.Tooltip(tooltipTriggerEl) });
    }

    function handleDeleteNode(screenId, appName) { // Hàm xử lý xóa node
        // ... (Logic xóa node như đã có, gọi API_DELETE_NODE_BASE_URL)
        if (confirm(`Bạn chắc chắn muốn xóa Node '${screenId}' của app '${appName}' không?`)) {
            const deleteUrl = API_DELETE_NODE_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(screenId));
            fetch(deleteUrl, {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
                body: JSON.stringify({ app_name: appName }) // API backend cần app_name
            })
                .then(res => res.json().then(data => { if (!res.ok) throw data; return data; }))
                .then(result => {
                    if (result.success) { alert(result.message || 'Xóa Node thành công!'); fetchAndRenderNodes(); }
                    else { alert("Lỗi Xóa Node: " + (result.error || "Thất bại.")); }
                })
                .catch(error => { console.error('Lỗi Fetch khi xóa:', error); alert('Lỗi máy chủ: ' + (error.error || error.message)); });
        }
    }

    function handleNodeClassificationChange() { // Hàm xử lý đổi classification
        // ... (Logic phân loại node như đã có, gọi API_CLASSIFY_NODE_BASE_URL)
        const screenId = this.dataset.currentScreenId; // Đảm bảo data attribute đúng
        const appName = this.dataset.appName;
        const newClassification = this.value;
        const statusSpan = this.closest('td').querySelector('.classification-status');
        if (statusSpan) { statusSpan.textContent = 'Đang lưu...'; }
        const classifyUrl = API_CLASSIFY_NODE_BASE_URL.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(screenId));
        fetch(classifyUrl, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
            body: JSON.stringify({ app_name: appName, node_classification: newClassification })
        })
            .then(res => res.json().then(data => { if (!res.ok) throw data; return data; }))
            .then(result => {
                if (statusSpan) {
                    if (result.success) { statusSpan.textContent = 'Đã lưu!'; statusSpan.className = 'classification-status small ms-1 text-success'; }
                    else { statusSpan.textContent = 'Lỗi!'; statusSpan.className = 'classification-status small ms-1 text-danger'; alert("Lỗi: " + (result.error || "Thất bại.")); }
                    setTimeout(() => { if (statusSpan) statusSpan.textContent = ''; }, 3000);
                }
            })
            .catch(error => { /* ... */ if (statusSpan) { statusSpan.textContent = 'Lỗi mạng!'; } console.error('Lỗi Fetch:', error); alert('Lỗi máy chủ: ' + (error.error || error.message)); });
    }

    function renderNodeRow(node) {
        // ... (Nội dung hàm này đã được cập nhật ở các phản hồi trước, đảm bảo nó tạo đúng HTML và data attributes cho thẻ <tr>)
        // ... (đã bao gồm việc gọi ADMIN_SCREEN_ELEMENTS_URL_BASE và các class trigger)
        // ... (sử dụng node.screenshot_full_url từ API)
        const row = document.createElement('tr');
        row.dataset.nodeNeo4jId = node.id || node.element_id || '';
        row.dataset.currentScreenId = node.screen_id || '';
        row.dataset.appName = node.app_name || '';
        row.dataset.nodeStatus = node.status || 'unknown';
        row.dataset.screenshotFilename = node.screenshot_path || ''; // Chỉ là tên file
        row.dataset.activityName = node.activity_name || '';
        row.dataset.pieLogicalName = node.logical_pie_name || '';
        row.dataset.width = node.width || '';
        row.dataset.height = node.height || '';

        const screenElementsUrl = ADMIN_SCREEN_ELEMENTS_URL_BASE.replace('SCREEN_ID_PLACEHOLDER', encodeURIComponent(node.screen_id || ''));

        let imgHtml = `<span class="text-muted small manage-pie-trigger" style="cursor:pointer; display:inline-block; width:70px; height:70px; border:1px dashed #ccc; text-align:center; line-height:70px;">N/A</span>`;
        if (node.screenshot_full_url) {
            imgHtml = `<img src="${node.screenshot_full_url}" alt="ss_${node.screen_id}" class="node-thumbnail manage-pie-trigger">`;
        }

        let logicalNameHtml = `<em class="text-muted small">Chưa có PIE</em>`;
        if (node.logical_pie_name && node.logical_pie_name !== "PIE Def không tìm thấy" && node.logical_pie_name !== "Lỗi lấy PIE Def") {
            logicalNameHtml = `<span title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}</span>`;
        } else if (node.logical_pie_name) {
            logicalNameHtml = `<em class="text-danger small" title="${node.logical_pie_name}">${(node.logical_pie_name).substring(0, 25)}</em>`;
        }

        let statusClass = 'bg-secondary';
        if (node.status === 'defined') statusClass = 'bg-success';
        else if (node.status === 'provisional_unknown') statusClass = 'bg-warning text-dark';

        const classificationsOpts = [{ v: "", l: "--" }, { v: "login_screen", l: "Login" }, { v: "profile_screen", l: "Profile" }, { v: "feed_screen", l: "Feed/Home" }, { v: "settings_screen", l: "Settings" }, { v: "popup_dialog", l: "Popup" }, { v: "item_list", l: "Item List" }, { v: "item_detail", l: "Item Detail" }, { v: "other", l: "Khác" }];
        let classificationSelectHtml = `<select class="form-select form-select-sm node-classification-select" data-current-screen-id="${node.screen_id}" data-app-name="${node.app_name}">`;
        classificationsOpts.forEach(opt => {
            classificationSelectHtml += `<option value="${opt.v}" ${node.node_classification == opt.v ? 'selected' : ''}>${opt.l}</option>`;
        });
        classificationSelectHtml += `</select><span class="classification-status small ms-1"></span>`;

        let actionButtonsHtml = `<div class="action-button-row mb-1">
                                        <a href="${screenElementsUrl}" target="_blank" class="btn btn-xs btn-outline-info view-elements-btn me-1" title="Xem Elements (Trang riêng)" data-bs-toggle="tooltip"><i class="fas fa-search-plus"></i> Elements</a>
                                        <button class="btn btn-xs btn-outline-danger delete-node-btn" title="Xóa Node" data-bs-toggle="tooltip"><i class="fas fa-trash-alt"></i> Xóa</button>
                                     </div>`;
        if (node.status === 'unknown' || node.status === 'provisional_unknown') {
            actionButtonsHtml += `<div class="action-button-row">
                                        <button class="btn btn-xs btn-outline-success define-new-pie-metadata-trigger" title="Tạo PIE Mới cho Node này" data-bs-toggle="tooltip"><i class="fas fa-plus-circle"></i> Tạo PIE Mới</button>
                                     </div>`;
        }

        row.innerHTML = `
                <td><input type="checkbox" class="node-checkbox" value="${node.screen_id || ''}"></td>
                <td><a href="${screenElementsUrl}" target="_blank"><code class="small">${(node.screen_id || 'N/A').substring(0, 20)}</code></a></td>
                <td><code class="small">${node.app_name || 'N/A'}</code></td>
                <td><code class="small" title="${node.activity_name || ''}">${(node.activity_name || 'N/A').substring(0, 20)}</code></td>
                <td>${imgHtml}</td>
                <td>${logicalNameHtml}</td>
                <td><span class="badge ${statusClass}">${node.status || 'N/A'}</span></td>
                <td>${classificationSelectHtml}</td>
                <td class="text-center">${node.actual_element_count_rel ?? node.defined_element_count ?? 0}</td>
                <td class="text-center">${node.incoming_transitions_count || 0} / ${node.outgoing_transitions_count || 0}</td>
                <td class="small text-nowrap">${node.last_seen ? new Date(node.last_seen).toLocaleDateString('vi-VN') : 'N/A'}</td>
                <td class="action-buttons text-nowrap">${actionButtonsHtml}</td>
            `;
        return row;
    }


    function renderNodePagination(paginationData, currentPageFilters) {
        // ... (Hàm renderNodePagination đầy đủ như đã cung cấp, đảm bảo nó dùng đúng class và data attributes cho page links)
        if (!paginationContainer) return;
        paginationContainer.innerHTML = '';
        if (!paginationData || paginationData.total_pages <= 1) return;
        let html = '<ul class="pagination pagination-sm justify-content-center">';
        html += `<li class="page-item ${paginationData.has_prev ? '' : 'disabled'}"><a class="page-link" href="#" data-page="${paginationData.prev_num || 1}">&laquo;</a></li>`;
        const window = 2;
        let start = Math.max(1, paginationData.page - window);
        let end = Math.min(paginationData.total_pages, paginationData.page + window);
        if (start > 1) { html += `<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>`; if (start > 2) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`; }
        for (let i = start; i <= end; i++) { html += `<li class="page-item ${i === paginationData.page ? 'active' : ''}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`; }
        if (end < paginationData.total_pages) { if (end < paginationData.total_pages - 1) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`; html += `<li class="page-item"><a class="page-link" href="#" data-page="${paginationData.total_pages}">${paginationData.total_pages}</a></li>`; }
        html += `<li class="page-item ${paginationData.has_next ? '' : 'disabled'}"><a class="page-link" href="#" data-page="${paginationData.next_num || paginationData.total_pages}">&raquo;</a></li>`;
        html += '</ul>';
        paginationContainer.innerHTML = html;
        paginationContainer.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                if (this.closest('.page-item.disabled')) return;
                fetchAndRenderNodes(parseInt(this.dataset.page), currentPageFilters.appName, currentPageFilters.status);
            });
        });
    }



    function fetchAndRenderNodes(page = 1, appName = null, statusFilter = null) {
        // ... (Cập nhật để gọi attachTableTriggers sau khi render xong tbody)
        const currentAppName = appName !== null ? appName : (appNameFilterSelect ? appNameFilterSelect.value : '');
        const currentStatus = statusFilter !== null ? statusFilter : (statusFilterSelect ? statusFilterSelect.value : 'unknown');
        const apiUrl = buildApiUrl(page, currentAppName, currentStatus);

        if (!nodesTableBody) { console.error("nodesTableBody not found!"); return; }
        nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center py-3"><i class="fas fa-spinner fa-spin me-2"></i>Đang tải...</td></tr>`;
        if (paginationContainer) paginationContainer.innerHTML = '';

        fetch(apiUrl)
            .then(response => { if (!response.ok) { return response.json().then(err => { throw new Error(err.error || `HTTP ${response.status}`) }); } return response.json(); })
            .then(data => {
                nodesTableBody.innerHTML = '';
                if (data.nodes && data.nodes.length > 0) { data.nodes.forEach(node => { nodesTableBody.appendChild(renderNodeRow(node)); }); }
                else { nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-muted fst-italic py-3">Không có Node nào.</td></tr>`; }
                if (data.pagination) { renderNodePagination(data.pagination, { appName: currentAppName, status: currentStatus }); }
                attachTableTriggers(); // QUAN TRỌNG
            })
            .catch(error => { console.error("Lỗi tải Node:", error); nodesTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-danger py-3">Lỗi: ${error.message}</td></tr>`; });
    }

    // --- KHỞI TẠO BAN ĐẦU ---
    if (filterForm) { filterForm.addEventListener('submit', function (event) { event.preventDefault(); fetchAndRenderNodes(1); }); }

    const currentUrlParams = new URLSearchParams(window.location.search);
    const initialPage = parseInt(currentUrlParams.get('page') || '1', 10);
    const initialAppName = currentUrlParams.get('app_name_filter') || (appNameFilterSelect ? appNameFilterSelect.value : '');
    const initialStatus = currentUrlParams.get('filter_status') || (statusFilterSelect ? statusFilterSelect.value : 'unknown');

    // Nếu tbody đã có nội dung từ server render, chỉ attach listeners. Nếu không thì fetch.
    if (nodesTableBody && nodesTableBody.children.length > 0 && !(nodesTableBody.firstElementChild && nodesTableBody.firstElementChild.children.length === 1 && nodesTableBody.firstElementChild.firstElementChild.textContent.includes("Không tìm thấy Node nào"))) {
        attachTableTriggers();
        // Gắn listener cho pagination hiện tại (được render bởi server)
        document.querySelectorAll('#nodeManagementPagination .page-link').forEach(link => {
            if (link.closest('.page-item.disabled')) return; // Bỏ qua link disabled
            // Xóa event cũ nếu có thể, hoặc đảm bảo hàm attach chỉ chạy 1 lần cho mỗi element
            const newLink = link.cloneNode(true); // Clone để xóa event cũ hiệu quả
            link.parentNode.replaceChild(newLink, link);
            newLink.addEventListener('click', function (e) {
                e.preventDefault();
                const pageNum = parseInt(this.dataset.page, 10);
                const appName = appNameFilterSelect ? appNameFilterSelect.value : '';
                const status = statusFilterSelect ? statusFilterSelect.value : 'unknown';
                fetchAndRenderNodes(pageNum, appName, status);
            });
        });
        var serverTooltips = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
        serverTooltips.map(function (el) { return new bootstrap.Tooltip(el) });
    } else {
        fetchAndRenderNodes(initialPage, initialAppName, initialStatus);
    }

    // Logic cho modal xem ảnh gốc (originalImagePreviewModal) - Giữ lại nếu cần
    const originalImagePreviewModalEl = document.getElementById('originalImagePreviewModal');
    if (originalImagePreviewModalEl) {
        const modalImgOrig = document.getElementById('modalScreenshotImageOriginal');
        const modalContainerOrig = document.getElementById('modalScreenshotContainerOriginal');
        const modalElementsListOrig = document.getElementById('originalModalElementsList');
        const modalScreenIdDispOrig = document.getElementById('originalModalScreenIdDisplay');

        originalImagePreviewModalEl.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            if (!button || !button.dataset) return; // Kiểm tra button và dataset
            const imageUrl = button.dataset.imageUrl; // Giả sử nút trigger có data-image-url
            const screenId = button.dataset.screenId;
            const elementsUrl = button.dataset.elementsUrl; // Và data-elements-url
            const origW = parseInt(button.dataset.originalWidth);
            const origH = parseInt(button.dataset.originalHeight);

            if (modalScreenIdDispOrig) modalScreenIdDispOrig.textContent = screenId || 'N/A';
            if (modalImgOrig) {
                modalImgOrig.src = imageUrl || '';
                modalImgOrig.style.display = imageUrl ? 'block' : 'none';
            }
            if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-muted small">Đang tải elements...</p>';
            if (modalContainerOrig) modalContainerOrig.querySelectorAll('.element-overlay-displayonly').forEach(ov => ov.remove());

            if (imageUrl && elementsUrl && modalImgOrig) {
                modalImgOrig.onload = function () { // Đợi ảnh load xong mới lấy elements và vẽ
                    fetch(elementsUrl)
                        .then(res => res.json())
                        .then(data => {
                            if (data.success && data.elements) {
                                // Gọi hàm vẽ overlay chỉ hiển thị (không tương tác)
                                // Bạn cần tạo hàm drawDisplayOnlyOverlays tương tự drawInteractiveOverlays
                                // drawDisplayOnlyOverlays(modalImgOrig, data.elements, origW, origH, modalContainerOrig); 
                                if (modalElementsListOrig) {
                                    modalElementsListOrig.innerHTML = ''; // Clear
                                    // Render danh sách text elements (tương tự renderElementTextList nhưng không cần tương tác)
                                    data.elements.forEach(el => {
                                        const li = document.createElement('li'); li.className = 'list-group-item small';
                                        li.textContent = `ID: ${el.resource_id || el.element_id}, Text: ${el.text_content || '--'}, Class: ${el.class_name || 'N/A'}`;
                                        modalElementsListOrig.appendChild(li);
                                    });
                                }
                            } else {
                                if (modalElementsListOrig) modalElementsListOrig.innerHTML = `<p class="text-danger small">Lỗi: ${data.error || 'Không lấy được elements.'}</p>`;
                            }
                        })
                        .catch(err => {
                            if (modalElementsListOrig) modalElementsListOrig.innerHTML = `<p class="text-danger small">Lỗi tải elements: ${err.message}</p>`;
                        });
                }
                modalImgOrig.onerror = () => { if (modalElementsListOrig) modalElementsListOrig.innerHTML = '<p class="text-danger small">Lỗi tải ảnh.</p>'; }
            } else {
                if (modalElementsListOrig && !imageUrl) modalElementsListOrig.innerHTML = '<p class="text-muted small">Không có ảnh.</p>';
                else if (modalElementsListOrig && !elementsUrl) modalElementsListOrig.innerHTML = '<p class="text-muted small">Không có URL elements.</p>';
            }
        });
    }


}); // End DOMContentLoaded
