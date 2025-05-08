  Tôi hoàn toàn hiểu mong muốn của bạn. Bạn không chỉ muốn một trang để phân loại element trên từng màn hình riêng lẻ, mà bạn muốn một giao diện quản lý bản đồ (mapping) tổng thể, trực quan và mạnh mẽ, giống như cách bạn tương tác với đồ thị trong Neo4j Browser, nhưng được tích hợp ngay trong Admin UI của bạn và có thêm các chức năng quản lý chuyên biệt.
Đây là một tầm nhìn rất hợp lý và giá trị, bởi vì:
Trực quan hóa: Nhìn thấy các node (screen) và cạnh (transition) liên kết với nhau giúp bạn dễ dàng hình dung luồng hoạt động của ứng dụng, phát hiện các vòng lặp, đường cụt hoặc các nhánh bất thường.
Kiểm soát và Tinh chỉnh: Bản đồ do AI/client tự động tạo ra không phải lúc nào cũng hoàn hảo hoặc đúng ý đồ chiến lược. Việc có thể xem, phân loại element trực tiếp trên node, đánh dấu các luồng quan trọng, thậm chí sửa lỗi hoặc thêm các liên kết thủ công là cực kỳ cần thiết.
Quản lý Phiên bản: Khả năng lưu lại các "phiên bản" của bản đồ (dạng dự phòng, tham khảo, hoặc bản đồ chính đã được xác thực) giúp bạn quản lý sự phát triển của bản đồ, so sánh hoặc thậm chí khôi phục lại trạng thái trước đó nếu quá trình tự động tạo ra kết quả không mong muốn.
Tối ưu Hóa Client: Khi bạn đã có một bản đồ đáng tin cậy (dù là tự động được xác thực hay tạo thủ công), bạn có thể giảm thiểu việc client phải chạy dò lại những đường đã biết, chỉ tập trung vào việc khám phá phần mới hoặc cập nhật khi ứng dụng thay đổi.
Vấn đề bạn nêu ra là hoàn toàn xác đáng. Việc xây dựng một trang quản lý mapping như vậy là bước tiếp theo rất logic và cần thiết để hệ thống thực sự thông minh và dễ kiểm soát. Trang phân loại element (admin_screen_elements.html) chỉ là một phần nhỏ trong bức tranh lớn này.
Giải pháp và Kế hoạch Phát triển (Đề xuất):
Chúng ta nên xây dựng tính năng này theo từng giai đoạn, tích hợp dần các khả năng bạn mong muốn:
Giai đoạn A: Hiển thị Đồ thị và Tương tác Cơ bản
Tạo Trang Mapping Mới:
Tạo route mới, ví dụ: /admin/mapping/<app_name> trong admin_routes.py.
Tạo template mới: templates/admin_mapping_viewer.html.
Tích hợp Thư viện Đồ thị Frontend:
Chọn một thư viện JavaScript mạnh mẽ để vẽ đồ thị (ví dụ: Cytoscape.js, Vis.js, d3.js). Cytoscape.js thường được ưa chuộng cho các ứng dụng tương tác đồ thị phức tạp.
Nhúng thư viện này vào template admin_mapping_viewer.html.
API Backend Lấy Dữ liệu Đồ thị:
Tạo API endpoint mới, ví dụ: /api/map/graph_data/<app_name> trong admin_routes.py.
API này sẽ gọi các hàm trong graph_db.py để truy vấn Neo4j, lấy tất cả các node Screen và cạnh TRANSITION liên quan đến app_name.
Định dạng dữ liệu trả về theo cấu trúc mà thư viện frontend yêu cầu (thường là một danh sách các nodes và một danh sách các edges với các thuộc tính cần thiết).
Hiển thị Đồ thị Frontend:
Viết mã JavaScript trong admin_mapping_viewer.html để gọi API /api/map/graph_data/... khi trang tải.
Sử dụng dữ liệu nhận được để khởi tạo và vẽ đồ thị bằng thư viện đã chọn.
Cho phép các thao tác cơ bản như zoom, pan, kéo thả node.
Liên kết đến Trang Phân loại Element:
Làm cho các node trên đồ thị có thể click được.
Khi click vào một node (Screen), thay vì hiển thị chi tiết ngay tại chỗ (sẽ làm ở giai đoạn sau), tạm thời tạo một nút hoặc liên kết để điều hướng người dùng đến trang phân loại element đã có: url_for('admin.admin_screen_elements', screen_id=CLICKED_NODE_ID). Điều này giúp tái sử dụng công việc đã làm ở Task 4.1.
Thêm Menu Điều hướng: Trong admin_base.html, thêm một mục menu mới (ví dụ: "App Mapping") để người dùng có thể truy cập vào trang /admin/mapping/<app_name> (cần cơ chế chọn app_name).
Giai đoạn B: Tương tác Nâng cao và Chỉnh sửa Tại chỗ
Panel Chi tiết: Thay vì điều hướng sang trang khác, khi click vào node/edge trên đồ thị, hiển thị thông tin chi tiết của nó trong một panel bên cạnh (sidebar) ngay trên trang mapping viewer. Dữ liệu chi tiết được lấy qua API riêng (/api/map/node_details/<screen_id>, /api/map/edge_details/<edge_id>).
Phân loại Element Tại chỗ: Tích hợp giao diện xem và phân loại element (như trang admin_screen_elements.html) vào bên trong panel chi tiết của node. Cho phép người dùng phân loại trực tiếp tại đây và lưu lại qua API.
Đánh dấu/Cập nhật Trạng thái: Thêm các nút trong panel chi tiết để người dùng có thể cập nhật status (vd: 'confirmed', 'provisional', 'ignore') hoặc thêm các tag/label tùy chỉnh (vd: 'verified', 'core_flow', 'buggy') cho node/edge trong Neo4j thông qua các API backend mới.
Chỉnh sửa Thủ công Cơ bản (Cẩn thận):
Cho phép đổi tên/thêm mô tả cho node Screen (cập nhật thuộc tính trong Neo4j).
Cho phép xóa các cạnh TRANSITION đang ở trạng thái provisional hoặc bị đánh dấu là lỗi (cần xác nhận). Việc thêm node/cạnh thủ công phức tạp hơn và có thể làm nhiễu dữ liệu tự động, nên cân nhắc kỹ.
Giai đoạn C: Quản lý Bản đồ và Tinh chỉnh Nâng cao
Lọc Hiển thị: Thêm các bộ lọc trên UI để người dùng có thể chọn hiển thị đồ thị theo các tiêu chí khác nhau (vd: chỉ hiện node/edge confirmed, chỉ hiện node/edge có tag core_flow, chỉ hiện các node liên quan đến mapping_goal nào đó). Backend sẽ thực hiện các truy vấn Neo4j tương ứng.
Highlight Đường đi: Tạo chức năng (có thể dùng AI hoặc truy vấn Cypher phức tạp được kích hoạt qua API) để làm nổi bật các đường đi cụ thể trên đồ thị (vd: "hiển thị luồng đăng nhập", "hiển thị đường đi có lỗi nhiều nhất").
Quản lý Phiên bản/Snapshot (Dựa trên Neo4j):
Thay vì lưu map ra DB ngoài, ta có thể tận dụng Neo4j. Khi muốn "lưu" một phiên bản, tạo một cơ chế để đánh dấu (tag) tất cả các node/edge hiện tại bằng một thuộc tính phiên bản (vd: map_version: "v1.0-approved") hoặc một label mới.
Giao diện Admin có thể cho phép xem các node/edge thuộc về một phiên bản cụ thể bằng cách lọc theo tag/label đó.
Việc "khôi phục" có thể là xóa các node/edge không mong muốn và đánh dấu lại phiên bản cũ hơn là "chính". Cách này tránh được sự phức tạp của việc đồng bộ giữa Neo4j và CSDL quan hệ.
Tích hợp Phân tích AI: Thêm các nút trên UI kích hoạt các phân tích AI (qua API gọi đến ai_service.py) trên đồ thị đang xem: tìm vòng lặp tiềm ẩn, tìm đường cụt, gợi ý khu vực cần khám phá/xác thực tiếp theo.
Giải quyết các lo ngại của bạn:
Mapping Neo4j không mong muốn: Cách tiếp cận này tập trung vào việc cải thiện và kiểm soát dữ liệu trong Neo4j thông qua logic mapping tốt hơn, phân loại thủ công, đánh dấu trạng thái và phân tích AI, thay vì loại bỏ Neo4j. Neo4j trở thành nguồn dữ liệu đáng tin cậy và đang phát triển có kiểm soát.
Điều chỉnh/Sửa lỗi: Giai đoạn B và C cung cấp công cụ trực quan để bạn sửa lỗi, đánh dấu, cập nhật trạng thái trực tiếp trên đồ thị.
Xóa/Thay thế: Mặc dù không sao lưu/khôi phục từ DB ngoài, cơ chế Snapshot/Tagging trong Neo4j (Giai đoạn C) cho phép quản lý phiên bản. Nếu bản đồ quá tệ, bạn có thể xóa các node/edge thuộc phiên bản đó và bắt đầu lại, có thể dựa trên luồng chính bạn tự định nghĩa thủ công (dùng công cụ Giai đoạn B/C).
Giảm Client chạy lại: Bằng cách phân loại element (ignore, non_interactive), đánh dấu node/edge (confirmed), và cải thiện AI Planner (dùng dữ liệu này), client sẽ hoạt động hiệu quả hơn nhiều. Tính năng "Pause Mapping" cũng giúp kiểm soát. Việc bạn có thể tự định nghĩa luồng chính (qua Giai đoạn B/C) càng làm giảm nhu cầu client khám phá lại.

