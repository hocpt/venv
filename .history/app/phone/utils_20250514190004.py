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

def process_raw_ui_state(reported_ui_state: dict | None) -> dict | None:
    logger = current_app.logger if current_app else print
    if not isinstance(reported_ui_state, dict):
        logger.warning("process_raw_ui_state: reported_ui_state không phải là dictionary hoặc là None.")
        return None

    logger.debug(f"process_raw_ui_state: Input reported_ui_state keys: {list(reported_ui_state.keys())}")

    processed_state = {
        "timestamp": reported_ui_state.get('timestamp'),
        "package_name": reported_ui_state.get('package_name'),
        "activity_name": reported_ui_state.get('activity_name'),
        "screen_width": reported_ui_state.get('screen_width'),
        "screen_height": reported_ui_state.get('screen_height'),
        "elements": []
    }
    processed_state = {k: v for k, v in processed_state.items() if v is not None or k == 'elements'}

    ids = reported_ui_state.get('ids', []) 
    texts = reported_ui_state.get('texts', [])
    coords_str_list = reported_ui_state.get('coords', []) 
    class_names = reported_ui_state.get('class_names', []) # Vẫn lấy ra, có thể là list rỗng

    logger.debug(f"  Raw ids from client (first 5): {ids[:5]} (Total: {len(ids if ids else [])})")
    logger.debug(f"  Raw texts from client (first 5): {texts[:5]} (Total: {len(texts if texts else [])})")
    logger.debug(f"  Raw coords_str_list from client (first 5): {coords_str_list[:5]} (Total: {len(coords_str_list if coords_str_list else [])})")
    logger.debug(f"  Raw class_names from client (first 5): {class_names[:5]} (Total: {len(class_names if class_names else [])})")


    # Tính min_len dựa trên các list BẮT BUỘC phải có cùng độ dài (ví dụ: ids, texts, coords)
    # Class_names có thể tùy chọn.
    min_len = 0
    if ids is not None and texts is not None and coords_str_list is not None:
         # Giả sử ids, texts, coords luôn phải có cùng độ dài với nhau nếu client gửi đúng
         # Nếu một trong số này thiếu, client đã gửi sai dữ liệu cơ bản.
         if not (len(ids) == len(texts) == len(coords_str_list)):
             logger.warning(f"Độ dài của ids ({len(ids)}), texts ({len(texts)}), coords ({len(coords_str_list)}) không khớp! Sẽ dùng độ dài nhỏ nhất của 3 list này.")
             # Nếu muốn chặt chẽ hơn, có thể return None ở đây nếu độ dài không khớp.
             min_len = min(len(ids), len(texts), len(coords_str_list))
         else:
             min_len = len(ids) # Hoặc len(texts), len(coords_str_list)

    logger.debug(f"  Calculated min_len for element processing (based on ids, texts, coords): {min_len}")

    if min_len == 0 and (ids or texts or coords_str_list): # Có list chính nhưng min_len = 0 do không đồng bộ
        logger.error(f"  min_len is 0, but some core lists are not empty. This indicates a data mismatch from client.")
        # Có thể return None ở đây hoặc xử lý như không có element
    elif min_len == 0:
        logger.warning(f"  min_len is 0. No elements will be iterated and processed from core lists.")

    processed_elements_count = 0
    for i in range(min_len): 
        element_id_val = None
        identifier_type_val = None

        raw_resource_id = ids[i]
        raw_text = texts[i]
        # Lấy class_name một cách an toàn, chấp nhận nó có thể thiếu
        raw_class_name = class_names[i] if i < len(class_names) and class_names and class_names[i] else None

        # Logic chọn element_id_val và identifier_type_val
        if raw_resource_id and str(raw_resource_id).strip():
            element_id_val = str(raw_resource_id).strip()
            identifier_type_val = 'resource-id'
        elif raw_text and str(raw_text).strip(): # Nếu class_name không bắt buộc để tạo ID từ text
            element_id_val = str(raw_text).strip() 
            identifier_type_val = 'text' 
            # Nếu bạn MUỐN dùng text+class:
            # if raw_class_name and str(raw_class_name).strip():
            #    element_id_val = f"{str(raw_class_name).strip()}_text={str(raw_text).strip()}"
            #    identifier_type_val = 'text_and_class'
            # else: # Fallback nếu chỉ có text
            #    element_id_val = str(raw_text).strip()
            #    identifier_type_val = 'text_only_no_class'
        elif raw_class_name and str(raw_class_name).strip(): # Nếu chỉ có class_name
            element_id_val = f"class={str(raw_class_name).strip()}_idx={i}" 
            identifier_type_val = 'class_only_indexed'

        if element_id_val:
            element_entry = {
                'element_id': element_id_val,
                'identifier_type': identifier_type_val,
                'element_type': raw_class_name if raw_class_name else None, # Sẽ là None nếu class_names rỗng
                'text_content': raw_text if raw_text and str(raw_text).strip() else None,
            }

            current_coord_str = coords_str_list[i] # Sẽ không lỗi nếu i < min_len
            coordinates = _parse_coordinates_safe(current_coord_str)
            if coordinates:
                element_entry['coordinates'] = coordinates

            element_entry_clean = {k:v for k, v in element_entry.items() if v is not None}
            if element_entry_clean.get('element_id'):
                processed_state["elements"].append(element_entry_clean)
                processed_elements_count +=1

    logger.info(f"process_raw_ui_state: Finished processing. Added {processed_elements_count} elements to processed_state. Screen WxH: {processed_state.get('screen_width')}x{processed_state.get('screen_height')}")
    return processed_state

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

