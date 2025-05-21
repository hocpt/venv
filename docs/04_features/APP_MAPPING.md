# Tính năng Ánh xạ Ứng dụng (App Mapping)

## 1. Giới thiệu

Tính năng App Mapping là một thành phần trung tâm của hệ thống HPT11, cho phép hệ thống "hiểu" và xây dựng một mô hình về cấu trúc và luồng hoạt động của các ứng dụng di động. Mục tiêu chính của App Mapping là:

* **Tự động hóa tương tác:** Cung cấp một cơ sở dữ liệu về các màn hình và phần tử UI để các chiến lược điều khiển (Control Strategies) có thể tự động thực hiện các hành động trên ứng dụng.
* **Trực quan hóa luồng ứng dụng:** Tạo ra một đồ thị trực quan thể hiện các màn hình và cách người dùng có thể di chuyển giữa chúng, giúp con người và AI dễ dàng nắm bắt cấu trúc ứng dụng.
* **Phân tích và Gỡ lỗi:** Hỗ trợ việc phân tích các kịch bản người dùng và gỡ lỗi các chiến lược tự động hóa.

Thông tin App Mapping chủ yếu được lưu trữ trong cơ sở dữ liệu đồ thị Neo4j và được bổ sung bằng dữ liệu từ PostgreSQL.

## 2. Các Khái niệm Cốt lõi

### 2.1. Screen Node (Nút Màn hình)

* **Định nghĩa:** Một `Screen Node` trong Neo4j đại diện cho một màn hình hoặc một trạng thái UI (Giao diện Người dùng) cụ thể và duy nhất trong một ứng dụng di động.
* **Thuộc tính chính (Properties) trong Neo4j:**
    * `screen_id` (string, unique): ID định danh duy nhất cho màn hình. Đây có thể là sự kết hợp của `app_name`, `activity_name` và một giá trị hash của các phần tử nhận dạng hoặc một UUID do client tạo ra ban đầu.
    * `app_name` (string): Tên package của ứng dụng (ví dụ: `com.example.app`).
    * `activity_name` (string): Tên của Activity Android (hoặc View Controller iOS) tương ứng với màn hình.
    * `screenshot_path` (string): Tên file ảnh chụp màn hình, được lưu trên server tại `SCREENSHOT_STORAGE_PATH/{app_name}/{screenshot_path}`.
    * `status` (string): Trạng thái của node màn hình:
        * `unknown`: Màn hình mới được phát hiện, chưa được định danh bằng PIE.
        * `defined`: Màn hình đã được liên kết với một Định nghĩa Màn hình Nhận dạng (PIE Definition). `screen_id` của node này sẽ khớp với `defined_screen_id` của PIE.
        * `defined_from_unknown`: Node này ban đầu là 'unknown' và sau đó được admin định nghĩa thành một PIE. Thuộc tính `defined_as_screen_id` sẽ trỏ đến `defined_screen_id` của PIE tương ứng.
        * `explored`: Màn hình đã được khám phá (ví dụ: tất cả các hành động có thể từ màn hình này đã được thử).
        * `error`: Có lỗi liên quan đến việc xử lý hoặc nhận dạng màn hình này.
        * `merged_to_defined`: Node này (thường là 'unknown') đã được merge vào một node 'defined' khác.
    * `element_count` (integer): Số lượng phần tử UI được phát hiện trên màn hình (thông tin tóm tắt).
    * `width` (integer): Chiều rộng gốc của màn hình (ảnh chụp) tính bằng pixel.
    * `height` (integer): Chiều cao gốc của màn hình (ảnh chụp) tính bằng pixel.
    * `node_classification` (string, optional): Phân loại chung cho màn hình (ví dụ: 'login_screen', 'profile_view', 'feed').
    * `logical_pie_name` (string, optional): Tên logic của PIE Definition liên kết với node này (nếu status là 'defined').
    * `last_seen` (datetime): Thời điểm cuối cùng client gửi dữ liệu cho màn hình này.
    * `created_at` (datetime): Thời điểm node được tạo.
    * `updated_at` (datetime): Thời điểm node được cập nhật lần cuối.