# README - Dự án HPT Automation - Cập nhật 05/05/2025

## Mục tiêu Tổng thể

Xây dựng hệ thống tự động hóa Android đa năng, tập trung vào việc tự động xây dựng bản đồ ứng dụng (App Mapping) và tương tác thông minh.

## Trạng thái Hiện tại (Sau các phiên làm việc gần nhất)

**1. Backend API (Tương tác Client - `/phone/explore_step`)**

* **API `/phone/explore_step`:** Hiện đang là API chính cho client (MacroDroid) gửi trạng thái UI và nhận hành động tiếp theo cho việc mapping.
* **Xử lý Đồng bộ:** Logic xử lý state, ghi log PostgreSQL, và cập nhật Neo4j (tạo/cập nhật node, cạnh) được thực hiện **đồng bộ** bên trong hàm `handle_explore_step` của `app/phone/controller.py`.
* **Planner:** Tạm thời **bỏ qua AI Planner** (`ai_service.plan_exploration_action`) do các vấn đề về quyết định chưa chính xác. Thay vào đó, đang sử dụng một **planner tuần tự đơn giản** (`plan_sequential_click` trong `controller.py` hoặc `planner.py`) với logic:
    * Ưu tiên click vào các element có `resource-id` hoặc `content-desc` chưa được thử từ màn hình hiện tại.
    * Click theo thứ tự element xuất hiện trong state UI.
    * Tránh click lại ngay vào element vừa gây ra loop quay lại màn hình hiện tại.
    * Fallback về action "back" nếu hết element để thử, sau đó là "stuck" (hoặc "wait").
