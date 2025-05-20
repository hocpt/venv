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

    // Luôn khởi tạo modal vì HTML của nó luôn được render (nằm ngoài khối if selected_app_name)
    // và nó cần được tham chiếu bởi APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal
    if (document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal)) {
        initEditTransitionModal(updateEdgeInGraph);
    } else {
        console.error("MAIN_MAPPING: Modal element '" + APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal + "' not found in DOM. Edit transition functionality will not work.");
    }


    if (APP_CONFIG.APP_NAME_FROM_FLASK) {
        console.log("MAIN_MAPPING: App name is present ('" + APP_CONFIG.APP_NAME_FROM_FLASK + "'). Initializing UI components that depend on specific DOM elements.");

        // Kiểm tra sự tồn tại của các container chính trước khi khởi tạo modules
        const graphContainerEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
        const detailsPanelEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);

        if (graphContainerEl) {
            initCytoscapeManager(APP_CONFIG.APP_NAME_FROM_FLASK);
        } else {
            console.error("MAIN_MAPPING: Graph container '" + APP_CONFIG.DOM_ELEMENT_IDS.graphContainer + "' not found. Cytoscape manager not initialized.");
        }

        if (detailsPanelEl) {
            initDetailsPanelManager();
        } else {
            console.error("MAIN_MAPPING: Details panel '" + APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel + "' not found. Details panel manager not initialized.");
        }

    } else {
        console.log("MAIN_MAPPING: No app name selected initially. Displaying placeholder messages if relevant divs exist.");
        const initialMessageDiv = document.getElementById('initialMessage');
        if (initialMessageDiv && initialMessageDiv.style.display !== 'none') {
            console.log("MAIN_MAPPING: Initial message div is visible.");
        }
        // Ẩn loading indicator nếu nó vô tình hiển thị
        const loadingIndicator = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    if (loadGraphButton && appNameSelect) {
        loadGraphButton.addEventListener('click', function () {
            const selectedApp = appNameSelect.value;
            let targetUrl = APP_CONFIG.BASE_MAPPING_VIEWER_URL;

            if (!targetUrl.endsWith('/')) {
                targetUrl += '/';
            }

            if (selectedApp) {
                window.location.href = targetUrl + encodeURIComponent(selectedApp);
            } else {
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
                    console.error("MAIN_MAPPING: fetchAndRenderGraph is not available. Cytoscape manager might not have initialized correctly.");
                }
            } else {
                alert("Vui lòng chọn một ứng dụng trước khi làm mới.");
            }
        });
    }
    console.log("MAIN_MAPPING: Admin Mapping Viewer page fully initialized.");
});