### 2.2. PIE (Potentially Identifiable Elements / Page Identifying Elements - Phần tử Nhận dạng Tiềm năng)

* **Định nghĩa:** PIE là một tập hợp các điều kiện dựa trên thuộc tính của các phần tử UI (UI Elements) được sử dụng để nhận dạng một cách duy nhất một màn hình cụ thể trong ứng dụng. Mục tiêu là phân biệt màn hình này với các màn hình khác, ngay cả khi `activity_name` giống nhau.
* **Lưu trữ:** Các định nghĩa PIE được lưu trữ trong CSDL PostgreSQL:
    * Bảng `screen_definitions`: Lưu thông tin chung của một PIE (ví dụ: `app_name`, `activity_name`, `logical_screen_name`, `defined_screen_id`, `description`).
    * Bảng `screen_definition_elements`: Lưu trữ các điều kiện cụ thể của từng PIE (ví dụ: `attribute`='resource_id', `comparison`='equals', `value`='com.app:id/button_login').
* **Ví dụ về Điều kiện PIE:**
    * Element có `resource_id` là `com.example.app:id/username_field` PHẢI tồn tại.
    * Element có `text` là "Đăng nhập" PHẢI tồn tại.
    * Element có `class_name` là `android.widget.ImageView` VÀ `content_desc` chứa "Ảnh đại diện" PHẢI tồn tại.

### 2.3. UI Element (Phần tử Giao diện Người dùng)

* **Định nghĩa:** Đại diện cho một thành phần tương tác hoặc hiển thị trên màn hình ứng dụng, ví dụ: nút bấm (button), trường nhập liệu (text field), hình ảnh (image), đoạn văn bản (text view).
* **Thu thập:** Thông tin về các UI Elements được client di động thu thập và gửi về server qua API `/phone/screen_data`.
* **Thuộc tính (ví dụ):** `element_id` (do client tạo, unique trong context màn hình), `text`, `resource_id`, `class_name`, `xpath`, `bounds`, `clickable`, `visible_to_user`, `is_password`, `parent_id`, `children_ids`.
* **Lưu trữ:**
    * **Neo4j:** Thông tin tóm tắt về element có thể được lưu như một phần của thuộc tính `elements` (dạng JSON) trên `Screen Node` hoặc trên quan hệ `:TRANSITION` (ví dụ: `element_id` kích hoạt transition).
    * **PostgreSQL:**
        * Toàn bộ cấu trúc chi tiết của các elements trên một màn hình tại một thời điểm cụ thể được ghi vào bảng `detailed_ui_interaction_logs` (cột `raw_ui_state_json`).
        * Phân loại (classification) và trạng thái khám phá thủ công (manual explored override) của từng element được lưu trong bảng `element_classifications`.

### 2.4. Transition (Quan hệ Chuyển tiếp)

* **Định nghĩa:** Một quan hệ `:TRANSITION` trong Neo4j đại diện cho một hành động được thực hiện trên một `UIElement` (hoặc một hành động không cần element cụ thể như "NAV_GO_BACK") dẫn đến việc chuyển từ một `Screen Node` (nguồn) sang một `Screen Node` khác (đích), hoặc ở lại cùng một màn hình nhưng có sự thay đổi trạng thái.
* **Thuộc tính chính (Properties) trong Neo4j:**
    * `actionType` (string): Loại hành động (ví dụ: 'click', 'input', 'swipe_up', 'nav_go_back', 'run_macro').
    * `element_id` (string, optional): ID của `UIElement` mà hành động được thực hiện trên đó.
    * `identifier_type` (string, optional): Loại định danh đã được sử dụng để tìm `element_id` (ví dụ: 'resource_id', 'text', 'xpath').
    * `element_text` (string, optional): Nội dung text của element tại thời điểm tương tác.
    * `macro_code` (string, optional): Mã của macro được thực thi nếu `actionType` là 'run_macro'.
    * `params_json_str` (string, optional): Chuỗi JSON chứa các tham số cho macro.
    * `status` (string): Trạng thái của transition (ví dụ: 'provisional' - mới tạo, 'confirmed' - đã xác nhận hoạt động, 'failed' - gây lỗi, 'disabled' - bị vô hiệu hóa).
    * `attempt_count` (integer): Số lần thử thực hiện transition này.
    * `success_count` (integer): Số lần thực hiện transition này thành công.
    * `created_at` (datetime): Thời điểm transition được tạo.
    * `updated_at` (datetime): Thời điểm transition được cập nhật lần cuối.

