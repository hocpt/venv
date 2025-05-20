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
        console.log("CONFIG_MAPPING: Default APP_CONFIG.DOM_ELEMENT_IDS:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
        return;
    }

    APP_CONFIG.APP_NAME_FROM_FLASK = pageConfig.appNameFromFlask || APP_CONFIG.APP_NAME_FROM_FLASK;
    APP_CONFIG.CSRF_TOKEN = pageConfig.csrfToken || APP_CONFIG.CSRF_TOKEN;
    APP_CONFIG.BASE_MAPPING_VIEWER_URL = pageConfig.baseMappingViewerUrl || APP_CONFIG.BASE_MAPPING_VIEWER_URL;
    APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS = pageConfig.urlForAdminScreenElements || APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS;

    if (pageConfig.apiBaseUrls) {
        APP_CONFIG.API_BASE_URLS.MAPPING_DATA = pageConfig.apiBaseUrls.mappingData || APP_CONFIG.API_BASE_URLS.MAPPING_DATA;
        // Đảm bảo key 'screenElements' khớp
        APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS = pageConfig.apiBaseUrls.screenElements || APP_CONFIG.API_BASE_URLS.SCREEN_ELEMENTS;
        APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION = pageConfig.apiBaseUrls.updateTransition || APP_CONFIG.API_BASE_URLS.UPDATE_TRANSITION;
    }

    console.log("CONFIG_MAPPING: pageConfig.domElementIds received from HTML:", JSON.parse(JSON.stringify(pageConfig.domElementIds || {})));

    if (pageConfig.domElementIds && typeof pageConfig.domElementIds === 'object') {
        APP_CONFIG.DOM_ELEMENT_IDS = { ...APP_CONFIG.DOM_ELEMENT_IDS, ...pageConfig.domElementIds };
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.domElementIds không phải là object hoặc không được cung cấp. DOM_ELEMENT_IDS có thể không đúng.");
    }

    console.log("CONFIG_MAPPING: Final APP_CONFIG.DOM_ELEMENT_IDS after initialization:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));

    // Log cụ thể các ID quan trọng để kiểm tra giá trị của chúng
    for (const key in APP_CONFIG.DOM_ELEMENT_IDS) {
        if (Object.hasOwnProperty.call(APP_CONFIG.DOM_ELEMENT_IDS, key)) {
            console.log(`CONFIG_MAPPING: CHECK - APP_CONFIG.DOM_ELEMENT_IDS.${key} = '${APP_CONFIG.DOM_ELEMENT_IDS[key]}' (Type: ${typeof APP_CONFIG.DOM_ELEMENT_IDS[key]})`);
            if (APP_CONFIG.DOM_ELEMENT_IDS[key] === undefined) {
                console.error(`CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.${key} IS UNDEFINED!`);
            }
        }
    }
}
