Tổng kết Dự án Tự động hóa HPT (Tính đến 10/05/2025)
============================================================================
README: Chức năng Bản đồ Ứng dụng (App Mapping) - Cập nhật & Hướng đi
============================================================================

Mục lục:
1. Trạng thái Hiện tại và Thành tựu
2. Các Vấn đề Cốt lõi và Mục tiêu (Tổng hợp từ `a.txt` và thảo luận)
3. Luồng Xử lý Dữ liệu Mapping (Đã cập nhật)
4. Các Thành phần và Hàm Chính Liên quan
5. Kế hoạch Hành động Tiếp theo (Ưu tiên)

--------------------------------------
1. TRẠNG THÁI HIỆN TẠI VÀ THÀNH TỰU
--------------------------------------

- **Hiển thị Overlay trên Ảnh:**
    - `admin_screen_elements.html`: Đã vẽ overlay thành công và chính xác tọa độ.
    - `admin_mapping_viewer.html`:
        - Đã hiển thị được ảnh chụp màn hình khi click node.
        - Đã lấy được `original_width`, `original_height` cho node.
        - Đã gọi API `/admin/api/screen_elements_for_mapping/` và nhận được danh sách elements.
        - **Đã vẽ overlay element thành công và chính xác tọa độ** trên ảnh trong panel chi tiết (dựa trên xác nhận mới nhất của bạn).
- **Hiển thị Thông tin Node/Cạnh:**
    - Thông tin text của Node (Màn hình) hiển thị đầy đủ.
    - Nút "Xem/Phân loại Elements" hiển thị và hoạt động.
    - **Vấn đề còn lại:** "Chi tiết Cạnh (Transition)" chưa hiển thị ID liên kết (source, target) hoặc các thông tin chi tiết khác của cạnh một cách rõ ràng.

-----------------------------------------------------------------
2. CÁC VẤN ĐỀ CỐT LÕI VÀ MỤC TIÊU (TỔNG HỢP)
-----------------------------------------------------------------

Đây là những điểm chính bạn muốn giải quyết để hệ thống mapping thông minh và dễ quản lý hơn:

A. **Nhận diện Màn hình (`screen_id`) và Cạnh (`:TRANSITION`) Chính xác và Ổn định:**
    - **Vấn đề:** Tránh việc server tạo ra `screen_id` và cạnh một cách "không chắc chắn". Cần cơ chế phân biệt màn hình dựa trên cấu trúc ổn định để quyết định tạo mới hay cập nhật node/cạnh đã có.
    - **Mục tiêu:** `screen_id` phải phản ánh đúng sự khác biệt hoặc tương đồng về cấu trúc của các màn hình.

B. **Minh bạch hóa Quá trình Tạo `screen_id`:**
    - **Yêu cầu:** Có một giao diện (UI) cho phép admin xem những thuộc tính element nào (IDs, text, loại, XPath) đã đóng góp vào việc tạo ra `structure_hash` (và từ đó là `screen_id`).
    - **Mục tiêu:** Giúp admin hiểu, phân tích, và có thể (gián tiếp) ảnh hưởng đến cách server nhận diện màn hình.

C. **Logic Quyết định Hành động cho Client (Planner) Thông minh:**
    - **Yêu cầu:**
        - Server cần biết client đang ở màn hình nào trên bản đồ.
        - Server đưa ra hành động tiếp theo một cách logic: khám phá các element/ID chưa được thử, ưu tiên khám phá các màn hình/element quan trọng, tránh tạo vòng lặp vô ích, và không tạo lại node đã có nếu `screen_id` được nhận diện đúng.
    - **Mục tiêu:** Tự động hóa quá trình khám phá một cách hiệu quả và toàn diện.

D. **Phân loại Element và Vai trò trong Mapping/Planner:**
    - **Câu hỏi:** Server phân tích và gán "Phân loại" cho element như thế nào? Phân loại này được sử dụng ra sao trong việc tạo bản đồ và ưu tiên hành động của planner? `structure_hash` có nên dựa vào phân loại không? Giải quyết sự khác biệt giữa "đã có cạnh" và "chưa có cạnh nhưng đã được phân loại thủ công".
    - **Mục tiêu:** Sử dụng thông tin phân loại element để tăng cường độ chính xác của mapping và sự thông minh của planner.

