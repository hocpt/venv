```markdown
# Quy trình Định nghĩa PIE (Màn hình Nhận dạng)

Quy trình này mô tả cách một quản trị viên (Admin) có thể định nghĩa một Màn hình Nhận dạng mới (PIE - Potentially Identifiable Elements / Page Identifying Elements) từ một "Screen Node" chưa được xác định (status='unknown') trong hệ thống App Mapping, hoặc cập nhật các điều kiện nhận dạng cho một PIE đã tồn tại.

## 1. Tổng quan

Mục tiêu của việc định nghĩa PIE là giúp hệ thống nhận dạng chính xác các màn hình của ứng dụng di động, ngay cả khi chúng có cùng `activity_name`. Điều này rất quan trọng cho việc điều hướng tự động và thực thi các Control Strategies.

**Điểm kích hoạt:**

* Admin tương tác trên trang "Quản lý Node" (`/admin/mapping/node-management`) và chọn định nghĩa PIE cho một node "unknown".
* Admin tương tác trên trang "Quản lý Định nghĩa Màn hình" (`/admin/mapping/screen-definitions`) để sửa đổi các điều kiện của một PIE đã có.

**Các thành phần chính liên quan:**

* Giao diện Admin:
    * `admin_node_management.html` (và các modal/JS liên quan)
    * `admin_screen_definitions.html` (và các modal/JS liên quan)
* `app/admin_routes.py`:
    * API `POST /admin/api/mapping/management/nodes/define_new_pie_with_conditions`
    * API `GET /admin/api/pie_definition_conditions`
    * API `POST /admin/api/pie_definition/{defined_pie_id}/update_conditions`
* `app/database.py`:
    * `create_new_pie_definition_from_node()`
    * `get_pie_conditions_from_db()`
    * `update_pie_conditions_in_db()`
    * `get_last_detailed_ui_state_for_screen()` (để lấy danh sách elements cho node unknown)
    * `check_defined_screen_id_exists()` (được gọi trong API)
* `app/graph_db.py`:
    * `convert_unknown_to_defined_node_wrapper()` (hoặc hàm tương đương để cập nhật node Neo4j)
* CSDL PostgreSQL: Bảng `screen_definitions`, `screen_definition_elements`, `detailed_ui_interaction_logs`.
* CSDL Neo4j: Các `Screen Node`.

## 2. Quy trình A: Định nghĩa PIE Mới từ Node "Unknown"

Quy trình này diễn ra khi Admin muốn gán một định danh chính thức (PIE) cho một "Screen Node" đang có trạng thái `unknown` trong Neo4j.

```mermaid
graph TD
    A[Admin: Mở trang Quản lý Node (/admin/mapping/node-management)] --> B{Chọn node 'unknown'};
    B --> C[Admin: Nhấp nút "Define PIE"];
    C --> D[UI: Hiển thị Modal/Form "Define New PIE"];
    D -- Lấy danh sách elements từ log UI state (PostgreSQL) cho node unknown --> D;
    D --> E[Admin: Nhập Tên Logic, Defined Screen ID, Mô tả];
    E --> F[Admin: Chọn các Elements và Điều kiện nhận dạng (attribute, comparison, value)];
    F --> G[Admin: Submit Form];
    G --> H[Frontend: Gửi POST Request đến /api/.../define_new_pie_with_conditions];
    H -- Payload: unknown_node_id, app_name, activity_name, logical_name, new_defined_id, conditions_list, description --> I[Backend API: api_define_new_pie_and_update_node];
    I --> J[DB (PG): Gọi create_new_pie_definition_from_node];
    J -- Tạo bản ghi trong screen_definitions & screen_definition_elements --> K{Tạo PIE trong PG thành công?};
    K -- Có --> L[GraphDB: Gọi convert_unknown_to_defined_node_wrapper];
    L -- Cập nhật screen_id, status='defined', logical_name cho node Neo4j. Xử lý transitions. --> M{Cập nhật Neo4j thành công?};
    M -- Có --> N[Backend: Trả JSON success (201 Created) với new_pie_db_id, defined_screen_id];
    N --> O[UI: Thông báo thành công, làm mới bảng Node hoặc cập nhật dòng];
    M -- Không --> P[Backend: Trả JSON error (500). Ghi chú: PIE đã tạo trong PG nhưng Neo4j lỗi];
    P --> O;
    K -- Không (ví dụ: defined_id trùng) --> Q[Backend: Trả JSON error (409 hoặc 500) về lỗi tạo PIE];
    Q --> O;
    H -- Dữ liệu không hợp lệ --> R[Backend: Trả JSON error (400)];
    R --> O;

