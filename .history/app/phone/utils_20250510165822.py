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

# Sửa lại hàm trong app/phone/utils.py

def process_raw_ui_state(reported_ui_state: dict | None) -> dict | None:
    """
    Trích xuất và chuẩn hóa element data.
    Đã sửa lỗi undefined variable cho content_descs và class_names.
    Đồng thời sao chép các key cấp cao khác (như screen_width, screen_height) từ input.
    """
    logger = current_app.logger if current_app else print
    if not isinstance(reported_ui_state, dict):
        logger.warning("process_raw_ui_state: reported_ui_state không phải là dictionary hoặc là None.")
        return None

    # Sao chép các key cấp cao quan trọng từ input
    processed_state = {
        "timestamp": reported_ui_state.get('timestamp'),
        "package_name": reported_ui_state.get('package_name'),
        "activity_name": reported_ui_state.get('activity_name'),
        "screen_width": reported_ui_state.get('screen_width'),
        "screen_height": reported_ui_state.get('screen_height'),
        # ... các key cấp cao khác nếu client gửi ...
        "elements": []
    }
    # Loại bỏ các key có giá trị None khỏi processed_state (trừ 'elements')
    processed_state = {k: v for k, v in processed_state.items() if v is not None or k == 'elements'}

    # Lấy danh sách các thuộc tính thô của elements
    ids = reported_ui_state.get('ids', [])
    texts = reported_ui_state.get('texts', [])
    coords_str = reported_ui_state.get('coords', [])
    # === SỬA LỖI: Lấy class_names và content_descs từ reported_ui_state ===
    class_names = reported_ui_state.get('class_names', [])
    content_descs = reported_ui_state.get('content_descs', [])
    # =====================================================================
    # Lấy các thuộc tính khác nếu client gửi (ví dụ)
    clickable_list = reported_ui_state.get('clickable', [])
    editable_list = reported_ui_state.get('editable', [])
    bounds_list = reported_ui_state.get('bounds', []) # Giả sử client gửi 'bounds' là list các chuỗi "[x1,y1][x2,y2]" hoặc list các dict

    # Kiểm tra kiểu dữ liệu cơ bản của các list
    if not all(isinstance(lst, list) for lst in [ids, texts, coords_str, class_names, content_descs]):
        logger.warning("process_raw_ui_state: Một trong các list ids, texts, coords, class_names, content_descs không hợp lệ.")
        processed_state['elements'] = []
        return processed_state

    # Xác định độ dài tối thiểu để tránh lỗi IndexError
    # min_len nên dựa trên các list chính như ids, texts, coords
    # các list phụ như class_names, content_descs sẽ được kiểm tra index khi truy cập
    min_len = min(len(ids), len(texts), len(coords_str))
    # Không cần dùng len_class_names, len_content_descs nữa, kiểm tra trực tiếp khi truy cập

    for i in range(min_len):
        el_id_raw = ids[i] if ids[i] else None
        id_type = 'resource-id'
        if not el_id_raw:
            # Kiểm tra content_descs[i] có tồn tại không trước khi truy cập
            el_id_raw = content_descs[i] if i < len(content_descs) and content_descs[i] else None
            id_type = 'content-desc'
        # Cân nhắc việc dùng text làm ID nếu cả resource-id và content-desc đều không có
        # if not el_id_raw: el_id_raw = texts[i] if texts[i] else None; id_type = 'text'

        if el_id_raw: # Chỉ xử lý nếu có ID (resource-id hoặc content-desc)
            element_entry = {
                'element_id': el_id_raw,
                'identifier_type': id_type,
                'element_type': class_names[i] if i < len(class_names) and class_names[i] else None,
                'text_content': texts[i] if texts[i] else None,
            }
            coordinates = _parse_coordinates_safe(coords_str[i])
            if coordinates:
                element_entry['coordinates'] = coordinates

            # Thêm các thuộc tính khác nếu client gửi và có giá trị
            if i < len(clickable_list) and clickable_list[i] is not None:
                element_entry['is_clickable_observed'] = bool(clickable_list[i]) # Chuyển thành boolean
            if i < len(editable_list) and editable_list[i] is not None:
                element_entry['is_editable_observed'] = bool(editable_list[i])

            # Xử lý bounds nếu có (cần chuẩn hóa định dạng bounds từ client)
            if i < len(bounds_list) and bounds_list[i]:
                # Giả sử bounds_list[i] là một dict {'left': x, 'top': y, 'right': x2, 'bottom': y2}
                # Hoặc là chuỗi "[x1,y1][x2,y2]" cần parse
                # Tạm thời gán trực tiếp, bạn cần chuẩn hóa nếu client gửi định dạng khác
                element_entry['bounds'] = bounds_list[i]

            # Bỏ các key có giá trị None
            element_entry_clean = {k:v for k, v in element_entry.items() if v is not None}
            processed_state["elements"].append(element_entry_clean)

    logger.debug(f"process_raw_ui_state: Đã xử lý state. Keys: {list(processed_state.keys())}. Số elements: {len(processed_state['elements'])}")
    return processed_state