E. **Phân loại Node (Màn hình):**
    - **Yêu cầu:** Cần cơ chế phân loại cho cả node (màn hình) do admin gán thủ công (ví dụ: login_screen, profile_screen, v.v.).
    - **Mục tiêu:** Bổ sung ngữ cảnh cho các màn hình, hỗ trợ planner và phân tích.

F. **Quản lý Screenshots:**
    - **Yêu cầu:** Tự động xóa file screenshot trên server khi node `:Screen` tương ứng bị xóa (hoặc hợp nhất). Xử lý việc client tạo screenshot mới hay ghi đè khi server xác định node là mới hay đã tồn tại.
    - **Mục tiêu:** Quản lý tài nguyên ảnh hiệu quả, tránh lãng phí dung lượng.

---------------------------------------------------
3. LUỒNG XỬ LÝ DỮ LIỆU MAPPING (ĐÃ CẬP NHẬT)
---------------------------------------------------

I. THU THẬP DỮ LIỆU TỪ CLIENT (EXPLORATION STEP - API `/phone/explore_step`):
   1. Client gửi: `device_id`, `account_id`, `raw_ui_state` (chứa **elements thô**, **`screen_width`**, **`screen_height`**), `screenshot_filename`, `previous_action`.
   2. `controller.handle_explore_step` nhận request.

II. XỬ LÝ Ở SERVER (`controller.handle_explore_step`):
   1. **`utils.process_raw_ui_state(raw_ui_state)`:**
      - Chuẩn hóa `elements` thô.
      - **QUAN TRỌNG:** Tạo `xpath_id` (hoặc ID ổn định khác) cho mỗi element nếu client không cung cấp.
      - Giữ lại `package_name`, `activity_name`, `screen_width`, `screen_height` gốc.
      - Trả về `processed_ui_state`.
   2. **`utils.determine_screen_id_from_state(processed_ui_state)`:**
      - Tạo `structure_hash` dựa trên `app_name`, `activity_name`, và danh sách **`xpath_id` (đã sắp xếp)** của các elements quan trọng (hoặc tất cả).
      - Tạo `screen_id` từ `structure_hash`.
      - Trả về `screen_id`, `structure_hash_value`, `contributing_elements_details`.
   3. Trích xuất `app_name`, `activity_name`, `original_screen_width`, `original_screen_height`.
   4. (Tùy chọn) Ghi log `processed_ui_state` vào PostgreSQL (`phone_action_log`).
   5. **Cập nhật Neo4j:**
      - Gọi `graph_db.merge_screen` với:
         - `screen_id`, `app_name`, `activity_name`.
         - `extracted_elements` (từ `processed_ui_state.elements`, đã có `xpath_id`).
         - `screenshot_path`, `screen_width`, `screen_height`.
         - **`structure_hash_value`, `contributing_elements_details` để lưu vào node `:Screen`.**
      - `graph_db.merge_screen` sẽ:
         - `MERGE (s:Screen {screen_id: ...}) SET s.width = ..., s.height = ..., s.structure_hash = ..., s.contributing_elements = ...`.
         - Lặp qua elements, `MERGE (e:Element {screen_id: ..., element_id: xpath_id_cua_element}) SET e... = ...`.
         - `MERGE (s)-[:HAS_ELEMENT]->(e)`.
      - Nếu có `previous_action`, gọi `graph_db.merge_transition`, lưu `element_id` (là `xpath_id`) của element gây ra transition.
   6. Gọi Planner để quyết định `nextAction`.
   7. Trả về `nextAction` và `confirmedCurrentScreenId` cho client.