Các bước chi tiết:

Truy cập Trang Quản lý Node: Admin vào trang /admin/mapping/node-management. Trang này hiển thị danh sách các Screen Node từ Neo4j, bao gồm cả các node có status unknown.

Chọn Node "Unknown": Admin xác định một node "unknown" cần được định nghĩa.

Kích hoạt Chức năng "Define PIE": Admin nhấp vào một nút hoặc tùy chọn "Define PIE" (hoặc tên tương tự) liên kết với node "unknown" đó.

Hiển thị Form Định nghĩa PIE:

Một modal hoặc một form mới được hiển thị.
Form này sẽ tự động điền một số thông tin nếu có thể từ node "unknown" (ví dụ: app_name, activity_name).
Quan trọng: Giao diện sẽ truy xuất và hiển thị danh sách các UI Elements của node "unknown" này. Thông tin elements này được lấy từ bản ghi log gần nhất trong detailed_ui_interaction_logs (PostgreSQL) cho screen_id của node unknown (thông qua hàm db.get_last_detailed_ui_state_for_screen).
Admin Nhập Thông tin PIE Mới:

logical_name: Tên logic, thân thiện với người dùng cho màn hình này (ví dụ: "Màn hình Đăng nhập", "Trang chủ Người dùng").
new_defined_screen_id: Một ID chuỗi duy nhất (trong phạm vi app_name) để định danh PIE này (ví dụ: com.example.app_login_screen_v1). ID này sẽ là screen_id mới của node trong Neo4j sau khi cập nhật.
description (tùy chọn): Mô tả chi tiết hơn về PIE.
Admin Chọn Điều kiện Nhận dạng:

Từ danh sách các UI Elements của node "unknown" đã hiển thị, admin chọn một hoặc nhiều elements quan trọng.
Đối với mỗi element được chọn, admin chỉ định:
attribute: Thuộc tính của element dùng để so sánh (ví dụ: 'resource_id', 'text', 'class_name', 'xpath', 'element_id' (ID do client sinh ra)).
comparison: Phép so sánh (ví dụ: 'equals', 'contains', 'starts_with', 'ends_with', 'exists', 'not_exists', 'matches_regex').
value: Giá trị để so sánh. Có thể là null nếu comparison là 'exists' hoặc 'not_exists'.
Tập hợp các điều kiện này (selected_conditions) sẽ định nghĩa cách nhận dạng màn hình này.
Admin Submit Form.

Frontend Gửi Yêu cầu API:

Frontend thu thập tất cả thông tin từ form và gửi một HTTP POST request đến API /admin/api/mapping/management/nodes/define_new_pie_with_conditions.
Payload JSON bao gồm: unknown_node_neo4j_id (ID nội bộ của node Neo4j cần cập nhật), current_unknown_screen_id (giá trị screen_id hiện tại của node unknown), app_name, activity_name, logical_name (mới), new_defined_screen_id, selected_conditions (danh sách các object điều kiện), description (mới).
Backend Xử lý API (api_define_new_pie_and_update_node):

