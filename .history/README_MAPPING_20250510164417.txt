==============================================================
README: Chức năng Bản đồ Ứng dụng (App Mapping) - Tổng quan
==============================================================

Mục lục:
1. Tổng quan chức năng
2. Luồng dữ liệu và xử lý chính
3. Các thành phần và hàm liên quan
4. Các vấn đề đã gặp và giải pháp (Tóm tắt)
5. Điểm cần lưu ý cho phát triển tiếp theo

------------------------------
1. TỔNG QUAN CHỨC NĂNG
------------------------------

Hệ thống "App Mapping" nhằm mục đích:
- Thu thập dữ liệu về trạng thái giao diện người dùng (UI state) và các hành động (actions) từ client (ứng dụng di động/MacroDroid).
- Xử lý và lưu trữ dữ liệu này vào cơ sở dữ liệu đồ thị Neo4j để xây dựng một bản đồ trực quan về các màn hình (Screens) và các chuyển tiếp (Transitions) giữa chúng.
- Hiển thị bản đồ này trên giao diện admin (`/admin/mapping/`) bằng Cytoscape.js.
- Cho phép người dùng xem chi tiết từng màn hình, bao gồm ảnh chụp màn hình và các phần tử UI (elements) trên đó.
- Cho phép người dùng phân loại (classify) các elements và quản lý các khía cạnh khác của bản đồ.

-------------------------------------
2. LUỒNG DỮ LIỆU VÀ XỬ LÝ CHÍNH
-------------------------------------

Luồng dữ liệu cơ bản cho việc xây dựng bản đồ:

Client (Điện thoại/MacroDroid) --> Server API --> Controller --> Utils/GraphDB/DB --> Neo4j & PostgreSQL

**Chi tiết hơn:**

I. THU THẬP DỮ LIỆU TỪ CLIENT (EXPLORATION STEP):
   1. Client gửi yêu cầu POST đến `/phone/explore_step` (trong `app/phone/routes.py`).
   2. Payload JSON bao gồm:
      - `device_id`, `account_id`
      - `raw_ui_state`: Dữ liệu UI thô (ids, texts, coords, class_names, content_descs, và QUAN TRỌNG: `screen_width`, `screen_height` của màn hình gốc).
      - `screenshot_filename`: Tên file ảnh chụp màn hình đã được upload trước đó (thông qua API `/api/upload/screenshot`).
      - `previous_action` (tùy chọn): Thông tin về hành động trước đó dẫn đến state hiện tại.
   3. Route `/phone/explore_step` gọi hàm `controller.handle_explore_step` (trong `app/phone/controller.py`).

II. XỬ LÝ Ở SERVER (`controller.handle_explore_step`):
   1. **Xử lý UI State thô:** Gọi `utils.process_raw_ui_state` (trong `app/phone/utils.py`) để chuẩn hóa `raw_ui_state` thành `processed_ui_state`.
      - `process_raw_ui_state` cần sao chép các key quan trọng như `package_name`, `activity_name`, `screen_width`, `screen_height` và chuẩn hóa danh sách `elements`.
   2. **Xác định Screen ID:** Gọi `utils.determine_screen_id_from_state` để tạo `screen_id` duy nhất cho `processed_ui_state`.
   3. **Lấy thông tin cần thiết:** Trích xuất `app_name`, `activity_name`, `original_screen_width`, `original_screen_height` từ `processed_ui_state`.
   4. **Ghi log PostgreSQL (tùy chọn):** Gọi `db.add_phone_action_logs` (trong `app/database.py`) để lưu `processed_ui_state` (dưới dạng JSON) và thông tin hành động vào bảng `phone_action_log`.
   5. **Cập nhật Neo4j:**
      - Gọi `graph_db.merge_screen` (trong `app/graph_db.py`) với các tham số:
         - `screen_id` (đã xác định)
         - `app_name`, `activity_name`
         - `extracted_elements` (từ `processed_ui_state.elements`)
         - `screenshot_path` (tên file từ client)
         - `screen_width`, `screen_height` (kích thước gốc của màn hình)
      - Nếu có `previous_action`, gọi `graph_db.merge_transition` để tạo/cập nhật cạnh `:TRANSITION`.
   6. **Lập kế hoạch hành động tiếp theo (Planner):** Gọi hàm planner (ví dụ: `plan_intelligent_exploration_action` trong `app/ai_service.py` hoặc `plan_simple_exploration_action` trong `app/phone/controller.py`) để quyết định hành động kế tiếp.
   7. **Trả về Next Action:** Gửi `nextAction` cho client.

