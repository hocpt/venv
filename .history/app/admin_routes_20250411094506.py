# app/admin_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash,current_app 
from datetime import datetime
import psycopg2
import math
import json
from . import ai_service
import importlib # Để kiểm tra function path (tùy chọn)
from apscheduler.jobstores.base import JobLookupError
from . import scheduler
# Import module database đúng với cấu trúc dự án
try:
    from . import database as db
except ImportError:
    import database as db  # Khi chạy file này riêng
try:
    from .. import scheduler # Giả sử scheduler được tạo trong __init__.py của package cha (app)
    # Hoặc nếu scheduler nằm trong create_app() thì cần cách khác để truy cập,
    # ví dụ: current_app.scheduler nếu bạn gắn nó vào app
    # Tạm thời giả định cách import trên hoạt động
except ImportError:
     print("WARNING: Không thể import scheduler từ app. Các thao tác live với scheduler sẽ thất bại.")
     scheduler = None # Đặt là None để tránh lỗi, nhưng chức năng sẽ không hoàn chỉnh

# ... (import db, ...) ...

# --- Định nghĩa các loại trigger hợp lệ ---
TRIGGER_TYPES = ['interval', 'cron', 'date']
admin_bp = Blueprint(
    'admin',
    __name__,
    # static_folder='../static', # Xem xét bỏ dòng này nếu static nằm trong app/static
    template_folder='../templates',
    url_prefix='/admin'
)
VALID_INTENTS_FOR_TRANSITION = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'any' # Thêm 'any'
]
PER_PAGE = 30 # Đặt số lượng item mỗi trang ở đây

# --- Danh sách status có thể lọc (Tùy chọn) ---
# Lấy từ các status bạn dùng trong routes.py và ai_service.py
POSSIBLE_HISTORY_STATUS = [
    'received', 'success_strategy_template', 'success_ai', 'success_fallback_template',
    'error_no_json_data', 'error_missing_data', 'error_no_variation',
    'error_ai_no_key_or_config_failed', 'error_ai_blocked', 'error_ai_empty_response',
    'error_ai_no_text_content', 'error_ai_bad_response_structure',
    'error_ai_unhelpful_no_fallback', 'error_ai_call', 'error_server_unexpected'
    # Thêm các status khác nếu có
]
PROMPT_TASK_TYPES = ['generate_reply', 'suggest_rule', 'detect_intent', 'other'] # Có thể mở rộng sau
# === Dashboard ===
@admin_bp.route('/')
def index():
    stats_data = None # Khởi tạo là None
    try:
        stats_data = db.get_dashboard_stats()
    except Exception as e:
        print(f"Lỗi khi lấy dashboard stats trong route: {e}")
        flash("Không thể tải dữ liệu thống kê cho dashboard.", "error")

    # Nếu stats_data là None (do lỗi DB), truyền vào dict rỗng để template không bị lỗi
    return render_template('admin_index_content.html',
                           title="Admin Dashboard",
                           stats=stats_data if stats_data is not None else {})


# === Quản lý Luật (Đã có từ trước - Bổ sung endpoint cho edit) ===
@admin_bp.route('/rules')
def view_rules():
    try:
        # Giả sử db.get_all_rules() tồn tại và trả về list các dict
        rules = db.get_all_rules()
        if rules is None: # Xử lý trường hợp hàm DB trả về None do lỗi
             flash("Lỗi khi tải danh sách luật từ CSDL.", "error")
             rules = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi load rules: {e}")
        flash("Đã xảy ra lỗi không mong muốn khi tải danh sách luật.", "error")
        rules = [] # Trả về list rỗng để template không bị lỗi
    return render_template('admin_rules.html', title="Quản lý Luật", rules=rules)


# Sửa lỗi thiếu endpoint='add_rule_form' trong route GET
@admin_bp.route('/rules/add', methods=['GET', 'POST'])
def add_rule(): # Đổi tên hàm thành add_rule thay vì add_rule_form cho nhất quán
    if request.method == 'POST':
        try:
            # --- Lấy dữ liệu từ form ---
            keywords = request.form.get('keywords')
            category = request.form.get('category') # Có thể None nếu không nhập
            template_ref = request.form.get('template_ref')
            priority_str = request.form.get('priority', '0') # Lấy dạng string, mặc định '0'
            notes = request.form.get('notes') # Có thể None

            # --- Validate dữ liệu ---
            if not keywords or not template_ref:
                 flash("Keywords và Template Ref là bắt buộc.", "warning")
                 # Trả về lại form với dữ liệu cũ (nếu cần) hoặc chỉ báo lỗi
                 # Cần lấy lại danh sách template cho form GET
                 templates = db.get_all_template_refs() or []
                 return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form), 400 # Bad request

            try:
                 priority = int(priority_str) # Chuyển đổi priority
            except ValueError:
                 flash("Priority phải là một số nguyên.", "warning")
                 templates = db.get_all_template_refs() or []
                 return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form), 400

            # --- Gọi hàm DB ---
            # Giả sử hàm add_new_rule trả về True/False
            success = db.add_new_rule(
                keywords=keywords,
                category=category,
                template_ref=template_ref,
                priority=priority,
                notes=notes
            )

            # --- Phản hồi ---
            if success:
                flash('Thêm luật thành công!', 'success')
                return redirect(url_for('admin.view_rules'))
            else:
                flash('Thêm luật thất bại! (Lỗi CSDL hoặc dữ liệu không hợp lệ)', 'error')
                # Ở lại trang add, cần lấy lại template list
                templates = db.get_all_template_refs() or []
                return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm luật: {e}")
            flash(f"Đã xảy ra lỗi không mong muốn khi thêm luật: {e}", "error")
            # Ở lại trang add, cần lấy lại template list
            templates = db.get_all_template_refs() or []
            return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form)

    # GET request
    try:
        # Giả sử hàm này lấy list các dict [{'template_ref': 'ref1'}, ...]
        templates = db.get_all_template_refs()
        if templates is None:
             flash("Không thể tải danh sách template từ CSDL.", "error")
             templates = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng load templates cho add rule: {e}")
        flash("Lỗi không mong muốn khi tải danh sách template.", "error")
        templates = []

    # Truyền templates vào template admin_add_rule.html
    return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates)


@admin_bp.route('/rules/<int:rule_id>/edit', methods=['GET', 'POST'])
def edit_rule(rule_id):
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            keywords = request.form.get('keywords')
            category = request.form.get('category')
            template_ref = request.form.get('template_ref')
            priority_str = request.form.get('priority', '0')
            notes = request.form.get('notes')

            # Validate
            if not keywords: # Chỉ cần keywords là đủ ở đây, template có thể để trống
                 flash("Keywords là bắt buộc.", "warning")
                 # Cần lấy lại rule và templates để render lại form
                 rule = db.get_rule_by_id(rule_id)
                 templates = db.get_all_template_refs() or []
                 if not rule: return redirect(url_for('admin.view_rules')) # Không tìm thấy rule để sửa
                 return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates), 400

            try:
                 priority = int(priority_str)
            except ValueError:
                 flash("Priority phải là một số nguyên.", "warning")
                 rule = db.get_rule_by_id(rule_id)
                 templates = db.get_all_template_refs() or []
                 if not rule: return redirect(url_for('admin.view_rules'))
                 return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates), 400

            # Gọi hàm DB để cập nhật (giả sử có hàm update_rule)
            success = db.update_rule(
                rule_id=rule_id,
                keywords=keywords,
                category=category,
                template_ref=template_ref if template_ref else None, # Cho phép bỏ trống template
                priority=priority,
                notes=notes
            )

            if success:
                flash('Cập nhật luật thành công!', 'success')
                return redirect(url_for('admin.view_rules'))
            else:
                flash('Cập nhật luật thất bại!', 'error')
                # Ở lại trang edit, cần lấy lại rule và templates
                rule = db.get_rule_by_id(rule_id) # Lấy lại dữ liệu mới nhất (hoặc giữ nguyên form)
                templates = db.get_all_template_refs() or []
                if not rule: return redirect(url_for('admin.view_rules'))
                return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật luật: {e}")
            flash(f"Đã xảy ra lỗi không mong muốn khi cập nhật luật: {e}", "error")
            # Ở lại trang edit, lấy lại dữ liệu
            rule = db.get_rule_by_id(rule_id)
            templates = db.get_all_template_refs() or []
            if not rule: return redirect(url_for('admin.view_rules'))
            return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)

    # GET request
    try:
        rule = db.get_rule_by_id(rule_id) # Giả sử hàm này lấy dict thông tin rule
        templates = db.get_all_template_refs() # Giả sử hàm này lấy list template ref
        if templates is None: templates = []
        if rule is None:
             flash(f"Không tìm thấy luật có ID {rule_id}.", "error")
             return redirect(url_for('admin.view_rules'))

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa luật: {e}")
        flash("Không thể tải dữ liệu để sửa luật.", "error")
        return redirect(url_for('admin.view_rules'))

    return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)


@admin_bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
def delete_rule(rule_id):
    try:
        # Giả sử có hàm db.delete_rule(rule_id) trả về True/False
        success = db.delete_rule(rule_id)
        if success:
            flash(f"Đã xóa luật #{rule_id}.", 'success')
        else:
            flash(f"Xóa luật #{rule_id} thất bại (có thể do ID không tồn tại hoặc lỗi CSDL).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa luật: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa luật: {e}", "error")
    # Luôn redirect về trang danh sách luật sau khi xử lý
    return redirect(url_for('admin.view_rules'))


# === Đề xuất AI (Đã có từ trước) ===
@admin_bp.route('/suggestions')
def view_suggestions():
    try:
        # Giả sử hàm này trả về list dict suggestion hoặc None nếu lỗi
        suggestions = db.get_pending_suggestions()
        if suggestions is None:
             flash("Không thể tải đề xuất từ CSDL.", "error")
             suggestions = [] # Gán list rỗng để tránh lỗi template
    except Exception as e:
        print(f"Lỗi nghiêm trọng load suggestions: {e}")
        suggestions = []
        flash("Lỗi không mong muốn khi tải đề xuất.", "error")
    return render_template('admin_suggestions.html', title="Đề xuất từ AI", suggestions=suggestions)


