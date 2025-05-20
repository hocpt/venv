// static/js/admin_mapping_viewer/config_mapping.js

export let APP_CONFIG = {
    APP_NAME_FROM_FLASK: '',
    CSRF_TOKEN: '',
    BASE_MAPPING_VIEWER_URL: '/admin/mapping/', // Giá trị mặc định nếu Flask không truyền
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
        appSelectForm: 'appSelectForm', // Thêm ID này
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
    DEFAULT_SIZES_FOR_OVERLAY: { /* ... như cũ ... */ },
    VALID_ACTION_TYPES: [ /* ... như cũ ... */],
    VALID_TRANSITION_STATUSES: [ /* ... như cũ ... */]
};

export function initializeAppConfig(pageConfig) {
    if (!pageConfig) {
        console.warn("CONFIG_MAPPING: pageConfig không được cung cấp, sử dụng giá trị mặc định.");
        console.log("CONFIG_MAPPING: Default APP_CONFIG.DOM_ELEMENT_IDS:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
        return;
    }
    APP_CONFIG.APP_NAME_FROM_FLASK = pageConfig.appNameFromFlask || APP_CONFIG.APP_NAME_FROM_FLASK;
    APP_CONFIG.CSRF_TOKEN = pageConfig.csrfToken || APP_CONFIG.CSRF_TOKEN;
    APP_CONFIG.BASE_MAPPING_VIEWER_URL = pageConfig.baseMappingViewerUrl || APP_CONFIG.BASE_MAPPING_VIEWER_URL; // Lấy base URL
    APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS = pageConfig.urlForAdminScreenElements || APP_CONFIG.URL_FOR_ADMIN_SCREEN_ELEMENTS;

    if (pageConfig.apiBaseUrls) {
        APP_CONFIG.API_BASE_URLS = { ...APP_CONFIG.API_BASE_URLS, ...pageConfig.apiBaseUrls };
    }

    console.log("CONFIG_MAPPING: pageConfig.domElementIds received from HTML:", JSON.parse(JSON.stringify(pageConfig.domElementIds || {})));

    if (pageConfig.domElementIds && typeof pageConfig.domElementIds === 'object') {
        APP_CONFIG.DOM_ELEMENT_IDS = { ...APP_CONFIG.DOM_ELEMENT_IDS, ...pageConfig.domElementIds };
    } else {
        console.warn("CONFIG_MAPPING: pageConfig.domElementIds không phải là object hoặc không được cung cấp. Sử dụng DOM_ELEMENT_IDS mặc định.");
    }

    console.log("CONFIG_MAPPING: Final APP_CONFIG.DOM_ELEMENT_IDS after merge:", JSON.parse(JSON.stringify(APP_CONFIG.DOM_ELEMENT_IDS)));
    console.log("CONFIG_MAPPING: Check - editTransitionModal ID should be 'editTransitionModal':", APP_CONFIG.DOM_ELEMENT_IDS.editTransitionModal);
    console.log("CONFIG_MAPPING: Check - graphContainer ID should be 'cyGraphContainer':", APP_CONFIG.DOM_ELEMENT_IDS.graphContainer);
}