III. HIỂN THỊ BẢN ĐỒ TRÊN ADMIN UI (`/admin/mapping/`):
   1. Route `/admin/mapping/<app_name>` (trong `app/admin_routes.py`, hàm `admin_mapping_viewer`) được gọi.
   2. Template `admin_mapping_viewer.html` được render.
   3. **JavaScript trong `admin_mapping_viewer.html`:**
      - Gọi API `/admin/api/mapping_data?app_name=<app_name>` (hàm `api_get_app_graph_data` trong `admin_routes.py`).
      - **`api_get_app_graph_data`:**
         - Query Neo4j để lấy danh sách các node `:Screen` (bao gồm `screen_id`, `activity_name`, `status`, `element_count`, `screenshot_path`, và QUAN TRỌNG: `width` và `height` của màn hình gốc).
         - Query Neo4j để lấy danh sách các cạnh `:TRANSITION` (bao gồm `source`, `target`, và các thuộc tính của cạnh như `actionType`, `element_id` (của element gây ra transition), `macro_code`, `params_json_str`).
         - Tạo `screenshot_url` cho mỗi node Screen.
         - Trả về dữ liệu nodes và edges cho Cytoscape.
      - Cytoscape.js render bản đồ.
      - **Khi click vào một Node (Màn hình) trên bản đồ:**
         - Lấy `nodeData` (bao gồm `id`, `screenshot_url`, `original_width`, `original_height`).
         - Hiển thị thông tin text của node.
         - Hiển thị nút "Xem/Phân loại Elements" trỏ đến `/admin/screen/<screen_id>/elements`.
         - Nếu có `screenshot_url` và kích thước gốc:
            - Hiển thị ảnh chụp màn hình (thẻ `img#map-screenshot-image`).
            - Sau khi ảnh load và có `clientWidth`/`clientHeight` > 0:
               - Gọi API `/admin/api/screen_elements_for_mapping/<screen_id>` (hàm `api_get_screen_elements_for_mapping` trong `admin_routes.py`).
               - **`api_get_screen_elements_for_mapping`:**
                  - Query Neo4j (hàm `graph_db.get_elements_for_screen`) để lấy danh sách các node `:Element` liên kết với `:Screen` này. Mỗi element chứa các thuộc tính như `element_id`, `bounds_left/top/right/bottom` (hoặc `coordinate_x/y`), `element_type`, `text_content`.
                  - **QUAN TRỌNG:** Chuyển đổi các kiểu dữ liệu thời gian (DateTime) thành chuỗi ISO trước khi trả về JSON để tránh lỗi "not JSON serializable".
               - **JavaScript nhận `elementsData` và gọi `drawMapScreenOverlays`:**
                  - **`drawMapScreenOverlays`:**
                     - Tính toán `overallScaleX`, `overallScaleY` dựa trên `nodeOriginalWidth`, `nodeOriginalHeight` (từ `nodeData`) và `displayedImgWidth`, `displayedImgHeight` (kích thước ảnh trên web).
                     - Lặp qua `elementsData`, đọc tọa độ (`bounds_left/top/right/bottom` hoặc `coordinate_x/y` TÙY THEO CẤU TRÚC API TRẢ VỀ) và kích thước gốc.
                     - Scale các giá trị này bằng `overallScaleX/Y`.
                     - Tạo và đặt vị trí các `div.element-overlay`.
      - **Khi click vào một Cạnh (Transition) trên bản đồ:**
         - Lấy `edgeData` (bao gồm `source`, `target`, `action_type`, `element_id`, `params_json`, etc.).
         - Hiển thị thông tin chi tiết của cạnh.

