# README: Tình trạng Dự án và Các Vấn đề Ảnh Screenshot (Tính đến 19/05/2025)

## I. Mục tiêu chính đang thực hiện:
Hoàn thiện trang "Quản lý Vấn đề Node (Screens)" (`admin_node_management.html`) với các chức năng:
1.  Hiển thị danh sách các Node (Screens) từ Neo4j.
2.  Hiển thị ảnh thumbnail cho mỗi Node.
3.  Cho phép click vào ảnh thumbnail để mở modal `#managePieConditionsModal`.
4.  Modal `#managePieConditionsModal` (layout 3 cột):
    * **Cột 1 (Ảnh Node):** Hiển thị ảnh screenshot của Node, cho phép vẽ và click vào các overlay của UI elements.
    * **Cột 2 (Danh sách Elements):** Liệt kê các UI elements có trên ảnh.
    * **Cột 3 (Điều kiện PIE):** Hiển thị các điều kiện PIE đã chọn; cho phép thêm/sửa/xóa điều kiện.
5.  Luồng tạo PIE mới cho Node "unknown":
    * Click nút "Tạo PIE Mới" -> Mở `#managePieConditionsModal` để chọn elements.
    * Từ `#managePieConditionsModal`, nhấn "Tiếp tục" -> Mở `#defineNewPieMetadataModal` để điền thông tin metadata và lưu PIE mới.
6.  Luồng sửa PIE cho Node "defined":
    * Click ảnh thumbnail -> Mở `#managePieConditionsModal` để xem/sửa conditions.

## II. Luồng Xử Lý Ảnh Screenshot ĐÃ THỐNG NHẤT:

