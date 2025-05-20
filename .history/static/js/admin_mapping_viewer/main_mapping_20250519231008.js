// static/js/admin_mapping_viewer/main_mapping.js
import { APP_CONFIG, initializeAppConfig } from './config_mapping.js';
import { initCytoscapeManager, fetchAndRenderGraph, updateEdgeInGraph } from './cytoscape_manager.js';
import { initDetailsPanelManager, showDefaultDetailsMessage } from './details_panel_manager.js';
import { initEditTransitionModal } from './modal_edit_transition.js';

document.addEventListener("DOMContentLoaded", function () {
    console.log("MAIN_MAPPING: DOMContentLoaded event fired.");

    if (typeof window.templatePageConfig !== 'undefined') {
        initializeAppConfig(window.templatePageConfig);
        console.log("MAIN_MAPPING: App config initialized from window.templatePageConfig.");
    } else {
        console.warn("MAIN_MAPPING: window.templatePageConfig không được định nghĩa. Sử dụng cấu hình mặc định.");
        initializeAppConfig({});
    }

    const appNameSelect = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.appNameSelect);
    const loadGraphButton = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadGraphButton);
    const refreshButton = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.refreshGraphButton);

    // Luôn khởi tạo modal vì HTML của nó luôn có mặt
    // Truyền callback để cytoscape_manager có thể cập nhật đồ thị
    initEditTransitionModal(updateEdgeInGraph);

    if (APP_CONFIG.APP_NAME_FROM_FLASK) {
        console.log("MAIN_MAPPING: App name is present. Initializing UI components that depend on specific DOM elements.");
        // Chỉ khởi tạo các module này nếu các DOM element cần thiết (graphContainer, selectionDetailsPanel) tồn tại.
        // Các hàm init này nên có kiểm tra nội bộ của riêng chúng.
        initDetailsPanelManager();
        initCytoscapeManager(APP_CONFIG.APP_NAME_FROM_FLASK);
    } else {
        console.log("MAIN_MAPPING: No app name selected initially. UI components for graph/details will not be fully initialized yet.");
        // Hiển thị thông báo trên các panel nếu chúng tồn tại (trường hợp {% else %} trong HTML)
        const initialMessageDiv = document.getElementById('initialMessage');
        if (initialMessageDiv && initialMessageDiv.style.display !== 'none') {
            // Thông báo đã được hiển thị bởi HTML
            console.log("MAIN_MAPPING: Initial message div is visible.");
        } else {
            // Nếu không có initialMessageDiv (ví dụ, người dùng xóa nó khỏi HTML),
            // hoặc nếu các div rỗng được render, thử đặt thông báo vào đó.
            const graphContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
            const selectionDetailsPanel = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);
            const panelTextContentDiv = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.panelTextContent);

            if (graphContainer) graphContainer.innerHTML = '<p class="text-center text-muted mt-5">Vui lòng chọn một ứng dụng để hiển thị bản đồ.</p>';
            if (panelTextContentDiv) {
                panelTextContentDiv.innerHTML = '<p class="text-info fst-italic">Vui lòng chọn một ứng dụng từ danh sách thả xuống ở trên để xem bản đồ của nó.</p>';
            } else if (selectionDetailsPanel) {
                selectionDetailsPanel.innerHTML = '<p class="text-info fst-italic p-3">Vui lòng chọn một ứng dụng từ danh sách thả xuống ở trên để xem bản đồ của nó.</p>';
            }
        }
        const loadingIndicator = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    if (loadGraphButton && appNameSelect) {
        loadGraphButton.addEventListener('click', function () {
            const selectedApp = appNameSelect.value;
            let targetUrl = APP_CONFIG.BASE_MAPPING_VIEWER_URL; // Lấy URL cơ sở từ config

            if (!targetUrl.endsWith('/')) {
                targetUrl += '/';
            }

            if (selectedApp) {
                window.location.href = targetUrl + encodeURIComponent(selectedApp);
            } else {
                // Nếu không chọn app, điều hướng về URL cơ sở (không có app_name)
                window.location.href = targetUrl;
            }
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener('click', function () {
            const currentApp = APP_CONFIG.APP_NAME_FROM_FLASK || (appNameSelect ? appNameSelect.value : null);
            if (currentApp) {
                console.log("MAIN_MAPPING: Refresh button clicked for app:", currentApp);
                if (typeof fetchAndRenderGraph === 'function') {
                    fetchAndRenderGraph(currentApp);
                } else {
                    console.error("MAIN_MAPPING: fetchAndRenderGraph is not available.");
                }
            } else {
                alert("Vui lòng chọn một ứng dụng trước khi làm mới.");
            }
        });
    }
    console.log("MAIN_MAPPING: Admin Mapping Viewer page fully initialized.");
});