# ... (hàm _parse_coordinates_safe và process_raw_ui_state giữ nguyên) ...


def determine_screen_id_from_state(processed_ui_state, app_name):
    activity_name = processed_ui_state.get('activity_name', 'UnknownActivity')

    # Giả sử processed_ui_state.elements là danh sách các dict phần tử đã được chuẩn hóa
    # hoặc processed_ui_state.get('simplified_elements')
    elements_for_hashing = processed_ui_state.get('elements', []) 
    # Nếu bạn có 'simplified_elements' riêng thì dùng nó

    contributing_features_for_hash = []
    string_to_hash_parts = []

    # Sắp xếp elements_for_hashing theo một key ổn định (ví dụ: xpath_id nếu có)
    # (Như logic đã thảo luận ở phản hồi trước)
    try:
        if all(el.get('xpath_id') is not None for el in elements_for_hashing): # Kiểm tra xem có xpath_id không
            elements_for_hashing.sort(key=lambda x: x.get('xpath_id'))
    except TypeError: # Xử lý lỗi nếu không sort được
        pass # Log warning

    for el_data in elements_for_hashing:
        element_feature_parts = []
        el_xpath_id = el_data.get('xpath_id') # Nên có từ process_raw_ui_state

        # Logic chọn thuộc tính để hash:
        # (Giữ lại logic ưu tiên resource-id, class_name, content-desc như phản hồi trước)
        if el_data.get('resource-id'):
            val = str(el_data['resource-id'])
            element_feature_parts.append(val)
            contributing_features_for_hash.append({
                'xpath_id': el_xpath_id, 'attribute': 'resource-id', 'value': val
            })

        if el_data.get('class_name'):
            val = str(el_data['class_name'])
            element_feature_parts.append(val)
            contributing_features_for_hash.append({
                'xpath_id': el_xpath_id, 'attribute': 'class_name', 'value': val
            })

        # Xem xét content-desc
        if el_data.get('content-desc'): # Hoặc contentDescription
            val = str(el_data['content-desc'])
            element_feature_parts.append(val)
            contributing_features_for_hash.append({
                'xpath_id': el_xpath_id, 'attribute': 'content-desc', 'value': val
            })

        # Có thể thêm các thuộc tính khác nếu chúng ổn định và quan trọng

        if element_feature_parts:
            string_to_hash_parts.append("[" + "|".join(sorted(element_feature_parts)) + "]")

    final_string_to_hash = "".join(string_to_hash_parts)
    structure_hash = hashlib.md5(final_string_to_hash.encode('utf-8')).hexdigest()
    screen_id = f"{app_name}-{activity_name}-{structure_hash}"

    return screen_id, structure_hash, contributing_features_for_hash, activity_name, final_string_to_hash
# ... (Các hàm tiện ích khác nếu có) ...