@admin_bp.route('/suggestions/<int:suggestion_id>/approve', methods=['POST'])
def approve_suggestion(suggestion_id):
    try:
        suggestion = db.get_suggestion_by_id(suggestion_id)
        if not suggestion or suggestion.get('status') != 'pending':
            flash("Đề xuất không hợp lệ hoặc đã được xử lý.", "warning")
            return redirect(url_for('admin.view_suggestions'))

        # Lấy dữ liệu từ form phê duyệt
        template_ref = request.form.get('template_ref')
        category = request.form.get('category', 'ai_suggested') # Mặc định category
        priority_str = request.form.get('priority', '0')

        # Validate
        if not template_ref:
             flash("Cần cung cấp Template Ref khi phê duyệt.", "warning")
             # Cần render lại trang suggestions hoặc trang chi tiết suggestion nếu có
             return redirect(url_for('admin.view_suggestions')) # Redirect đơn giản

        try:
            priority = int(priority_str)
        except ValueError:
            flash("Priority phải là số nguyên.", "warning")
            return redirect(url_for('admin.view_suggestions'))

        # Bắt đầu transaction hoặc xử lý tuần tự
        # 1. Thêm template mới (nếu chưa có) VÀ variation đầu tiên
        # Giả sử add_new_template trả về template_ref nếu thành công, None nếu lỗi
        added_template_ref = db.add_new_template(
            template_ref=template_ref,
            first_variation_text=suggestion['suggested_template_text'],
            description=f"AI suggested template from suggestion {suggestion_id}",
            category=category # Sử dụng category từ form
        )

        if added_template_ref:
            # 2. Thêm rule mới trỏ đến template vừa tạo
            rule_added = db.add_new_rule(
                keywords=suggestion['suggested_keywords'],
                category=category, # Sử dụng category từ form
                template_ref=added_template_ref, # Dùng ref trả về từ hàm add_new_template
                priority=priority,
                notes=f"Approved from AI suggestion #{suggestion_id}. Original keywords: {suggestion['suggested_keywords']}"
            )

            if rule_added:
                # 3. Cập nhật trạng thái suggestion thành 'approved'
                status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                if status_updated:
                    flash("Đã phê duyệt và thêm luật/template thành công!", "success")
                else:
                    # Vẫn thành công về mặt thêm luật/template nhưng lỗi cập nhật status suggestion
                    flash("Đã thêm luật/template, nhưng không thể cập nhật trạng thái đề xuất.", "warning")
                return redirect(url_for('admin.view_suggestions'))
            else:
                # Lỗi khi thêm rule (sau khi đã thêm template/variation)
                # Cần xử lý rollback hoặc báo lỗi rõ ràng
                flash("Đã thêm template/variation nhưng thêm rule thất bại.", "error")
                # Cân nhắc xóa template/variation vừa thêm nếu logic yêu cầu
        else:
            # Lỗi ngay từ bước thêm template/variation
            flash("Thêm template/variation mới thất bại.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi phê duyệt: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi phê duyệt: {e}", "error")

    # Nếu có lỗi xảy ra, quay lại trang suggestions
    return redirect(url_for('admin.view_suggestions'))


@admin_bp.route('/suggestions/<int:suggestion_id>/reject', methods=['POST'])
def reject_suggestion(suggestion_id):
    try:
        # Giả sử hàm update_suggestion_status trả về True/False
        success = db.update_suggestion_status(suggestion_id, 'rejected')
        if success:
            flash(f"Đã từ chối đề xuất #{suggestion_id}.", 'info')
        else:
            flash("Từ chối đề xuất thất bại (ID không tồn tại hoặc lỗi CSDL).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi từ chối đề xuất: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi từ chối: {e}", "error")
    return redirect(url_for('admin.view_suggestions'))


# =============================================
# === CÁC ROUTE MỚI THÊM VÀO ===
# =============================================

