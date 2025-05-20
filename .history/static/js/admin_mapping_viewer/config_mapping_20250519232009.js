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
        editTransitionModal: 'editTransitionModal', // Đảm bảo key này có giá trị mặc định đúng
        editTransitionForm: 'editTransitionForm',
        // ... (các ID khác của modal edit transition như đã định nghĩa trong HTML)
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
    DEFAULT_SIZES_FOR_OVERLAY: { /* ... như cũ ... */ },
    VALID_ACTION_TYPES: [ /* ... như cũ ... */],
    VALID_TRANSITION_STATUSES: [ /* ... như cũ ... */]
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
        APP_CONFIG.API_BASE_URLS = { ...APP_CONFIG.API_BASE_URLS, ...pageConfig.apiBaseUrls };
    }

    console.log("CONFIG_MAPPING: pageConfig.domElementIds received from HTML:", JSON.parse(JSON.stringify(pageConfig.domElementIds || {})));

    if (pageConfig.domElementIds && typeof pageConfig.domElementIds === 'object') {
        // Merge cẩn thận, ưu tiên giá trị từ pageConfig
        for (const key in pageConfig.domElementIds) {
            if (pageConfig.domElementIds.hasOwnProperty(key)) {
                APP_CONFIG.DOM_ELEMENT_IDS[key] = pageConfig.domElementIds[key];
            }
        }
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.domElementIds không phải là object hoặc không được cung cấp. DOM_ELEMENT_IDS có thể không đúng.");
    }

    console.log("CONFIG_MAPPING: Final APP_CONFIG.DOM_ELEMENT_IDS after initialization:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
    // Log cụ thể các ID quan trọng
    console.log("CONFIG_MAPPING: CHECK - graphContainer ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
    console.log("CONFIG_MAPPING: CHECK - loadingIndicator ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.loadingIndicator);
    console.log("CONFIG_MAPPING: CHECK - selectionDetailsPanel ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.selectionDetailsPanel);
    console.log("CONFIG_MAPPING: CHECK - detailsPanelTextContent ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.detailsPanelTextContent);
    console.log("CONFIG_MAPPING: CHECK - editTransitionModal ID from APP_CONFIG:", APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal);

    if (APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal === undefined) {
        console.error("CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal IS UNDEFINED AFTER INITIALIZATION!");
    }
    if (APP_CONFIG.DOM_ELEMENT_IDS.graphContainer === undefined) {
        console.error("CONFIG_MAPPING: CRITICAL - APP_CONFIG.DOM_ELEMENT_IDS.graphContainer IS UNDEFINED AFTER INITIALIZATION!");
    }

}
