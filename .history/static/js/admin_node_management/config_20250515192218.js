window.APP_CONFIG = {
    API_MANAGED_NODES_URL: "{{ url_for('admin.api_get_managed_nodes') }}",
    API_SCREEN_ELEMENTS_BASE_URL: "{{ url_for('admin.api_get_screen_elements_for_mapping', screen_id='SCREEN_ID_PLACEHOLDER') }}",
    API_CLASSIFY_NODE_BASE_URL: "{{ url_for('admin.api_classify_managed_node', screen_id='SCREEN_ID_PLACEHOLDER') }}",
    API_DELETE_NODE_BASE_URL: "{{ url_for('admin.api_delete_managed_node', screen_id='SCREEN_ID_PLACEHOLDER') }}",
    API_GET_PIE_CONDITIONS_URL: "{{ url_for('admin.api_get_pie_definition_conditions') }}",
    API_UPDATE_PIE_CONDITIONS_BASE_URL: "{{ url_for('admin.index') }}api/pie_definition",
    API_DEFINE_NEW_PIE_WITH_CONDITIONS_URL: "{{ url_for('admin.api_define_new_pie_and_update_node') }}",
    SCREENSHOTS_BASE_URL: "{{ url_for('static', filename=config.SCREENSHOTS_SUBDIR_IN_STATIC if config.SCREENSHOTS_SUBDIR_IN_STATIC else 'screenshots') }}/",
    ADMIN_SCREEN_ELEMENTS_URL_BASE: "{{ url_for('admin.admin_screen_elements', screen_id='SCREEN_ID_PLACEHOLDER') }}",
    CSRF_TOKEN: document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '{{ csrf_token() if csrf_token else "" }}',
    ELEMENT_ATTRIBUTES_FOR_PIE: [ /* ... */],
    COMPARISON_TYPES_FOR_PIE: [ /* ... */],
    DEFAULT_SIZES_FOR_OVERLAY: { /* ... */ }
};