* **Định dạng `nextAction`:** Output của planner đơn giản đã được **sửa lại** để trả về cấu trúc JSON chuẩn mà MacroDroid mong đợi (`actionType: run_macro`, `macro_code`, `params.target{...}`, `random_delay_ms`,...).
* **CSRF Protection:** Blueprint `/phone` đã được **loại trừ (exempt)** khỏi kiểm tra CSRF token để client gọi API không bị lỗi 400.

**2. Database (PostgreSQL - `database.py`)**

* **Bảng `exploration_logs`:** Đã tạo bảng này để lưu log thô chi tiết từ API `/phone/explore_step`.
* **Bảng `task_assignments`:** Đã thêm cột `mapping_status` (kiểu `VARCHAR`, default 'active', NOT NULL) và cột `updated_at` (kiểu `TIMESTAMPTZ`, nên có trigger tự động cập nhật). Hàm cập nhật status (`update_task_mapping_status`) đã được tạo.
* **Bảng `api_keys`:** Đã có bảng này. Các hàm `add_api_key`, `get_active_api_keys_by_provider` đã được tạo/sửa để xử lý việc lưu key mã hóa (`BYTEA` hoặc TEXT chứa Base64) và đọc/giải mã key `active` cho việc xoay vòng.
* **Mã hóa (`encryption.py`):** Đã tạo module này với logic dùng thư viện `cryptography` (Fernet) để mã hóa/giải mã API key. Yêu cầu biến môi trường `API_ENCRYPTION_KEY` trong file `.env`.
* **Tiện ích (`utils.py`):** Đã tạo file này chứa các hàm helper như `determine_screen_id_from_state`, `process_raw_ui_state`.
* **Cấu hình (`config.py`):** Đã cập nhật để đọc `SQLALCHEMY_DATABASE_URI` (cho SQLAlchemy/APScheduler) và `API_ENCRYPTION_KEY` từ file `.env`.

