# Kế hoạch Chuyển đổi và Xây dựng Hệ thống Tài liệu Dự án (HPT11)

**Ngày tạo:** 20/05/2025
**Người tạo:** Gemini (AI) & Developer

## 1. Mục tiêu

Tài liệu này mô tả kế hoạch chuyển đổi hệ thống tài liệu hiện tại của dự án (từ trang `/admin/api-docs` dựa trên CSDL) sang một hệ thống tài liệu tập trung, dựa trên các file Markdown được lưu trữ trên GitHub. Mục tiêu chính là:

* **Cải thiện khả năng nắm bắt thông tin dự án cho AI (Gemini):** Giúp AI hiểu rõ hơn về luồng code, cấu trúc CSDL, các chức năng chính, và API của dự án trong các phiên làm việc mới, giảm thiểu thời gian giải thích lặp lại.
* **Tạo nguồn tài liệu tham khảo tập trung và dễ cập nhật:** Cho phép developer và các thành viên trong nhóm dễ dàng truy cập, đọc hiểu và duy trì tài liệu dự án.
* **Hiển thị tài liệu trên trình duyệt một cách thân thiện:** Tích hợp vào giao diện admin của Flask để hiển thị nội dung Markdown dưới dạng HTML, thay thế chức năng của trang `/admin/api-docs` hiện tại.
* **Quản lý phiên bản tài liệu cùng với code:** Lưu trữ tài liệu trên GitHub giúp theo dõi thay đổi và đồng bộ với các phiên bản code.

## 2. Vấn đề Hiện tại và Giải pháp Đề xuất

* **Vấn đề:**
    * AI (Gemini) cần được cung cấp lại bối cảnh dự án trong mỗi phiên làm việc mới, gây mất thời gian.
    * Thông tin dự án có thể nằm rải rác ở nhiều nơi (code, CSDL, các file README riêng lẻ).
    * Trang `/admin/api-docs` hiện tại lấy dữ liệu từ CSDL, có thể không tiện lợi cho việc xem nhanh hoặc chia sẻ ngoài hệ thống.

* **Giải pháp Đề xuất:**
    * Xây dựng một thư mục `docs/` tại gốc dự án, chứa các file tài liệu dạng Markdown.
    * Tổ chức các file Markdown theo cấu trúc thư mục con rõ ràng, theo chủ đề (kiến trúc, CSDL, API, chức năng, luồng xử lý).
    * Developer sẽ duy trì các file Markdown này trên GitHub.
    * AI sẽ sử dụng các file Markdown này (do người dùng upload) để nắm bắt thông tin dự án.
    * Tạo một route mới trong Flask (ví dụ: `/admin/documentation/`) để đọc, chuyển đổi Markdown sang HTML và hiển thị trên trình duyệt, có sidebar điều hướng.

## 3. Cấu trúc Thư mục `docs/` Đề xuất

hpt11/├── app/├── static/├── templates/├── docs/  <-- THƯ MỤC TÀI LIỆU MỚI│   ├── README.md                 <-- Tổng quan về tài liệu, cách sử dụng, mục lục chính│   ├── 00_PROJECT_OVERVIEW/│   │   └── PROJECT_SUMMARY.md    <-- Mục tiêu, chức năng chính, công nghệ│   ├── 01_ARCHITECTURE/│   │   ├── SYSTEM_ARCHITECTURE.md  <-- Kiến trúc tổng thể, các thành phần│   │   └── DATA_FLOWS.md           <-- Các luồng dữ liệu chính│   ├── 02_DATABASE/│   │   ├── POSTGRESQL_SCHEMA.md    <-- Schema bảng PostgreSQL, mô tả cột, quan hệ (từ automation_schema.sql)│   │   ├── NEO4J_MODEL.md          <-- Labels, Relationships, Properties cho Neo4j│   │   └── SEED_DATA.md            <-- Giải thích về dữ liệu mẫu (từ seed_data.sql nếu cần)│   ├── 03_API_REFERENCE/         <-- Thay thế cho /admin/api-docs│   │   ├── README.md               <-- Giới thiệu chung về API, cách sử dụng tài liệu API│   │   ├── PHONE_CLIENT_API.md     <-- Các API cho client di động (từ app/phone/routes.py)│   │   ├── ADMIN_INTERNAL_API.md   <-- Các API nội bộ cho trang admin (ví dụ: lấy data cho modal)│   │   └── GENERAL_API.md          <-- Các API khác (từ app/routes.py)│   ├── 04_FEATURES/│   │   ├── README.md               <-- Tổng quan các chức năng│   │   ├── APP_MAPPING.md          <-- Chi tiết về chức năng App Mapping (từ README_MAPPING.txt)│   │   ├── STRATEGIES_STAGES.md    <-- Language, Control, MainLoop Strategies và Stages│   │   ├── AI_INTEGRATION.md       <-- AI Personas, Suggestions, Playground, Simulations│   │   ├── SCHEDULED_TASKS.md      <-- Các tác vụ nền và scheduler (APScheduler, background_tasks.py)│   │   └── ... (các feature khác)│   ├── 05_WORKFLOWS/│   │   ├── README.md               <-- Tổng quan các luồng xử lý│   │   ├── PHONE_INTERACTION.md    <-- Luồng xử lý tương tác từ điện thoại (app/phone/controller.py)│   │   ├── PIE_DEFINITION.md       <-- Luồng định nghĩa PIE từ unknown node│   │   └── ... (các workflow khác)│   ├── 06_SETUP_AND_CONFIG/│   │   ├── REQUIREMENTS.md         <-- Hướng dẫn cài đặt (từ requirements.txt, requirements2.txt)│   │   └── ENVIRONMENT_VARIABLES.md  <-- Các biến môi trường cần thiết (từ config.py)│   ├── 07_GLOSSARY.md              <-- Bảng thuật ngữ, các từ viết tắt│   └── images/                     <-- Chứa các hình ảnh (sơ đồ, screenshot) nhúng vào Markdown└── ... (các file và thư mục khác của project)
## 4. Kế hoạch Thực hiện Chi tiết

