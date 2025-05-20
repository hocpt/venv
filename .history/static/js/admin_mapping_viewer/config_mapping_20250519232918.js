// static/js/admin_mapping_viewer/config_mapping.js

export let APP_CONFIG = {
    APP_NAME_FROM_FLASK: '',
    CSRF_TOKEN: '',
    BASE_MAPPING_VIEWER_URL: '/admin/mapping/',
    URL_FOR_ADMIN_SCREEN_ELEMENTS: '',
    API_BASE_URLS: {
        MAPPING_DATA: '/admin/api/mapping_data',
        SCREEN_ELEMENTS: '/admin/api/screen_elements_for_mapping/',
        UPDATE_TRANSITION: '/admin/api/mapping/transition/update/'
    },
    DOM_ELEMENT_IDS: {
        // IDs cho các phần tử chính của trang
        graphContainer: 'cyGraphContainer',
        loadingIndicator: 'loadingIndicator',
        selectionDetailsPanel: 'selectionDetailsPanel',
        detailsPanelTextContent: 'detailsPanelTextContent',
        detailsPanelActionsArea: 'detailsPanelActionsArea',
        detailsPanelScreenshotArea: 'detailsPanelScreenshotArea',
        detailsPanelScreenshotContainer: 'detailsPanelScreenshotContainer',
        detailsPanelScreenshotImage: 'detailsPanelScreenshotImage',

        // IDs cho form chọn app
        appSelectForm: 'appSelectForm',
        appNameSelect: 'appNameSelect',
        loadGraphButton: 'loadGraphButton',
        refreshGraphButton: 'refreshGraphBtn',

        // IDs cho Modal Sửa Transition (phải khớp với HTML của modal)
        editTransitionModal: 'editTransitionModal', // Đảm bảo key này tồn tại và đúng
        editTransitionForm: 'editTransitionForm',
        saveTransitionChangesBtn: 'saveTransitionChangesBtn',
        editTransitionErrorMessages: 'editTransitionErrorMessages',
        editTransitionNeo4jIdInput: 'editTransitionNeo4jId',
        editTransitionSourceNodeInput: 'editTransitionSourceNode',
        editTransitionTargetNodeInput: 'editTransitionTargetNode',
        editTransitionActionTypeSelect: 'editTransitionActionType',
        editTransitionElementIdInput: 'editTransitionElementId',
        editTransitionIdentifierTypeInput: 'editTransitionIdentifierType',
        editTransitionElementTextInput: 'editTransitionElementText',
        editTransitionMacroCodeInput: 'editTransitionMacroCode',
        editTransitionParamsJsonTextarea: 'editTransitionParamsJson',
        editTransitionStatusSelect: 'editTransitionStatus',
        editTransitionAttemptCountInput: 'editTransitionAttemptCount',
        editTransitionSuccessCountInput: 'editTransitionSuccessCount'
    },
    DEFAULT_SIZES_FOR_OVERLAY: {
        'android.widget.Button': { width: 100, height: 40 },
        'android.widget.ImageButton': { width: 50, height: 50 },
        'android.widget.EditText': { width: 200, height: 40 },
        'android.widget.ImageView': { width: 50, height: 50 },
        'android.widget.TextView': { width: 150, height: 30 },
        'default': { width: 60, height: 30 }
    },
    VALID_ACTION_TYPES: [
        { value: "", label: "-- Chọn loại --" }, { value: "click", label: "Click" }, { value: "input", label: "Input Text" },
        { value: "swipe_up", label: "Swipe Up" }, { value: "swipe_down", label: "Swipe Down" }, { value: "swipe_left", label: "Swipe Left" },
        { value: "swipe_right", label: "Swipe Right" }, { value: "nav_go_back", label: "Go Back" }, { value: "start_app", label: "Start App" },
        { value: "run_macro", label: "Run Macro" }, { value: "other", label: "Khác" }
    ],
    VALID_TRANSITION_STATUSES: [
        { value: "provisional", label: "Provisional" }, { value: "confirmed", label: "Confirmed" }, { value: "failed", label: "Failed" },
        { value: "needs_review", label: "Needs Review" }, { value: "disabled", label: "Disabled" }
    ]
};