**3. Neo4j Data & Logic (`graph_db.py`)**

* **Dọn dẹp Dữ liệu:** Đã thực hiện xóa dữ liệu cũ (`MATCH (n:Screen) DETACH DELETE n`).
* **Chuẩn hóa Tên Thuộc tính:** Thống nhất sử dụng `snake_case` (ví dụ: `screen_id`, `app_name`, `activity_name`, `element_count`, `elements`...) cho tất cả các thuộc tính của node `:Screen` và cạnh `:TRANSITION` được tạo bởi ứng dụng. Code Python (trong `graph_db.py`, `controller.py`...) đã được cập nhật để dùng tên chuẩn này. **Cần đảm bảo dữ liệu cũ (nếu còn sót) cũng được đổi tên trong Neo4j.**
* **Hàm `merge_screen`:** Đã sửa lỗi `CypherTypeError` do lưu kiểu dữ liệu không hợp lệ (Map `coordinates`, đối tượng `datetime`) vào list `elements`. Hiện tại lưu `coordinate_x`, `coordinate_y` riêng và `last_seen_timestamp` dạng chuỗi ISO. Hàm này đảm bảo tạo/cập nhật các thuộc tính chuẩn `screen_id`, `app_name`, `activity_name`, `status`, `elements` (khởi tạo `[]`), `element_count`, `last_seen`, `created_at`, `updated_at`.
* **Hàm `merge_transition`:** Đã sửa để dùng tên chuẩn `screen_id`, lưu `action_details` và cập nhật counts.
* **Hàm `get_app_graph_data`:** Đã sửa lỗi cú pháp Cypher (`Variable r not defined`). Query đã được cập nhật để dùng tên chuẩn `screen_id`, `app_name`... và xử lý các trường hợp thuộc tính bị thiếu (`None`) một cách an toàn hơn (ví dụ: bỏ qua node thiếu `screen_id`).
* **Hàm `update_element_interaction_stats`:** Đã định nghĩa hàm này để cập nhật `attempt_count`, `success_count`... cho element trong list `elements` của node Screen.
* **Tình trạng Dữ liệu Hiện tại (Ví dụ app 'com.ss.android.ugc.trill'):** Query `get_app_graph_data` đang trả về một số node (ví dụ: 2 nodes) nhưng **0 edges**. Điều này cho thấy việc **tạo cạnh transition** đang gặp vấn đề hoặc chưa diễn ra.

**4. Admin UI (`admin_routes.py`, `templates/`)**

* **Layout & Styling:** Đã sửa lỗi hiển thị nút bấm (dùng Bootstrap 5 + Font Awesome thay vì CSS tùy chỉnh), sửa lỗi layout không full màn hình (dùng `container-fluid`).
* **Trang Task Assignments:** Nút Pause/Resume đã hoạt động ở backend (gọi API cập nhật `mapping_status`). JavaScript frontend gọi đúng API (có prefix `/admin`). Cần kiểm tra logic controller để đảm bảo việc pause thực sự có hiệu lực với client.
* **Mapping Viewer (`/admin/mapping/<app_name>`):**
    * Trang và route đã tồn tại.
    * Đã tích hợp Cytoscape.js.
    * Dropdown chọn App đã hoạt động (lấy `app_name` từ Neo4j).
    * Việc hiển thị đồ thị đang gặp vấn đề do `get_app_graph_data` trả về **0 edges**. Cần giải quyết vấn đề tạo cạnh trong Neo4j.
    * Đã có logic JS để khi click vào node sẽ mở trang phân loại element.
