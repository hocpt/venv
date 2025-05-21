# Tính năng: Trình xem Tài liệu Dự án (/admin/documentation/)

## 1. Mục tiêu

Trang "Trình xem Tài liệu Dự án" (`/admin/documentation/`) được xây dựng để cung cấp một giao diện tập trung, thân thiện cho việc đọc và điều hướng các tài liệu kỹ thuật của dự án HPT11. Các tài liệu này được viết dưới dạng Markdown và lưu trữ trong thư mục `docs/` của mã nguồn.

Mục tiêu chính của tính năng này bao gồm:

* **Cải thiện khả năng nắm bắt thông tin dự án cho AI (Gemini):** Giúp AI hiểu rõ hơn về luồng code, cấu trúc CSDL, các chức năng chính, và API của dự án, giảm thiểu thời gian giải thích lặp lại trong các phiên làm việc mới.
* **Tạo nguồn tài liệu tham khảo tập trung và dễ cập nhật:** Cho phép các nhà phát triển và thành viên trong nhóm dễ dàng truy cập, đọc hiểu và duy trì tài liệu dự án.
* **Hiển thị tài liệu trên trình duyệt một cách thân thiện:** Tích hợp vào giao diện admin của Flask để hiển thị nội dung Markdown dưới dạng HTML, thay thế chức năng của trang `/admin/api-docs` cũ (vốn dựa trên CSDL).
* **Quản lý phiên bản tài liệu cùng với code:** Do tài liệu được lưu trữ trên GitHub (trong thư mục `docs/`), việc theo dõi thay đổi và đồng bộ với các phiên bản code trở nên dễ dàng.

## 2. Kiến trúc và Thành phần Kỹ thuật

### 2.1. Backend (Flask - `app/admin_routes.py`)

* **Route:**
    * `@admin_bp.route('/documentation/', defaults={'filepath': 'README.md'})`
    * `@admin_bp.route('/documentation/<path:filepath>')`
    Hàm xử lý chính là `project_documentation_viewer(filepath)`.
