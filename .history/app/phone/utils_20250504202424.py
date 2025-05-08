# Nội dung file: app/utils.py
import json
import hashlib
import time
from flask import current_app # Để dùng logger

def _parse_coordinates_safe(coord_str: str | None) -> dict | None:
    """Hàm phụ trợ an toàn để parse tọa độ 'x,y'."""
    if not coord_str or ',' not in coord_str:
        return None
    try:
        x, y = map(int, coord_str.split(','))
        return {"x": x, "y": y}
    except (ValueError, TypeError):
        return None

def process_raw_ui_state(reported_ui_state: dict | None) -> dict | None:
    """
    Trích xuất và chuẩn hóa danh sách các element từ dữ liệu UI state thô
    để dùng trong việc tính screen_id và lưu trữ.
    Trả về dictionary chứa thông tin state đã xử lý hoặc None nếu lỗi.
    """
    logger = current_app.logger if current_app else print
    structured_elements = []

    if not isinstance(reported_ui_state, dict):
        logger.warning("process_raw_ui_state: reported_ui_state không phải là dict hoặc là None.")
        return None # Trả về None nếu đầu vào không hợp lệ

    # Trích xuất thông tin cơ bản
    timestamp = reported_ui_state.get('timestamp')
    package_name = reported_ui_state.get('package_name')
    activity_name = reported_ui_state.get('activity_name')

    # Lấy các danh sách element data
    ids = reported_ui_state.get('ids', [])
    texts = reported_ui_state.get('texts', [])
    coords_str = reported_ui_state.get('coords', [])
    class_names = reported_ui_state.get('class_names', [])
    content_descs = reported_ui_state.get('content_descs', [])

    # Kiểm tra kiểu dữ liệu và lấy độ dài an toàn
    valid_lists = True
    base_lists_len = []
    for lst in [ids, texts, coords_str]:
        if not isinstance(lst, list): valid_lists = False; break
        base_lists_len.append(len(lst))
    if not valid_lists:
         logger.warning("process_raw_ui_state: Một hoặc nhiều list cơ bản (ids, texts, coords) không phải là list.")
         return None # Không thể xử lý nếu thiếu list cơ bản

    min_len = min(base_lists_len) if base_lists_len else 0
    if len(set(base_lists_len)) > 1:
        logger.warning(f"process_raw_ui_state: Độ dài list cơ bản không khớp: {base_lists_len}. Dùng min_len={min_len}.")

    len_class_names = len(class_names) if isinstance(class_names, list) else 0
    len_content_descs = len(content_descs) if isinstance(content_descs, list) else 0

    # Xây dựng structured_elements
    for i in range(min_len):
        el_id = ids[i] if ids[i] else None
        id_type = 'resource-id'
        if not el_id:
            el_id = content_descs[i] if i < len_content_descs and content_descs[i] else None
            id_type = 'content-desc'
        # if not el_id: el_id = texts[i] if texts[i] else None; id_type = 'text' # Cân nhắc kỹ

        if el_id: # Chỉ xử lý nếu có ID
            element_entry = {
                'index': i, # Giữ lại index gốc nếu cần
                'element_id': el_id,
                'identifier_type': id_type,
                'element_type': class_names[i] if i < len_class_names and class_names[i] else None,
                'text_content': texts[i] if texts[i] else None,
                # Thêm các trường khác nếu cần xử lý ở đây
            }
            coordinates = _parse_coordinates_safe(coords_str[i])
            if coordinates:
                element_entry['coordinates'] = coordinates
            structured_elements.append(element_entry)

    structured_state = {
        "timestamp": timestamp,
        "package_name": package_name,
        "activity_name": activity_name,
        "elements": structured_elements # Danh sách element đã xử lý
    }
    logger.debug(f"process_raw_ui_state: Processed state for {package_name}. Found {len(structured_elements)} elements.")
    return structured_state


def determine_screen_id_from_state(processed_ui_state: dict | None) -> str | None:
    """
    Xác định screenId duy nhất từ dữ liệu UI state đã được xử lý bởi process_raw_ui_state.
    """
    logger = current_app.logger if current_app else print
    if not processed_ui_state or not isinstance(processed_ui_state, dict):
        logger.error("determine_screen_id: Invalid or empty processed_ui_state received.")
        return None

    app_name = processed_ui_state.get('package_name')
    activity_name = processed_ui_state.get('activity_name')
    elements = processed_ui_state.get('elements', [])

    if not app_name:
        logger.warning("determine_screen_id: Missing package_name.")
        return f"error_missing_pkg_{int(time.time())}"

    screen_id_generated = None
    try:
        # Tạo chuỗi đại diện cấu trúc, dùng identifier_type và element_id
        element_repr_list = sorted([
            f"id={el.get('element_id','_')};type={el.get('identifier_type','_')};cls={el.get('element_type','_')}"
            for el in elements if isinstance(el, dict)
        ])
        structure_string = f"{app_name}|{activity_name or 'UnknownActivity'}|{'|'.join(element_repr_list)}"
        # Dùng SHA256 và lấy một phần hex digest
        screen_id_generated = hashlib.sha256(structure_string.encode('utf-8')).hexdigest()[:24]

    except Exception as hash_err:
         logger.error(f"Error generating screen hash for {app_name}, activity {activity_name}: {hash_err}", exc_info=True)
         screen_id_generated = f"error_hash_{int(time.time())}"

    return screen_id_generated

# Thêm các hàm tiện ích khác vào đây nếu cần