III. HIỂN THỊ TRÊN ADMIN UI:
   A. **`admin_mapping_viewer.html`:**
      1. JS gọi `/admin/api/mapping_data`.
      2. `api_get_app_graph_data`: Query Neo4j lấy nodes `:Screen` (lấy cả `width`, `height`, `screenshot_path`) và edges `:TRANSITION` (lấy cả `element_id` trên cạnh). Tạo `screenshot_url`.
      3. JS hiển thị bản đồ. Khi click node:
         - Lấy `original_width`, `original_height`, `screenshot_url` từ `nodeData`.
         - Hiển thị ảnh.
         - Gọi `/admin/api/screen_elements_for_mapping/<screen_id>`.
         - `api_get_screen_elements_for_mapping` gọi `graph_db.get_elements_for_screen`.
         - `graph_db.get_elements_for_screen`: Query các node `:Element` liên kết với `:Screen`. **Đảm bảo trả về dữ liệu tọa độ (`coordinate_x/y` hoặc `bounds_...`) và `element_id` (là `xpath_id`) mà JS `drawMapScreenOverlays` cần.** Chuyển đổi DateTime.
         - `drawMapScreenOverlays` vẽ overlay dựa trên tọa độ và kích thước gốc.
      4. Khi click cạnh: Hiển thị chi tiết cạnh, bao gồm `source`, `target`, `action_type`, `element_id` (của action).

   B. **`admin_screen_elements.html`:**
      1. `admin_screen_elements` (route):
         - Lấy `screen_data` từ Neo4j (bao gồm `width`, `height`, `screenshot_path`, **`structure_hash`**, **`contributing_elements`**).
         - Lấy `elements_list` từ PostgreSQL (log UI gần nhất).
         - Hợp nhất, tạo `screenshot_url`.
         - Truyền xuống template.
      2. Template hiển thị thông tin `structure_hash`, `contributing_elements`.
      3. JavaScript `drawOverlays` vẽ overlay.

IV. PHỤC VỤ VÀ XÓA SCREENSHOTS: Logic như đã thảo luận.

----------------------------------------------------------
4. CÁC THÀNH PHẦN VÀ HÀM CHÍNH (TẬP TRUNG MAPPING)
----------------------------------------------------------

- **Client:** Gửi `raw_ui_state` (với `screen_width`, `screen_height`, `elements` thô), `screenshot_filename`.
- **`app/phone/utils.py`:**
    - `process_raw_ui_state()`: **Tạo `xpath_id`**, chuẩn hóa elements, giữ lại `screen_width/height`.
    - `determine_screen_id_from_state()`: **Tạo `screen_id` từ `app_name, activity_name, list_xpath_ids_sorted`**. Trả về `screen_id`, `structure_hash`, `contributing_elements_details`.
- **`app/phone/controller.py`:**
    - `handle_explore_step()`: Điều phối chính, gọi utils, graph_db, planner.
- **`app/graph_db.py`:**
    - `merge_screen()`: Lưu `:Screen` (với `width`, `height`, `structure_hash`, `contributing_elements`), `:Element` (với `element_id` là `xpath_id`, `bounds`/`coords`), và `:HAS_ELEMENT`.
    - `merge_transition()`: Lưu `:TRANSITION` (với `element_id` là `xpath_id`).
    - `get_screen_with_elements()`: Lấy thuộc tính `:Screen` (bao gồm `width`, `height`, `structure_hash`, `contributing_elements`).
    - `get_elements_for_screen()`: Lấy các node `:Element` của một màn hình. **Quan trọng: trả về cấu trúc tọa độ (`coordinate_x/y` hoặc `bounds_...`) mà JS cần.**
- **`app/admin_routes.py`:**
    - `api_get_app_graph_data()`: Cung cấp dữ liệu cho Cytoscape (nodes có `original_width/height`, edges có chi tiết action).
    - `api_get_screen_elements_for_mapping()`: Cung cấp elements cho overlay trên map viewer.
    - `admin_screen_elements()`: Chuẩn bị dữ liệu cho trang chi tiết element, bao gồm thông tin debug `screen_id`.
- **Templates (JavaScript):**
    - `admin_mapping_viewer.html`: `drawMapScreenOverlays` vẽ overlay.
    - `admin_screen_elements.html`: `drawOverlays` vẽ overlay.

----------------------------------------------
5. KẾ HOẠCH HÀNH ĐỘNG TIẾP THEO (ƯU TIÊN)
----------------------------------------------