# === Quản lý Tài khoản ===
@admin_bp.route('/accounts')
def view_accounts():
    try:
        # Giả sử db.get_all_accounts() trả về list các dict account hoặc None
        accounts = db.get_all_accounts()
        if accounts is None:
             flash("Lỗi khi tải danh sách tài khoản từ CSDL.", "error")
             accounts = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng load accounts: {e}")
        flash("Lỗi không mong muốn khi tải danh sách tài khoản.", "error")
        accounts = []
    return render_template('admin_accounts.html', title="Quản lý Tài khoản", accounts=accounts)

    """Hiển thị form sửa và xử lý cập nhật tài khoản."""
    if request.method == 'POST':
        account = None # Khởi tạo
        strategies = [] # Khởi tạo
        valid_platforms = [] # Khởi tạo
        valid_goals = []     # Khởi tạo
        try:
            account = db.get_account_details(account_id)
            strategies = db.get_all_strategies() or []

            if account is None:
                flash(f"Không tìm thấy tài khoản có ID {account_id}.", "error")
                return redirect(url_for('admin.view_accounts'))
            valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
            valid_goals = current_app.config.get('VALID_GOALS', [])
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa account {account_id}: {e}")
            flash("Không thể tải dữ liệu để sửa tài khoản.", "error")
            return redirect(url_for('admin.view_accounts'))

        # <<< Truyền thêm valid_platforms và valid_goals >>>
        return render_template('admin_edit_account.html',
                            title=f"Sửa Tài khoản {account_id}",
                            account=account,
                            strategies=strategies,
                            valid_platforms=VALID_PLATFORMS, # Truyền list platforms
                            valid_goals=VALID_GOALS)  
        try:
            # Lấy dữ liệu từ form
            platform = request.form.get('platform')
            username = request.form.get('username')
            status = request.form.get('status')
            notes = request.form.get('notes')
            goal = request.form.get('goal')
            strategy_id = request.form.get('default_strategy_id')

            # Validate (tương tự như khi add, nhưng không cần validate account_id)
            if not platform or not username:
                 flash("Platform và Username là bắt buộc.", "warning")
                 # Cần lấy lại dữ liệu account và strategies để hiển thị lại form
                 account = db.get_account_details(account_id)
                 strategies = db.get_all_strategies() or []
                 if not account: # Nếu không tìm thấy account nữa thì về trang list
                      flash(f"Không tìm thấy tài khoản ID {account_id} để sửa.", "error")
                      return redirect(url_for('admin.view_accounts'))
                 return render_template('admin_edit_account.html', title=f"Sửa Tài khoản {account_id}", account=account, strategies=strategies), 400

            # Gọi hàm update_account từ database.py (đã tạo skeleton trước đó)
            success = db.update_account(
                account_id=account_id,
                platform=platform,
                username=username,
                status=status,
                notes=notes,
                goal=goal,
                default_strategy_id=strategy_id if strategy_id else None
            )

            if success:
                flash('Cập nhật tài khoản thành công!', 'success')
                return redirect(url_for('admin.view_accounts'))
            else:
                flash('Cập nhật tài khoản thất bại (ID không tồn tại hoặc lỗi CSDL).', 'error')
                # Ở lại trang edit, cần lấy lại dữ liệu
                account = db.get_account_details(account_id)
                strategies = db.get_all_strategies() or []
                if not account: return redirect(url_for('admin.view_accounts'))
                return render_template('admin_edit_account.html', title=f"Sửa Tài khoản {account_id}", account=account, strategies=strategies)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật account {account_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật tài khoản: {e}", "error")
            # Ở lại trang edit, lấy lại dữ liệu
            account = db.get_account_details(account_id)
            strategies = db.get_all_strategies() or []
            if not account: return redirect(url_for('admin.view_accounts'))
            return render_template('admin_edit_account.html', title=f"Sửa Tài khoản {account_id}", account=account, strategies=strategies)

    # GET request: Hiển thị form với dữ liệu hiện tại
    try:
        account = db.get_account_details(account_id) # Hàm này đã có
        strategies = db.get_all_strategies() or [] # Hàm này đã có

        if account is None:
            flash(f"Không tìm thấy tài khoản có ID {account_id}.", "error")
            return redirect(url_for('admin.view_accounts'))

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa account {account_id}: {e}")
        flash("Không thể tải dữ liệu để sửa tài khoản.", "error")
        return redirect(url_for('admin.view_accounts'))

    return render_template('admin_edit_account.html', title=f"Sửa Tài khoản {account_id}", account=account, strategies=strategies)


@admin_bp.route('/accounts/add', methods=['GET', 'POST'])
def add_account():
    # --- Xử lý POST Request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            account_id = request.form.get('account_id')
            platform = request.form.get('platform')
            username = request.form.get('username')
            notes = request.form.get('notes')
            goal = request.form.get('goal')
            strategy_id = request.form.get('default_strategy_id')
            status = request.form.get('status', 'active')

            # Validate dữ liệu
            if not account_id or not platform or not username:
                 flash("Account ID, Platform và Username là bắt buộc.", "warning")
                 # --- Nếu validation lỗi, cần lấy lại dữ liệu để hiển thị form ---
                 strategies = db.get_all_strategies() or []
                 valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                 valid_goals = current_app.config.get('VALID_GOALS', [])
                 return render_template('admin_add_account.html',
                                        title="Thêm Tài khoản Mới",
                                        strategies=strategies,
                                        valid_platforms=valid_platforms,
                                        valid_goals=valid_goals,
                                        current_data=request.form), 400 # Trả về form với dữ liệu đã nhập

            # Gọi hàm DB để thêm mới
            success = db.add_new_account(account_id, platform, username, status, notes, goal, strategy_id if strategy_id else None)

            # Xử lý kết quả
            if success:
                flash('Thêm tài khoản thành công!', 'success')
                return redirect(url_for('admin.view_accounts')) # Redirect nếu thành công
            else:
                flash('Thêm tài khoản thất bại! (ID có thể đã tồn tại?)', 'error')
                # --- Nếu thêm thất bại, lấy lại dữ liệu để hiển thị form ---
                strategies = db.get_all_strategies() or []
                valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                valid_goals = current_app.config.get('VALID_GOALS', [])
                return render_template('admin_add_account.html',
                                       title="Thêm Tài khoản Mới",
                                       strategies=strategies,
                                       valid_platforms=valid_platforms,
                                       valid_goals=valid_goals,
                                       current_data=request.form) # Ở lại form với dữ liệu đã nhập

        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm account: {e}")
             flash(f"Lỗi không mong muốn khi thêm tài khoản: {e}", "error")
             # --- Nếu có lỗi Exception, lấy lại dữ liệu để hiển thị form ---
             strategies = db.get_all_strategies() or []
             valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
             valid_goals = current_app.config.get('VALID_GOALS', [])
             return render_template('admin_add_account.html',
                                    title="Thêm Tài khoản Mới",
                                    strategies=strategies,
                                    valid_platforms=valid_platforms,
                                    valid_goals=valid_goals,
                                    current_data=request.form) # Ở lại form với dữ liệu đã nhập

    # --- Xử lý GET Request ---
    # Chỉ thực hiện khi request.method là 'GET'
    strategies = []
    valid_platforms = []
    valid_goals = []
    try:
        # Lấy danh sách strategies, platforms, goals để hiển thị form
        strategies = db.get_all_strategies()
        if strategies is None:
             flash("Lỗi tải danh sách chiến lược.", "error")
             strategies = []
        valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
        valid_goals = current_app.config.get('VALID_GOALS', [])

    except Exception as e:
        print(f"Lỗi nghiêm trọng load data for add account form: {e}")
        flash("Lỗi không mong muốn khi tải dữ liệu form.", "error")
        # strategies, valid_platforms, valid_goals sẽ là list rỗng đã khởi tạo

    # Render template cho GET request
    return render_template('admin_add_account.html',
                           title="Thêm Tài khoản Mới",
                           strategies=strategies,
                           valid_platforms=valid_platforms,
                           valid_goals=valid_goals)


@admin_bp.route('/accounts/<account_id>/edit', methods=['GET', 'POST'])
def edit_account(account_id):
    # --- Xử lý POST Request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            platform = request.form.get('platform')
            username = request.form.get('username')
            status = request.form.get('status')
            notes = request.form.get('notes')
            goal = request.form.get('goal')
            strategy_id = request.form.get('default_strategy_id')

            # Validate dữ liệu
            if not platform or not username:
                 flash("Platform và Username là bắt buộc.", "warning")
                 # --- Nếu validation lỗi, cần lấy lại dữ liệu để hiển thị form ---
                 account = db.get_account_details(account_id) # Lấy lại account data
                 strategies = db.get_all_strategies() or []
                 valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                 valid_goals = current_app.config.get('VALID_GOALS', [])
                 if not account: # Kiểm tra lại account tồn tại
                      flash(f"Không tìm thấy tài khoản ID {account_id} để sửa.", "error")
                      return redirect(url_for('admin.view_accounts'))
                 # Truyền account vào lại để giữ giá trị cũ trên form
                 return render_template('admin_edit_account.html',
                                        title=f"Sửa Tài khoản {account_id}",
                                        account=account, # Dùng account data cũ
                                        strategies=strategies,
                                        valid_platforms=valid_platforms,
                                        valid_goals=valid_goals), 400 # Trả về form

            # Gọi hàm DB để cập nhật
            success = db.update_account(
                account_id=account_id, platform=platform, username=username, status=status,
                notes=notes, goal=goal, default_strategy_id=strategy_id if strategy_id else None
            )

            # Xử lý kết quả
            if success:
                flash('Cập nhật tài khoản thành công!', 'success')
                return redirect(url_for('admin.view_accounts')) # Redirect nếu thành công
            else:
                flash('Cập nhật tài khoản thất bại (ID không tồn tại hoặc lỗi CSDL).', 'error')
                # --- Nếu update thất bại, lấy lại dữ liệu để hiển thị form ---
                account = db.get_account_details(account_id) # Lấy lại account data
                strategies = db.get_all_strategies() or []
                valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
                valid_goals = current_app.config.get('VALID_GOALS', [])
                if not account: return redirect(url_for('admin.view_accounts'))
                # Truyền account vào lại để giữ giá trị cũ trên form
                return render_template('admin_edit_account.html',
                                       title=f"Sửa Tài khoản {account_id}",
                                       account=account, # Dùng account data cũ
                                       strategies=strategies,
                                       valid_platforms=valid_platforms,
                                       valid_goals=valid_goals)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật account {account_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật tài khoản: {e}", "error")
            # --- Nếu có lỗi Exception, lấy lại dữ liệu để hiển thị form ---
            account = db.get_account_details(account_id) # Lấy lại account data
            strategies = db.get_all_strategies() or []
            valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
            valid_goals = current_app.config.get('VALID_GOALS', [])
            if not account: return redirect(url_for('admin.view_accounts'))
            # Truyền account vào lại để giữ giá trị cũ trên form
            return render_template('admin_edit_account.html',
                                   title=f"Sửa Tài khoản {account_id}",
                                   account=account, # Dùng account data cũ
                                   strategies=strategies,
                                   valid_platforms=valid_platforms,
                                   valid_goals=valid_goals)

    # --- Xử lý GET Request ---
    # Chỉ thực hiện khi request.method là 'GET'
    account = None
    strategies = []
    valid_platforms = []
    valid_goals = []
    try:
        # Lấy dữ liệu account cần sửa và các list để hiển thị form
        account = db.get_account_details(account_id)
        strategies = db.get_all_strategies() or []

        if account is None:
            flash(f"Không tìm thấy tài khoản có ID {account_id}.", "error")
            return redirect(url_for('admin.view_accounts'))

        valid_platforms = current_app.config.get('VALID_PLATFORMS', [])
        valid_goals = current_app.config.get('VALID_GOALS', [])

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa account {account_id}: {e}")
        flash("Không thể tải dữ liệu để sửa tài khoản.", "error")
        return redirect(url_for('admin.view_accounts'))

    # Render template cho GET request
    return render_template('admin_edit_account.html',
                           title=f"Sửa Tài khoản {account_id}",
                           account=account,
                           strategies=strategies,
                           valid_platforms=valid_platforms,
                           valid_goals=valid_goals)

@admin_bp.route('/accounts/<account_id>/delete', methods=['POST'])
def delete_account(account_id):
    """Xử lý xóa tài khoản."""
    try:
        # Gọi hàm delete_account từ database.py (đã tạo skeleton trước đó)
        success = db.delete_account(account_id)
        if success:
            flash(f"Đã xóa tài khoản ID {account_id}.", 'success')
        else:
            flash(f"Xóa tài khoản ID {account_id} thất bại (ID không tồn tại hoặc lỗi CSDL).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa account {account_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa tài khoản: {e}", "error")

    # Luôn redirect về trang danh sách tài khoản sau khi xử lý
    return redirect(url_for('admin.view_accounts'))

# === Quản lý Templates ===
@admin_bp.route('/templates')
def view_templates():
    try:
        # Giả sử hàm này trả về list of dicts [{template_ref, description, category, variation_count}]
        templates_data = db.get_all_template_refs_with_details()
        if templates_data is None:
            flash("Lỗi khi tải danh sách template từ CSDL.", "error")
            templates_data = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng load templates: {e}")
        flash("Lỗi không mong muốn khi tải danh sách template.", "error")
        templates_data = []
    return render_template('admin_templates.html', title="Quản lý Templates", templates=templates_data)

@admin_bp.route('/templates/add', methods=['GET', 'POST'])
def add_template(): 
    if request.method == 'POST':
        try:
            template_ref = request.form.get('template_ref')
            description = request.form.get('description')
            category = request.form.get('category')
            variation_text = request.form.get('variation_text') # Biến thể đầu tiên

            if not template_ref or not variation_text:
                 flash("Template Ref và ít nhất một Variation Text là bắt buộc.", "warning")
                 return render_template('admin_add_template.html', title="Thêm Template Mới", current_data=request.form), 400

            # Giả sử db.add_new_template đã được cập nhật để xử lý cả ref và variation đầu tiên
            added_ref = db.add_new_template(template_ref, variation_text, description, category)
            if added_ref:
                flash(f'Thêm template "{added_ref}" thành công!', 'success')
                # Chuyển đến trang xem chi tiết variations của template vừa thêm
                return redirect(url_for('admin.view_template_variations', template_ref=added_ref))
            else:
                flash('Thêm template thất bại!', 'error')
                return render_template('admin_add_template.html', title="Thêm Template Mới", current_data=request.form)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm template: {e}")
             flash(f"Lỗi không mong muốn khi thêm template: {e}", "error")
             return render_template('admin_add_template.html', title="Thêm Template Mới", current_data=request.form)

    # GET request
    return render_template('admin_add_template.html', title="Thêm Template Mới")

@admin_bp.route('/templates/<template_ref>/variations')
def view_template_variations(template_ref):
    try:
        # Sử dụng hàm db.get_template_variations đã có
        variations = db.get_template_variations(template_ref)
        template_details = db.get_template_ref_details(template_ref) # Cần thêm hàm này để lấy description/category

        if variations is None:
            flash(f"Lỗi khi tải variations cho template '{template_ref}'.", "error")
            # Có thể redirect về trang view_templates hoặc hiển thị trang lỗi riêng
            return redirect(url_for('admin.view_templates'))
        if template_details is None:
             # Không tìm thấy template ref này
             flash(f"Không tìm thấy template ref '{template_ref}'.", "warning")
             return redirect(url_for('admin.view_templates'))

    except Exception as e:
        print(f"Lỗi nghiêm trọng load variations for {template_ref}: {e}")
        flash("Lỗi không mong muốn khi tải variations.", "error")
        return redirect(url_for('admin.view_templates'))

    return render_template('admin_template_variations.html',
                           title=f"Variations cho '{template_ref}'",
                           template_ref=template_ref,
                           template_details=template_details,
                           variations=variations)


@admin_bp.route('/templates/<template_ref>/variations/add', methods=['GET', 'POST'])
def add_template_variation(template_ref):
     # Kiểm tra xem template_ref có tồn tại không
     template_details = db.get_template_ref_details(template_ref)
     if not template_details:
          flash(f"Template ref '{template_ref}' không tồn tại.", "error")
          return redirect(url_for('admin.view_templates'))

     if request.method == 'POST':
          variation_text = request.form.get('variation_text')
          if not variation_text:
               flash("Nội dung variation không được để trống.", "warning")
               # Render lại form GET
               return render_template('admin_add_template_variation.html', title=f"Thêm Variation cho '{template_ref}'", template_ref=template_ref)

          try:
               # Giả sử có hàm add_single_variation(template_ref, variation_text) trả về True/False
               success = db.add_single_variation(template_ref, variation_text)
               if success:
                    flash("Thêm variation thành công!", "success")
                    return redirect(url_for('admin.view_template_variations', template_ref=template_ref))
               else:
                    flash("Thêm variation thất bại (có thể do lỗi CSDL hoặc text trùng lặp?).", "error")
                    # Ở lại trang add
                    return render_template('admin_add_template_variation.html', title=f"Thêm Variation cho '{template_ref}'", template_ref=template_ref, current_text=variation_text)
          except Exception as e:
               print(f"Lỗi nghiêm trọng khi thêm variation: {e}")
               flash(f"Lỗi không mong muốn khi thêm variation: {e}", "error")
               return render_template('admin_add_template_variation.html', title=f"Thêm Variation cho '{template_ref}'", template_ref=template_ref, current_text=variation_text)

     # GET request
     return render_template('admin_add_template_variation.html', title=f"Thêm Variation cho '{template_ref}'", template_ref=template_ref)

@admin_bp.route('/templates/<template_ref>/delete', methods=['POST'])
def delete_template(template_ref):
    """Xử lý xóa Template Ref và các variations liên quan."""
    try:
        # Gọi hàm xóa từ database.py (cần tạo hàm này)
        success = db.delete_template_ref(template_ref)
        if success:
            flash(f"Đã xóa Template Ref '{template_ref}' và các variations của nó.", 'success')
        else:
            # Trường hợp này ít xảy ra nếu không có lỗi FK, có thể do ref không tồn tại
            flash(f"Xóa Template Ref '{template_ref}' thất bại (Ref không tồn tại?).", 'error')

    except psycopg2.errors.ForeignKeyViolation:
         # Bắt lỗi cụ thể khi template đang được tham chiếu bởi bảng khác (rules, transitions)
         flash(f"Không thể xóa Template Ref '{template_ref}' vì nó đang được sử dụng bởi Rules hoặc Transitions.", 'error')
         print(f"INFO: Ngăn chặn xóa template '{template_ref}' do vi phạm khóa ngoại.")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa template {template_ref}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa Template Ref: {e}", "error")

    # Luôn redirect về trang danh sách templates
    return redirect(url_for('admin.view_templates'))

def delete_template_ref(template_ref: str) -> bool:
    """Xóa một template_ref khỏi response_templates.
       Do có ràng buộc ON DELETE CASCADE trong DB, các variations liên quan
       trong template_variations cũng sẽ tự động bị xóa.
       Hàm sẽ thất bại (ném ForeignKeyViolation) nếu template_ref đang được
       tham chiếu bởi simple_rules hoặc stage_transitions (do không có ON DELETE).
    """
    if not template_ref: return False
    conn = get_db_connection()
    if not conn: return False
    cur = None
    success = False
    try:
        cur = conn.cursor()
        print(f"DEBUG (database.py): Xóa template_ref='{template_ref}'...")
        # Chỉ cần xóa từ response_templates, variations sẽ tự xóa theo CASCADE
        sql = "DELETE FROM response_templates WHERE template_ref = %s;"
        cur.execute(sql, (template_ref,))
        conn.commit()
        # Kiểm tra xem có dòng nào thực sự bị xóa không
        success = cur.rowcount > 0
        if not success:
            print(f"WARNING (database.py - delete_template_ref): Không tìm thấy template_ref '{template_ref}' để xóa.")

    except psycopg2.Error as db_err:
         # Không bắt lỗi ForeignKeyViolation ở đây, để route xử lý
         print(f"LỖI (database.py - delete_template_ref): DELETE thất bại: {db_err}")
         if conn: conn.rollback()
         # Ném lại lỗi để route có thể bắt cụ thể lỗi FK
         raise db_err
    except Exception as e:
        print(f"LỖI (database.py - delete_template_ref): Lỗi không xác định: {e}")
        if conn: conn.rollback()
        raise e # Ném lại lỗi để route bắt
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return success # Chỉ trả về True nếu không có Exception và rowcount > 0

@admin_bp.route('/templates/variations/<int:variation_id>/delete', methods=['POST'])
def delete_template_variation(variation_id):
    """Xử lý xóa một variation cụ thể."""
    # Lấy template_ref từ form ẩn để redirect về đúng trang
    template_ref_redirect = request.form.get('template_ref_redirect')

    if not template_ref_redirect:
         # Nếu không có template_ref để redirect, thì về trang template list chung
         flash("Lỗi: Không xác định được template gốc để quay lại.", "error")
         return redirect(url_for('admin.view_templates'))

    try:
        # Gọi hàm xóa variation từ database.py (cần tạo hàm này)
        success = db.delete_single_variation(variation_id)
        if success:
            flash(f"Đã xóa variation ID {variation_id}.", 'success')
        else:
            flash(f"Xóa variation ID {variation_id} thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa variation {variation_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa variation: {e}", "error")

    # Redirect về trang xem variations của template gốc
    return redirect(url_for('admin.view_template_variations', template_ref=template_ref_redirect))


    
@admin_bp.route('/templates/<template_ref>/edit', methods=['GET', 'POST'])
def edit_template_details(template_ref):
    """Sửa description và category của Template Ref."""
    if request.method == 'POST':
        # ... (Phần xử lý POST giữ nguyên) ...
        pass # Giữ nguyên

    # GET request
    template_details = None
    distinct_categories = [] # Khởi tạo list rỗng
    try:
        template_details = db.get_template_ref_details(template_ref)
        if not template_details:
            flash(f"Không tìm thấy template ref '{template_ref}'.", "error")
            return redirect(url_for('admin.view_templates'))

        # <<< LẤY DANH SÁCH CATEGORIES DUY NHẤT >>>
        distinct_categories = db.get_distinct_template_categories() or []

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải data cho edit template details {template_ref}: {e}")
        flash("Lỗi không mong muốn khi tải dữ liệu form.", "error")
        # Nếu lỗi, không thể hiển thị form sửa, quay về trang list
        return redirect(url_for('admin.view_templates'))


    return render_template('admin_edit_template_details.html',
                           title=f"Sửa Chi tiết Template '{template_ref}'",
                           template=template_details,
                           distinct_categories=distinct_categories) # <<< TRUYỀN VÀO TEMPLATE


@admin_bp.route('/templates/variations/<int:variation_id>/edit', methods=['GET', 'POST'])
def edit_template_variation(variation_id):
    """Sửa nội dung text của một variation."""
    # Lấy thông tin variation hiện tại cho cả GET và POST (nếu có lỗi)
    variation = db.get_variation_details(variation_id)
    if not variation:
        flash(f"Không tìm thấy variation ID {variation_id}.", "error")
        # Không biết redirect về template ref nào, quay về trang template list chung
        return redirect(url_for('admin.view_templates'))
    # Lấy template_ref để dùng cho redirect và link Hủy
    template_ref_redirect = variation.get('template_ref')

    if request.method == 'POST':
        new_variation_text = request.form.get('variation_text')

        if not new_variation_text: # Kiểm tra text không rỗng
             flash("Nội dung variation không được để trống.", "warning")
             # Render lại form với lỗi và dữ liệu cũ (variation)
             return render_template('admin_edit_template_variation.html',
                                    title=f"Sửa Variation {variation_id}",
                                    variation=variation), 400
        try:
            success = db.update_variation(variation_id, new_variation_text)
            if success:
                flash(f"Cập nhật variation ID {variation_id} thành công!", 'success')
                # Redirect về trang xem variations của template gốc
                return redirect(url_for('admin.view_template_variations', template_ref=template_ref_redirect))
            else:
                 # Ít xảy ra nếu variation tồn tại
                flash(f"Cập nhật variation ID {variation_id} thất bại.", 'error')
                # Render lại form với dữ liệu cũ
                return render_template('admin_edit_template_variation.html',
                                        title=f"Sửa Variation {variation_id}",
                                        variation=variation)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi cập nhật variation {variation_id}: {e}")
             flash(f"Lỗi không mong muốn khi cập nhật variation: {e}", "error")
             # Render lại form với dữ liệu cũ
             return render_template('admin_edit_template_variation.html',
                                     title=f"Sửa Variation {variation_id}",
                                     variation=variation)

    # GET request: Hiển thị form với dữ liệu hiện tại
    return render_template('admin_edit_template_variation.html',
                           title=f"Sửa Variation {variation_id}",
                           variation=variation) # Truyền variation details vào template

# === Quản lý Chiến lược ===
@admin_bp.route('/strategies')
def view_strategies():
    try:
        # Giả sử hàm này trả về list of dicts [{strategy_id, name, description, initial_stage_id}]
        strategies = db.get_all_strategies()
        if strategies is None:
            flash("Lỗi khi tải danh sách chiến lược từ CSDL.", "error")
            strategies = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng load strategies: {e}")
        flash("Lỗi không mong muốn khi tải danh sách chiến lược.", "error")
        strategies = []
    return render_template('admin_strategies.html', title="Quản lý Chiến lược", strategies=strategies)


    if request.method == 'POST':
        try:
            strategy_id = request.form.get('strategy_id')
            name = request.form.get('name')
            description = request.form.get('description')
            initial_stage_id = request.form.get('initial_stage_id') # Cần có danh sách stage để chọn? Hoặc nhập tay?

            if not strategy_id or not name or not initial_stage_id:
                 flash("Strategy ID, Name, và Initial Stage ID là bắt buộc.", "warning")
                 # Cần lấy lại danh sách stages nếu có dropdown
                 stages = db.get_all_stages() or [] # Giả sử có hàm này
                 return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages, current_data=request.form), 400

            # Giả sử db.add_new_strategy trả về True/False
            success = db.add_new_strategy(strategy_id, name, description, initial_stage_id)
            if success:
                flash('Thêm chiến lược thành công!', 'success')
                return redirect(url_for('admin.view_strategies'))
            else:
                flash('Thêm chiến lược thất bại (ID có thể đã tồn tại?).', 'error')
                stages = db.get_all_stages() or []
                return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages, current_data=request.form)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm strategy: {e}")
             flash(f"Lỗi không mong muốn khi thêm chiến lược: {e}", "error")
             stages = db.get_all_stages() or []
             return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages, current_data=request.form)

    # GET request
    try:
         # Lấy danh sách stages để chọn initial_stage_id (nếu cần)
         stages = db.get_all_stages() # Giả sử hàm này trả về list of dicts [{'stage_id': 's1', 'name': 'Stage 1'}, ...]
         if stages is None:
              flash("Lỗi tải danh sách stages.", "error")
              stages = []
    except Exception as e:
         print(f"Lỗi nghiêm trọng load stages for add strategy: {e}")
         flash("Lỗi không mong muốn khi tải danh sách stages.", "error")
         stages = []
    return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages)

