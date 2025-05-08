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
    """Trích xuất và chuẩn hóa element data dùng tên chuẩn snake_case."""
    logger = current_app.logger if current_app else print
    if not isinstance(reported_ui_state, dict): return None

    processed_state = {
        "timestamp": reported_ui_state.get('timestamp'),
        "package_name": reported_ui_state.get('package_name'), # Dùng làm app_name sau này
        "activity_name": reported_ui_state.get('activity_name'),
        "elements": []
    }
    # ... (logic lấy ids, texts, coords_str, class_names, content_descs như trước) ...
    ids = reported_ui_state.get('ids', [])
    texts = reported_ui_state.get('texts', [])
    coords_str = reported_ui_state.get('coords', [])
    class_names = reported_ui_state.get('class_names', [])
    content_descs = reported_ui_state.get('content_descs', [])

    if not isinstance(ids, list) or not isinstance(texts, list) or not isinstance(coords_str, list):
         return None
    min_len = min(len(ids), len(texts), len(coords_str))
    len_class_names = len(class_names) if isinstance(class_names, list) else 0
    len_content_descs = len(content_descs) if isinstance(content_descs, list) else 0

    for i in range(min_len):
        el_id_raw = ids[i] if ids[i] else None
        id_type = 'resource-id'
        if not el_id_raw:
            el_id_raw = content_descs[i] if i < len_content_descs and content_descs[i] else None
            id_type = 'content-desc'
        # if not el_id_raw: el_id_raw = texts[i] if texts[i] else None; id_type = 'text'

        if el_id_raw:
            element_entry = {
                # <<< Dùng tên chuẩn snake_case >>>
                'element_id': el_id_raw,
                'identifier_type': id_type,
                'element_type': class_names[i] if i < len_class_names and class_names[i] else None,
                'text_content': texts[i] if texts[i] else None,
            }
            coordinates = _parse_coordinates_safe(coords_str[i])
            if coordinates:
                element_entry['coordinates'] = coordinates
            processed_state["elements"].append(element_entry)

    logger.debug(f"process_raw_ui_state: Processed {len(processed_state['elements'])} elements.")
    return processed_state



# ... (hàm _parse_coordinates_safe và process_raw_ui_state giữ nguyên) ...

def determine_screen_id_from_state(processed_ui_state: dict | None) -> str | None:
    """
    Xác định screen_id chuẩn hóa từ state đã xử lý.
    Cải thiện: Chỉ hash dựa trên các element có ID ổn định (resource-id hoặc content-desc).
    """
    logger = current_app.logger if current_app else print
    if not processed_ui_state or not isinstance(processed_ui_state, dict):
        logger.warning("determine_screen_id: Input state không hợp lệ hoặc None.")
        return None

    app_name = processed_ui_state.get('package_name')
    activity_name = processed_ui_state.get('activity_name')
    elements = processed_ui_state.get('elements', []) # elements đã chuẩn hóa tên

    if not app_name:
        # Vẫn cần app_name để phân biệt các app khác nhau
        timestamp_fallback = int(time.time())
        logger.error(f"determine_screen_id: Thiếu package_name trong state. Tạo ID lỗi: error_missing_pkg_{timestamp_fallback}")
        return f"error_missing_pkg_{timestamp_fallback}"

    try:
        # --- LỌC VÀ CHỌN LỌC THUỘC TÍNH ---
        stable_element_identifiers = []
        for el in elements:
            if isinstance(el, dict):
                el_id = el.get('element_id')
                id_type = el.get('identifier_type')

                # Chỉ xem xét các element có ID và loại ID là resource-id hoặc content-desc
                if el_id and id_type in ['resource-id', 'content-desc']:
                    # Chỉ lấy ID và loại ID để đưa vào hash
                    stable_element_identifiers.append(f"id={el_id};type={id_type}")
                    # BỎ QUA 'element_type' và 'text_content' khỏi việc tạo ID

        # Sắp xếp các định danh đã lọc để đảm bảo thứ tự không ảnh hưởng đến hash
        stable_element_identifiers.sort()

        # Tạo chuỗi cấu trúc chỉ từ các thành phần ổn định
        # Bao gồm app_name và activity_name (quan trọng)
        structure_string = f"{app_name}|{activity_name or 'UnknownActivity'}|{'|'.join(stable_element_identifiers)}"

        # Dùng SHA256 (giữ nguyên)
        screen_id_generated = hashlib.sha256(structure_string.encode('utf-8')).hexdigest()[:24] # Giữ độ dài 24 ký tự
        logger.debug(f"Generated screen_id '{screen_id_generated}' based on {len(stable_element_identifiers)} stable elements for app '{app_name}'.")

    except Exception as hash_err:
         timestamp_fallback = int(time.time())
         logger.error(f"Error generating screen hash for app {app_name}: {hash_err}", exc_info=True)
         screen_id_generated = f"error_hash_{timestamp_fallback}"

    return screen_id_generated

# ... (Các hàm tiện ích khác nếu có) ...
