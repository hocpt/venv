// static/js/admin_mapping_viewer/main_mapping.js
import { APP_CONFIG, initializeAppConfig } from './config_mapping.js';
import { initCytoscapeManager, fetchAndRenderGraph, updateEdgeInGraph } from './cytoscape_manager.js';
import { initDetailsPanelManager } from './details_panel_manager.js';
import { initEditTransitionModal } from './modal_edit_transition.js';

document.addEventListener("DOMContentLoaded", function () {
    // 1. Khởi tạo cấu hình từ window.templatePageConfig (được nhúng bởi Flask)
    if (typeof window.templatePageConfig !== 'undefined') {
        initializeAppConfig(window.templatePageConfig);
    } else {
        console.warn("MAIN_MAPPING: window.templatePageConfig không được định nghĩa. Sử dụng cấu hình mặc định.");
        initializeAppConfig({}); // Khởi tạo với object rỗng để APP_CONFIG có giá trị
    }

    // 2. Khởi tạo các modules
    initDetailsPanelManager();

    // Truyền hàm updateEdgeInGraph từ cytoscape_manager vào initEditTransitionModal
    // để modal có thể gọi lại khi lưu thành công.
    initEditTransitionModal(updateEdgeInGraph);

    initCytoscapeManager(APP_CONFIG.APP_NAME_FROM_FLASK); // Tải đồ thị ban đầu nếu appName có sẵn

    // 3. Gắn sự kiện cho các nút điều khiển chung của trang
    const appNameSelect = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.appNameSelect);
    const loadGraphButton = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadGraphButton);
    const refreshButton = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.refreshGraphButton);

    if (loadGraphButton && appNameSelect) {
        loadGraphButton.addEventListener('click', function () {
            const selectedApp = appNameSelect.value;
            if (selectedApp) {
                // Xây dựng URL mới và điều hướng để tải lại trang với app_name mới
                // Điều này đơn giản hơn là cố gắng thay đổi app_name và fetch lại trong cùng một trang
                // nếu URL của bạn có dạng /admin/mapping/<app_name>
                let baseMappingUrl = "{{ url_for('admin.admin_mapping_viewer') }}"; // Lấy từ Flask nếu có thể, hoặc hardcode
                if (baseMappingUrl.endsWith('/mapping/') && !selectedApp.startsWith('/')) {
                    window.location.href = baseMappingUrl + encodeURIComponent(selectedApp);
                } else if (!baseMappingUrl.endsWith('/')) { // Đảm bảo có dấu /
                    window.location.href = baseMappingUrl + '/' + encodeURIComponent(selectedApp);
                } else {
                    window.location.href = baseMappingUrl + encodeURIComponent(selectedApp);
                }
            } else {
                // Nếu không chọn app nào, có thể điều hướng về trang mapping cơ sở
                let baseMappingUrl = "{{ url_for('admin.admin_mapping_viewer') }}";
                if (baseMappingUrl.endsWith('/mapping/') || baseMappingUrl.endsWith('/mapping')) {
                    window.location.href = baseMappingUrl.replace(/\/mapping\/.*/, '/mapping/');
                } else {
                    window.location.href = "/admin/mapping/"; // Fallback
                }
            }
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener('click', function () {
            const currentApp = APP_CONFIG.APP_NAME_FROM_FLASK || (appNameSelect ? appNameSelect.value : null);
            if (currentApp) {
                console.log("MAIN_MAPPING: Refresh button clicked for app:", currentApp);
                fetchAndRenderGraph(currentApp); // Gọi hàm từ cytoscape_manager
            } else {
                alert("Vui lòng chọn một ứng dụng trước khi làm mới.");
            }
        });
    }
    console.log("MAIN_MAPPING: Admin Mapping Viewer page fully initialized.");
});
