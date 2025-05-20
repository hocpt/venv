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
    const editModalElement = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal);


    if (editModalElement) {
        console.log("MAIN_MAPPING: Edit transition modal element found. Initializing modal script.");
        initEditTransitionModal(updateEdgeInGraph);
    } else {
        console.error(`MAIN_MAPPING: Modal element với ID '${APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal}' không tìm thấy. Chức năng sửa transition sẽ không hoạt động.`);
    }

    if (APP_CONFIG.APP_NAME_FROM_FLASK) {
        console.log("MAIN_MAPPING: App name is present ('" + APP_CONFIG.APP_NAME_FROM_FLASK + "'). Attempting to initialize UI components.");

        // Kiểm tra sự tồn tại của các container chính TRƯỚC KHI gọi init của các module
        const graphContainerEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
        const detailsPanelEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);
        const loadingIndicatorEl = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);

        let canInitializeGraph = false;
        let canInitializeDetails = false;

        if (graphContainerEl && loadingIndicatorEl) {
            console.log("MAIN_MAPPING: Graph container và loading indicator ĐƯỢC TÌM THẤY.");
            canInitializeGraph = true;
        } else {
            console.error("MAIN_MAPPING: Graph container ('" + APP_CONFIG.DOM_ELEMENT_IDS.graphContainer +
                "') hoặc loading indicator ('" + APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator +
                "') KHÔNG TÌM THẤY. Cytoscape manager SẼ KHÔNG được khởi tạo.");
        }

        if (detailsPanelEl) {
            console.log("MAIN_MAPPING: Details panel ĐƯỢC TÌM THẤY.");
            canInitializeDetails = true;
        } else {
            console.error("MAIN_MAPPING: Details panel ('" + APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel +
                "') KHÔNG TÌM THẤY. Details panel manager SẼ KHÔNG được khởi tạo.");
        }

        if (canInitializeGraph) {
            initCytoscapeManager(APP_CONFIG.APP_NAME_FROM_FLASK);
        }
        if (canInitializeDetails) {
            initDetailsPanelManager();
        }

    } else {
        console.log("MAIN_MAPPING: No app name selected initially. Main UI components (graph, details) will not be initialized by main_mapping.js.");
        const initialMessageDiv = document.getElementById('initialMessage');
        if (initialMessageDiv && initialMessageDiv.style.display !== 'none') {
            console.log("MAIN_MAPPING: Initial message div is visible.");
        }
        const loadingIndicator = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    // ... (Gắn sự kiện cho loadGraphButton và refreshButton như cũ) ...
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
        console.warn("MAIN_MAPPING: Load graph button hoặc app name select không tìm thấy.");
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
    } else if (APP_CONFIG.APP_NAME_FROM_FLASK) {
        console.warn("MAIN_MAPPING: Refresh graph button ('" + APP_CONFIG.DOM_ELEMENT_IDS.refreshGraphButton + "') not found, but an app is selected.");
    }

    console.log("MAIN_MAPPING: Admin Mapping Viewer page initialization script finished.");
});
