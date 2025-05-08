Tổng kết Dự án Tự động hóa HPT (Tính đến 07/05/2025)
File này tóm tắt các vấn đề chính đã được thảo luận, các giải pháp đã triển khai và trạng thái công việc hiện tại của dự án tự động hóa HPT, tập trung vào các module Admin UI, Mapping và Khám phá.
I. Các Vấn đề Chính Đã Thảo Luận và Giải Quyết:
1. Trang Mapping Viewer (/admin/mapping/...):
   * Lỗi Hiển thị Đồ thị (Cytoscape):
      * Ban đầu đồ thị không hiển thị do container #cy có height: 0px.
      * Giải pháp: Điều chỉnh CSS để đảm bảo container cha (.graph-display-area, .card-body) có chiều cao xác định và #cy chiếm 100% chiều cao đó. Đã khắc phục.
   * Lỗi Lấy Dữ liệu (404, 400):
      * Lỗi 404 do gọi sai URL API (ví dụ: /admin/api/... thay vì /api/... do blueprint không có prefix).
      * Lỗi 400 do API mong đợi app_name là query parameter nhưng JS lại gửi trong path.
      * Giải pháp: Xác định đúng URL API dựa trên cách đăng ký blueprint và sửa lại lệnh fetch trong Javascript. Đã khắc phục.
   * Lỗi Tạo URL (BuildError):
      * Lỗi url_for không tìm thấy endpoint (ví dụ: admin.admin_index vs admin.index, admin.get_mapping_data vs admin.api_get_app_graph_data).
      * Lỗi url_for yêu cầu tham số không cần thiết (ví dụ: yêu cầu app_name cho API lấy dữ liệu map dù nó là query param).
      * Giải pháp: Sửa tên endpoint trong url_for cho đúng. Sử dụng URL cố định trong Javascript thay vì url_for cho các API đơn giản. Đã khắc phục.
   * Hiển thị Chi tiết Node/Cạnh:
      * Panel chi tiết cần hiển thị thông tin khi click vào node/cạnh.
      * Cần hiển thị ảnh chụp màn hình trong chi tiết node.
      * Giải pháp: Cập nhật API backend để trả về các thuộc tính cần thiết (bao gồm screenshot_url). Cập nhật Javascript để hiển thị thông tin và ảnh trong panel #selection-details. Đã triển khai.
   * Dropdown Chọn App Rỗng:
      * Do hàm graph_db.get_distinct_app_names không trả về dữ liệu.
      * Nguyên nhân: Các node :Screen trong Neo4j thiếu thuộc tính app_name.
      * Giải pháp: Đảm bảo hàm graph_db.merge_screen luôn lưu app_name. (Cần kiểm tra lại luồng tạo node).
2. Lưu trữ và Xử lý Dữ liệu Neo4j:
   * Nhận diện Node không nhất quán: Hàm determine_screen_id_from_state tạo ra các ID khác nhau cho cùng một màn hình do quá nhạy cảm với thay đổi element.
      * Giải pháp: Cải thiện hàm hash bằng cách chỉ sử dụng các element ổn định (có resource-id/content-desc) và các thuộc tính cốt lõi (element_id, identifier_type), bỏ qua element_type, text_content. Đã triển khai.
   * Không tạo được Cạnh (:TRANSITION):
      * Do client chưa gửi previous_action đúng cấu trúc.
      * Do lỗi CypherTypeError khi cố gắng lưu dictionary action_details vào thuộc tính cạnh.
      * Giải pháp: Client gửi previous_action với source_screen_id, actionType, onElementId, identifier_type. Sửa hàm merge_transition để lưu từng thuộc tính nguyên thủy (actionType, element_id, macro_code...) thay vì cả dictionary. Đã khắc phục.
   * Thiếu screenshot_path: Tên file ảnh không được lưu vào Neo4j.
      * Do lỗi logic truyền tham số từ client -> routes -> controller -> graph_db.
      * Do lỗi gán thuộc tính trong Cypher (s += $props).
      * Giải pháp: Đảm bảo client gửi screenshot_filename (chỉ tên file). Sửa các hàm backend để truyền đúng tên file. Sửa merge_screen để gán từng thuộc tính tường minh trong Cypher. Đã khắc phục.