@admin_bp.route('/strategies/<strategy_id>/edit', methods=['GET', 'POST'])
def edit_strategy(strategy_id):
    """Hiển thị form sửa và xử lý cập nhật chiến lược."""
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            name = request.form.get('name')
            description = request.form.get('description')
            initial_stage_id = request.form.get('initial_stage_id')

            # Validate dữ liệu
            if not name or not initial_stage_id:
                 flash("Name và Initial Stage ID là bắt buộc.", "warning")
                 # Cần lấy lại dữ liệu strategy và stages để hiển thị lại form
                 strategy = db.get_strategy_details(strategy_id)
                 stages = db.get_all_stages() or [] # Lấy tất cả stages cho dropdown
                 if not strategy:
                      flash(f"Không tìm thấy chiến lược ID {strategy_id} để sửa.", "error")
                      return redirect(url_for('admin.view_strategies'))
                 return render_template('admin_edit_strategy.html',
                                        title=f"Sửa Chiến lược {strategy_id}",
                                        strategy=strategy,
                                        stages=stages), 400

            # Gọi hàm DB để cập nhật (đã có skeleton/implementation)
            success = db.update_strategy(
                strategy_id=strategy_id,
                name=name,
                description=description,
                initial_stage_id=initial_stage_id
            )

            if success:
                flash('Cập nhật chiến lược thành công!', 'success')
                return redirect(url_for('admin.view_strategies'))
            else:
                flash('Cập nhật chiến lược thất bại (ID không tồn tại, Name trùng hoặc lỗi CSDL).', 'error')
                # Ở lại trang edit, lấy lại dữ liệu
                strategy = db.get_strategy_details(strategy_id)
                stages = db.get_all_stages() or []
                if not strategy: return redirect(url_for('admin.view_strategies'))
                return render_template('admin_edit_strategy.html',
                                       title=f"Sửa Chiến lược {strategy_id}",
                                       strategy=strategy,
                                       stages=stages)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật strategy {strategy_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật chiến lược: {e}", "error")
            # Ở lại trang edit, lấy lại dữ liệu
            strategy = db.get_strategy_details(strategy_id)
            stages = db.get_all_stages() or []
            if not strategy: return redirect(url_for('admin.view_strategies'))
            return render_template('admin_edit_strategy.html',
                                   title=f"Sửa Chiến lược {strategy_id}",
                                   strategy=strategy,
                                   stages=stages)

    # GET request: Hiển thị form với dữ liệu hiện tại
    try:
        strategy = db.get_strategy_details(strategy_id) # Hàm này đã có
        stages = db.get_all_stages() or [] # Lấy tất cả stages để chọn initial_stage

        if strategy is None:
            flash(f"Không tìm thấy chiến lược có ID {strategy_id}.", "error")
            return redirect(url_for('admin.view_strategies'))

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa strategy {strategy_id}: {e}")
        flash("Không thể tải dữ liệu để sửa chiến lược.", "error")
        return redirect(url_for('admin.view_strategies'))

    return render_template('admin_edit_strategy.html',
                           title=f"Sửa Chiến lược {strategy_id}",
                           strategy=strategy,
                           stages=stages) # Truyền danh sách stages cho dropdown


@admin_bp.route('/strategies/<strategy_id>/delete', methods=['POST'])
def delete_strategy(strategy_id):
    """Xử lý xóa chiến lược."""
    try:
        # Gọi hàm delete_strategy từ database.py (cần tạo hàm này)
        success = db.delete_strategy(strategy_id)
        if success:
            flash(f"Đã xóa chiến lược ID {strategy_id}.", 'success')
        else:
            flash(f"Xóa chiến lược ID {strategy_id} thất bại (ID không tồn tại hoặc lỗi CSDL - kiểm tra khóa ngoại).", 'error')
    except Exception as e:
        # Bắt lỗi cụ thể hơn nếu cần, ví dụ lỗi khóa ngoại
        print(f"Lỗi nghiêm trọng khi xóa strategy {strategy_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa chiến lược: {e}", "error")

    return redirect(url_for('admin.view_strategies'))


@admin_bp.route('/strategies/<strategy_id>/stages')
def view_strategy_stages(strategy_id):
    """Hiển thị các stages và transitions liên quan đến một chiến lược."""
    strategy = None
    strategy_stages_list = []
    transitions_list = []
    try:
        strategy = db.get_strategy_details(strategy_id)
        if strategy is None:
            flash(f"Không tìm thấy chiến lược ID {strategy_id}.", "warning")
            return redirect(url_for('admin.view_strategies'))
        strategy_stages_list = db.get_stages_for_strategy(strategy_id) or []
        transitions_list = db.get_transitions_for_strategy(strategy_id) or []
        # Lấy các stages thuộc về strategy này (cần tạo hàm db.get_stages_for_strategy)
        strategy_stages_list = db.get_stages_for_strategy(strategy_id)
        if strategy_stages_list is None:
             flash(f"Lỗi khi tải các stage cho chiến lược {strategy_id}.", "error")
             strategy_stages_list = []

        # Lấy các transitions bắt đầu từ các stage của strategy này (cần tạo hàm db.get_transitions_for_strategy)
        transitions_list = db.get_transitions_for_strategy(strategy_id)
        if transitions_list is None:
             flash(f"Lỗi khi tải các transition cho chiến lược {strategy_id}.", "error")
             transitions_list = []

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải stages/transitions cho strategy {strategy_id}: {e}")
        flash("Lỗi không mong muốn khi tải chi tiết chiến lược.", "error")
        # Có thể redirect hoặc render template lỗi

    return render_template('admin_strategy_stages.html',
                           title=f"Stages & Transitions cho '{strategy.get('name', strategy_id)}'",
                           strategy=strategy,
                           strategy_stages=strategy_stages_list,
                           transitions=transitions_list)

# --- Quản lý Stages (Các route riêng biệt) ---

@admin_bp.route('/stages/add', methods=['GET', 'POST'])
def add_stage():
    strategy_id = request.args.get('strategy_id') # Lấy strategy_id từ query param
    if not strategy_id:
        flash("Cần cung cấp strategy_id để thêm stage.", "error")
        return redirect(url_for('admin.view_strategies'))

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        stage_id = request.form.get('stage_id')
        description = request.form.get('description')
        order_str = request.form.get('stage_order', '0')
        # strategy_id lấy từ hidden input hoặc dùng lại từ biến strategy_id ở trên
        form_strategy_id = request.form.get('strategy_id') # Nên có hidden input

        if not stage_id or not form_strategy_id:
             flash("Stage ID và Strategy ID là bắt buộc.", "warning")
             # Cần strategy_id để render lại form
             return render_template('admin_add_stage.html', title="Thêm Stage Mới", strategy_id=strategy_id, current_data=request.form), 400
        if form_strategy_id != strategy_id:
             flash("Lỗi không khớp Strategy ID.", "error")
             return redirect(url_for('admin.view_strategies'))

        try:
            order = int(order_str)
        except ValueError:
             flash("Stage Order phải là số nguyên.", "warning")
             return render_template('admin_add_stage.html', title="Thêm Stage Mới", strategy_id=strategy_id, current_data=request.form), 400

        try:
            success = db.add_new_stage(stage_id, form_strategy_id, description, order)
            if success:
                flash(f"Thêm stage '{stage_id}' thành công!", 'success')
                return redirect(url_for('admin.view_strategy_stages', strategy_id=form_strategy_id))
            else:
                flash(f"Thêm stage '{stage_id}' thất bại (ID đã tồn tại?).", 'error')
                return render_template('admin_add_stage.html', title="Thêm Stage Mới", strategy_id=strategy_id, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm stage: {e}")
            flash(f"Lỗi không mong muốn khi thêm stage: {e}", "error")
            return render_template('admin_add_stage.html', title="Thêm Stage Mới", strategy_id=strategy_id, current_data=request.form)

    # GET request
    return render_template('admin_add_stage.html', title=f"Thêm Stage Mới cho Strategy {strategy_id}", strategy_id=strategy_id)


@admin_bp.route('/stages/<stage_id>/edit', methods=['GET', 'POST'])
def edit_stage(stage_id):
    """Sửa description và order của stage."""
    # Lấy thông tin stage hiện tại cho cả GET và POST (nếu có lỗi)
    stage = db.get_stage_details(stage_id)
    if not stage:
        flash(f"Không tìm thấy stage ID {stage_id}.", "error")
        # Không biết strategy nào để quay về, quay về trang strategies chung
        return redirect(url_for('admin.view_strategies'))
    # Lấy strategy_id để redirect về đúng trang
    strategy_id_redirect = stage.get('strategy_id')

    if request.method == 'POST':
        description = request.form.get('description')
        order_str = request.form.get('stage_order', '0')

        try:
            order = int(order_str)
        except ValueError:
             flash("Stage Order phải là số nguyên.", "warning")
             # Render lại form với dữ liệu hiện tại (stage)
             return render_template('admin_edit_stage.html', title=f"Sửa Stage {stage_id}", stage=stage), 400

        try:
            success = db.update_stage(stage_id, description, order)
            if success:
                flash(f"Cập nhật stage '{stage_id}' thành công!", 'success')
                return redirect(url_for('admin.view_strategy_stages', strategy_id=strategy_id_redirect))
            else:
                flash(f"Cập nhật stage '{stage_id}' thất bại.", 'error')
                # Render lại form với dữ liệu hiện tại (stage)
                return render_template('admin_edit_stage.html', title=f"Sửa Stage {stage_id}", stage=stage)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi sửa stage {stage_id}: {e}")
            flash(f"Lỗi không mong muốn khi sửa stage: {e}", "error")
            return render_template('admin_edit_stage.html', title=f"Sửa Stage {stage_id}", stage=stage)

    # GET request
    return render_template('admin_edit_stage.html', title=f"Sửa Stage {stage_id}", stage=stage)

@admin_bp.route('/stages/<stage_id>/delete', methods=['POST'])
def delete_stage(stage_id):
    """Xóa một stage."""
    # Lấy strategy_id TRƯỚC KHI XÓA để biết đường redirect
    stage_details = db.get_stage_details(stage_id)
    strategy_id_redirect = stage_details.get('strategy_id') if stage_details else None

    try:
        success = db.delete_stage(stage_id)
        if success:
            flash(f"Đã xóa stage '{stage_id}'.", 'success')
        else:
            flash(f"Xóa stage '{stage_id}' thất bại (ID không tồn tại?).", 'error')
    except psycopg2.Error as db_err: # Bắt lỗi DB chung (bao gồm cả FK nếu có)
         print(f"Lỗi DB khi xóa stage {stage_id}: {db_err}")
         flash(f"Lỗi CSDL khi xóa stage '{stage_id}'. Kiểm tra xem có thành phần nào khác còn phụ thuộc vào nó không.", "error")
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa stage {stage_id}: {e}")
        flash(f"Lỗi không mong muốn khi xóa stage: {e}", "error")

    # Redirect về trang strategy detail nếu biết, nếu không về trang strategies chung
    if strategy_id_redirect:
        return redirect(url_for('admin.view_strategy_stages', strategy_id=strategy_id_redirect))
    else:
        return redirect(url_for('admin.view_strategies'))


# --- Quản lý Transitions (Các route riêng biệt) ---

@admin_bp.route('/transitions/add', methods=['GET', 'POST'])
def add_transition():
    # Lấy strategy_id và current_stage_id gợi ý từ query params
    strategy_id = request.args.get('strategy_id')
    current_stage_id_prefill = request.args.get('current_stage_id')

    if not strategy_id:
        flash("Cần cung cấp strategy_id để thêm transition.", "error")
        return redirect(url_for('admin.view_strategies'))

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_logic = request.form.get('condition_logic') # Có thể trống
        next_stage_id = request.form.get('next_stage_id') # Có thể trống
        action_to_suggest = request.form.get('action_to_suggest') # Có thể trống
        response_template_ref = request.form.get('response_template_ref') # Có thể trống
        priority_str = request.form.get('priority', '0')
        form_strategy_id = request.form.get('strategy_id') # Từ hidden input

        if not current_stage_id or not user_intent or not form_strategy_id:
             flash("Current Stage, User Intent và Strategy ID là bắt buộc.", "warning")
             # Lấy lại data cho form
             strategy_stages = db.get_stages_for_strategy(strategy_id) or []
             all_stages = db.get_all_stages() or []
             all_templates = db.get_all_template_refs() or []
             return render_template('admin_add_transition.html', title="Thêm Transition",
                                    strategy_id=strategy_id, current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                    current_data=request.form), 400
        if form_strategy_id != strategy_id:
             flash("Lỗi không khớp Strategy ID.", "error")
             return redirect(url_for('admin.view_strategies'))

        try:
            priority = int(priority_str)
        except ValueError:
             flash("Priority phải là số nguyên.", "warning")
             strategy_stages = db.get_stages_for_strategy(strategy_id) or []
             all_stages = db.get_all_stages() or []
             all_templates = db.get_all_template_refs() or []
             return render_template('admin_add_transition.html', title="Thêm Transition",
                                    strategy_id=strategy_id, current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                    current_data=request.form), 400

        try:
            success = db.add_new_transition(current_stage_id, user_intent, condition_logic,
                                            next_stage_id, action_to_suggest,
                                            response_template_ref, priority)
            if success:
                flash('Thêm transition thành công!', 'success')
                return redirect(url_for('admin.view_strategy_stages', strategy_id=form_strategy_id))
            else:
                flash('Thêm transition thất bại.', 'error')
                # Render lại form với lỗi
                strategy_stages = db.get_stages_for_strategy(strategy_id) or []
                all_stages = db.get_all_stages() or []
                all_templates = db.get_all_template_refs() or []
                return render_template('admin_add_transition.html', title="Thêm Transition",
                                       strategy_id=strategy_id, current_stage_id_prefill=current_stage_id,
                                       strategy_stages=strategy_stages, all_stages=all_stages,
                                       all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                       current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm transition: {e}")
            flash(f"Lỗi không mong muốn khi thêm transition: {e}", "error")
            strategy_stages = db.get_stages_for_strategy(strategy_id) or []
            all_stages = db.get_all_stages() or []
            all_templates = db.get_all_template_refs() or []
            return render_template('admin_add_transition.html', title="Thêm Transition",
                                   strategy_id=strategy_id, current_stage_id_prefill=current_stage_id,
                                   strategy_stages=strategy_stages, all_stages=all_stages,
                                   all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                   current_data=request.form)

    # GET request
    try:
        strategy_stages = db.get_stages_for_strategy(strategy_id) or []
        all_stages = db.get_all_stages() or []
        all_templates = db.get_all_template_refs() or []
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải data cho add transition form: {e}")
        flash("Lỗi tải dữ liệu cần thiết cho form.", "error")
        strategy_stages, all_stages, all_templates = [], [], []

    return render_template('admin_add_transition.html', title=f"Thêm Transition cho Strategy {strategy_id}",
                           strategy_id=strategy_id,
                           current_stage_id_prefill=current_stage_id_prefill, # Để chọn sẵn nếu có
                           strategy_stages=strategy_stages, # Chỉ các stage của strategy này
                           all_stages=all_stages,         # Tất cả các stage
                           all_templates=all_templates,   # Tất cả template refs
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)


@admin_bp.route('/transitions/<int:transition_id>/edit', methods=['GET', 'POST'])
def edit_transition(transition_id):
    """Sửa một transition."""
    # Lấy thông tin transition hiện tại cho cả GET và POST lỗi
    transition = db.get_transition_details(transition_id)
    if not transition:
        flash(f"Không tìm thấy transition ID {transition_id}.", "error")
        return redirect(url_for('admin.view_strategies')) # Không biết về strategy nào, về trang chung
    # Lấy strategy_id để redirect
    strategy_id_redirect = transition.get('strategy_id')

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_logic = request.form.get('condition_logic')
        next_stage_id = request.form.get('next_stage_id')
        action_to_suggest = request.form.get('action_to_suggest')
        response_template_ref = request.form.get('response_template_ref')
        priority_str = request.form.get('priority', '0')

        if not current_stage_id or not user_intent:
             flash("Current Stage và User Intent là bắt buộc.", "warning")
             # Lấy lại data cho form
             strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or [] # Chỉ stage của strategy này
             all_stages = db.get_all_stages() or []
             all_templates = db.get_all_template_refs() or []
             # Truyền transition cũ vào lại để giữ giá trị
             return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                                    transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION), 400
        try:
            priority = int(priority_str)
        except ValueError:
             flash("Priority phải là số nguyên.", "warning")
             strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
             all_stages = db.get_all_stages() or []
             all_templates = db.get_all_template_refs() or []
             return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                                    transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION), 400

        try:
            success = db.update_transition(transition_id, current_stage_id, user_intent, condition_logic,
                                            next_stage_id, action_to_suggest,
                                            response_template_ref, priority)
            if success:
                flash('Cập nhật transition thành công!', 'success')
                return redirect(url_for('admin.view_strategy_stages', strategy_id=strategy_id_redirect))
            else:
                flash('Cập nhật transition thất bại.', 'error')
                 # Render lại form với lỗi
                strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
                all_stages = db.get_all_stages() or []
                all_templates = db.get_all_template_refs() or []
                return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                                       transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                       all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật transition {transition_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật transition: {e}", "error")
            strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
            all_stages = db.get_all_stages() or []
            all_templates = db.get_all_template_refs() or []
            return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                                   transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                   all_templates=all_templates, valid_intents=VALID_INTENTS_FOR_TRANSITION)

    # GET request
    try:
        # Lấy dữ liệu cần thiết cho dropdowns
        strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or [] # Chỉ stage của strategy này
        all_stages = db.get_all_stages() or []
        all_templates = db.get_all_template_refs() or []
    except Exception as e:
         print(f"Lỗi nghiêm trọng khi tải data cho edit transition form: {e}")
         flash("Lỗi tải dữ liệu cần thiết cho form.", "error")
         strategy_stages, all_stages, all_templates = [], [], []

    # transition đã được lấy ở đầu hàm
    return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                           transition=transition,
                           strategy_stages=strategy_stages, # Chỉ các stage của strategy này
                           all_stages=all_stages,         # Tất cả các stage
                           all_templates=all_templates,   # Tất cả template refs
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)


