# README: Phát triển Giao diện Admin cho Chức năng App Mapping

Ngày cập nhật: 15-05-2025

## Mục tiêu chung

Xây dựng các giao diện quản trị (Admin UI) cho phép người dùng quản lý và tinh chỉnh quá trình tạo bản đồ ứng dụng (App Mapping), bao gồm việc định nghĩa cách nhận diện các màn hình (Screens) và xử lý các vấn đề liên quan đến Nodes (Screens) và Transitions (Edges) trong bản đồ.

## I. Trang "Định nghĩa Nhận diện Màn hình (PIE)"

* **URL:** `/admin/mapping/screen-definitions`
* **File Template:** `templates/admin_screen_definitions.html`
* **Backend:** `app/admin_routes.py` (route `view_screen_definitions` và các API CRUD), `app/database.py` (tương tác với bảng `screen_definitions` trong PostgreSQL).
* **Mục đích:** Cho phép admin tạo, xem, sửa, xóa các "Định nghĩa PIE" (Primary Identifying Elements). Mỗi định nghĩa này là một bộ quy tắc (dựa trên `resource-id` hoặc `text` của elements) để hệ thống nhận diện một màn hình logic cụ thể và gán cho nó một `Defined Screen ID` (do admin đặt, phải duy nhất cho mỗi app).

* **Các Vấn đề UI & Tính năng Đã/Đang Xử lý:**
    1.  **Hiển thị danh sách Định nghĩa PIE:**
        * [OK] Bảng hiển thị các cột: `ID Định nghĩa` (PostgreSQL), `App Name`, `Activity Name`, `Tên Logic Màn hình`, `Defined Screen ID`, `Số PIE Conditions`, `Mô tả`, `Hành động`.
        * [OK] Lọc theo `App Name` (dropdown lấy từ các `app_name` đã có trong bảng).
        * [OK] Hỗ trợ tùy chọn "-- Tất cả Apps --" để xem tất cả định nghĩa (có phân trang).
    2.  **Modal "Thêm/Sửa Định nghĩa PIE":**
        * [OK] Form nhập liệu cho `App Name`, `Activity Name`, `Tên Logic`, `Defined Screen ID`, `Mô tả`.
        * [OK] Khu vực quản lý động "PIE Conditions" (`identifying_elements_json`):
            * Cho phép thêm/sửa/xóa các dòng điều kiện.
            * Mỗi dòng cho phép chọn "Loại Định danh" (`Resource ID`, `Chỉ Text` - do client hiện không gửi `class_name`), nhập "Giá trị Định danh", và chọn "Sự hiện diện" (`Required`).
            * JavaScript tự động ẩn/hiện các input "Giá trị" dựa trên "Loại Định danh" được chọn.
        * **Khi Sửa:**
            * [OK] Các trường `App Name`, `Activity Name`, `Defined Screen ID` được thiết kế là **chỉ đọc (readonly)** để đảm bảo tính nhất quán với các Node Neo4j đã được nhận diện bằng `Defined Screen ID` đó.
            * [OK] Chỉ cho phép sửa `Tên Logic Màn hình`, `Mô tả`, và danh sách "PIE Conditions".
    3.  **Layout Nút "Hành động":**
        * [ĐÃ SỬA] Các nút "Sửa", "Xóa" đã được đặt đúng vào cột "Hành động" của bảng.
    4.  **Truy cập trang:**
        * [OK] Đã thêm mục menu "Định nghĩa PIE" trong `admin_base.html`.
    5.  **Lỗi `TypeError` khi render `definition.description` và `definition.identifying_elements_json`:**
        * [ĐÃ SỬA] Đã xử lý trong template Jinja2 bằng cách dùng `(variable | default('')) | filter` hoặc `(variable or []) | length`.

## II. Trang "Quản lý Vấn đề Node (Screens)"