IV. TRANG CHI TIẾT ELEMENTS (`/admin/screen/<screen_id>/elements`):
   1. Route (hàm `admin_screen_elements` trong `admin_routes.py`) được gọi.
   2. Lấy dữ liệu Screen từ Neo4j (`graph_db.get_screen_with_elements`), bao gồm `screenshot_path`, `app_name`, và QUAN TRỌNG: `width`, `height` (kích thước gốc của màn hình).
   3. Lấy danh sách elements chi tiết từ log PostgreSQL (`db.get_last_detailed_ui_state_for_screen`) để có cấu trúc UI mới nhất.
   4. Lấy thông tin phân loại và override từ PostgreSQL (`db.get_element_classifications_for_screen`).
   5. Hợp nhất dữ liệu, tạo `screenshot_url`.
   6. Truyền tất cả vào template `admin_screen_elements.html`.
   7. **JavaScript trong `admin_screen_elements.html` (`drawOverlays`):**
      - Sử dụng `original_screen_width`, `original_screen_height` (từ Neo4j, truyền qua backend) và `displayedImgWidth`, `displayedImgHeight` để tính `overallScaleX/Y`.
      - Lặp qua `tableElementsData` (lấy từ `data-element-info` trên bảng HTML, vốn được tạo từ `elements_list` ở backend).
      - Đọc tọa độ (`bounds` hoặc `coords` từ `elData`).
      - Scale và vẽ overlay.

-------------------------------------------
3. CÁC THÀNH PHẦN VÀ HÀM LIÊN QUAN CHÍNH
-------------------------------------------

**Client (Điện thoại/MacroDroid):**
- Gửi UI state (bao gồm `screen_width`, `screen_height`, `ids`, `texts`, `coords`, `class_names`, `content_descs`, `screenshot_filename`) đến `/phone/explore_step`.

**app/phone/routes.py:**
- `@phone_bp.route('/explore_step', methods=['POST'])`: Nhận dữ liệu từ client, gọi `controller.handle_explore_step`.

**app/phone/controller.py:**
- `handle_explore_step(...)`:
    - Gọi `utils.process_raw_ui_state`.
    - Gọi `utils.determine_screen_id_from_state`.
    - Trích xuất `app_name`, `activity_name`, `original_screen_width`, `original_screen_height`.
    - Gọi `graph_db.merge_screen` và `graph_db.merge_transition`.
    - Gọi planner.
- `plan_simple_exploration_action(...)` hoặc `plan_intelligent_exploration_action(...)`: Logic quyết định hành động tiếp theo.

**app/phone/utils.py:**
- `process_raw_ui_state(...)`: Chuẩn hóa `raw_ui_state` từ client, **QUAN TRỌNG:** phải giữ lại `screen_width`, `screen_height` và các thông tin cần thiết khác. Trả về `processed_ui_state`.
- `determine_screen_id_from_state(...)`: Tạo `screen_id` từ `processed_ui_state`.

**app/graph_db.py:**
- `get_driver()`: Lấy Neo4j driver.
- `merge_screen(screen_id, app_name, activity_name, extracted_elements, log_id, screenshot_path, screen_width, screen_height)`:
    - Tạo/cập nhật node `:Screen` với các thuộc tính nguyên thủy (bao gồm `width`, `height`).
    - Lặp qua `extracted_elements` (đã chuẩn hóa), tạo/cập nhật các node `:Element` và mối quan hệ `:HAS_ELEMENT` từ Screen đến Element.
- `merge_transition(source_screen_id, target_screen_id, app_name, action_details, ...)`: Tạo/cập nhật cạnh `:TRANSITION`.
- `get_screen_with_elements(screen_id)`: Lấy thuộc tính của node `:Screen` từ Neo4j (bao gồm `width`, `height`).
- `get_elements_for_screen(screen_id)`: Lấy danh sách các node `:Element` liên kết với một `:Screen`. **QUAN TRỌNG:** Chuyển đổi kiểu `DateTime` thành chuỗi ISO. Đảm bảo trả về cấu trúc tọa độ (`bounds` hoặc `coordinate_x/y`) mà JavaScript mong đợi.
- `get_distinct_app_names()`: Lấy danh sách app_name cho dropdown.

