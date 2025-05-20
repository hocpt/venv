function drawInteractiveOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight, containerElement) {
    // ... (Nội dung hàm này sẽ được tách ra file js/admin_node_management/modal_manage_pie_conditions.js)
    // Tạm thời để trống, sẽ điền code chi tiết sau
    if (!containerElement) { console.error("drawInteractiveOverlays: containerElement is null!"); return; }
    containerElement.querySelectorAll('.element-overlay-interactive').forEach(ov => ov.remove());

    const displayedImgWidth = imgElement.clientWidth;
    const displayedImgHeight = imgElement.clientHeight;

    if (!nodeOriginalWidth || !nodeOriginalHeight || nodeOriginalWidth <= 0 || nodeOriginalHeight <= 0 || displayedImgWidth === 0 || displayedImgHeight === 0) {
        console.warn(`Kích thước không hợp lệ để vẽ overlay. Gốc: ${nodeOriginalWidth}x${nodeOriginalHeight}, Hiển thị: ${displayedImgWidth}x${displayedImgHeight}`);
        return;
    }
    const scaleX = displayedImgWidth / nodeOriginalWidth;
    const scaleY = displayedImgHeight / nodeOriginalHeight;

    if (!elementsData || !elementsData.length) return;

    elementsData.forEach((elData, index) => {
        if (!elData || (!elData.resource_id && !elData.text_content && !elData.class_name && !elData.bounds)) return;

        let el_orig_left, el_orig_top, el_orig_width, el_orig_height;
        const bounds = elData.bounds;
        if (bounds && typeof bounds === 'object' && bounds.left !== undefined) {
            try {
                el_orig_left = parseInt(bounds.left, 10); el_orig_top = parseInt(bounds.top, 10);
                const el_orig_right = parseInt(bounds.right, 10); const el_orig_bottom = parseInt(bounds.bottom, 10);
                if (isNaN(el_orig_left) || isNaN(el_orig_top) || isNaN(el_orig_right) || isNaN(el_orig_bottom)) throw new Error("NaN in bounds");
                el_orig_width = el_orig_right - el_orig_left; el_orig_height = el_orig_bottom - el_orig_top;
                if (el_orig_width <= 0 || el_orig_height <= 0) el_orig_width = undefined;
            } catch (e) { el_orig_width = undefined; }
        }
        if (el_orig_width === undefined) { /* Fallback logic */ return; }

        const overlay = document.createElement('div');
        overlay.className = 'element-overlay-interactive';
        overlay.dataset.elementIndex = index;
        overlay.title = `ID: ${elData.resource_id || elData.element_id || 'N/A'}\nText: ${elData.text_content || '--'}\nClass: ${elData.class_name || 'N/A'}`;
        overlay.style.left = `${(el_orig_left * scaleX).toFixed(1)}px`;
        overlay.style.top = `${(el_orig_top * scaleY).toFixed(1)}px`;
        overlay.style.width = `${Math.max(5, el_orig_width * scaleX).toFixed(1)}px`;
        overlay.style.height = `${Math.max(5, el_orig_height * scaleY).toFixed(1)}px`;

        const isSelected = currentSelectedPieConditions.some(cond => cond.internal_element_index === index);
        if (isSelected) overlay.classList.add('selected-for-pie');

        overlay.addEventListener('click', function () { handleElementSelectionFromVisualizer(index, this); });
        containerElement.appendChild(overlay);
    });
}