* **URL:** `/admin/mapping/node-management`
* **File Template:** `templates/admin_node_management.html`
* **Backend:** `app/admin_routes.py` (route `view_node_management` và các API liên quan), `app/graph_db.py` (tương tác Neo4j), `app/database.py` (tham chiếu `screen_definitions`).
* **Mục đích:** Trung tâm để admin xem xét các Node `:Screen` thực tế trong Neo4j, phân biệt Node "defined" và "unknown", và thực hiện các hành động quản lý.

* **Các Vấn đề UI & Tính năng Đã/Đang Xử lý:**
    1.  **Hiển thị danh sách Node:**
        * [OK] Bảng hiển thị các cột: `Checkbox`, `Screen ID`, `App Name`, `Activity`, `Ảnh thumbnail`, `Tên Logic PIE` (nếu defined), `Status`, `Phân loại Node`, `Số Elements`, `Số Transitions`, `Lần cuối thấy`, `Hành động`.
        * [OK] Lọc theo `App Name` và `Status` Node.
        * [OK] Phân trang (server-side rendering cho lần tải đầu, JavaScript xử lý các lần tải sau qua API).
        * [ĐANG LÀM/CẦN HOÀN THIỆN] JavaScript gọi API `GET /api/mapping/management/nodes` để render động bảng và phân trang.
            * **Lỗi 404 cho API này đã được xác định là do route chưa được đăng ký/gọi đúng.** (Đã có hướng dẫn sửa).
    2.  **Hiển thị Ảnh và Elements trong Modal (`#imagePreviewModal`):**
        * [OK] Khi click ảnh thumbnail, modal hiện ra.
        * [OK] Ảnh lớn được hiển thị.
        * [ĐÃ SỬA] **Lỗi URL ảnh (404):** Đã thống nhất cách tạo URL (`url_for('serve_app_specific_screenshot', filename=...)` trỏ đến route trong `app/__init__.py` hoặc blueprint gốc) và cấu hình `SCREENSHOT_STORAGE_PATH` (trỏ đến `app/static/screenshots/` nơi ảnh được lưu trực tiếp, không có thư mục con `app_name`).
        * [OK] API (`/admin/api/screen_elements_for_mapping/<screen_id>`) lấy elements từ Neo4j.
        * [OK] JavaScript (`drawOverlaysOnModal`) vẽ overlay elements lên ảnh.
        * [OK] Hiển thị danh sách text của elements.
    3.  **Chức năng "Phân loại Node":**
        * [OK] Dropdown trên mỗi dòng Node.
        * [OK] JavaScript gọi API `POST /api/mapping/management/nodes/<screen_id>/classify`.
        * [OK] Backend API cập nhật thuộc tính `node_classification` cho Node `:Screen` trong Neo4j.
    4.  **Chức năng "Xóa Node":**
        * [OK] Nút "Xóa" trên mỗi dòng.
        * [OK] JavaScript gọi API `POST /api/mapping/management/nodes/<screen_id>/delete`.
        * [OK] Backend API xóa Node `:Screen` (và `:Element`, `:TRANSITION` liên quan) khỏi Neo4j, và xóa file ảnh vật lý.
    5.  **Chức năng "Định nghĩa PIE cho Node này" (cho Node "unknown"):**
        * [ĐANG TRIỂN KHAI] Nút "Định nghĩa" trên dòng Node "unknown".
        * **UI Modal `#definePieForUnknownNodeModal`:**
            * [OK] Mở modal, tự động điền `App Name`, `Activity Name`.
            * [OK] Admin nhập `Tên Logic Màn hình` mới, `Defined Screen ID` mới.
            * [ĐANG LÀM] **Hiển thị danh sách elements gợi ý** từ Node "unknown" (lấy qua API).
            * [ĐANG LÀM] **Cho phép admin click chọn element gợi ý** để tự động thêm vào "Điều kiện PIE" trong form.
            * [OK] Admin có thể thêm/sửa/xóa "Điều kiện PIE" thủ công (dùng `createPieConditionRowInDefineModal`).
        * **Khi Lưu:**
            * [OK] JavaScript thu thập dữ liệu và gọi API `POST /api/mapping/management/nodes/define-from-unknown`.
            * **Backend API (`api_define_node_from_unknown`):**
                * [OK] Tạo bản ghi PIE mới trong `screen_definitions` (PostgreSQL), kiểm tra tính duy nhất của `new_defined_screen_id`.
                * [ĐANG LÀM/CẦN HOÀN THIỆN] Cập nhật Node "unknown" trong Neo4j: đổi `screen_id` thành `new_defined_screen_id`, đổi `status` thành `defined`. **Cần làm rõ và hoàn thiện logic xử lý các cạnh `:TRANSITION` khi `screen_id` của Node thay đổi.** (Hiện tại đang dùng cách đơn giản là chỉ cập nhật `screen_id` và `status` của node hiện có).
    6.  **Chức năng "Merge Node này vào một Định nghĩa PIE đã có" (cho Node "unknown"):**
        * [TIẾP THEO] Nút "Merge vào PIE" trên dòng Node "unknown".
        * Modal `#mergeToPieModal` cho phép chọn `Defined Screen ID` đích.
        * API backend `POST /api/mapping/management/nodes/merge-unknown-to-defined` để thực hiện merge trong Neo4j.
    7.  **Chức năng "Merge Selected Nodes":**
        * [ĐỂ SAU] Xử lý checkbox và nút `#mergeSelectedNodesBtn`.
    8.  **Layout nút "Hành động":**
        * [ĐÃ SỬA] Đã điều chỉnh để chia thành 2 dòng nếu có 4 nút, giúp UI gọn gàng hơn.
    9.  **Truy cập trang:**
        * [OK] Đã thêm mục menu trong `admin_base.html`.
    10. **Thông báo "Không tìm thấy node":**
        * [OK] Đã điều chỉnh để chỉ JavaScript hiển thị thông báo này trong bảng, loại bỏ flash message trùng lặp từ backend.
    11. **Node `:Screen` với `screen_id = "unknown_..."` không được tạo trong Neo4j:**
        * [ĐÃ SỬA] Vấn đề là do `min_len` bị tính là 0 khi client không gửi `class_names`. Đã sửa `utils.process_raw_ui_state` để tính `min_len` dựa trên các list client thực sự gửi và xử lý việc thiếu `class_names` một cách linh hoạt hơn khi tạo `element_id`.
        * [ĐÃ SỬA] Lỗi `UnboundLocalError` trong `utils.process_raw_ui_state` do thứ tự gán biến và logging.
        * [ĐÃ SỬA] Lỗi `ParameterMissing: Expected parameter(s): isDefinedByPieParam` và `NameError: Neo4jError not defined` trong `graph_db.merge_screen`.