* **Logic xử lý `project_documentation_viewer`:**
    1.  **Xác định đường dẫn gốc `docs_base_dir`:** Trỏ đến thư mục `docs/` nằm ngang cấp với thư mục `app/` trong thư mục gốc của dự án (ví dụ: `venv/docs/`).
    2.  **Chuẩn hóa và kiểm tra an toàn `filepath`:** `filepath` nhận được từ URL được chuẩn hóa (ví dụ: xử lý dấu `\`, `/`) và kiểm tra để ngăn chặn các lỗi path traversal. Nếu đường dẫn không hợp lệ hoặc nằm ngoài `docs_base_dir`, lỗi 404 sẽ được trả về bằng `abort(404)` của Flask.
    3.  **Tạo cấu trúc Sidebar:** Gọi hàm `get_docs_sidebar_structure(real_docs_base_dir)` để quét đệ quy thư mục `docs/` và tạo ra một cấu trúc dữ liệu (list các dictionary) mô tả các tệp `.md` và thư mục con. Hàm này bỏ qua các thư mục/tệp ẩn, có tiền tố `_`, và thư mục `images`. Nó cũng xử lý việc tạo tên hiển thị (loại bỏ số thứ tự, chuyển `_` thành dấu cách, viết hoa) và thêm cờ `is_readme`, `has_readme` để hỗ trợ logic hiển thị trong template.
    4.  **Xử lý `filepath`:**
        * **Nếu là tệp `.md` hợp lệ:**
            * Đọc nội dung tệp Markdown.
            * Sử dụng thư viện `markdown` của Python để chuyển đổi nội dung Markdown sang HTML. Các extension được sử dụng bao gồm: `fenced_code`, `tables`, `toc` (Table of Contents), `codehilite` (để tô sáng cú pháp với Pygments), `nl2br`, `extra`, `sane_lists`, `footnotes`, `attr_list`, `md_in_html`.
            * Cấu hình cho `codehilite` (sử dụng class CSS) và `toc` (permalink, slugify) cũng được áp dụng.
            * Tạo tiêu đề trang (`page_title`) từ tên tệp.
        * **Nếu là thư mục:**
            * Kiểm tra sự tồn tại của tệp `README.md` bên trong thư mục đó.
            * Nếu có `README.md`, thực hiện redirect đến URL của tệp `README.md` đó.
            * Nếu không có, hiển thị thông báo hướng dẫn và giữ nguyên sidebar.
        * **Nếu đường dẫn không hợp lệ:** Trả về lỗi 404.
    5.  **Render Template:** Gọi `render_template` để hiển thị `admin_documentation_viewer.html`, truyền vào `title`, `sections` (hoặc `content_html` nếu bạn giữ nguyên cách hiển thị toàn trang), `sidebar_structure`, `current_filepath`, và `error_message` (nếu có).

### 2.2. Frontend (`templates/admin_documentation_viewer.html`)

* **Kế thừa:** Từ `admin_base.html`.
* **CSS:**
    * Nạp `pygments_style.css` (để tô sáng mã).
    * Nạp `admin_documentation_styles.css` (tệp CSS tùy chỉnh cho layout và kiểu dáng của trang tài liệu).
    * Các style trong `admin_documentation_styles.css` (hoặc trước đó là inline style) định nghĩa:
        * Layout 2 cột sử dụng Flexbox: `.doc-layout-container`, `.doc-sidebar`, `.doc-content`.
        * Kiểu dáng cho sidebar: chiều rộng cố định, `position: sticky`, thanh cuộn, kiểu chữ, màu sắc cho link thường và active.
        * Kiểu dáng cho khu vực nội dung: typography (headings, paragraphs, lists), tables, code blocks, images, blockquotes, Table of Contents (TOC).
        * Responsive design cho màn hình nhỏ (sidebar và content chuyển thành 1 cột, TOC không float).
* **Cấu trúc HTML:**
    * Khối `content` được chia thành `.doc-layout-container`.
    * Bên trong là `<nav class="doc-sidebar">` và `<main class="doc-content">`.
* **Sidebar Điều hướng:**
    * Sử dụng một macro Jinja2 tên là `render_sidebar_items` để đệ quy hiển thị cấu trúc `sidebar_structure` (được truyền từ Python).
    * Mỗi mục là một thư mục (hiển thị tên) hoặc một tệp `.md` (hiển thị dưới dạng liên kết `<a>`).
    * Liên kết được tạo bằng `url_for('admin.project_documentation_viewer', filepath=item.path)`.
    * Mục đang được xem (`current_filepath == item.path`) sẽ có class `active`.
    * Logic hiển thị thư mục có `README.md` và file `README.md` được xử lý để tránh trùng lặp và tạo link hợp lý.
* **Hiển thị Nội dung Markdown:**
    * Nội dung HTML đã được chuyển đổi từ Markdown (`content_html` hoặc `sections[0].summary_html` nếu hiển thị toàn trang) được render bằng `| safe`.
    * Hiển thị thông báo lỗi nếu có (`error_message`).
* **JavaScript:**
    * Nút "Lên đầu trang" (`scrollTopBtn`).
    * Smooth scroll cho các liên kết hash (ví dụ: từ TOC).
    * Logic cuộn sidebar để mục active luôn trong tầm nhìn.

## 3. Quy trình Tạo và Xem Tài liệu

1.  **Tạo/Cập nhật Tài liệu:**
    * Nhà phát triển tạo hoặc chỉnh sửa các tệp `.md` trong thư mục `docs/` theo cấu trúc đã định.
    * Commit và push các thay đổi này lên GitHub cùng với các thay đổi code khác.
2.  **Xem Tài liệu:**
    * Người dùng (Admin, Developer, AI) truy cập route `/admin/documentation/` trên ứng dụng web.
    * Trang sẽ mặc định hiển thị nội dung của `docs/README.md`.
    * Người dùng có thể nhấp vào các mục trong sidebar để điều hướng và xem nội dung của các tệp tài liệu khác.

## 4. Các Vấn đề và Giải pháp đã Thực hiện (trong quá trình xây dựng)

* **Lỗi đường dẫn `docs_base_dir`:** Ban đầu `docs_base_dir` được tính toán sai, dẫn đến việc tìm kiếm thư mục `docs` bên trong `app/`. Đã sửa bằng cách sử dụng `os.path.dirname(current_app.root_path)` để lấy thư mục gốc dự án một cách chính xác hơn.
* **Lỗi `filepath` nhận giá trị là chuỗi Jinja2:** Do thẻ `{% raw %}` đặt sai ở đầu tệp `admin_documentation_viewer.html`, khiến Jinja2 không xử lý `{{ url_for(...) }}` trong thẻ `<link>` CSS. Đã sửa bằng cách xóa thẻ `{% raw %}` đó.
* **Lỗi `No filter named 'basename'`:** Do sử dụng filter `basename` không tồn tại trong Jinja2 để xử lý logic hiển thị `README.md` trong sidebar. Đã sửa bằng cách chuyển logic này về phía Python (trong hàm `get_docs_sidebar_structure`) bằng cách thêm các cờ `is_readme` và `has_readme` cho các item.
* **Lỗi Layout 1 cột:** Do xung đột CSS hoặc cách CSS được nạp. Giải pháp tạm thời là đặt link đến `admin_documentation_styles.css` trong `admin_base.html`. Cách tiếp cận tốt hơn là đảm bảo độ ưu tiên CSS hoặc tách file CSS và nạp đúng thứ tự. (Hiện tại người dùng xác nhận đặt trong `admin_base.html` đã hoạt động).
* **Hiển thị JSON không định dạng:** Do thiếu hoặc bị ghi đè thuộc tính `white-space: pre` hoặc `white-space: pre-wrap` cho thẻ `<pre>` chứa JSON. Cần kiểm tra và bổ sung CSS nếu cần.

## 5. Hướng Phát triển Tương lai (Tùy chọn)

* **Chức năng Tìm kiếm:** Tích hợp tìm kiếm nội dung trong các tệp tài liệu.
* **Chế độ xem Tóm tắt (Summary View):** Cho phép hiển thị tóm tắt các mục lớn (ví dụ: các endpoint API) và bung rộng để xem chi tiết, thay vì hiển thị toàn bộ nội dung file một lúc.
* **Cache Sidebar Structure:** Nếu số lượng file lớn, việc quét thư mục `docs/` mỗi lần request có thể ảnh hưởng hiệu suất. Cân nhắc cache lại `sidebar_structure`.

---