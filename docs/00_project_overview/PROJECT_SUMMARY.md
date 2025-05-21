# Tổng quan Dự án HPT11

## 1. Mục tiêu Dự án

Dự án HPT11 (tên mã nội bộ) được xây dựng nhằm mục đích [***Người dùng cần bổ sung mục tiêu chính của dự án***]. Hệ thống tập trung vào việc [***Người dùng cần bổ sung mô tả ngắn gọn về giải pháp/sản phẩm***].

Các mục tiêu phụ bao gồm:

* Cải thiện khả năng nắm bắt thông tin dự án cho AI (Gemini) để giảm thời gian giải thích lặp lại trong các phiên làm việc mới.
* Tạo nguồn tài liệu tham khảo tập trung, dễ truy cập và cập nhật cho các thành viên trong nhóm.
* Quản lý phiên bản tài liệu đồng bộ với mã nguồn trên GitHub.

## 2. Chức năng Chính

Hệ thống bao gồm các nhóm chức năng chính sau:

* **Quản lý Tài khoản và Thiết bị:** Cho phép quản lý thông tin các tài khoản người dùng và các thiết bị liên kết.
* **Hệ thống Trả lời Tự động:**
    * Xử lý yêu cầu từ client (ví dụ: điện thoại) và tạo phản hồi dựa trên luật hoặc AI.
    * Quản lý luật đơn giản (Simple Rules) và các mẫu trả lời (Templates & Variations).
    * Tích hợp AI (ví dụ: Gemini) để phát hiện ý định người dùng và tạo phản hồi thông minh.
    * Hỗ trợ chiến lược hội thoại (Language Strategies) và chiến lược điều khiển (Control Strategies, MainLoop Strategies) để quản lý luồng tương tác.
* **Quản lý Tác vụ Nền:** Lên lịch và thực thi các tác vụ nền như phân tích và đề xuất AI, duyệt đề xuất tự động, chạy mô phỏng hội thoại.
* **Mapping Ứng dụng (App Mapping):**
    * Trực quan hóa cấu trúc màn hình và luồng chuyển tiếp của các ứng dụng di động.
    * Quản lý các Screen Node và Transition trong cơ sở dữ liệu đồ thị Neo4j.
    * Định nghĩa các Phần tử Nhận diện Chính (PIE - Primary Identifying Elements) cho các màn hình.
* **Tích hợp AI Nâng cao:**
    * AI Personas để tùy chỉnh hành vi của AI.
    * AI Playground để thử nghiệm tương tác trực tiếp với AI.
    * Mô phỏng hội thoại AI (AI Conversation Simulations) để kiểm thử và đánh giá các kịch bản.
* **Giao diện Admin:** Cung cấp các công cụ để quản lý tất cả các khía cạnh trên, bao gồm cả hệ thống tài liệu này.

## 3. Công nghệ Sử dụng

* **Backend:** Python, Flask
* **Cơ sở dữ liệu:**
    * PostgreSQL (cho dữ liệu có cấu trúc như rules, templates, accounts, logs, PIE definitions, etc.)
    * Neo4j (cho dữ liệu đồ thị như app mapping, screen nodes, transitions)
* **AI:** Google Gemini (và các mô hình khác nếu có)
* **Frontend (Admin):** HTML, CSS, JavaScript (có thể sử dụng Bootstrap và các thư viện JS khác như Cytoscape.js cho mapping)
* **Quản lý Tác vụ Nền:** APScheduler
* **Hiển thị Tài liệu:** Thư viện Markdown, Pygments (cho syntax highlighting)