Validate Input: Kiểm tra các trường bắt buộc và định dạng dữ liệu. Kiểm tra xem new_defined_screen_id có bị trùng với PIE đã có của app_name đó không (sử dụng db.check_defined_screen_id_exists).
Tạo PIE Definition trong PostgreSQL:
Gọi hàm db.create_new_pie_definition_from_node(app_name, activity_name, new_logical_name, new_defined_screen_id, selected_conditions, description).
Hàm này sẽ:
Tạo một bản ghi mới trong bảng screen_definitions.
Với mỗi điều kiện trong selected_conditions, tạo một bản ghi mới trong bảng screen_definition_elements liên kết với screen_definitions.definition_id vừa tạo.
Nếu thành công, trả về new_pie_db_id (ID của bản ghi trong screen_definitions). Nếu thất bại (ví dụ: new_defined_screen_id bị trùng), trả về lỗi.
Cập nhật Node trong Neo4j:
Nếu tạo PIE trong PostgreSQL thành công, gọi hàm graph_db.convert_unknown_to_defined_node_wrapper(unknown_screen_id=current_unknown_screen_id, app_name=app_name, new_defined_screen_id=new_defined_screen_id, new_status='defined', new_logical_name=new_logical_name).
Hàm này có trách nhiệm:
Tìm Screen Node trong Neo4j dựa trên current_unknown_screen_id và app_name.
Đổi screen_id của node này thành new_defined_screen_id.
Cập nhật status của node thành 'defined'.
Cập nhật các thuộc tính khác nếu cần (ví dụ: logical_pie_name = new_logical_name, updated_at).
Quan trọng: Tìm tất cả các cạnh :TRANSITION đi vào và đi ra node này. Cập nhật các thuộc tính source hoặc target trên các cạnh đó để chúng trỏ đến new_defined_screen_id thay vì current_unknown_screen_id.
Nếu cập nhật Neo4j thất bại, cần ghi log lỗi. Có thể cân nhắc việc rollback tạo PIE trong PostgreSQL hoặc thông báo lỗi rõ ràng cho admin.
Phản hồi và Cập nhật UI:

Backend API trả về JSON cho frontend, thông báo thành công (mã 201) hoặc lỗi (mã 400, 409, 500).
Nếu thành công, UI sẽ làm mới danh sách Node hoặc cập nhật thông tin của node vừa được định nghĩa (đổi screen_id, status, hiển thị logical_pie_name).
3. Quy trình B: Sửa đổi Điều kiện của PIE Đã có
Quy trình này diễn ra khi Admin muốn thay đổi các điều kiện nhận dạng (elements và thuộc tính của chúng) cho một PIE Definition đã tồn tại.

Truy cập Trang Quản lý Định nghĩa Màn hình: Admin vào trang /admin/mapping/screen-definitions. Trang này hiển thị danh sách các PIE Definitions từ PostgreSQL.
Chọn PIE và Kích hoạt Sửa Điều kiện: Admin chọn một PIE Definition và nhấp vào nút/tùy chọn để "Sửa Điều kiện" (hoặc tên tương tự).
Hiển thị Form Sửa Điều kiện:
Một modal hoặc form được hiển thị.
Giao diện gọi API GET /admin/api/pie_definition_conditions?defined_screen_id={defined_id}&app_name={app_name} để lấy danh sách các điều kiện hiện tại của PIE đó.
Admin có thể thêm điều kiện mới, sửa đổi các điều kiện hiện có, hoặc xóa bớt điều kiện. Giao diện cần cung cấp cách chọn attribute, comparison, và nhập value cho mỗi điều kiện.
Admin Submit Form.
Frontend Gửi Yêu cầu API:
Frontend thu thập danh sách các điều kiện mới (sau khi đã sửa đổi) và gửi một HTTP POST request đến API /admin/api/pie_definition/{defined_pie_id}/update_conditions (trong đó {defined_pie_id} là defined_screen_id của PIE).
Payload JSON: {"app_name": "...", "new_conditions_list": [ {điều_kiện_1}, {đi_ều_kiện_2}, ... ]}. new_conditions_list là danh sách ĐẦY ĐỦ các điều kiện mới, sẽ thay thế hoàn toàn các điều kiện cũ.
Backend Xử lý API (api_update_pie_definition_conditions):
Validate Input.
Gọi hàm db.update_pie_conditions_in_db(app_name, defined_pie_id, new_conditions_list).
Hàm này sẽ:
Xóa tất cả các bản ghi hiện có trong screen_definition_elements cho screen_definition_id tương ứng với app_name và defined_pie_id.
Thêm các bản ghi mới vào screen_definition_elements dựa trên new_conditions_list.
Phản hồi và Cập nhật UI:
Backend API trả về JSON thông báo thành công hoặc lỗi.
UI có thể đóng modal và làm mới danh sách PIE (nếu cần) hoặc chỉ hiển thị thông báo.
Lưu ý: Việc thay đổi PIE conditions có thể ảnh hưởng đến việc nhận dạng màn hình của client trong tương lai. Các Screen Node trong Neo4j đã được đánh dấu là "defined" dựa trên PIE cũ có thể không còn khớp nữa nếu PIE thay đổi đáng kể. Cần có cơ chế để rà soát lại hoặc client sẽ tự động không khớp và có thể tạo ra node "unknown" mới nếu không tìm thấy PIE nào phù hợp.


---