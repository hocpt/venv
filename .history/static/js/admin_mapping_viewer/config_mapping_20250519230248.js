// static/js/admin_mapping_viewer/config_mapping.js

export let APP_CONFIG = {
    APP_NAME_FROM_FLASK: '',
    CSRF_TOKEN: '',
    URL_FOR_ADMIN_SCREEN_ELEMENTS: '',
    API_BASE_URLS: {
        MAPPING_DATA: '/admin/api/mapping_data',
        SCREEN_ELEMENTS: '/admin/api/screen_elements_for_mapping/',
        UPDATE_TRANSITION: '/admin/api/mapping/transition/update/'
    },
    // Các giá trị mặc định này PHẢI KHỚP với các key được sử dụng trong các module JS khác
    // và các value của chúng PHẢI KHỚP với ID trong HTML.
    DOM_ELEMENT_IDS: {
        graphContainer: 'cyGraphContainer',
        loadingIndicator: 'loadingIndicator',
        panelTextContent: 'detailsPanelTextContent',
        panelActionsArea: 'detailsPanelActionsArea',
        panelScreenshotArea: 'detailsPanelScreenshotArea',
        panelScreenshotContainer: 'detailsPanelScreenshotContainer',
        panelScreenshotImage: 'detailsPanelScreenshotImage',
        appNameSelect: 'appNameSelect',
        loadGraphButton: 'loadGraphButton',
        refreshGraphButton: 'refreshGraphBtn',
        selectionDetailsPanel: 'selectionDetailsPanel',

        editTransitionModal: 'editTransitionModal',
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
        // Thêm các ID khác nếu cần
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
    if (!pageConfig) {
        console.warn("CONFIG_MAPPING: pageConfig không được cung cấp, sử dụng giá trị mặc định.");
        // Log APP_CONFIG.DOM_ELEMENT_IDS mặc định
        console.log("CONFIG_MAPPING: Default APP_CONFIG.DOM_ELEMENT_IDS:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
        return;
    }
    APP_CONFIG.APP_NAME_FROM_FLASK = pageConfig.appNameFromFlask || APP_CONFIG.APP_NAME_FROM_FLASK;
    APP_CONFIG.CSRF_TOKEN = pageConfig.csrfToken || APP_CONFIG.CSRF_TOKEN;
    APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS = pageConfig.urlForAdminScreenElements || APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS;

    if (pageConfig.apiBaseUrls) {
        APP_CONFIG.API_BASE_URLS = { ...APP_CONFIG.API_BASE_URLS, ...pageConfig.apiBaseUrls };
    }

    // Log pageConfig.domElementIds nhận được từ HTML
    console.log("CONFIG_MAPPING: pageConfig.domElementIds received from HTML:", JSON.parse(JSON.stringify(pageConfig.domElementIds)));

    if (pageConfig.domElementIds && typeof pageConfig.domElementIds === 'object') {
        // Ghi đè/merge cẩn thận, đảm bảo các key từ pageConfig được ưu tiên
        APP_CONFIG.DOM_ELEMENT_IDS = { ...APP_CONFIG.DOM_ELEMENT_IDS, ...pageConfig.domElementIds };
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.domElementIds không phải là object hoặc không được cung cấp. Sử dụng DOM_ELEMENT_IDS mặc định.");
    }

    console.log("CONFIG_MAPPING: Final APP_CONFIG.DOM_ELEMENT_IDS after merge:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
    console.log("CONFIG_MAPPING: Specifically, APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal is:", APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal);
    console.log("CONFIG_MAPPING: Specifically, APP_CONFIG.DOM_ELEMENT_IDS.graphContainer is:", APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
    console.log("CONFIG_MAPPING: Specifically, APP_CONFIG.DOM_ELEMENT_IDS.panelTextContent is:", APP_CONFIG.DOM_ELEMENT_IDS.panelTextContent);
}