* **Element Classifier (`/admin/screen/<screen_id>/elements`):**
    * Trang và route đã tồn tại.
    * Đã có link điều hướng đến trang này từ trang Logs (cột `screen_id`).
    * **Cần kiểm thử và hoàn thiện:** Hiển thị danh sách `elements` từ Neo4j (yêu cầu `merge_screen` lưu đúng), chức năng phân loại qua dropdown và lưu lại, chức năng gọi AI gợi ý (tùy chọn).

**5. Tác vụ nền (`background_tasks.py`)**

* Hàm `analyze_logs_and_update_map` tạm thời **không còn là nơi chính** để tạo node/cạnh cơ bản (do đã chuyển sang xử lý đồng bộ trong `handle_explore_step`).
* Job tương ứng (`analyze_map_logs_job`) trong `scheduler_runner.py` nên được **comment out hoặc xóa đi** để tránh xung đột hoặc xử lý thừa.
* Tác vụ nền này có thể được xem xét lại sau cho các mục đích phân tích phức tạp hơn (tìm vòng lặp, xác nhận trạng thái...).

## Các Vấn đề Còn Tồn đọng / Bước Tiếp theo Ưu tiên

1.  **[QUAN TRỌNG] Xác minh và Sửa lỗi Tạo Cạnh Neo4j (`:TRANSITION`):**
    * Kiểm tra kỹ logic trong `handle_explore_step` (controller) và `merge_transition` (graph_db) để đảm bảo cạnh được tạo ra đúng cách khi có sự thay đổi màn hình và `previous_action` hợp lệ.
    * Chạy client để tạo ra các transition và theo dõi log server xem `merge_transition` có được gọi và thành công không.
    * Kiểm tra trực tiếp Neo4j xem cạnh có được tạo với đầy đủ thuộc tính (`action_details`, `status`) không.
2.  **Kiểm thử Mapping Viewer:** Sau khi đảm bảo cạnh được tạo, kiểm tra lại trang `/admin/mapping/<app_name>` xem đồ thị có hiển thị đúng các node và cạnh liên kết chưa.
3.  **Hoàn thiện và Kiểm thử Trang Phân loại Element:**
    * Đảm bảo trang `/admin/screen/<screen_id>/elements` hiển thị đúng danh sách `elements` lấy từ thuộc tính node Neo4j.
    * Kiểm tra chức năng phân loại (lưu `classification` vào đúng element trong list).
4.  **Kiểm tra Logic Pause/Resume trong Controller:** Xác nhận hàm `handle_explore_step` trả về action `wait` khi `mapping_status` là `paused`.
5.  **Tinh chỉnh Planner Tuần tự:** Đánh giá hiệu quả của `plan_sequential_click`. Nó có bỏ sót element nào không? Có bị kẹt không? Có cần thêm heuristic nhận diện element không?
6.  **Dọn dẹp Dữ liệu Neo4j:** Chạy lại các lệnh Cypher để đảm bảo tất cả node `:Screen` đều có các thuộc tính chuẩn (`screen_id`, `app_name`, `activity_name`, `status`, `elements=[]`...) và không còn tên camelCase.

## Các Quyết định / Lưu ý Quan trọng

* Thống nhất dùng `snake_case` cho tên thuộc tính trong Neo4j.
* Cập nhật Neo4j (node/cạnh cơ bản) đang được thực hiện **đồng bộ** trong API `/phone/explore_step`.
* Tạm thời **bỏ qua AI Planner**, dùng planner tuần tự đơn giản (`plan_sequential_click`).
* API cho client (`/phone/*`) đã được **loại trừ khỏi CSRF**.
* Cần biến môi trường `API_ENCRYPTION_KEY` trong file `.env` để mã hóa/giải mã API key.
* Giao diện Admin đang dùng Bootstrap 5 và Font Awesome.

---