@admin_bp.route('/transitions/<int:transition_id>/delete', methods=['POST'])
def delete_transition(transition_id):
    """Xóa một transition."""
    # Lấy strategy_id TRƯỚC KHI XÓA để redirect
    transition_details = db.get_transition_details(transition_id)
    strategy_id_redirect = transition_details.get('strategy_id') if transition_details else None

    try:
        success = db.delete_transition(transition_id)
        if success:
            flash(f"Đã xóa transition ID {transition_id}.", 'success')
        else:
            flash(f"Xóa transition ID {transition_id} thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa transition {transition_id}: {e}")
        flash(f"Lỗi không mong muốn khi xóa transition: {e}", "error")

    # Redirect về trang strategy detail nếu biết, nếu không về trang strategies chung
    if strategy_id_redirect:
        return redirect(url_for('admin.view_strategy_stages', strategy_id=strategy_id_redirect))
    else:
        return redirect(url_for('admin.view_strategies'))

@admin_bp.route('/strategies/add', methods=['GET', 'POST'])
def add_strategy():
    if request.method == 'POST':
        try:
            strategy_id = request.form.get('strategy_id')
            name = request.form.get('name') # <<< Lấy thêm 'name'
            description = request.form.get('description')
            initial_stage_id = request.form.get('initial_stage_id')

            # <<< Thêm 'name' vào kiểm tra bắt buộc >>>
            if not strategy_id or not name or not initial_stage_id:
                 flash("Strategy ID, Name, và Initial Stage ID là bắt buộc.", "warning")
                 stages = db.get_all_stages() or []
                 return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages, current_data=request.form), 400

            # <<< Truyền 'name' vào hàm DB >>>
            success = db.add_new_strategy(strategy_id, name, description, initial_stage_id)
            if success:
                flash('Thêm chiến lược thành công!', 'success')
                return redirect(url_for('admin.view_strategies'))
            else:
                flash('Thêm chiến lược thất bại (ID hoặc Name có thể đã tồn tại?).', 'error')
                stages = db.get_all_stages() or []
                return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages, current_data=request.form)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm strategy: {e}")
             flash(f"Lỗi không mong muốn khi thêm chiến lược: {e}", "error")
             stages = db.get_all_stages() or []
             return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages, current_data=request.form)

    # GET request (không cần thay đổi nhiều, nhưng đảm bảo get_all_stages hoạt động)
    try:
         stages = db.get_all_stages()
         if stages is None:
              flash("Lỗi tải danh sách stages.", "error")
              stages = []
    except Exception as e:
         print(f"Lỗi nghiêm trọng load stages for add strategy: {e}")
         flash("Lỗi không mong muốn khi tải danh sách stages.", "error")
         stages = []
    return render_template('admin_add_strategy.html', title="Thêm Chiến lược Mới", stages=stages)