**app/admin_routes.py:**
- `@admin_bp.route('/mapping/<app_name>')` (`admin_mapping_viewer`): Render trang bản đồ.
- `@admin_bp.route('/api/mapping_data')` (`api_get_app_graph_data`):
    - Query Neo4j lấy nodes `:Screen` (bao gồm `id`, `activity_name`, `status`, `screenshot_path`, và quan trọng là `width`, `height` được alias thành `original_width`, `original_height`).
    - Query Neo4j lấy edges `:TRANSITION` (bao gồm `source`, `target`, và các thuộc tính cạnh).
    - Trả về JSON cho Cytoscape.
- `@admin_bp.route('/api/screen_elements_for_mapping/<screen_id>')` (`api_get_screen_elements_for_mapping`):
    - Gọi `graph_db.get_elements_for_screen(screen_id)`.
    - Trả về JSON danh sách elements.
- `@admin_bp.route('/screen/<screen_id>/elements')` (`admin_screen_elements`):
    - Lấy `screen_data` từ Neo4j (bao gồm `width`, `height` gốc).
    - Lấy `elements_list` chi tiết từ PostgreSQL (`db.get_last_detailed_ui_state_for_screen`).
    - Render template `admin_screen_elements.html`, truyền `original_screen_width`, `original_screen_height`.

**templates/admin_mapping_viewer.html (JavaScript):**
- Fetch dữ liệu từ `/api/mapping_data`.
- Render đồ thị Cytoscape.
- Khi click node:
    - Lấy `nodeData.original_width`, `nodeData.original_height`, `nodeData.screenshot_url`.
    - Hiển thị ảnh.
    - Fetch elements từ `/api/screen_elements_for_mapping/`.
    - Gọi `drawMapScreenOverlays()` với các tham số đúng.
- `drawMapScreenOverlays(imgElement, elementsData, nodeOriginalWidth, nodeOriginalHeight)`:
    - Tính `overallScaleX/Y`.
    - Lặp qua `elementsData`.
    - **QUAN TRỌNG:** Đọc tọa độ (`bounds_left/top/right/bottom` hoặc `coordinate_x/y`) từ `elData` cho khớp với cấu trúc API trả về.
    - Scale và vẽ overlay.

**templates/admin_screen_elements.html (JavaScript):**
- `drawOverlays()`: Logic tương tự `drawMapScreenOverlays` nhưng lấy `original_screen_width/height` từ biến Jinja render trực tiếp.

-------------------------------------------------
4. CÁC VẤN ĐỀ ĐÃ GẶP VÀ GIẢI PHÁP (TÓM TẮT)
-------------------------------------------------

- **Lỗi Neo4j TypeError khi lưu `elements` vào Screen node:**
    - **Nguyên nhân:** Cố gắng lưu list các dictionary (elements) vào một thuộc tính của node Neo4j.
    - **Giải pháp:** Sửa `graph_db.merge_screen` để tạo các node `:Element` riêng biệt và liên kết chúng với node `:Screen` bằng mối quan hệ `:HAS_ELEMENT`.
- **Overlay không đúng vị trí/kích thước trong `admin_screen_elements.html`:**
    - **Nguyên nhân ban đầu:** Thiếu `original_screen_width`, `original_screen_height`.
    - **Giải pháp ban đầu:** Client gửi kích thước, server lưu vào Neo4j, `admin_screen_elements` đọc từ Neo4j.
    - **Nguyên nhân tiếp theo:** Sai lệch do status bar/navigation bar, hoặc tọa độ client không tuyệt đối.
    - **Giải pháp hiện tại (đã hoạt động):** Xác định kích thước ảnh chụp màn hình thực tế (1080x2220) và sử dụng logic scale đơn giản `overallScaleX/Y` vì tọa độ client có vẻ đã là tuyệt đối hoặc client đã tự xử lý offset.
