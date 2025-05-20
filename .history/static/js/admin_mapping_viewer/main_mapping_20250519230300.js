// static/js/admin_mapping_viewer/main_mapping.js
import { APP_CONFIG, initializeAppConfig } from './config_mapping.js';
import { initCytoscapeManager, fetchAndRenderGraph, updateEdgeInGraph } from './cytoscape_manager.js';
import { initDetailsPanelManager, showDefaultDetailsMessage } from './details_panel_manager.js'; // Import thêm showDefaultDetailsMessage
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

    // Các DOM elements chung, luôn cần
    const appNameSelect = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.appNameSelect);
    const loadGraphButton = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadGraphButton);
    const refreshButton = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.refreshGraphButton);

    // Khởi tạo modal sửa transition vì HTML của nó luôn có mặt
    // Truyền hàm callback để cập nhật đồ thị sau khi lưu thành công
    initEditTransitionModal(updateEdgeInGraph);

    if (APP_CONFIG.APP_NAME_FROM_FLASK) {
        console.log("MAIN_MAPPING: App name is present. Initializing full UI.");
        // Các module này chỉ nên được khởi tạo đầy đủ nếu các DOM elements của chúng tồn tại
        // (tức là khi một app đã được chọn và render)
        initDetailsPanelManager();
        initCytoscapeManager(APP_CONFIG.APP_NAME_FROM_FLASK); // Tải đồ thị ban đầu
    } else {
        console.log("MAIN_MAPPING: No app name selected initially. Displaying placeholder messages.");
        // Xử lý trường hợp không có app nào được chọn ban đầu
        // Các DOM elements này có thể không tồn tại nếu selected_app_name là false.
        // Chúng ta sẽ thử lấy chúng, nếu không có thì bỏ qua.
        const graphContainer = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
        const loadingIndicator = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
        const panelTextContentDiv = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.panelTextContent); // Sử dụng key đúng
        const selectionDetailsPanel = document.getElementById(APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);


        if (loadingIndicator) loadingIndicator.style.display = 'none';

        // Hiển thị thông báo trên các panel nếu chúng tồn tại (trường hợp {% else %} trong HTML)
        const initialMessageDiv = document.getElementById('initialMessage'); // Div này chỉ hiển thị khi không có app
        if (!initialMessageDiv) { // Nếu các div rỗng được render
            if (graphContainer) graphContainer.innerHTML = '<p class="text-center text-muted mt-5">Vui lòng chọn một ứng dụng để hiển thị bản đồ.</p>';
            if (panelTextContentDiv) { // panelTextContentDiv là con của selectionDetailsPanel
                panelTextContentDiv.innerHTML = '<p class="text-info fst-italic">Vui lòng chọn một ứng dụng từ danh sách thả xuống ở trên để xem bản đồ của nó.</p>';
            } else if (selectionDetailsPanel) { // Nếu chỉ có selectionDetailsPanel
                selectionDetailsPanel.innerHTML = '<p class="text-info fst-italic p-3">Vui lòng chọn một ứng dụng từ danh sách thả xuống ở trên để xem bản đồ của nó.</p>';
            }
        }
        // Không cần gọi showDefaultDetailsMessage() ở đây vì initDetailsPanelManager chưa được gọi.
    }

    if (loadGraphButton && appNameSelect) {
        loadGraphButton.addEventListener('click', function () {
            const selectedApp = appNameSelect.value;
            if (selectedApp) {
                let baseMappingUrl = "{{ url_for('admin.admin_mapping_viewer') }}";
                if (baseMappingUrl.endsWith('/mapping/') && !selectedApp.startsWith('/')) {
                    window.location.href = baseMappingUrl + encodeURIComponent(selectedApp);
                } else if (!baseMappingUrl.endsWith('/')) {
                    window.location.href = baseMappingUrl + '/' + encodeURIComponent(selectedApp);
                } else {
                    window.location.href = baseMappingUrl + encodeURIComponent(selectedApp);
                }
            } else {
                let baseMappingUrl = "{{ url_for('admin.admin_mapping_viewer') }}";
                // Đảm bảo URL không chứa app_name cũ
                const mappingBaseRegex = /\/admin\/mapping(\/)?([^\/]*)$/;
                const match = baseMappingUrl.match(mappingBaseRegex);
                if (match && match[1]) { // Nếu URL là /admin/mapping/some_app
                    window.location.href = baseMappingUrl.replace(match[2], ''); // Bỏ some_app
                } else if (match && !match[1] && !match[2]) { // Nếu URL là /admin/mapping
                    window.location.href = baseMappingUrl; // Giữ nguyên
                }
                else { // Fallback
                    window.location.href = "/admin/mapping/";
                }
            }
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener('click', function () {
            const currentApp = APP_CONFIG.APP_NAME_FROM_FLASK || (appNameSelect ? appNameSelect.value : null);
            if (currentApp) {
                console.log("MAIN_MAPPING: Refresh button clicked for app:", currentApp);
                if (typeof fetchAndRenderGraph === 'function') { // Đảm bảo hàm đã được export và import
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
