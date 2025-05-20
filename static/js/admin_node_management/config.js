// static/js/admin_node_management/config.js

// APP_CONFIG sẽ được khởi tạo và điền giá trị trong main.js
// từ window.templatePageConfig (được nhúng từ Flask template)
export const APP_CONFIG = {
    API_MANAGED_NODES_URL: '',
    API_SCREEN_ELEMENTS_BASE_URL: '',
    API_CLASSIFY_NODE_BASE_URL: '',
    API_DELETE_NODE_BASE_URL: '',
    API_GET_PIE_CONDITIONS_URL: '',
    API_UPDATE_PIE_CONDITIONS_BASE_URL: '',
    API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL: '',
    SCREENSHOTS_BASE_URL: '',
    ADMIN_SCREEN_ELEMENTS_URL_BASE: '',
    CSRF_TOKEN: '',

    ELEMENT_ATTRIBUTES_FOR_PIE: [
        { value: "text", label: "Nội dung Text" },
        { value: "resource_id", label: "Resource ID" },
        { value: "description", label: "Content Desc." },
        { value: "class_name", label: "Class Name" },
        { value: "xpath", label: "XPath" }
    ],
    COMPARISON_TYPES_FOR_PIE: [
        { value: "EQUALS", label: "Bằng với (Equals)" },
        { value: "CONTAINS", label: "Chứa (Contains)" },
        { value: "STARTS_WITH", label: "Bắt đầu với (Starts With)" },
        { value: "ENDS_WITH", label: "Kết thúc với (Ends With)" },
        { value: "REGEX", label: "Khớp Regex" },
        { value: "EXISTS", label: "Tồn tại (Exists)" },
        { value: "NOT_EXISTS", label: "Không tồn tại (Not Exists)" }
    ],
    DEFAULT_SIZES_FOR_OVERLAY: { // Giữ lại nếu hàm vẽ overlay của bạn có dùng
        'android.widget.Button': { width: 100, height: 40 },
        'android.widget.ImageButton': { width: 50, height: 50 },
        // ... thêm các class khác nếu cần
        'default': { width: 60, height: 30 }
    },
    CSS_CLASSES: {
        MANAGE_PIE_TRIGGER: 'manage-pie-trigger',
        DEFINE_NEW_PIE_TRIGGER: 'define-new-pie-metadata-trigger',
        DELETE_NODE_BTN: 'delete-node-btn',
        NODE_CLASSIFICATION_SELECT: 'node-classification-select',
        SELECTED_FOR_PIE: 'selected-for-pie',
        ELEMENT_OVERLAY_INTERACTIVE: 'element-overlay-interactive',
        CONDITION_ITEM_ROW: 'condition-item-row'
    },
    ELEMENT_IDS: {
        NODES_TABLE_BODY: 'nodesTableBody',
        NODE_FILTER_FORM: 'nodeFilterForm',
        APP_NAME_FILTER_SELECT: 'app_name_filter_select_node',
        STATUS_FILTER_SELECT: 'filter_status_select',
        PAGINATION_CONTAINER: 'nodeManagementPagination',
        MANAGE_PIE_MODAL: 'managePieConditionsModal',
        MANAGE_PIE_LABEL: 'managePieConditionsModalLabel',
        MANAGE_PIE_CURRENT_SCREEN_ID: 'managePie_currentScreenIdDisplay',
        MANAGE_PIE_CURRENT_APP_NAME: 'managePie_currentAppNameDisplay',
        MANAGE_PIE_IMAGE_CONTAINER: 'pieConditionsImageContainer',
        MANAGE_PIE_SCREENSHOT: 'pieConditionsScreenshot',
        MANAGE_PIE_ELEMENT_TEXT_LIST: 'pieConditionsElementTextList',
        MANAGE_PIE_SELECTED_CONDITIONS_LIST: 'pieConditionsSelectedConditionsList',
        MANAGE_PIE_ADD_MANUAL_BTN: 'pieConditions_addManualConditionBtn',
        MANAGE_PIE_MAIN_ACTION_BTN: 'managePieConditions_mainActionBtn',
        MANAGE_PIE_ERROR_MESSAGES: 'managePieConditions_errorMessages',
        DEFINE_METADATA_MODAL: 'defineNewPieMetadataModal',
        DEFINE_METADATA_FORM: 'defineNewPieMetadataForm',
        METADATA_NODE_NEO4J_ID_INPUT: 'metadata_unknownNodeNeo4jId',
        METADATA_CURRENT_UNKNOWN_SCREEN_ID_INPUT: 'metadata_currentUnknownScreenId',
        METADATA_SELECTED_CONDITIONS_JSON_INPUT: 'metadata_selectedConditionsJson',
        METADATA_CURRENT_UNKNOWN_SCREEN_ID_DISPLAY: 'metadata_currentUnknownScreenIdDisplay',
        METADATA_APP_NAME_INPUT: 'metadata_appName',
        METADATA_ACTIVITY_NAME_INPUT: 'metadata_activityName',
        METADATA_LOGICAL_NAME_INPUT: 'metadata_logicalName',
        METADATA_NEW_DEFINED_SCREEN_ID_INPUT: 'metadata_newDefinedScreenId',
        METADATA_DESCRIPTION_INPUT: 'metadata_description',
        METADATA_CONDITIONS_COUNT_DISPLAY: 'metadata_conditionsCountDisplay',
        DEFINE_METADATA_ERROR_MESSAGES: 'defineMetadata_errorMessages',
        SAVE_NEW_PIE_DEFINITION_BTN: 'saveNewPieDefinitionBtn'
    }
};

export function initializeAppConfig(templateConfig) {
    if (templateConfig) {
        APP_CONFIG.API_MANAGED_NODES_URL = templateConfig.API_MANAGED_NODES_URL || APP_CONFIG.API_MANAGED_NODES_URL;
        APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL = templateConfig.API_SCREEN_ELEMENTS_BASE_URL || APP_CONFIG.API_SCREEN_ELEMENTS_BASE_URL;
        APP_CONFIG.API_CLASSIFY_NODE_BASE_URL = templateConfig.API_CLASSIFY_NODE_BASE_URL || APP_CONFIG.API_CLASSIFY_NODE_BASE_URL;
        APP_CONFIG.API_DELETE_NODE_BASE_URL = templateConfig.API_DELETE_NODE_BASE_URL || APP_CONFIG.API_DELETE_NODE_BASE_URL;
        APP_CONFIG.API_GET_PIE_CONDITIONS_URL = templateConfig.API_GET_PIE_CONDITIONS_URL || APP_CONFIG.API_GET_PIE_CONDITIONS_URL;
        APP_CONFIG.API_UPDATE_PIE_CONDITIONS_BASE_URL = templateConfig.API_UPDATE_PIE_CONDITIONS_BASE_URL || APP_CONFIG.API_UPDATE_PIE_CONDITIONS_BASE_URL;
        APP_CONFIG.API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL = templateConfig.API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL || APP_CONFIG.API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL;
        APP_CONFIG.SCREENSHOTS_BASE_URL = templateConfig.SCREENSHOTS_BASE_URL || APP_CONFIG.SCREENSHOTS_BASE_URL;
        APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE = templateConfig.ADMIN_SCREEN_ELEMENTS_URL_BASE || APP_CONFIG.ADMIN_SCREEN_ELEMENTS_URL_BASE;
        APP_CONFIG.CSRF_TOKEN = templateConfig.CSRF_TOKEN || APP_CONFIG.CSRF_TOKEN;
    }
}