# Nội dung file: app/utils.py
import json
import hashlib
import os
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
    logger = current_app.logger if current_app else print # Giữ lại logger
    if not isinstance(reported_ui_state, dict):
        logger.warning("process_raw_ui_state: reported_ui_state không phải là dictionary hoặc là None.")
        return None

    processed_state = {
        "timestamp": reported_ui_state.get('timestamp'),
        "package_name": reported_ui_state.get('package_name'),
        "activity_name": reported_ui_state.get('activity_name'),
        "screen_width": reported_ui_state.get('screen_width'),
        "screen_height": reported_ui_state.get('screen_height'),
        "elements": []
    }
    processed_state = {k: v for k, v in processed_state.items() if v is not None or k == 'elements'}

    ids = reported_ui_state.get('ids', []) # Đây là resource-id từ client
    texts = reported_ui_state.get('texts', [])
    coords_str_list = reported_ui_state.get('coords', []) # Đổi tên để rõ là list
    class_names = reported_ui_state.get('class_names', [])
    # Client KHÔNG gửi content_descs, bounds theo thông tin mới của bạn

    if not all(isinstance(lst, list) for lst in [ids, texts, coords_str_list, class_names]):
        logger.warning("process_raw_ui_state: Một trong các list ids, texts, coords, class_names không hợp lệ.")
        return processed_state # Trả về state với elements rỗng

    min_len = min(len(ids), len(texts), len(coords_str_list), len(class_names))

    for i in range(min_len):
        element_id_val = None
        identifier_type_val = None

        raw_resource_id = ids[i]
        raw_text = texts[i]
        raw_class_name = class_names[i]

        if raw_resource_id and str(raw_resource_id).strip():
            element_id_val = str(raw_resource_id).strip()
            identifier_type_val = 'resource-id'
        elif raw_text and str(raw_text).strip() and raw_class_name and str(raw_class_name).strip():
            # Kết hợp text và class_name nếu không có resource-id
            # Để đơn giản, tạm thời chỉ dùng text nếu có, sau này có thể làm phức tạp hơn
            # element_id_val = f"{str(raw_class_name).strip()}_text={str(raw_text).strip()}" 
            # ĐƠN GIẢN HÓA: Ưu tiên dùng text làm ID nếu không có resource-id, cho mục đích khớp PIE
            element_id_val = str(raw_text).strip()
            identifier_type_val = 'text' # Hoặc 'text_only' để phân biệt với 'text_and_class' sau này
        elif raw_class_name and str(raw_class_name).strip(): # Nếu chỉ có class_name (ít dùng làm PIE)
            # Vẫn tạo để lưu trữ, nhưng có thể không dùng cho PIE
            element_id_val = f"class={str(raw_class_name).strip()}_idx={i}" # Thêm index để cố gắng làm duy nhất
            identifier_type_val = 'class_only_indexed'
        else:
            # Nếu không có thông tin gì để tạo ID, bỏ qua element này hoặc tạo ID ngẫu nhiên
            # logger.debug(f"Skipping element at index {i} due to lack of identifying information.")
            continue # Bỏ qua element này

        element_entry = {
            'element_id': element_id_val,
            'identifier_type': identifier_type_val,
            'element_type': raw_class_name if raw_class_name and str(raw_class_name).strip() else None,
            'text_content': raw_text if raw_text and str(raw_text).strip() else None,
        }

        coordinates = _parse_coordinates_safe(coords_str_list[i] if i < len(coords_str_list) else None)
        if coordinates:
            element_entry['coordinates'] = coordinates

        # Client không gửi bounds, clickable, editable theo thông tin mới
        # if i < len(clickable_list) and clickable_list[i] is not None:
        #     element_entry['is_clickable_observed'] = bool(clickable_list[i])
        # if i < len(editable_list) and editable_list[i] is not None:
        #     element_entry['is_editable_observed'] = bool(editable_list[i])

        element_entry_clean = {k:v for k, v in element_entry.items() if v is not None}
        if element_entry_clean.get('element_id'): # Chỉ thêm nếu có element_id thực sự
            processed_state["elements"].append(element_entry_clean)
            # logger.debug(f"Processed element: {element_entry_clean}")


    logger.debug(f"process_raw_ui_state: Extracted screen_width={processed_state.get('screen_width')}, screen_height={processed_state.get('screen_height')}. Processed {len(processed_state['elements'])} elements.")
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
def determine_screen_id_by_defined_pie(app_name: str, activity_name: str | None, 
                                       processed_elements_list: list, 
                                       db_get_screen_definitions_func) -> str | None:
    """
    Xác định screen_id dựa trên các PIE được định nghĩa trước trong CSDL.
    db_get_screen_definitions_func là hàm được truyền vào để lấy screen_definitions.
    """
    logger = current_app.logger if current_app else print
    if not app_name or not processed_elements_list:
        logger.warning("determine_screen_id_by_defined_pie: app_name hoặc processed_elements_list rỗng.")
        return None

    # Lấy các định nghĩa PIE từ DB (PostgreSQL)
    # Hàm get_screen_definitions_for_app cần được tạo trong app/database.py
    screen_definitions = db_get_screen_definitions_func(app_name, activity_name)

    if not screen_definitions:
        logger.debug(f"Không tìm thấy screen_definitions nào cho app: {app_name}, activity: {activity_name}")
        return None # Không có định nghĩa nào để khớp

    logger.debug(f"Tìm thấy {len(screen_definitions)} screen_definitions cho app: {app_name}, activity: {activity_name}")

    # Chuyển processed_elements_list thành một dạng dễ truy vấn hơn
    # Ví dụ: dict theo resource-id, dict theo text (cần xử lý text trùng lặp)
    elements_by_resource_id = {el['element_id']: el for el in processed_elements_list if el.get('identifier_type') == 'resource-id' and el.get('element_id')}
    elements_by_text_and_class = {} # Key: "text_value@class_value"
    for el in processed_elements_list:
        if el.get('text_content') and el.get('element_type'):
            key = f"{el['text_content']}@{el['element_type']}"
            if key not in elements_by_text_and_class: # Chỉ lấy cái đầu tiên nếu trùng
                elements_by_text_and_class[key] = el

    elements_by_text_only = {}
    for el in processed_elements_list:
        if el.get('text_content') and el.get('identifier_type') == 'text': # Giả sử type là 'text' cho text only
            key = el['text_content']
            if key not in elements_by_text_only:
                 elements_by_text_only[key] = el


    # Duyệt qua từng định nghĩa PIE
    for screen_def in screen_definitions:
        defined_screen_id = screen_def.get('defined_screen_id')
        pie_conditions_json = screen_def.get('identifying_elements_json')
        logical_name = screen_def.get('logical_screen_name')

        if not defined_screen_id or not pie_conditions_json:
            logger.warning(f"Bỏ qua screen_definition ID {screen_def.get('definition_id')} do thiếu defined_screen_id hoặc PIE JSON.")
            continue

        all_required_pies_match = True
        # logger.debug(f"Kiểm tra khớp với defined_screen_id: {defined_screen_id} ({logical_name}) với {len(pie_conditions_json)} PIE.")

        for pie_condition in pie_conditions_json:
            id_type = pie_condition.get('identifier_type')
            pie_value = pie_condition.get('value') # Cho resource-id, text
            pie_text_value = pie_condition.get('text_value') # Cho text_and_class
            pie_class_value = pie_condition.get('class_value') # Cho text_and_class
            presence = pie_condition.get('presence', 'required') # Mặc định là required

            element_found_for_this_pie = False
            if id_type == 'resource-id':
                if pie_value in elements_by_resource_id:
                    element_found_for_this_pie = True
            elif id_type == 'text_and_class':
                lookup_key = f"{pie_text_value}@{pie_class_value}"
                if lookup_key in elements_by_text_and_class:
                    element_found_for_this_pie = True
            elif id_type == 'text': # Nếu bạn định nghĩa PIE chỉ dựa vào text
                if pie_value in elements_by_text_only:
                    element_found_for_this_pie = True
            # Thêm các id_type khác nếu có

            if presence == 'required' and not element_found_for_this_pie:
                all_required_pies_match = False
                # logger.debug(f"  PIE BẮT BUỘC KHÔNG KHỚP cho {defined_screen_id}: {pie_condition}")
                break # Không cần kiểm tra các PIE khác của screen_def này nữa
            # logger.debug(f"  PIE Check for {defined_screen_id}: {pie_condition} -> Found: {element_found_for_this_pie}")


        if all_required_pies_match:
            logger.info(f"KHỚP! Screen state hiện tại khớp với defined_screen_id: '{defined_screen_id}' (Logical Name: '{logical_name}')")
            return defined_screen_id # Trả về defined_screen_id "chuẩn"

    logger.info(f"Không có defined_screen_id nào khớp cho app: {app_name}, activity: {activity_name} với state hiện tại.")
    return None 

def delete_screenshot_file_on_server(base_static_screenshots_path: str, filename: str, logger=None) -> tuple[bool, str | None]:
    if not logger: # Fallback logger nếu không được truyền
        import logging
        logger = logging.getLogger(__name__)

    if not base_static_screenshots_path or not filename:
        logger.warning("delete_screenshot_file_on_server: Thiếu base_static_screenshots_path hoặc filename.")
        return False, "Thiếu đường dẫn gốc hoặc filename."
    try:
        # Đường dẫn đầy đủ: C:\...\app\static\screenshots\image.png
        file_path = os.path.join(base_static_screenshots_path, filename) # Không còn app_name ở giữa

        logger.debug(f"Attempting to delete screenshot file: {file_path}")
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Đã xóa file: {file_path}")
            return True, None
        else:
            logger.warning(f"File không tồn tại để xóa: {file_path}")
            return False, "File không tồn tại."
    except Exception as e:
        logger.error(f"Lỗi khi xóa file {filename}: {e}", exc_info=True)
        return False, str(e)