# === Xem Lịch sử ===



@admin_bp.route('/history')

def view_history():
    accounts_list = [] # Khởi tạo list account
    history_items = [] # Khởi tạo list history
    pagination = {'page': 1, 'per_page': PER_PAGE, 'total_items': 0, 'total_pages': 0} # Khởi tạo pagination
    active_filters = {} # Khởi tạo filters

    try:
        # --- Lấy tham số từ URL ---
        page = request.args.get('page', 1, type=int)
        if page < 1: page = 1

        filters = {
            'account_id': request.args.get('account_id', '').strip(),
            'thread_id': request.args.get('thread_id', '').strip(),
            'status': request.args.get('status', '').strip(),
            'date_from': request.args.get('date_from', '').strip(),
            'date_to': request.args.get('date_to', '').strip(),
        }
        active_filters = {k: v for k, v in filters.items() if v}

        # --- Lấy danh sách Accounts cho dropdown lọc ---
        accounts_list = db.get_all_accounts() # <<< LẤY DANH SÁCH ACCOUNTS >>>
        if accounts_list is None:
             flash("Lỗi khi tải danh sách tài khoản để lọc.", "warning") # Dùng warning thay vì error
             accounts_list = []

        # --- Gọi hàm DB với phân trang và bộ lọc ---
        history_items, total_items = db.get_interaction_history_paginated(
            page=page,
            per_page=PER_PAGE,
            filters=active_filters
        )

        if history_items is None or total_items is None:
             flash("Lỗi khi tải lịch sử tương tác từ CSDL.", "error")
             history_items = []
             total_items = 0

        # --- Tính toán thông tin phân trang ---
        total_pages = 0
        if total_items > 0:
             total_pages = math.ceil(total_items / PER_PAGE)
        if page > total_pages and total_pages > 0: page = total_pages

        pagination = {
            'page': page, 'per_page': PER_PAGE, 'total_items': total_items,
            'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
            'prev_num': page - 1, 'next_num': page + 1
        }

    except Exception as e:
        print(f"Lỗi nghiêm trọng trong route view_history: {e}")
        flash("Lỗi không mong muốn khi tải lịch sử tương tác.", "error")
        # Đảm bảo các biến vẫn được khởi tạo là list rỗng/dict mặc định

    # Truyền dữ liệu vào template
    return render_template('admin_history.html',
                           title="Lịch sử Tương tác",
                           history=history_items,
                           pagination=pagination,
                           filters=active_filters,
                           possible_statuses=POSSIBLE_HISTORY_STATUS,
                           accounts=accounts_list) # <<< TRUYỀN accounts VÀO TEMPLATE >>>

# === Các hàm helper hoặc route khác nếu cần ===
# Ví dụ: lấy danh sách tất cả template refs cho dropdown
@admin_bp.route('/_get_templates') # Route nội bộ (ví dụ)
def get_templates_for_select():
     # Hàm này có thể được gọi bằng AJAX để cập nhật dropdown
     templates = db.get_all_template_refs()
     # Trả về JSON
     from flask import jsonify
     return jsonify(templates or [])

# Ví dụ: Lấy danh sách các stage ID
@admin_bp.route('/_get_stages')
def get_stages_for_select():
     
     stages = db.get_all_stages() # Giả sử trả về list of dicts [{stage_id, name}]
     from flask import jsonify
     return jsonify(stages or [])

# =============================================
# === QUẢN LÝ AI PERSONAS ===
# =============================================

@admin_bp.route('/ai-personas')
def view_personas():
    """Hiển thị danh sách các AI Personas."""
    personas = []
    try:
        personas = db.get_all_personas()
        if personas is None:
             flash("Lỗi khi tải danh sách AI Personas.", "error")
             personas = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi load personas: {e}")
        flash("Lỗi không mong muốn khi tải AI Personas.", "error")
        personas = []
    return render_template('admin_personas.html', title="Quản lý AI Personas", personas=personas)

@admin_bp.route('/ai-personas/add', methods=['GET', 'POST'])
def add_persona():
    """Thêm AI Persona mới."""
    if request.method == 'POST':
        persona_id = request.form.get('persona_id', '').strip()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        base_prompt = request.form.get('base_prompt', '').strip()
        model_name = request.form.get('model_name', '').strip()
        generation_config_str = request.form.get('generation_config', '').strip()

        if not persona_id or not name or not base_prompt:
             flash("Persona ID, Name, và Base Prompt là bắt buộc.", "warning")
             return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form), 400

        # Validate JSON cơ bản (nếu người dùng nhập)
        gen_config_json = None
        if generation_config_str:
            try:
                gen_config_json = json.loads(generation_config_str)
            except json.JSONDecodeError:
                flash("Generation Config không phải là JSON hợp lệ. Vui lòng nhập đúng định dạng hoặc để trống.", "warning")
                return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form), 400

        try:
            success = db.add_new_persona(persona_id, name, description, base_prompt,
                                         model_name or None, # Chuyển chuỗi rỗng thành None
                                         generation_config_str or None) # Truyền chuỗi JSON (hoặc None) vào hàm DB
            if success:
                flash(f"Thêm persona '{persona_id}' thành công!", 'success')
                return redirect(url_for('admin.view_personas'))
            else:
                flash(f"Thêm persona '{persona_id}' thất bại (ID hoặc Name đã tồn tại?).", 'error')
                return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm persona: {e}")
            flash(f"Lỗi không mong muốn khi thêm persona: {e}", "error")
            return render_template('admin_add_ai_persona.html', title="Thêm AI Persona", current_data=request.form)

    # GET request
    return render_template('admin_add_ai_persona.html', title="Thêm AI Persona")


