// static/js/admin_mapping_viewer/config_mapping.js

export let APP_CONFIG = {
    APP_NAME_FROM_FLASK: '',
    CSRF_TOKEN: '',
    BASE_MAPPING_VIEWER_URL: '/admin/mapping/',
    URL_FOR_ADMIN_SCREEN_ELEMENTS: '',
    API_BASE_URLS: {
        MAPPING_DATA: '/admin/api/mapping_data',
        // Giá trị mặc định này PHẢI chứa __SCREEN_ID_PLACEHOLDER__
        SCREEN_ELEMENTS: '/admin/api/screen_elements_for_mapping/__SCREEN_ID_PLACEHOLDER__',
        UPDATE_TRANSITION: '/admin/api/mapping/transition/update/'
    },
    DOM_ELEMENT_IDS: {
        graphContainer: 'cyGraphContainer',
        loadingIndicator: 'loadingIndicator',
        selectionDetailsPanel: 'selectionDetailsPanel',
        detailsPanelTextContent: 'detailsPanelTextContent',
        detailsPanelActionsArea: 'detailsPanelActionsArea',
        detailsPanelScreenshotArea: 'detailsPanelScreenshotArea',
        detailsPanelScreenshotContainer: 'detailsPanelScreenshotContainer',
        detailsPanelScreenshotImage: 'detailsPanelScreenshotImage',
        appSelectForm: 'appSelectForm',
        appNameSelect: 'appNameSelect',
        loadGraphButton: 'loadGraphButton',
        refreshGraphButton: 'refreshGraphBtn',
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
        editTransitionStatusSelect: 'editTransitionStatusSelect',
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
        console.log("CONFIG_MAPPING: Default API_BASE_URLS.SCREEN_ELEMENTS:", APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS);
        return;
    }

    APP_CONFIG.APP_NAME_FROM_FLASK = pageConfig.appNameFromFlask || APP_CONFIG.APP_NAME_FROM_FLASK;
    APP_CONFIG.CSRF_TOKEN = pageConfig.csrfToken || APP_CONFIG.CSRF_TOKEN;
    APP_CONFIG.BASE_MAPPING_VIEWER_URL = pageConfig.baseMappingViewerUrl || APP_CONFIG.BASE_MAPPING_VIEWER_URL;
    APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS = pageConfig.urlForAdminScreenElements || APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS;

    if (pageConfig.apiBaseUrls) {
        console.log("CONFIG_MAPPING: pageConfig.apiBaseUrls.SCREEN_ELEMENTS from HTML:", pageConfig.apiBaseUrls.screenElements);
        APP_CONFIG.API_BASE_URLS = { ...APP_CONFIG.API_BASE_URLS, ...pageConfig.apiBaseUrls };
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.apiBaseUrls không được cung cấp.");
    }

    if (pageConfig.domElementIds && typeof pageConfig.domElementIds === 'object') {
        APP_CONFIG.DOM_ELEMENT_IDS = { ...APP_CONFIG.DOM_ELEMENT_IDS, ...pageConfig.domElementIds };
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.domElementIds không phải là object hoặc không được cung cấp.");
    }

    console.log("CONFIG_MAPPING: Final APP_CONFIG.API_BASE_URLS after initialization:", JSON.parse(JSON.stringify(APP_CONFIG.API_BASE_URLS)));

    const screenElementsUrl = APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS;
    console.log("CONFIG_MAPPING: CHECK - API_BASE_URLS.SCREEN_ELEMENTS:", screenElementsUrl, "(Type:", typeof screenElementsUrl, ")");
    if (!screenElementsUrl || typeof screenElementsUrl !== 'string' || !screenElementsUrl.includes('__SCREEN_ID_PLACEHOLDER__')) { // Đổi tên placeholder để dễ nhận diện
        console.error("CONFIG_MAPPING: CRITICAL - API_BASE_URLS.SCREEN_ELEMENTS không chứa '__SCREEN_ID_PLACEHOLDER__' hoặc không phải string! URL hiện tại:", screenElementsUrl);
    }

    const editModalId = APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal;
    console.log("CONFIG_MAPPING: CHECK - editTransitionModal ID from APP_CONFIG:", editModalId, "(Type:", typeof editModalId, ")");
    if (editModalId === undefined || typeof editModalId !== 'string' || editModalId.trim() === '') {
        console.error("CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal IS UNDEFINED hoặc không hợp lệ!");
    }
    // Kiểm tra các ID khác của modal
    if (!APP_CONFIG.DOM_ELEMENT_IDS.editTransitionActionTypeSelect) console.error("CONFIG_MAPPING: CRITICAL - editTransitionActionTypeSelect ID is missing in APP_CONFIG.DOM_ELEMENT_IDS");
    if (!APP_CONFIG.DOM_ELEMENT_IDS.editTransitionStatusSelect) console.error("CONFIG_MAPPING: CRITICAL - editTransitionStatusSelect ID is missing in APP_CONFIG.DOM_ELEMENT_IDS");
    if (!APP_CONFIG.DOM_ELEMENT_IDS.editTransitionForm) console.error("CONFIG_MAPPING: CRITICAL - editTransitionForm ID is missing in APP_CONFIG.DOM_ELEMENT_IDS");
    if (!APP_CONFIG.DOM_ELEMENT_IDS.saveTransitionChangesBtn) console.error("CONFIG_MAPPING: CRITICAL - saveTransitionChangesBtn ID is missing in APP_CONFIG.DOM_ELEMENT_IDS");
}