**GIAI ĐOẠN 1: HOÀN THIỆN NHẬN DIỆN SCREEN VÀ HIỂN THỊ CƠ BẢN (Đang thực hiện và gần xong)**

1.  **Đã hoàn thành (hoặc gần hoàn thành):**
    * `admin_mapping_viewer.html` hiển thị ảnh và nút "Xem/Phân loại".
    * Overlay element đã vẽ được thành công và chính xác trên `admin_mapping_viewer.html` (dựa trên xác nhận mới nhất của bạn là "đã vẽ thành công nhưng phần Chi tiết Cạnh...").

2.  **Cần làm ngay:**
    * **1.1. Hoàn thiện hiển thị "Chi tiết Cạnh (Transition)" trong `admin_mapping_viewer.html`:**
        * **Hành động:**
            1.  **Kiểm tra `edgeData` trong console:** Khi click vào một cạnh, log `edge.data()` ra. Xem nó có chứa `source`, `target`, `action_type`, `element_id` (ID của element gây ra action, nên là `xpath_id`), `macro_code`, `params_json` không.
            2.  **Nếu thiếu:** Sửa hàm `api_get_app_graph_data` (trong `admin_routes.py`) để câu lệnh Cypher query các cạnh lấy đủ các thuộc tính này từ mối quan hệ `:TRANSITION` và các node liên quan (nếu cần). Đảm bảo các thuộc tính này được đưa vào JSON response.
            3.  **Nếu đủ:** Sửa phần JavaScript tạo `edgeDetailsHtml` trong `admin_mapping_viewer.html` để hiển thị các thông tin này một cách rõ ràng.

    * **1.2. (Song song) Hoàn thiện `utils.process_raw_ui_state` để tạo `xpath_id` ổn định (nếu chưa hoàn hảo):**
        * **Hành động:** Xem xét lại logic tạo `xpath_id`. Nó có đủ mạnh để xử lý các thay đổi nhỏ về layout không? Có trường hợp nào client gửi ID ổn định hơn mà chúng ta có thể ưu tiên không?
        * Đảm bảo `xpath_id` này được sử dụng nhất quán làm `element_id` khi lưu vào node `:Element` và trên cạnh `:TRANSITION`.

    * **1.3. Hoàn thiện `utils.determine_screen_id_from_state`:**
        * **Hành động:** Đảm bảo hàm này sử dụng danh sách `xpath_id` (đã được sắp xếp) của các element quan trọng (hoặc tất cả) để tạo `structure_hash` và `screen_id`.
        * Đảm bảo nó trả về `structure_hash_value` và `contributing_elements_details` (ví dụ: list các `xpath_id` đã dùng).

    * **1.4. Cập nhật `graph_db.merge_screen`:**
        * **Hành động:** Đảm bảo hàm này nhận `structure_hash_value`, `contributing_elements_details` và lưu chúng vào thuộc tính của node `:Screen`.

    * **1.5. Hiển thị thông tin nhận dạng `screen_id` trên `admin_screen_elements.html`:**
        * **Hành động:** Backend lấy các thuộc tính debug này từ Neo4j và truyền xuống template. Frontend hiển thị chúng.

**SAU GIAI ĐOẠN 1, chúng ta sẽ có:**
* Overlay element hiển thị đúng trên cả hai trang.
* Thông tin chi tiết cạnh hiển thị đầy đủ trên map viewer.
* Cơ chế nhận diện `screen_id` ổn định hơn và minh bạch hơn.

Khi đó, chúng ta sẽ sẵn sàng để chuyển sang các giai đoạn tiếp theo như cải thiện Planner, phân loại node/element, và quản lý screenshot.

**Câu hỏi cho bạn để bắt đầu:**
Bạn muốn tập trung vào **1.1. Hoàn thiện hiển thị "Chi tiết Cạnh"** hay **1.2. Hoàn thiện `process_raw_ui_state` để tạo `xpath_id`** trước? Cả hai đều quan trọng. Nếu "Chi tiết Cạnh" chỉ là vấn đề hiển thị từ dữ liệu đã có thì có thể nhanh hơn.