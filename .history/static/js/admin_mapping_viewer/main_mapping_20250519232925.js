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

    // Luôn cố gắng khởi tạo modal edit transition vì HTML của nó luôn có mặt
    // Hàm initEditTransitionModal nên tự kiểm tra sự tồn tại của modalEl bên trong nó.
    initEditTransitionModal(updateEdgeInGraph);

    if (APP_CONFIG.APP_NAME_FROM_FLASK) {
        console.log("MAIN_MAPPING: App name is present ('" + APP_CONFIG.APP_NAME_FROM_FLASK + "'). Attempting to initialize UI components.");

        // Kiểm tra sự tồn tại của các container chính TRƯỚC KHI gọi init của các module
        const graphContainerEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
        const detailsPanelEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);
        const loadingIndicatorEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);


        if (graphContainerEl && loadingIndicatorEl) {
            console.log("MAIN_MAPPING: Graph container and loading indicator found. Initializing Cytoscape manager.");
            initCytoscapeManager(APP_CONFIG.APP_NAME_FROM_FLASK);
        } else {
            console.error("MAIN_MAPPING: Graph container ('" + APP_CONFIG.DOM_ELEMENT_IDS.graphContainer + "') or loading indicator ('" + APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator + "') not found. Cytoscape manager NOT initialized.");
            // Có thể hiển thị thông báo lỗi cho người dùng ở đây nếu cần
            const graphArea = document.querySelector('.graph-display-area');
            if (graphArea) graphArea.innerHTML = '<p class="text-danger p-3">Lỗi: Không thể tải khu vực hiển thị bản đồ.</p>';
        }

        if (detailsPanelEl) {
            console.log("MAIN_MAPPING: Details panel found. Initializing details panel manager.");
            initDetailsPanelManager();
        } else {
            console.error("MAIN_MAPPING: Details panel ('" + APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel + "') not found. Details panel manager NOT initialized.");
            // Có thể hiển thị thông báo lỗi cho người dùng ở đây nếu cần
            const detailsCol = document.querySelector('.col-lg-4 .card > .card-body'); // Tìm panel chi tiết một cách tương đối
            if (detailsCol) detailsCol.innerHTML = '<p class="text-danger p-3">Lỗi: Không thể tải khu vực hiển thị chi tiết.</p>';

        }

    } else {
        console.log("MAIN_MAPPING: No app name selected initially. Main UI components (graph, details) will not be initialized.");
        const initialMessageDiv = document.getElementById('initialMessage');
        if (initialMessageDiv && initialMessageDiv.style.display !== 'none') {
            console.log("MAIN_MAPPING: Initial message div is visible.");
        }
        const loadingIndicator = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
        if (loadingIndicator) loadingIndicator.style.display = 'none'; // Đảm bảo ẩn nếu không có app
    }

    // Gắn sự kiện cho các nút điều khiển chung
    if (loadGraphButton && appNameSelect) {
        loadGraphButton.addEventListener('click', function () {
            const selectedApp = appNameSelect.value;
            let targetUrl = APP_CONFIG.BASE_MAPPING_VIEWER_URL;

            if (targetUrl && !targetUrl.endsWith('/')) {
                targetUrl += '/';
            }

            if (selectedApp) {
                window.location.href = targetUrl + encodeURIComponent(selectedApp);
            } else {
                window.location.href = targetUrl;
            }
        });
    } else {
        console.warn("MAIN_MAPPING: Load graph button or app name select not found.");
    }

    if (refreshButton) {
        refreshButton.addEventListener('click', function () {
            const currentApp = APP_CONFIG.APP_NAME_FROM_FLASK || (appNameSelect ? appNameSelect.value : null);
            if (currentApp) {
                console.log("MAIN_MAPPING: Refresh button clicked for app:", currentApp);
                if (typeof fetchAndRenderGraph === 'function') {
                    fetchAndRenderGraph(currentApp);
                } else {
                    console.error("MAIN_MAPPING: fetchAndRenderGraph is not available. Cytoscape manager might not have initialized correctly.");
                }
            } else {
                alert("Vui lòng chọn một ứng dụng trước khi làm mới.");
            }
        });
    } else if (APP_CONFIG.APP_NAME_FROM_FLASK) { // Chỉ cảnh báo nếu refreshButton thiếu khi có app
        console.warn("MAIN_MAPPING: Refresh graph button not found.");
    }
    console.log("MAIN_MAPPING: Admin Mapping Viewer page initialization script finished.");
});