**III. Các vấn đề chung:**

* **CSRF Token:** Đảm bảo các request `POST`, `PUT`, `DELETE` từ JavaScript gửi kèm `X-CSRFToken` nếu backend có bảo vệ CSRF.
* **Xử lý lỗi (Error Handling):** Cả frontend (JavaScript) và backend (Python) cần có xử lý lỗi tốt, hiển thị thông báo thân thiện cho người dùng và log chi tiết cho nhà phát triển.
* **Tính nhất quán của `element_id`:** `utils.process_raw_ui_state` hiện tại ưu tiên `resource-id`, sau đó là `text` để tạo `element_id`. Điều này cần nhất quán với cách admin định nghĩa PIE.

**Công việc đang làm/tiếp theo:**

* **Hoàn thiện chức năng "Định nghĩa PIE cho Node này" trên Trang "Quản lý Vấn đề Node":**
    * Hoàn thiện phần JavaScript để hiển thị gợi ý elements và cho phép admin click chọn chúng vào form PIE.
    * Kiểm tra và hoàn thiện API backend `POST /api/mapping/management/nodes/define-from-unknown` để lưu PIE definition và cập nhật Node Neo4j một cách chính xác (đặc biệt là việc xử lý `screen_id` và các cạnh `TRANSITION`).
* Triển khai chức năng "Merge Node này vào một Định nghĩa PIE đã có".
* Triển khai chức năng "Merge Selected Nodes".

---

File README này sẽ giúp chúng ta có một cái nhìn tổng quan và theo dõi tiến độ.