3. Trang Phân loại Element (/admin/screen/.../elements):
   * Không hiển thị Element: Do danh sách element chi tiết không còn được lưu trực tiếp trên node Neo4j.
      * Giải pháp: Lấy danh sách element chi tiết từ log PostgreSQL gần nhất (db.get_last_detailed_ui_state_for_screen) và hợp nhất với thông tin classification/override từ bảng element_classifications. Đã triển khai.
   * Lưu Classification lỗi (CypherTypeError): Do cố gắng cập nhật thuộc tính list chứa map trong Neo4j.
      * Giải pháp: Chuyển sang lưu classification vào bảng element_classifications trong PostgreSQL. Tạo API mới (/api/element/classify) và các hàm DB tương ứng (upsert_element_classification, get_element_classifications_for_screen). Đã triển khai.
   * Classification reset khi tải lại trang: Do lỗi đọc lại classification đã lưu từ PostgreSQL hoặc lỗi logic hợp nhất.
      * Giải pháp: Thêm logging để debug hàm get_element_classifications_for_screen và logic hợp nhất trong route admin_screen_elements. (Đã thêm log, cần theo dõi thêm nếu vấn đề còn).
   * Gợi ý AI lỗi ("Screen or elements not found"): Do API gợi ý cố gắng đọc lại element từ log DB thay vì dùng dữ liệu đang hiển thị.
      * Giải pháp: Sửa API gợi ý (/api/screen/.../suggest_classifications) thành phương thức POST, nhận danh sách element từ frontend gửi lên. Sửa Javascript để thu thập element từ bảng và gửi đi. Đã triển khai.
   * Thêm cột "Đã khám phá?": Cần biết element nào đã được thử tương tác.
      * Giải pháp: Backend lấy thông tin cạnh :TRANSITION từ Neo4j, xác định các element_id đã thử. Thêm cờ is_explored vào dữ liệu element gửi cho frontend. Frontend hiển thị icon check/cross. Đã triển khai.
   * Thêm ghi đè thủ công "Đã khám phá?": Cho phép người dùng tự đánh dấu trạng thái khám phá.
      * Giải pháp: Thêm cột manual_explored_override vào bảng element_classifications (PostgreSQL). Tạo hàm DB và API (/api/element/mark_explored) để cập nhật trạng thái này. Cập nhật UI thành nhóm nút bấm tương tác. Đã triển khai.
   * Hiển thị Ảnh Screenshot:
      * Ảnh không hiển thị do lỗi 404 hoặc Internal Server Error khi truy cập URL ảnh.
      * Nguyên nhân: Đường dẫn lưu trữ (UPLOAD_FOLDER), cách tạo URL (url_for), và route phục vụ ảnh không khớp nhau.
      * Giải pháp: Chuẩn hóa lưu ảnh vào app/static/screenshots/. API upload trả về tên file. Hàm merge_screen lưu tên file vào Neo4j. Hàm admin_screen_elements dùng url_for('serve_app_specific_screenshot', ...) để tạo URL gọi đến route tùy chỉnh /app_screenshots/<filename> (định nghĩa trong app/__init__.py) để phục vụ ảnh. Đã khắc phục.
   * Ảnh quá lớn / Lỗi parse JSON data-element-info:
      * Ảnh tràn khung do CSS.
      * Lỗi Javascript do ký tự đặc biệt trong dữ liệu element làm hỏng JSON khi dùng | tojson | escape.
      * Giải pháp: Sửa CSS ảnh (max-width: 100%). Bỏ bộ lọc | escape sau | tojson và dùng | default(None) cho các giá trị trong dictionary khi tạo data-element-info. Đã triển khai.
   * Thêm Overlay tương tác trên ảnh: Vẽ vùng tương ứng với element và highlight khi rê chuột.
      * Giải pháp: Cập nhật Javascript để đọc tọa độ/bounds từ data-element-info, tính toán vị trí/kích thước (hiện tại dùng tọa độ điểm và kích thước mặc định), vẽ overlay, gắn sự kiện hover/click. Đã triển khai (cần client gửi tọa độ/bounds và có thể cần cải thiện scaling).