## 3. Luồng Hoạt động Chính

1.  **Thu thập Dữ liệu từ Client:**
    * Client di động (ví dụ: Macrodroid) theo dõi các thay đổi màn hình và thu thập thông tin về `activity_name`, các `UIElement` hiển thị, và chụp ảnh màn hình.
    * Client gửi dữ liệu này (trừ file ảnh) đến API `/phone/screen_data`.
    * Client sau đó tải file ảnh chụp màn hình lên API `/api/upload/screenshot` với tên file đã thông báo.

2.  **Xử lý Dữ liệu ở Server (`phone_controller.handle_screen_data`):**
    * **Lưu ảnh:** Đường dẫn ảnh được chuẩn bị.
    * **Xác định `screen_id`:** Server có thể tạo/chuẩn hóa `screen_id` dựa trên `app_name`, `activity_name` và có thể cả nội dung elements.
    * **Cập nhật/Tạo Node Screen trong Neo4j:**
        * Sử dụng `graph_db.add_or_update_screen_node` để tạo mới hoặc cập nhật thông tin cho `Screen Node` tương ứng với `screen_id` và `app_name`. Các thuộc tính như `screenshot_path`, `element_count`, `width`, `height`, `last_seen` được cập nhật.
        * Ban đầu, node mới thường có status là `unknown`.
    * **Ghi log chi tiết UI State:** Toàn bộ thông tin `elements` chi tiết, `window_width`, `window_height` được ghi vào bảng `detailed_ui_interaction_logs` trong PostgreSQL để phục vụ việc phân tích và định nghĩa PIE sau này.

3.  **Nhận dạng Màn hình (Screen Identification - logic trong `phone_controller.determine_current_defined_screen`):**
    * Khi client yêu cầu nhiệm vụ (`/phone/task_assignment/request`) và gửi kèm `current_ui_state` (thông tin elements hiện tại trên màn hình của client).
    * Hệ thống sẽ so sánh `current_ui_state` này với các PIE Definitions đã lưu trong `screen_definitions` và `screen_definition_elements` (PostgreSQL) cho `app_name` đó.
    * Nếu tìm thấy một PIE Definition khớp, hệ thống xác định được `defined_screen_id` hiện tại của client.
    * Nếu không khớp PIE nào, màn hình hiện tại của client được coi là "unknown" (và có thể đã được ghi nhận qua `/phone/screen_data` với một `screen_id` tạm thời).

4.  **Tạo và Cập nhật Transitions:**
    * Khi một hành động (ví dụ: click, input) được thực hiện trên client (thường là kết quả của một bước trong Control Strategy), client sẽ báo cáo lại hành động đó và màn hình kết quả.
    * Server sẽ tạo hoặc cập nhật một quan hệ `:TRANSITION` trong Neo4j giữa `Screen Node` nguồn và `Screen Node` đích, lưu trữ thông tin về hành động đã thực hiện. (Logic này nằm trong `phone_controller.update_task_assignment_status` khi xử lý log hoặc `graph_db.add_or_update_transition`).

## 4. Các Giao diện Quản lý Liên quan