@admin_bp.route('/ai-personas/<persona_id>/edit', methods=['GET', 'POST'])
def edit_persona(persona_id):
    """Sửa AI Persona."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        base_prompt = request.form.get('base_prompt', '').strip()
        model_name = request.form.get('model_name', '').strip()
        generation_config_str = request.form.get('generation_config', '').strip()

        if not name or not base_prompt: # ID không đổi, chỉ cần name và base_prompt
             flash("Name và Base Prompt là bắt buộc.", "warning")
             # Lấy lại persona cũ để hiển thị form
             persona = db.get_persona_details(persona_id)
             if not persona: return redirect(url_for('admin.view_personas')) # Should not happen if GET worked
             # Truyền lại request.form để giữ giá trị người dùng vừa nhập sai
             return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form), 400

        # Validate JSON
        gen_config_json = None
        if generation_config_str:
            try:
                gen_config_json = json.loads(generation_config_str)
            except json.JSONDecodeError:
                flash("Generation Config không phải là JSON hợp lệ. Vui lòng nhập đúng định dạng hoặc để trống.", "warning")
                persona = db.get_persona_details(persona_id)
                if not persona: return redirect(url_for('admin.view_personas'))
                return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form), 400

        try:
            success = db.update_persona(persona_id, name, description, base_prompt,
                                        model_name or None, generation_config_str or None)
            if success:
                flash(f"Cập nhật persona '{persona_id}' thành công!", 'success')
                return redirect(url_for('admin.view_personas'))
            else:
                flash(f"Cập nhật persona '{persona_id}' thất bại (Name đã tồn tại?).", 'error')
                # Lấy lại persona cũ và hiển thị lỗi
                persona = db.get_persona_details(persona_id)
                if not persona: return redirect(url_for('admin.view_personas'))
                return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật persona {persona_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật persona: {e}", "error")
            persona = db.get_persona_details(persona_id)
            if not persona: return redirect(url_for('admin.view_personas'))
            return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona, current_data=request.form)


    # GET request
    persona = db.get_persona_details(persona_id)
    if not persona:
        flash(f"Không tìm thấy persona ID '{persona_id}'.", "error")
        return redirect(url_for('admin.view_personas'))
    return render_template('admin_edit_ai_persona.html', title=f"Sửa AI Persona '{persona_id}'", persona=persona)


@admin_bp.route('/ai-personas/<persona_id>/delete', methods=['POST'])
def delete_persona(persona_id):
    """Xóa AI Persona."""
    try:
        success = db.delete_persona(persona_id)
        if success:
            flash(f"Đã xóa persona '{persona_id}'.", 'success')
        else:
            flash(f"Xóa persona '{persona_id}' thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
         print(f"Lỗi nghiêm trọng khi xóa persona {persona_id}: {e}")
         flash(f"Lỗi không mong muốn khi xóa persona: {e}", "error")
    return redirect(url_for('admin.view_personas'))


# =============================================
# === QUẢN LÝ PROMPT TEMPLATES ===
# =============================================

@admin_bp.route('/prompt-templates')
def view_prompt_templates():
    """Hiển thị danh sách các Prompt Templates."""
    templates = []
    try:
        templates = db.get_all_prompt_templates()
        if templates is None:
            flash("Lỗi khi tải danh sách Prompt Templates.", "error")
            templates = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi load prompt templates: {e}")
        flash("Lỗi không mong muốn khi tải Prompt Templates.", "error")
        templates = []
    return render_template('admin_prompt_templates.html', title="Quản lý Prompt Templates", templates=templates)

@admin_bp.route('/prompt-templates/add', methods=['GET', 'POST'])
def add_prompt_template():
    """Thêm Prompt Template mới."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        task_type = request.form.get('task_type', '').strip()
        template_content = request.form.get('template_content', '').strip()

        if not name or not task_type or not template_content:
             flash("Name, Task Type, và Template Content là bắt buộc.", "warning")
             return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                    task_types=PROMPT_TASK_TYPES, current_data=request.form), 400
        if task_type not in PROMPT_TASK_TYPES:
             flash("Task Type không hợp lệ.", "warning")
             return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                    task_types=PROMPT_TASK_TYPES, current_data=request.form), 400

        try:
            success = db.add_new_prompt_template(name, task_type, template_content)
            if success:
                flash(f"Thêm prompt template '{name}' thành công!", 'success')
                return redirect(url_for('admin.view_prompt_templates'))
            else:
                flash(f"Thêm prompt template '{name}' thất bại (Name đã tồn tại?).", 'error')
                return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                       task_types=PROMPT_TASK_TYPES, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm prompt template: {e}")
            flash(f"Lỗi không mong muốn khi thêm prompt template: {e}", "error")
            return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template",
                                   task_types=PROMPT_TASK_TYPES, current_data=request.form)

    # GET request
    return render_template('admin_add_prompt_template.html', title="Thêm Prompt Template", task_types=PROMPT_TASK_TYPES)