1.  **Client (MacroDroid) gọi API `/phone/explore_step`:**
    * Gửi `raw_ui_state`.
    * Gửi `screenshot_filename` (đây là **CHỈ TÊN FILE**, ví dụ: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.png`).
    * **Không gửi file ảnh thực tế** trong request này.

2.  **Server - Xử lý tại `/phone/explore_step`:**
    * Trong `app/phone/controller.py` (hàm `handle_explore_step`) và `app/phone/utils.py` (hàm `process_raw_ui_state`).
    * Hàm `graph_db.merge_screen` (trong `app/graph_db.py`) sẽ được gọi.
    * `graph_db.merge_screen` lưu `app_name` và `screenshot_path` (là giá trị `screenshot_filename` **CHỈ TÊN FILE** từ client) vào các thuộc tính của Node `:Screen` trong Neo4j.

3.  **Client (MacroDroid) - Gửi file ảnh thật:**
    * Sau khi gọi `/phone/explore_step`, client thực hiện một request **POST multipart/form-data** đến một API upload riêng. Dựa trên log và `client.txt`, URL này là: `http://<your_server_ip>:5000/phone/api/upload/screenshot`.
    * Request này phải chứa:
        * **Trường file (file part):** Tên trường là `screenshot_file` (dựa trên log `Request Files Keys: ['screenshot_file']`). Nội dung là file ảnh thật.
        * **Tham số form `filename`:** Giá trị là tên file đã gửi ở Bước 1 (ví dụ: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.png`). Server sẽ dùng tên này để lưu file.
        * **Tham số form `app_name`:** Tên package của ứng dụng (ví dụ: `com.ss.android.ugc.trill`). Server sẽ dùng tên này để tạo thư mục con.

4.  **Server - Xử lý tại API Upload Ảnh (ví dụ: `/phone/api/upload/screenshot` trong `app/phone/routes.py`):**
    * Hàm xử lý (ví dụ: `upload_screenshot_final_version` hoặc tên tương tự) nhận `uploaded_file_storage` (từ `request.files['screenshot_file']`), `filename_from_form` (từ `request.form.get('filename')`), và `app_name_from_form` (từ `request.form.get('app_name')`).
    * Lấy `storage_base_path` từ `current_app.config.get('SCREENSHOT_STORAGE_PATH')` (phải trỏ đến `...\hpt10\app\static\screenshots\`).
    * Tạo thư mục con: `app_specific_storage_directory = os.path.join(storage_base_path, app_name_from_form)`. Tạo thư mục này nếu chưa có.
    * Lưu file ảnh vào đường dẫn đầy đủ: `full_path_to_save_file = os.path.join(app_specific_storage_directory, filename_from_form)`.
    * Trả về JSON cho client, bao gồm `"filename_saved_on_server": filename_from_form` để client có thể xác nhận (nếu cần).

5.  **Server - Hiển thị ảnh ở Admin UI (Backend tạo URL):**
    * Các hàm backend (ví dụ: `view_node_management`, `api_get_managed_nodes` trong `admin_routes.py`, và các hàm tương tự cho `admin_mapping_viewer.html`, `admin_screen_elements.html`) khi cần hiển thị ảnh sẽ:
        * Đọc `app_name` và `screenshot_path` (chỉ tên file) từ Node `:Screen` trong Neo4j.
        * Tạo `screenshot_full_url` bằng cách gọi: `url_for('serve_screenshot_for_app', app_name=node_app_name, filename=node_screenshot_path)`.
    * URL được tạo sẽ có dạng: `/screenshots/APP_NAME/TEN_FILE.png`.

6.  **Server - Route Phục Vụ Ảnh (trong `app/__init__.py`):**
    * Định nghĩa route: `@app.route('/screenshots/<string:app_name>/<string:filename>')` với endpoint name là `serve_screenshot_for_app`.
    * Hàm `serve_screenshot_for_app(app_name, filename)` sẽ:
        * Lấy `screenshots_base_dir` từ `app.config.get('SCREENSHOT_STORAGE_PATH')`.
        * Tạo `app_specific_dir_to_serve_from = os.path.join(screenshots_base_dir, app_name)`.
        * Gọi `send_from_directory(app_specific_dir_to_serve_from, filename, as_attachment=False)`.

7.  **Server - Xóa Ảnh (trong `admin_routes.py` - `api_delete_managed_node`):**
    * Trước khi xóa Node khỏi Neo4j, đọc `app_name` và `screenshot_path` (chỉ tên file).
    * Xóa file vật lý tại `config.SCREENSHOT_STORAGE_PATH / app_name / screenshot_path`.

## III. Tình Trạng Hiện Tại và Các Vấn Đề Cần Fix:

### A. Trang "Quản lý Vấn đề Node" (`admin_node_management.html`):

1.  **Hiển thị ảnh thumbnail:**
    * **LẦN ĐẦU LOAD TRANG:** Đã hiển thị ảnh đúng (sau khi `view_node_management` được sửa để tạo `screenshot_full_url` nhất quán).
    * **SAU KHI LỌC NODES:** **Vẫn còn lỗi.** JavaScript (`table_handler.js` - hàm `renderNodeRow`) có thể đang không sử dụng đúng `node.screenshot_full_url` để tạo thẻ `<img>`, dẫn đến hiển thị text `{node.screenshot_full_url}...` thay vì ảnh.
        * **Cần làm:** Kiểm tra lại hàm `renderNodeRow` trong `table_handler.js` để đảm bảo nó dùng template literals (dấu \` \`) và `${node.screenshot_full_url}` để chèn URL vào `src` của thẻ `<img>`.

2.  **Modal `#managePieConditionsModal`:**
    * **Layout 3 Cột:** Đã được yêu cầu (Cột 1: Ảnh `col-lg-3`; Cột 2: List Elements `col-lg-4`; Cột 3: List Conditions `col-lg-5`). HTML và CSS cần được cập nhật/xác nhận cho layout này.
    * **Hiển thị ảnh trong modal (Cột 1):**
        * **Vấn đề:** Log cho thấy `screenshotImg.clientWidth` và `clientHeight` là 0 ngay cả sau khi modal `shown` và ảnh `onload`, dẫn đến "vẽ không đúng trên hình" (do tỷ lệ scale sai) hoặc không vẽ được overlay.
        * **Cần làm:** Tinh chỉnh logic trong `modal_manage_pie.js` (hàm `processImageAndElementsWhenReady` và có thể là `waitForImageDimensions`) để đợi một cách đáng tin cậy hơn cho đến khi ảnh thực sự có kích thước render trên DOM trước khi gọi `drawInteractiveOverlays`. Xem xét việc sử dụng `getBoundingClientRect()` hoặc các kỹ thuật khác nếu `clientWidth/Height` vẫn không ổn định. Đảm bảo CSS của `#pieConditionsImageContainer` và `#pieConditionsScreenshot` cho phép ảnh có không gian để render và đạt 100% chiều cao của container ảnh.
    * **Click vào overlay trên ảnh (Cột 1):**
        * **Vấn đề:** Hiện tại không click được vào element được vẽ trên hình để thêm vào "Điều kiện Nhận diện PIE Đã Chọn".
        * **Cần làm:**
            * Đảm bảo `drawInteractiveOverlays` (trong `utils.js`) gắn đúng sự kiện `click` cho mỗi overlay và gọi `selectionHandler` với `elementIndex` chính xác.
            * Đảm bảo `handleElementSelectionFromVisualizer` (trong `modal_manage_pie.js`) nhận đúng `elementIndex`, lấy đúng `elementData` từ `rawElementsDataForModal`, và cập nhật mảng `currentSelectedPieConditions` một cách chính xác.
            * Đảm bảo `renderSelectedPieConditions` và `updateVisualizerSelections` được gọi sau đó để làm mới UI.
    * **Chiều cao Cột 2 và 3:**
        * **Yêu cầu:** Chiều cao bằng modal body và có thanh cuộn nội bộ.
        * **Cần làm:** Điều chỉnh CSS (trong `admin_node_management_styles.css`) cho các wrapper của list elements và list conditions để sử dụng `flex-grow: 1` và `overflow-y: auto` trong một container flex cha có chiều cao xác định (là cột của chúng).

### B. Trang "Chi tiết Node (Màn hình)" (`admin_screen_elements.html` - URL `/admin/mapping/screen-elements/<screen_id>`):

* **Vấn đề:** Bạn báo cáo trang này (ví dụ khi click vào node từ `admin_mapping_viewer.html`) không hiển thị được ảnh.
* **Nguyên nhân có thể:** Hàm backend phục vụ trang này (hoặc API nó gọi để lấy dữ liệu node) đang sử dụng cách tạo URL ảnh cũ, không theo luồng thống nhất mới (tức là không dùng `url_for('serve_screenshot_for_app', app_name=..., filename=...)`).
* **Cần làm:**
    1.  Xác định route Flask và hàm xử lý cho trang `admin_screen_elements.html`.
    2.  Kiểm tra cách nó lấy thông tin `app_name` và `screenshot_path` (chỉ tên file) của node.
    3.  Đảm bảo nó tạo `screenshot_full_url` bằng cách gọi `_generate_screenshot_url_for_admin_ui` (hoặc logic tương tự).
    4.  Đảm bảo template Jinja2 của trang này (`admin_screen_elements.html`) sử dụng `screenshot_full_url` để hiển thị ảnh.

### C. Trang "Bản đồ App" (`admin_mapping_viewer.html`):

* **Vấn đề tiềm ẩn:** Tương tự như `admin_screen_elements.html`, nếu trang này hiển thị ảnh thumbnail hoặc ảnh chi tiết khi click vào node trên bản đồ, nó cũng cần được cập nhật để sử dụng luồng tạo URL ảnh mới.
* **Cần làm:**
    1.  Kiểm tra API mà `admin_mapping_viewer.html` gọi để lấy dữ liệu đồ thị (có thể là `api_get_app_graph_data`).
    2.  Đảm bảo API này trả về `screenshot_full_url` được tạo đúng cách cho mỗi node.
    3.  JavaScript của `admin_mapping_viewer.html` phải sử dụng URL này.

### D. API Upload Ảnh (`/phone/api/upload/screenshot` trong `app/phone/routes.py`):

* **Tình trạng:** Đã có nhiều phiên bản được thảo luận. Phiên bản cuối cùng (ví dụ: `upload_screenshot_final_version` hoặc `upload_screenshot_with_server_uuid_name` tùy theo việc client hay server quyết định tên file UUID) phải đảm bảo:
    * Nhận `app_name` và `filename` (tên file để lưu, khớp với `screenshot_path` trong Neo4j) từ tham số form của client.
    * Lưu file vào `config.SCREENSHOT_STORAGE_PATH / app_name / filename`.
* **Script client (`upload.sh`):** Phải được sửa để gửi đúng các tham số form `filename` và `app_name` cùng với file.

## IV. Các Bước Tiếp Theo Ưu Tiên:

1.  **Hoàn thiện API Upload Ảnh:** Đảm bảo client (script `upload.sh` và MacroDroid) gửi đúng tham số, và API server lưu file vào đúng `STORAGE_PATH/APP_NAME/FILENAME_FROM_FORM.png`. **Đây là nền tảng cho mọi thứ khác.**
2.  **Fix `table_handler.js` - `renderNodeRow`:** Sửa lỗi hiển thị ảnh sau khi lọc trên trang `admin_node_management.html`.
3.  **Fix `modal_manage_pie.js`:**
    * Giải quyết vấn đề `clientWidth/Height is 0` để ảnh hiển thị đúng kích thước trong modal.
    * Đảm bảo sự kiện click trên overlay ảnh hoạt động, cập nhật đúng danh sách conditions.
    * Tinh chỉnh CSS cho layout 3 cột và scroll nếu cần.
4.  **Rà soát `admin_screen_elements.html`:** Cập nhật backend và frontend của trang này để hiển thị ảnh đúng theo luồng mới.
5.  **Rà soát `admin_mapping_viewer.html`:** Tương tự, cập nhật để hiển thị ảnh đúng.

File này sẽ giúp chúng ta có một cái nhìn tổng quan và tập trung vào các vấn đề cần giải quyết trong các phiên làm việc tiếp theo.