Hệ thống cung cấp các giao diện admin để quản lý và tương tác với dữ liệu App Mapping:

### 4.1. Admin Mapping Viewer (`/admin/mapping/<app_name>`)

* **Mục đích:** Trực quan hóa đồ thị các `Screen Nodes` và `Transitions` cho một ứng dụng cụ thể.
* **Chức năng:**
    * Hiển thị đồ thị tương tác sử dụng Cytoscape.js.
    * Cho phép xem thông tin chi tiết của từng Node (Screen) và Edge (Transition) khi nhấp vào.
    * Hiển thị ảnh chụp màn hình của Node đang chọn.
    * Hiển thị các elements của Node đang chọn (lấy từ API `/admin/api/screen_elements_for_mapping/{screen_id}`).
    * Cho phép sửa thông tin Transition (ví dụ: `actionType`, `element_id`, `status`, `params_json_str`) thông qua modal và API `/admin/api/mapping/transition/update/{neo4j_edge_id}`.
    * (Trong tương lai) Có thể cho phép thêm Node/Edge thủ công hoặc khởi tạo khám phá từ đây.

### 4.2. Admin Screen Elements Viewer (`/admin/screen/<screen_id>/elements`)

* **Mục đích:** Hiển thị chi tiết các phần tử UI của một màn hình cụ thể, cho phép admin xem, phân loại và quản lý trạng thái khám phá.
* **Chức năng:**
    * Hiển thị ảnh chụp màn hình gốc với kích thước thật.
    * Vẽ overlay các bounding box của từng element lên ảnh.
    * Hiển thị danh sách các elements với các thuộc tính của chúng (lấy từ log `detailed_ui_interaction_logs` và `element_classifications` trong PostgreSQL).
    * Cho phép admin gán/thay đổi `classification` cho từng element (sử dụng API `/admin/api/element/classify`).
    * Cho phép admin ghi đè trạng thái "đã khám phá" (`manual_explored_override`) cho từng element (sử dụng API `/admin/api/element/mark_explored`).
    * Gọi AI để gợi ý `classification` cho các elements (sử dụng API `/admin/api/screen/{screen_id}/suggest_classifications`).

### 4.3. Quản lý Node (`/admin/mapping/node-management`)

* **Mục đích:** Cung cấp một giao diện bảng để quản lý các `Screen Nodes` trong Neo4j, đặc biệt là các node "unknown" hoặc các node có vấn đề.
* **Chức năng:**
    * Hiển thị danh sách các node dưới dạng bảng, có phân trang và bộ lọc (theo `app_name`, `status`).
    * Hiển thị các thông tin quan trọng: `screen_id`, `app_name`, `activity_name`, `status`, ảnh thumbnail, `node_classification`, `logical_pie_name` (nếu defined), `created_at`, `last_seen`.
    * **Hành động trên từng node:**
        * **Xem chi tiết Elements:** Liên kết đến trang `/admin/screen/{screen_id}/elements`.
        * **Xóa Node:** Gọi API `/admin/api/mapping/management/nodes/{screen_id}/delete` để xóa node khỏi Neo4j và file ảnh liên quan.
        * **Phân loại Node:** Cho phép admin gán một `node_classification` cho node (ví dụ: 'error_screen', 'popup_dialog'), cập nhật thuộc tính này trong Neo4j qua API `/admin/api/mapping/management/nodes/{screen_id}/classify`.
        * **(Đối với node "unknown") Định nghĩa PIE Mới:** Mở modal cho phép admin tạo một PIE Definition mới dựa trên node "unknown" này, chọn các elements nhận dạng, đặt tên logic, defined_screen_id. Sau khi tạo PIE trong PostgreSQL, node "unknown" trong Neo4j sẽ được cập nhật (ví dụ: đổi `screen_id`, `status`) để trở thành node "defined" mới này. Sử dụng API `/admin/api/mapping/management/nodes/define_new_pie_with_conditions`.
        * **(Đối với node "unknown") Merge vào PIE đã có:** Cho phép admin merge một node "unknown" vào một node "defined" đã tồn tại (nếu admin xác định chúng là cùng một màn hình). Node "unknown" sẽ bị xóa, các cạnh của nó sẽ được chuyển sang node "defined". Sử dụng API `/admin/api/mapping/management/nodes/merge-unknown-to-defined`.