### Giai đoạn 1: Thiết lập Nền tảng và Cấu trúc Tài liệu (Đã thảo luận)

* **Bước 1.1:** Tạo Cấu trúc Thư mục `docs/` như trên.
* **Bước 1.2:** Tạo các File Markdown Placeholder Ban đầu (file rỗng hoặc chỉ có tiêu đề).
* **Bước 1.3:** Cài đặt Thư viện Python cần thiết: `pip install Markdown Pygments`.
* **Bước 1.4:** Tạo Route Flask (`/admin/documentation/<path:filepath>`) và Template HTML (`admin_documentation_viewer.html`) để Hiển thị Tài liệu Markdown.
    * **Route (`app/admin_routes.py`):**
        * Hàm `get_docs_sidebar_structure(docs_root_path, current_dir_path='')` để tạo cấu trúc sidebar động từ thư mục `docs/`.
        * Hàm `project_documentation_viewer(filepath)`:
            * Xác định đường dẫn an toàn đến file Markdown.
            * Đọc nội dung file.
            * Sử dụng thư viện `markdown` để chuyển đổi sang HTML (với các extension như `fenced_code`, `tables`, `toc`, `codehilite`, `nl2br`, `extra`).
            * Truyền HTML và cấu trúc sidebar vào template.
            * Xử lý trường hợp file không tìm thấy hoặc là thư mục (thử load `README.md` trong thư mục đó).
    * **Template (`templates/admin_documentation_viewer.html`):**
        * Kế thừa từ `admin_base.html`.
        * Bố cục 2 cột: Sidebar điều hướng và Khu vực hiển thị nội dung.
        * Sử dụng macro Jinja2 để render sidebar đệ quy.
        * Link đến file CSS cho Pygments.
        * CSS tùy chỉnh cho trang tài liệu (layout, typography, code blocks, tables, TOC).
* **Bước 1.5:** Tạo file CSS cho Pygments (`app/static/css/pygments_style.css`) bằng lệnh:
    ```bash
    pygmentize -S default -f html -a .codehilite > app/static/css/pygments_style.css
    ```
* **Bước 1.6 (Bổ sung từ thảo luận):** Cập nhật `templates/admin_base.html` để thêm link "Tài liệu Dự án" trong menu sidebar chính, trỏ đến route `/admin/documentation/`.

### Giai đoạn 2: Xây dựng Nội dung Tài liệu Markdown (Đang tiến hành)

* **Bước 2.1:** Tài liệu Tổng quan và Cài đặt:
    * `docs/00_PROJECT_OVERVIEW/PROJECT_SUMMARY.md`
    * `docs/06_SETUP_AND_CONFIG/REQUIREMENTS.md`
    * `docs/06_SETUP_AND_CONFIG/ENVIRONMENT_VARIABLES.md`
* **Bước 2.2:** Tài liệu Cơ sở dữ liệu:
    * **`docs/02_DATABASE/POSTGRESQL_SCHEMA.md`**: Đã được tạo dự thảo dựa trên `automation_schema.sql`. Cần rà soát và bổ sung mô tả chi tiết.
    * `docs/02_DATABASE/NEO4J_MODEL.md`
    * `docs/02_DATABASE/SEED_DATA.md`