@admin_bp.route('/prompt-templates/<int:prompt_template_id>/edit', methods=['GET', 'POST'])
def edit_prompt_template(prompt_template_id):
    """Sửa Prompt Template."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        task_type = request.form.get('task_type', '').strip()
        template_content = request.form.get('template_content', '').strip()

        if not name or not task_type or not template_content:
             flash("Name, Task Type, và Template Content là bắt buộc.", "warning")
             template = db.get_prompt_template_details(prompt_template_id) # Lấy lại để hiển thị form
             if not template: return redirect(url_for('admin.view_prompt_templates'))
             return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                    template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form), 400
        if task_type not in PROMPT_TASK_TYPES:
             flash("Task Type không hợp lệ.", "warning")
             template = db.get_prompt_template_details(prompt_template_id)
             if not template: return redirect(url_for('admin.view_prompt_templates'))
             return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                    template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form), 400

        try:
            success = db.update_prompt_template(prompt_template_id, name, task_type, template_content)
            if success:
                flash(f"Cập nhật prompt template '{name}' thành công!", 'success')
                return redirect(url_for('admin.view_prompt_templates'))
            else:
                 flash(f"Cập nhật prompt template '{name}' thất bại (Name đã tồn tại?).", 'error')
                 template = db.get_prompt_template_details(prompt_template_id) # Lấy lại để hiển thị form
                 if not template: return redirect(url_for('admin.view_prompt_templates'))
                 return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                        template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật prompt template {prompt_template_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật prompt template: {e}", "error")
            template = db.get_prompt_template_details(prompt_template_id)
            if not template: return redirect(url_for('admin.view_prompt_templates'))
            return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                                   template=template, task_types=PROMPT_TASK_TYPES, current_data=request.form)


    # GET request
    template = db.get_prompt_template_details(prompt_template_id)
    if not template:
        flash(f"Không tìm thấy prompt template ID {prompt_template_id}.", "error")
        return redirect(url_for('admin.view_prompt_templates'))
    return render_template('admin_edit_prompt_template.html', title=f"Sửa Prompt Template {prompt_template_id}",
                           template=template, task_types=PROMPT_TASK_TYPES)


@admin_bp.route('/prompt-templates/<int:prompt_template_id>/delete', methods=['POST'])
def delete_prompt_template(prompt_template_id):

    """Xóa Prompt Template."""
    try:
        success = db.delete_prompt_template(prompt_template_id)
        if success:
            flash(f"Đã xóa prompt template ID {prompt_template_id}.", 'success')
        else:
            flash(f"Xóa prompt template ID {prompt_template_id} thất bại (ID không tồn tại?).", 'error')
    except Exception as e:
         print(f"Lỗi nghiêm trọng khi xóa prompt template {prompt_template_id}: {e}")
         flash(f"Lỗi không mong muốn khi xóa prompt template: {e}", "error")
    return redirect(url_for('admin.view_prompt_templates'))

# =============================================
# === AI PLAYGROUND / CHAT UTILITY ===
# =============================================

@admin_bp.route('/ai-playground', methods=['GET', 'POST'])
def ai_playground():
    """Trang tiện ích để chat trực tiếp với AI."""
    personas = []
    ai_response = None
    user_prompt = ""
    selected_persona_id = ""
    error_message = None

    try:
        # Lấy danh sách persona cho dropdown (cho cả GET và POST)
        personas = db.get_all_personas() or []
    except Exception as e:
        print(f"Lỗi khi lấy danh sách personas cho playground: {e}")
        flash("Không thể tải danh sách AI Personas.", "error")
        personas = [] # Vẫn render trang nhưng không có lựa chọn persona

    if request.method == 'POST':
        user_prompt = request.form.get('user_prompt', '').strip()
        selected_persona_id = request.form.get('persona_id', '').strip() # Lấy persona đã chọn
        # Nếu không chọn persona cụ thể, có thể truyền None hoặc ID mặc định
        persona_id_to_use = selected_persona_id if selected_persona_id else None # Hoặc dùng DEFAULT_REPLY_PERSONA_ID

        if not user_prompt:
            flash("Vui lòng nhập yêu cầu/prompt.", "warning")
        else:
            try:
                # Gọi hàm AI service tổng quát mới tạo
                ai_response_text, status = ai_service.call_generative_model(
                    prompt=user_prompt,
                    persona_id=persona_id_to_use
                )
                if status == 'success':
                    ai_response = ai_response_text
                else:
                    # Hiển thị lỗi chi tiết hơn cho admin
                    error_message = f"AI Error: {status}"
                    if ai_response_text: # Đôi khi có text lỗi trả về
                         error_message += f"\nDetails: {ai_response_text}"
                    ai_response = None # Không có kết quả thành công
                    flash(f"AI không thể xử lý yêu cầu (Status: {status}).", "error")

            except Exception as e:
                print(f"Lỗi nghiêm trọng khi gọi AI trong playground: {e}")
                flash(f"Lỗi không mong muốn khi gọi AI: {e}", "error")
                error_message = f"Server Error: {e}"
                ai_response = None

    # Render template cho cả GET và POST (POST sẽ có thêm user_prompt và ai_response/error_message)
    return render_template('admin_ai_playground.html',
                           title="AI Playground",
                           personas=personas,
                           user_prompt=user_prompt, # Giữ lại prompt đã nhập
                           ai_response=ai_response, # Kết quả từ AI
                           error_message=error_message, # Thông báo lỗi (nếu có)
                           selected_persona_id=selected_persona_id) # Giữ lại persona đã chọn

# =============================================
# === QUẢN LÝ TÁC VỤ NỀN (SCHEDULER) ===
# =============================================

@admin_bp.route('/scheduled-jobs')
def view_scheduled_jobs():
    """Hiển thị danh sách các Job đã cấu hình trong DB."""
    jobs = []
    try:
        jobs = db.get_all_job_configs()
        if jobs is None:
             flash("Lỗi khi tải danh sách cấu hình jobs.", "error")
             jobs = []
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi load job configs: {e}")
        flash("Lỗi không mong muốn khi tải cấu hình jobs.", "error")
        jobs = []
    # Lấy trạng thái job đang chạy thực tế từ scheduler (nếu có thể)
    live_jobs_status = {}
    if scheduler:
        try:
            running_jobs = scheduler.get_jobs()
            for job in running_jobs:
                 # next_run_time là None nếu job đang bị pause
                 live_jobs_status[job.id] = {'next_run': job.next_run_time}
        except Exception as e:
             print(f"Lỗi khi lấy trạng thái jobs từ scheduler: {e}")
             flash("Không thể lấy trạng thái job đang chạy từ scheduler.", "warning")

    return render_template('admin_scheduled_jobs.html',
                            title="Quản lý Tác vụ nền",
                            jobs=jobs,
                            live_jobs_status=live_jobs_status)

@admin_bp.route('/scheduled-jobs/add', methods=['GET', 'POST'])
def add_scheduled_job():
    """Thêm cấu hình Job mới vào DB và scheduler."""
    if request.method == 'POST':
        job_id = request.form.get('job_id', '').strip()
        function_path = request.form.get('job_function_path', '').strip()
        trigger_type = request.form.get('trigger_type', '').strip()
        trigger_args_str = request.form.get('trigger_args', '{}').strip() # Mặc định JSON rỗng
        is_enabled_str = request.form.get('is_enabled') # Checkbox sẽ gửi 'on' hoặc không gửi gì
        is_enabled = True if is_enabled_str == 'on' else False
        description = request.form.get('description', '').strip()

        # ----- Validate Input -----
        if not job_id or not function_path or not trigger_type:
            flash("Job ID, Function Path, và Trigger Type là bắt buộc.", "warning")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ",
                                   trigger_types=TRIGGER_TYPES, current_data=request.form), 400

        trigger_args_dict = {}
        try:
            trigger_args_dict = json.loads(trigger_args_str)
            if not isinstance(trigger_args_dict, dict):
                 raise ValueError("Trigger Args phải là một JSON object.")
        except json.JSONDecodeError:
            flash("Trigger Args không phải là định dạng JSON hợp lệ.", "warning")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ",
                                   trigger_types=TRIGGER_TYPES, current_data=request.form), 400
        except ValueError as ve:
            flash(str(ve), "warning")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ",
                                   trigger_types=TRIGGER_TYPES, current_data=request.form), 400

        # (Tùy chọn) Validate function path
        try:
             module_path, func_name = function_path.rsplit('.', 1)
             module = importlib.import_module(module_path)
             func = getattr(module, func_name)
             if not callable(func):
                  raise AttributeError("Function path không trỏ đến một đối tượng callable.")
        except (ValueError, ImportError, AttributeError) as import_err:
             flash(f"Function Path không hợp lệ hoặc không tìm thấy: {import_err}", "warning")
             return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ",
                                    trigger_types=TRIGGER_TYPES, current_data=request.form), 400

        # ----- Lưu vào DB -----
        db_success, db_error = db.add_job_config(job_id, function_path, trigger_type, trigger_args_str, is_enabled, description)

        if not db_success:
            flash(f"Lỗi lưu vào DB: {db_error}", "error")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ",
                                   trigger_types=TRIGGER_TYPES, current_data=request.form)

        # ----- Thêm vào Scheduler đang chạy (nếu được enable) -----
        scheduler_error = None
        if is_enabled and scheduler:
            try:
                print(f"Attempting to add job '{job_id}' to live scheduler...")
                scheduler.add_job(
                    id=job_id,
                    func=func, # Dùng func đã import ở trên
                    trigger=trigger_type,
                    replace_existing=True,
                    **trigger_args_dict # Giải nén dict thành kwargs
                )
                print(f"Successfully added job '{job_id}' to live scheduler.")
            except Exception as e:
                scheduler_error = f"Lưu DB thành công nhưng không thể thêm job vào scheduler đang chạy: {e}"
                print(f"ERROR adding job '{job_id}' to scheduler: {scheduler_error}")
                flash(scheduler_error, "warning") # Báo warning thay vì error vì DB đã lưu
        elif not scheduler:
             flash("Đã lưu cấu hình job vào DB, nhưng không thể thêm vào scheduler (scheduler chưa được khởi tạo đúng cách?).", "warning")


        if not scheduler_error:
             flash(f"Thêm tác vụ '{job_id}' thành công!", 'success')

        return redirect(url_for('admin.view_scheduled_jobs'))

    # GET request
    return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ Nền Mới", trigger_types=TRIGGER_TYPES)

@admin_bp.route('/scheduled-jobs/<job_id>/edit', methods=['GET', 'POST'])
def edit_scheduled_job(job_id):
    """Sửa cấu hình một Job."""
    if request.method == 'POST':
        # Lấy dữ liệu form (không cho sửa job_id, function_path)
        trigger_type = request.form.get('trigger_type', '').strip()
        trigger_args_str = request.form.get('trigger_args', '{}').strip()
        is_enabled_str = request.form.get('is_enabled')
        is_enabled = True if is_enabled_str == 'on' else False
        description = request.form.get('description', '').strip()

        # Validate
        if not trigger_type:
             flash("Trigger Type là bắt buộc.", "warning")
             job_details = db.get_job_config_details(job_id) # Lấy lại để render form
             if not job_details: return redirect(url_for('admin.view_scheduled_jobs'))
             return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}'",
                                    job=job_details, trigger_types=TRIGGER_TYPES, current_data=request.form), 400

        trigger_args_dict = {}
        try:
            trigger_args_dict = json.loads(trigger_args_str)
            if not isinstance(trigger_args_dict, dict):
                 raise ValueError("Trigger Args phải là một JSON object.")
        except json.JSONDecodeError:
            flash("Trigger Args không phải là định dạng JSON hợp lệ.", "warning")
            job_details = db.get_job_config_details(job_id)
            if not job_details: return redirect(url_for('admin.view_scheduled_jobs'))
            return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}'",
                                   job=job_details, trigger_types=TRIGGER_TYPES, current_data=request.form), 400
        except ValueError as ve:
             flash(str(ve), "warning")
             job_details = db.get_job_config_details(job_id)
             if not job_details: return redirect(url_for('admin.view_scheduled_jobs'))
             return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}'",
                                    job=job_details, trigger_types=TRIGGER_TYPES, current_data=request.form), 400


        # --- Cập nhật DB ---
        db_success, db_error = db.update_job_config(job_id, trigger_type, trigger_args_str, is_enabled, description)

        if not db_success:
             flash(f"Lỗi cập nhật DB: {db_error}", "error")
             job_details = db.get_job_config_details(job_id) # Lấy lại data cũ
             if not job_details: return redirect(url_for('admin.view_scheduled_jobs'))
             return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}'",
                                    job=job_details, trigger_types=TRIGGER_TYPES, current_data=request.form)

        # --- Cập nhật Scheduler đang chạy ---
        scheduler_error = None
        if scheduler:
            try:
                print(f"Attempting to update job '{job_id}' in live scheduler...")
                # 1. Reschedule (thay đổi trigger và args)
                scheduler.reschedule_job(job_id, trigger=trigger_type, **trigger_args_dict)
                print(f"Rescheduled job '{job_id}'.")
                # 2. Pause/Resume dựa trên is_enabled
                # Kiểm tra trạng thái hiện tại của job trong scheduler
                live_job = scheduler.get_job(job_id)
                is_currently_paused = (live_job.next_run_time is None) if live_job else True # Giả sử là paused nếu không tìm thấy

                if is_enabled and is_currently_paused:
                     print(f"Resuming job '{job_id}'...")
                     scheduler.resume_job(job_id)
                elif not is_enabled and not is_currently_paused:
                     print(f"Pausing job '{job_id}'...")
                     scheduler.pause_job(job_id)
                print(f"Successfully updated job '{job_id}' in live scheduler.")

            except JobLookupError:
                 scheduler_error = f"Lưu DB thành công, nhưng không tìm thấy job '{job_id}' trong scheduler đang chạy để cập nhật."
                 print(f"WARNING: {scheduler_error}")
                 flash(scheduler_error, "warning")
            except Exception as e:
                 scheduler_error = f"Lưu DB thành công, nhưng lỗi khi cập nhật scheduler: {e}"
                 print(f"ERROR updating job '{job_id}' in scheduler: {scheduler_error}")
                 flash(scheduler_error, "warning")
        else:
             flash("Đã cập nhật cấu hình job trong DB, nhưng không thể cập nhật scheduler (scheduler chưa được khởi tạo đúng cách?).", "warning")

        if not scheduler_error:
             flash(f"Cập nhật tác vụ '{job_id}' thành công!", 'success')

        return redirect(url_for('admin.view_scheduled_jobs'))

    # GET request
    job_details = db.get_job_config_details(job_id)
    if not job_details:
        flash(f"Không tìm thấy cấu hình cho job ID '{job_id}'.", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))
    return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}'",
                           job=job_details, trigger_types=TRIGGER_TYPES)


@admin_bp.route('/scheduled-jobs/<job_id>/delete', methods=['POST'])
def delete_scheduled_job(job_id):
    """Xóa cấu hình Job khỏi DB và Scheduler."""
    # --- Xóa khỏi Scheduler trước (nếu lỗi thì vẫn còn trong DB) ---
    scheduler_error = None
    if scheduler:
        try:
            print(f"Attempting to remove job '{job_id}' from live scheduler...")
            scheduler.remove_job(job_id, missing_ok=True) # missing_ok=True để không lỗi nếu job đã bị xóa hoặc chưa tồn tại
            print(f"Successfully removed job '{job_id}' from scheduler (if it existed).")
        except Exception as e:
             # Không nên chặn việc xóa khỏi DB nếu chỉ lỗi xóa khỏi scheduler
             scheduler_error = f"Lỗi khi xóa job '{job_id}' khỏi scheduler: {e}"
             print(f"ERROR: {scheduler_error}")
             flash(scheduler_error, "warning")
    else:
         flash("Không thể xóa job khỏi scheduler (scheduler chưa được khởi tạo đúng cách?).", "warning")


    # --- Xóa khỏi DB ---
    db_success, db_error = db.delete_job_config(job_id)
    if db_success:
        flash(f"Đã xóa cấu hình job '{job_id}' khỏi DB." + (f" ({scheduler_error})" if scheduler_error else ""), 'success')
    else:
        flash(f"Lỗi xóa cấu hình job '{job_id}' khỏi DB: {db_error}", "error")

    return redirect(url_for('admin.view_scheduled_jobs'))


@admin_bp.route('/scheduled-jobs/<job_id>/toggle', methods=['POST'])
def toggle_scheduled_job(job_id):
    """Bật/Tắt một Job."""
    new_enabled_state = None
    # Lấy trạng thái hiện tại từ DB để đảo ngược
    job_details = db.get_job_config_details(job_id)
    if not job_details:
        flash(f"Không tìm thấy job '{job_id}' để thay đổi trạng thái.", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))

    current_enabled_state = job_details.get('is_enabled', False)
    new_enabled_state = not current_enabled_state

    # --- Cập nhật trạng thái trong DB ---
    db_success, db_error = db.update_job_enabled_status(job_id, new_enabled_state)

    if not db_success:
        flash(f"Lỗi cập nhật trạng thái DB cho job '{job_id}': {db_error}", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))

    # --- Cập nhật trạng thái trong Scheduler ---
    scheduler_error = None
    if scheduler:
        try:
            live_job = scheduler.get_job(job_id)
            if not live_job:
                 raise JobLookupError(job_id) # Ném lỗi nếu job không tồn tại trong scheduler

            if new_enabled_state:
                print(f"Resuming job '{job_id}'...")
                scheduler.resume_job(job_id)
                flash(f"Đã kích hoạt (resume) job '{job_id}'.", 'success')
            else:
                print(f"Pausing job '{job_id}'...")
                scheduler.pause_job(job_id)
                flash(f"Đã tạm dừng (pause) job '{job_id}'.", 'info')

        except JobLookupError:
             scheduler_error = f"Lưu trạng thái DB thành công, nhưng không tìm thấy job '{job_id}' trong scheduler để bật/tắt."
             print(f"WARNING: {scheduler_error}")
             flash(scheduler_error, "warning")
        except Exception as e:
             scheduler_error = f"Lưu trạng thái DB thành công, nhưng lỗi khi bật/tắt job trong scheduler: {e}"
             print(f"ERROR toggling job '{job_id}' in scheduler: {scheduler_error}")
             flash(scheduler_error, "warning")
    else:
        flash("Đã cập nhật trạng thái job trong DB, nhưng không thể tương tác với scheduler (chưa khởi tạo?).", "warning")


    return redirect(url_for('admin.view_scheduled_jobs'))