### 4.4. Quản lý Định nghĩa Màn hình (`/admin/mapping/screen-definitions`)

* **Mục đích:** Cho phép admin xem, tạo mới, sửa đổi và xóa các Định nghĩa Màn hình Nhận dạng (PIE Definitions) được lưu trong PostgreSQL.
* **Chức năng:**
    * Hiển thị danh sách các PIE definitions dưới dạng bảng, có phân trang và bộ lọc theo `app_name`.
    * Cho phép **Thêm mới** một PIE definition: Nhập `app_name`, `activity_name`, `logical_screen_name`, `defined_screen_id`, `description`, và định nghĩa các điều kiện (`identifying_elements_json`) qua một giao diện thân thiện. Sử dụng API `POST /admin/api/mapping/screen-definitions`.
    * Cho phép **Sửa đổi** một PIE definition hiện có (bao gồm cả việc sửa các điều kiện của nó). Sử dụng API `PUT /admin/api/mapping/screen-definitions/{def_id}` và `POST /admin/api/pie_definition/{defined_pie_id}/update_conditions`.
    * Cho phép **Xóa** một PIE definition. Sử dụng API `DELETE /admin/api/mapping/screen-definitions/{def_id}`.

## 5. Tham chiếu từ `README_MAPPING.txt`

Kế hoạch tài liệu có đề cập đến việc chuyển nội dung từ `README_MAPPING.txt` vào đây. Nội dung của `README_MAPPING.txt` bao gồm:

* **Ý tưởng cốt lõi:** Xây dựng "bản đồ" của ứng dụng để tự động hóa.
* **Thành phần:**
    * `Screen Node`: Đại diện cho một màn hình, có `screen_id`, `screenshot_path`, `activity_name`, `app_name`, `elements_json` (JSON string chứa danh sách các properties của element).
    * `Transition Edge`: Kết nối hai `Screen Nodes`, có các thuộc tính như `actionType`, `element_id`, `params_json_str`.
* **Luồng hoạt động:**
    1.  **Thu thập:** Điện thoại gửi thông tin màn hình (elements, screenshot) và `activity_name`, `app_name`.
    2.  **Xử lý ở Server:**
        * Tạo `screen_id` (vd: `app_name` + `activity_name` + hash của một số element).
        * Lưu/cập nhật `Screen Node` vào Neo4j.
        * Lưu ảnh screenshot.
    3.  **Xác định hành động:**
        * Dựa trên `current_screen_id` và mục tiêu (từ `Task Assignment`), chọn `Strategy`.
        * `Strategy` xác định `action` cần làm (vd: click, input).
        * Server gửi lệnh (action, element_id, params) cho điện thoại.
    4.  **Thực thi và Báo cáo:** Điện thoại thực hiện, sau đó gửi lại `new_screen_id` và trạng thái. Server tạo `Transition Edge`.
* **Định danh màn hình (PIE):** Sử dụng tập hợp các thuộc tính của element để tạo `defined_screen_id`.
* **Merge Nodes:** Hợp nhất các `screen_id` tạm thời (unknown) vào `defined_screen_id`.
* **Giao diện Admin:**
    * Hiển thị đồ thị, thông tin node/edge.
    * Cho phép sửa `Transition` (actionType, element_id, params).
    * Hiển thị ảnh chụp màn hình.
    * Quản lý PIE.
    * Merge nodes.

Các điểm này đã được tích hợp và làm rõ hơn trong các phần trên của tài liệu này.