- **Ảnh không hiển thị / Overlay không vẽ trong `admin_mapping_viewer.html`:**
    - **Nguyên nhân:**
        - Ban đầu `nodeData` từ Cytoscape thiếu `original_width`/`height` do API `/api/mapping_data` không trả về. (ĐÃ SỬA)
        - Lỗi 500 khi gọi API `/api/screen_elements_for_mapping/` do lỗi `DateTime is not JSON serializable`. (ĐÃ SỬA bằng cách chuyển DateTime thành ISO string trong `graph_db.get_elements_for_screen`).
        - `clientWidth`/`clientHeight` của ảnh bằng 0 sau khi `load` do timing/CSS. (ĐÃ CẢI THIỆN bằng retry loop).
        - Logic trong `drawMapScreenOverlays` đọc sai cấu trúc `elData` (không có `bounds` object hay `coordinates` object, mà có `coordinate_x`, `coordinate_y` trực tiếp). (ĐANG CẦN SỬA TIẾP).
- **Mất nút "Xem/Phân loại Elements" trong `admin_mapping_viewer.html`:**
    - **Nguyên nhân:** Cách cập nhật `innerHTML` của panel chi tiết có thể ghi đè lẫn nhau.
    - **Giải pháp:** Chia panel chi tiết thành các `div` con và cập nhật từng phần riêng biệt (`selectionTextDetailsDiv`, `mapScreenshotDisplayArea`, `selectionActionsAreaDiv`). (ĐÃ ÁP DỤNG).

----------------------------------------------------
5. ĐIỂM CẦN LƯU Ý CHO PHÁT TRIỂN TIẾP THEO
----------------------------------------------------

- **Hoàn thiện `drawMapScreenOverlays` trong `admin_mapping_viewer.html`:**
    - Đảm bảo logic đọc `elData.coordinate_x`, `elData.coordinate_y` (và/hoặc `elData.bounds_left`...) là chính xác tuyệt đối với cấu trúc dữ liệu trả về từ API `/api/screen_elements_for_mapping/`.
    - Kiểm tra lại xem `graph_db.get_elements_for_screen` có thực sự trả về đầy đủ các thuộc tính cần thiết (`element_id`, `element_type`, `text_content`, và các thông tin tọa độ/bounds) cho mỗi element không.
- **Hiển thị thông tin cạnh (Transition) trong `admin_mapping_viewer.html`:**
    - Xác nhận API `/api/mapping_data` trả về đủ thuộc tính cho cạnh (`source`, `target`, `actionType`, `element_id` liên quan đến action, `macro_code`, `params_json_str`).
    - Kiểm tra JavaScript hiển thị các thông tin này.
- **Xóa Screenshot:** Triển khai logic xóa file ảnh screenshot trên server khi node `:Screen` tương ứng bị xóa khỏi Neo4j (như đã thảo luận).
- **Tính nhất quán của `screenshot_path`:** Đảm bảo `screenshot_path` lưu trong Neo4j (thường là tên file) được sử dụng nhất quán với `app_name` và `SCREENSHOT_STORAGE_PATH` (trong config) để có thể truy cập file ảnh từ các phần khác nhau của ứng dụng (ví dụ: khi xóa, khi hiển thị).
- **Tối ưu hóa:**
    - Nếu có quá nhiều elements trên một màn hình, việc vẽ nhiều overlay DOM có thể ảnh hưởng đến hiệu năng. Cân nhắc các kỹ thuật tối ưu nếu cần (ví dụ: vẽ lên canvas, chỉ vẽ overlay khi hover).
    - Truy vấn Neo4j có thể được tối ưu thêm.
- **Xử lý lỗi và độ tin cậy:** Tăng cường xử lý lỗi ở cả backend và frontend, đặc biệt là các cuộc gọi API và thao tác với DOM.
- **Client Data:** Đảm bảo client gửi lên đầy đủ và chính xác các thông tin cần thiết (đặc biệt là `screen_width`, `screen_height` và cấu trúc của `elements`).

==============================================================