4. Client (MacroDroid/Termux):
   * Upload Ảnh: Gặp khó khăn với Multipart Form Data trong MacroDroid.
      * Giải pháp: Sử dụng script Termux (upload.sh) với curl để thực hiện upload. Đã khắc phục các lỗi về đường dẫn, quyền, và định dạng kết thúc dòng.
   * Gửi Dữ liệu: Cần đảm bảo client gửi đúng cấu trúc JSON, đúng key (screenshot_filename, previous_action với cấu trúc chuẩn) và đúng giá trị (tên file từ API upload, tọa độ/bounds). (Đang trong quá trình hoàn thiện).
II. Trạng Thái Hiện Tại và Công Việc Tiếp Theo:
* Hoạt động tốt:
   * Admin UI cơ bản.
   * Mapping Viewer hiển thị được nodes và edges.
   * Panel chi tiết trên Mapping Viewer hiển thị thông tin node (kèm ảnh nếu có) và cạnh.
   * Trang Element Classification hiển thị danh sách element từ log, cho phép lưu classification vào DB, cho phép ghi đè trạng thái khám phá, và hiển thị ảnh chụp màn hình với overlay tương tác (dựa trên tọa độ điểm).
   * Cơ chế upload ảnh và lưu/phục vụ ảnh hoạt động.
   * Nhận diện node (determine_screen_id) đã được cải thiện (ít tạo node trùng hơn).
   * Tạo cạnh (merge_transition) hoạt động, lưu các thuộc tính cơ bản.
* Cần làm tiếp (Ưu tiên):
   1. Hoàn thiện Planner Thông minh (Ưu tiên 2):
      * Hiện tại: Vẫn đang dùng plan_sequential_click hoặc một phiên bản planner chưa hoàn chỉnh.
      * Công việc: Viết hoàn chỉnh hàm plan_intelligent_exploration_action trong controller.py (hoặc planner.py) để ưu tiên hành động dựa trên Classification (lấy từ PostgreSQL) và Lịch sử Tương tác (cạnh :TRANSITION từ Neo4j).
      * Tích hợp planner mới này vào hàm handle_explore_step.
   2. Cải thiện Overlay Tương tác:
      * Hiện tại: Dùng tọa độ điểm và kích thước mặc định, chưa có scaling.
      * Công việc: Yêu cầu client gửi kích thước màn hình gốc. Cập nhật Javascript trong admin_screen_elements.html để tính toán tỷ lệ scale và vẽ overlay chính xác hơn dựa trên bounds (nếu client gửi được) hoặc coordinates + scaling.
   3. Thêm Quản lý Cơ bản trên Mapping Viewer (Ưu tiên 3):
      * Hiện tại: Chỉ xem.
      * Công việc: Thêm các nút vào panel chi tiết (ví dụ: "Xóa Transition Provisional", "Đánh dấu Node/Edge Confirmed") và tạo các API backend tương ứng để cập nhật dữ liệu Neo4j.
   4. Xây dựng Tính năng Đánh dấu Lộ trình Chính (Ưu tiên 3):
      * Hiện tại: Chưa có.
      * Công việc: Thiết kế và triển khai UI trên Mapping Viewer cho phép Admin chọn chuỗi node/cạnh. Tạo cơ chế lưu trữ lộ trình này (PostgreSQL hoặc Neo4j). Cập nhật Planner để ưu tiên theo lộ trình.
   5. Kiểm tra và Hoàn thiện Client: Đảm bảo client gửi đầy đủ và chính xác các thông tin cần thiết (previous_action, screenshot_filename, bounds/coordinates, kích thước màn hình gốc).
* Cần theo dõi:
   * Tính nhất quán của determine_screen_id trong thực tế.
   * Hiệu năng của việc lấy dữ liệu và vẽ đồ thị/overlay khi dữ liệu lớn dần.
   * Độ chính xác của việc lấy classification từ DB và hợp nhất với element từ log.
Phiên làm việc tiếp theo nên tập trung vào Hoàn thiện Planner Thông minh (Ưu tiên 2).