export function initializeAppConfig(pageConfig) {
    console.log("CONFIG_MAPPING: Starting initialization with pageConfig:", JSON.parse(JSON.stringify(pageConfig || {})));

    if (!pageConfig) {
        console.warn("CONFIG_MAPPING: pageConfig không được cung cấp. Sử dụng APP_CONFIG mặc định.");
        // Log APP_CONFIG.DOM_ELEMENT_IDS mặc định để so sánh
        console.log("CONFIG_MAPPING: Default APP_CONFIG.DOM_ELEMENT_IDS:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
        return;
    }

    APP_CONFIG.APP_NAME_FROM_FLASK = pageConfig.appNameFromFlask || APP_CONFIG.APP_NAME_FROM_FLASK;
    APP_CONFIG.CSRF_TOKEN = pageConfig.csrfToken || APP_CONFIG.CSRF_TOKEN;
    APP_CONFIG.BASE_MAPPING_VIEWER_URL = pageConfig.baseMappingViewerUrl || APP_CONFIG.BASE_MAPPING_VIEWER_URL;
    APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS = pageConfig.urlForAdminScreenElements || APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS;

    if (pageConfig.apiBaseUrls) {
        APP_CONFIG.API_BASE_URLS = { ...APP_CONFIG.API_BASE_URLS, ...pageConfig.apiBaseUrls };
    }

    // Log domElementIds nhận được từ HTML để debug
    console.log("CONFIG_MAPPING: pageConfig.domElementIds received from HTML:", JSON.parse(JSON.stringify(pageConfig.domElementIds || {})));

    if (pageConfig.domElementIds && typeof pageConfig.domElementIds === 'object') {
        // Ghi đè/merge cẩn thận, đảm bảo các key từ pageConfig được ưu tiên
        // và các key không có trong pageConfig vẫn giữ giá trị mặc định từ APP_CONFIG
        APP_CONFIG.DOM_ELEMENT_IDS = { ...APP_CONFIG.DOM_ELEMENT_IDS, ...pageConfig.domElementIds };
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.domElementIds không phải là object hoặc không được cung cấp. Sử dụng DOM_ELEMENT_IDS mặc định.");
    }

    // Log DOM_ELEMENT_IDS cuối cùng sau khi merge
    console.log("CONFIG_MAPPING: Final APP_CONFIG.DOM_ELEMENT_IDS after initialization:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));

    // Log cụ thể các ID quan trọng để kiểm tra
    console.log("CONFIG_MAPPING: CHECK - graphContainer ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
    console.log("CONFIG_MAPPING: CHECK - loadingIndicator ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
    console.log("CONFIG_MAPPING: CHECK - selectionDetailsPanel ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);
    console.log("CONFIG_MAPPING: CHECK - detailsPanelTextContent ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.detailsPanelTextContent);
    console.log("CONFIG_MAPPING: CHECK - editTransitionModal ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal);

    // Thêm kiểm tra và báo lỗi nếu các ID quan trọng là undefined sau khi khởi tạo
    if (APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal === undefined) {
        console.error("CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal IS UNDEFINED AFTER INITIALIZATION! Check HTML and config.");
    }
    if (APP_CONFIG.DOM_ELEMENT_IDS.graphContainer === undefined) { // Kiểm tra ID container đồ thị
        console.error("CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.graphContainer IS UNDEFINED AFTER INITIALIZATION! Check HTML and config.");
    }
    if (APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel === undefined) { // Kiểm tra ID panel chi tiết
        console.error("CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel IS UNDEFINED AFTER INITIALIZATION! Check HTML and config.");
    }
}