* **Bước 2.3:** Tài liệu API (Ưu tiên):
    * Cấu trúc thư mục con trong `docs/03_API_REFERENCE/`.
    * Tạo file Markdown cho từng nhóm API: `PHONE_CLIENT_API.md`, `ADMIN_INTERNAL_API.md`, `GENERAL_API.md`.
    * **Đối với mỗi endpoint:**
        * Tiêu đề: `## METHOD /path/to/endpoint`
        * Mô tả chức năng.
        * Tham số URL (nếu có).
        * Headers đặc biệt (nếu có).
        * Request Body: Mô tả các trường, kiểu dữ liệu, tính bắt buộc, ví dụ JSON.
        * Response Success: Mã trạng thái, mô tả, ví dụ JSON.
        * Response Error: Mã trạng thái, mô tả, ví dụ JSON.
        * Ghi chú (nếu có).
* **Bước 2.4:** Tài liệu Kiến trúc và Luồng xử lý:
    * `docs/01_ARCHITECTURE/SYSTEM_ARCHITECTURE.md`
    * `docs/01_ARCHITECTURE/DATA_FLOWS.md`
    * `docs/05_WORKFLOWS/PHONE_INTERACTION.md`
    * `docs/05_WORKFLOWS/PIE_DEFINITION.md`
* **Bước 2.5:** Tài liệu Chức năng chi tiết:
    * `docs/04_FEATURES/APP_MAPPING.md` (từ `README_MAPPING.txt`)
    * Các file cho Strategies, AI Integration, Scheduled Tasks.
* **Bước 2.6:** Bảng thuật ngữ (`docs/07_GLOSSARY.md`).

### Giai đoạn 3: Hoàn thiện Trang Tài liệu Flask và Quy trình làm việc

* **Bước 3.1:** Hoàn thiện Sidebar Điều hướng Động trong Flask template.
* **Bước 3.2:** Tinh chỉnh CSS cho trang tài liệu (`pygments_style.css` và CSS tùy chỉnh).
* **Bước 3.3 (Tùy chọn nâng cao):** Cân nhắc thêm chức năng tìm kiếm cho trang tài liệu.
* **Bước 3.4:** Thiết lập Quy trình Cập nhật và Sử dụng:
    * Developer duy trì các file Markdown trên GitHub, commit cùng với code.
    * Khi làm việc với AI, upload thư mục `docs/` hoặc các file Markdown liên quan.

## 5. Các Vấn đề và Thảo luận Chính Trước Đó (Tóm tắt)

* **Admin Mapping Viewer (`/admin/mapping/<app_name>`):**
    * Ban đầu gặp lỗi không hiển thị node, lỗi JavaScript liên quan đến `graphContainerElement`, ID của modal sửa transition không khớp, và URL API `SCREEN_ELEMENTS` thiếu placeholder.
    * Đã thực hiện nhiều lần sửa đổi file JavaScript (`cytoscape_manager.js`, `details_panel_manager.js`, `config_mapping.js`, `modal_edit_transition.js`, `main_mapping.js`) và HTML (`admin_mapping_viewer.html`) để giải quyết các vấn đề này.
    * Thảo luận về việc làm cho vùng hiển thị ảnh chụp màn hình và panel chi tiết lớn hơn để vẽ overlay chính xác hơn (chủ yếu là thay đổi CSS).
* **Chuyển đổi sang Hệ thống Tài liệu Markdown:**
    * Nhu cầu về một cách hiệu quả để AI nắm bắt thông tin dự án.
    * Đề xuất sử dụng Markdown trên GitHub.
    * Lên kế hoạch chi tiết cho việc xây dựng hệ thống tài liệu mới này (như mô tả ở trên).

## 6. Thông tin Cần Thiết cho AI trong Phiên làm việc Mới

Khi bắt đầu một phiên làm việc mới, để AI (Gemini) có thể hỗ trợ tốt nhất, vui lòng cung cấp:

1.  **Toàn bộ thư mục `docs/`** (sau khi đã được xây dựng theo kế hoạch trên).
2.  Các file code Python chính của dự án (trong thư mục `app/`).
3.  Các file template HTML (`templates/`) và file JavaScript/CSS (`static/`) liên quan đến vấn đề đang thảo luận.
4.  File schema CSDL (`automation_schema.sql`) nếu có thay đổi hoặc cần tham chiếu.
5.  Mô tả rõ ràng vấn đề cần giải quyết hoặc chức năng cần phát triển.

File README này sẽ được cập nhật khi có những thay đổi lớn trong kế hoạch hoặc cấu trúc tài liệu.
