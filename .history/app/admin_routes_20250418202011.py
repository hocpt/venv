# app/admin_routes.py
import traceback
from typing import Counter
from flask import Blueprint, Flask, render_template, request, redirect, url_for, flash,current_app 
from datetime import datetime, timedelta, timezone 
import psycopg2
import math
import json
import uuid 
import importlib # Để kiểm tra function path (tùy chọn)
import pytz
from collections import Counter
from flask import jsonify
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)
from math import ceil # <<< Thêm import ceil

PER_PAGE_RULES = 30
PER_PAGE_TEMPLATES = 30
PER_PAGE_ACCOUNTS = 30
PER_PAGE_PERSONAS = 30
PER_PAGE_PROMPT_TEMPLATES = 30
PER_PAGE_SAVED_SIM_CONFIGS = 30
PER_PAGE_MACROS = 30
PER_PAGE = 30


try:
    from app.scheduler_runner import live_scheduler
except ImportError:
    print("CRITICAL WARNING (admin_routes): Could not import live_scheduler from app.scheduler_runner! Live control will fail.")
    live_scheduler = None
try:
    from . import ai_service
except ImportError:
    import ai_service
    print("WARNING (admin_routes): Using fallback ai_service import.")
# Import db và scheduler (đã chuyển sang SQLAlchemyJobStore và import trực tiếp)
try:
    from . import database as db
except ImportError:
    import database as db
    print("WARNING (admin_routes): Using fallback database import.")

try: from .background_tasks import approve_all_suggestions_task
except ImportError: approve_all_suggestions_task = None
# Import hàm tác vụ nền
try:
    from .background_tasks import run_ai_conversation_simulation # <<< Import hàm mô phỏng
except ImportError:
     print("CRITICAL WARNING (admin_routes): Could not import background tasks!")
     run_ai_conversation_simulation = None # Đặt là None nếu import lỗi
# --- Định nghĩa các loại trigger hợp lệ ---
try:
    from .phone import controller as phone_controller
except ImportError:
    # Fallback nếu cấu trúc hơi khác hoặc để test độc lập
    try:
        import phone.controller as phone_controller
        print("WARN (admin_routes): Using fallback import for phone.controller")
    except ImportError:
        print("CRITICAL ERROR (admin_routes): Cannot import phone controller!")
        phone_controller = None
TRIGGER_TYPES = ['interval', 'cron', 'date']
# === ĐỊNH NGHĨA CÁC TÁC VỤ NỀN CÓ THỂ LÊN LỊCH TỪ UI ===
# Key: Tên hiển thị trên UI
# Value: Đường dẫn Python đầy đủ đến hàm thực thi
AVAILABLE_SCHEDULED_TASKS = {
    'Phân tích & Đề xuất AI (Suggestion Job)': 'app.background_tasks.analyze_interactions_and_suggest',
    'Tự động Duyệt Tất Cả Đề Xuất': 'app.background_tasks.approve_all_suggestions_task',
    # Thêm các tác vụ nền định kỳ khác bạn muốn người dùng có thể lên lịch ở đây
    # Lưu ý: Không nên thêm run_ai_conversation_simulation ở đây vì nó cần tham số động
}
VALID_CONDITION_TYPES = [
    '', # Lựa chọn mặc định: Luôn chạy (Không có điều kiện)
    'current_stage_equals', # Điều kiện: Stage hiện tại bằng giá trị
    'element_exists_text', # Điều kiện: Element có text này tồn tại
    'element_exists_id', # Điều kiện: Element có ID này tồn tại
    # Thêm các loại điều kiện khác bạn muốn hỗ trợ ở đây
    # Ví dụ: 'variable_equals', 'element_not_exists_text', ...
]
admin_bp = Blueprint(
    'admin',
    __name__,
    template_folder='../templates',
    url_prefix='/admin'
)
VALID_INTENTS_FOR_TRANSITION = [
    'greeting', 'price_query', 'shipping_query', 'product_info_query',
    'compliment', 'complaint', 'connection_request', 'spam',
    'positive_generic', 'negative_generic', 'other', 'any' # Thêm 'any'
]
 # Đặt số lượng item mỗi trang ở đây
VALID_CONDITION_TYPES = ['', 'current_stage_equals', 'element_exists_text', 'element_exists_id']
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
VALID_STRATEGY_TYPES = ['language', 'control']
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

def _get_configured_timezone():
    try:
         # Cố gắng lấy từ config nếu có, nếu không dùng default
         # tz_str = current_app.config.get('SCHEDULER_TIMEZONE', 'Asia/Ho_Chi_Minh')
         tz_str = 'Asia/Ho_Chi_Minh' # Hoặc dùng giá trị mặc định trực tiếp
         return pytz.timezone(tz_str)
    except Exception:
         print("WARN: Could not get configured timezone, falling back to UTC.")
         return pytz.utc
# === Quản lý Luật (Đã có từ trước - Bổ sung endpoint cho edit) ===

@admin_bp.route('/rules')
def view_rules():
    title = "Quản lý Luật (Simple Rules)"
    rules = []
    duplicate_keyword_rule_ids = set()
    distinct_categories = []
    distinct_template_refs = []
    active_filters = {}
    pagination = None # <<< Biến lưu thông tin phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL, mặc định là 1
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            # Lấy các tham số filter (như cũ)
            filter_keywords = request.args.get('filter_keywords', '').strip()
            filter_category = request.args.get('filter_category', '').strip()
            filter_template_ref = request.args.get('filter_template_ref', '').strip()
            active_filters = {k.replace('filter_', ''): v for k, v in request.args.items() if v and k.startswith('filter_')}
            print(f"DEBUG (view_rules): Page={page}, Active Filters = {active_filters}")

            # Gọi hàm lấy luật đã lọc VÀ tổng số mục
            rules, total_items = db.get_filtered_rules(
                filters=active_filters,
                page=page,
                per_page=PER_PAGE_RULES
            ) # <<< Gọi hàm đã sửa

            if rules is None or total_items is None:
                 flash("Lỗi khi tải danh sách luật từ CSDL.", "error"); rules = []; total_items = 0

            print(f"DEBUG (view_rules): Fetched {len(rules)} rules for page {page}. Total matching: {total_items}")

            # --- Tính toán thông tin phân trang ---
            if total_items > 0:
                 total_pages = ceil(total_items / PER_PAGE_RULES)
                 if page > total_pages: page = total_pages # Tránh page ảo
                 pagination = {
                    'page': page, 'per_page': PER_PAGE_RULES, 'total_items': total_items,
                    'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                    'prev_num': page - 1 if page > 1 else None,
                    'next_num': page + 1 if page < total_pages else None
                 }
            else: # Nếu không có mục nào
                 pagination = {'page': 1, 'per_page': PER_PAGE_RULES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}

            # Lấy danh sách cho dropdown filter (như cũ)
            distinct_categories = db.get_distinct_rule_categories() or []
            distinct_template_refs = db.get_distinct_rule_template_refs() or []

            # --- Logic tìm keywords trùng lặp (chỉ chạy trên rules của trang hiện tại) ---
            if rules:
                # ... (Code tìm duplicate_keyword_rule_ids như cũ) ...
                keyword_counts = Counter()
                for rule in rules:
                    normalized_keywords=tuple(sorted([k.strip().lower() for k in rule.get('trigger_keywords','').split(',') if k.strip()]))
                    if normalized_keywords: keyword_counts[normalized_keywords] += 1
                duplicate_keywords = {kw for kw, count in keyword_counts.items() if count > 1}
                for rule in rules:
                    normalized_keywords=tuple(sorted([k.strip().lower() for k in rule.get('trigger_keywords','').split(',') if k.strip()]))
                    if normalized_keywords in duplicate_keywords: duplicate_keyword_rule_ids.add(rule.get('rule_id'))


        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load rules: {e}")
            flash("Đã xảy ra lỗi không mong muốn khi tải danh sách luật.", "error")
            rules = []; duplicate_keyword_rule_ids = set(); distinct_categories = []; distinct_template_refs = []; pagination = None

    # Truyền tất cả dữ liệu cần thiết vào template
    return render_template('admin_rules.html',
                           title=title,
                           rules=rules, # <<< Chỉ chứa dữ liệu trang hiện tại
                           duplicate_rule_ids=duplicate_keyword_rule_ids,
                           distinct_categories=distinct_categories,
                           distinct_template_refs=distinct_template_refs,
                           filters=active_filters,
                           pagination=pagination) # <<< Truyền pagination

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
        except psycopg2.IntegrityError as e:
            # Bắt lỗi nếu vi phạm ràng buộc UNIQUE mới thêm
            db.get_db_connection().rollback() # Rollback transaction
            print(f"IntegrityError while adding rule: {e}")
            flash("Thêm luật thất bại! Có vẻ luật với Keywords, Category, và Template Ref này đã tồn tại.", "error")
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm luật: {e}")
            flash(f"Đã xảy ra lỗi không mong muốn khi thêm luật: {e}", "error")
            # Ở lại trang add, cần lấy lại template list
            templates = db.get_all_template_refs() or []
            return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates, current_data=request.form)

    # GET request
    try:
        # Giả sử hàm này lấy list các dict [{'template_ref': 'ref1'}, ...]
        templates = db.get_all_template_refs() or []
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
    except psycopg2.IntegrityError as e:
         db.get_db_connection().rollback() # Rollback transaction
         print(f"IntegrityError while updating rule {rule_id}: {e}")
         flash("Cập nhật luật thất bại! Có vẻ bạn đang tạo ra một luật trùng lặp với luật khác (Keywords, Category, Template Ref).", "error")
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải dữ liệu sửa luật: {e}")
        flash("Không thể tải dữ liệu để sửa luật.", "error")
        return redirect(url_for('admin.view_rules'))
    rule = db.get_rule_by_id(rule_id)
    templates = db.get_all_template_refs() or []
    if not rule: return redirect(url_for('admin.view_rules'))
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


# === Đề xuất AI ===
@admin_bp.route('/suggestions')
def view_suggestions():
    title = "Đề xuất từ AI"
    suggestions = []
    suggestion_job_status = {'status': 'Unknown', 'next_run_time_str': 'N/A'} # <<< Khởi tạo dict trạng thái

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy danh sách suggestions đang chờ (như cũ)
            suggestions = db.get_pending_suggestions()
            if suggestions is None:
                 flash("Không thể tải đề xuất từ CSDL.", "error")
                 suggestions = []

            # --- <<< THÊM LOGIC LẤY TRẠNG THÁI LIVE CỦA suggestion_job >>> ---
            try:
                live_run_times = _get_live_next_run_times() or {}
                job_id_to_check = 'suggestion_job'
                server_tz = _get_configured_timezone()

                if job_id_to_check in live_run_times:
                    next_run_timestamp = live_run_times[job_id_to_check]
                    if next_run_timestamp is not None:
                        try:
                            utc_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
                            local_dt = utc_dt.astimezone(server_tz)
                            suggestion_job_status['next_run_time_str'] = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
                            suggestion_job_status['status'] = 'Scheduled'
                        except Exception as fmt_err:
                            print(f"Error formatting suggestion_job time: {fmt_err}")
                            suggestion_job_status['next_run_time_str'] = 'Lỗi Format'
                            suggestion_job_status['status'] = 'Error Formatting'
                    else:
                        # Timestamp là None -> Job đang Paused
                        suggestion_job_status['next_run_time_str'] = '---'
                        suggestion_job_status['status'] = 'Paused'
                else:
                    # Không tìm thấy job_id trong apscheduler_jobs
                    # Kiểm tra xem nó có đang được enable trong config không
                    job_config = db.get_job_config_details(job_id_to_check)
                    if job_config and job_config.get('is_enabled'):
                         suggestion_job_status['status'] = 'Error/Not Found in Scheduler' # Lẽ ra phải có nếu enabled
                    else:
                         suggestion_job_status['status'] = 'Disabled' # Bị tắt trong config

            except Exception as live_err:
                print(f"Error getting live status for suggestion_job: {live_err}")
                suggestion_job_status['status'] = 'Error Fetching Status'
            # --- <<< KẾT THÚC LOGIC LẤY TRẠNG THÁI LIVE >>> ---

        except Exception as e:
            print(f"Lỗi nghiêm trọng load suggestions page data: {e}")
            suggestions = []
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")

    # Truyền thêm suggestion_job_status vào template
    return render_template('admin_suggestions.html',
                           title=title,
                           suggestions=suggestions,
                           suggestion_job_status=suggestion_job_status)

@admin_bp.route('/suggestions/<int:suggestion_id>/edit', methods=['GET', 'POST'])
def edit_suggestion(suggestion_id):
    """ Hiển thị form để sửa và phê duyệt suggestion từ AI """
    if not db: # Kiểm tra db
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_suggestions'))

    # Lấy thông tin suggestion gốc cho cả GET và POST (nếu lỗi validation)
    suggestion = db.get_suggestion_by_id(suggestion_id)
    if not suggestion:
        flash(f"Không tìm thấy đề xuất ID {suggestion_id}.", "error")
        return redirect(url_for('admin.view_suggestions'))
    if suggestion.get('status') != 'pending':
        flash(f"Đề xuất ID {suggestion_id} không ở trạng thái 'pending'.", "warning")
        return redirect(url_for('admin.view_suggestions'))

    if request.method == 'POST':
        # Lấy dữ liệu đã chỉnh sửa từ form
        keywords = request.form.get('keywords', '').strip()
        category = request.form.get('category', '').strip()
        template_ref = request.form.get('template_ref', '').strip()
        template_text = request.form.get('template_text', '').strip()
        priority = request.form.get('priority', type=int, default=0)
        notes = f"Approved from AI suggestion #{suggestion_id}. Original keywords: {suggestion.get('suggested_keywords', '')}" # Giữ note gốc

        # Validate dữ liệu nhập (quan trọng!)
        error = False
        if not keywords:
            flash("Keywords là bắt buộc.", "warning"); error = True
        if not template_ref:
            flash("Template Ref là bắt buộc.", "warning"); error = True
        if not template_text:
             flash("Template Text (Variation) là bắt buộc.", "warning"); error = True

        if error:
             # Truyền lại dữ liệu vừa nhập vào form để người dùng sửa tiếp
             return render_template('admin_edit_suggestion.html',
                                    title=f"Sửa & Phê duyệt Đề xuất #{suggestion_id}",
                                    suggestion=suggestion, # Dùng suggestion gốc để hiển thị phần không sửa được
                                    current_data=request.form), 400 # current_data chứa giá trị vừa nhập

        # ----- Thực hiện logic phê duyệt với dữ liệu đã sửa -----
        approval_error = None
        try:
            # 1. Thêm Template và Variation mới (dùng dữ liệu đã sửa)
            # Hàm add_new_template sẽ tự xử lý ON CONFLICT nếu template_ref đã tồn tại
            # nhưng nên khuyến khích người dùng đặt ref mới nếu sửa đổi nhiều
            added_template_ref = db.add_new_template(
                template_ref=template_ref,
                first_variation_text=template_text,
                description=f"AI suggested, approved from #{suggestion_id}", # Hoặc để trống
                category=category if category else None
            )

            if added_template_ref:
                # 2. Thêm Rule mới (dùng dữ liệu đã sửa)
                rule_added = db.add_new_rule(
                    keywords=keywords,
                    category=category if category else None,
                    template_ref=added_template_ref, # Dùng ref trả về (có thể là cái cũ nếu đã tồn tại)
                    priority=priority,
                    notes=notes
                )

                if rule_added:
                    # 3. Cập nhật trạng thái suggestion thành 'approved'
                    status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                    if status_updated:
                        flash(f"Đã phê duyệt thành công đề xuất #{suggestion_id} và tạo rule/template.", "success")
                    else:
                        # Vẫn thành công về mặt thêm rule/template nhưng lỗi cập nhật status suggestion
                        flash(f"Đã tạo rule/template cho đề xuất #{suggestion_id}, nhưng không thể cập nhật trạng thái đề xuất.", "warning")
                    # Redirect về trang suggestions sau khi thành công
                    return redirect(url_for('admin.view_suggestions'))
                else:
                    # Lỗi khi thêm rule (sau khi đã thêm template/variation)
                    approval_error = "Đã thêm template/variation nhưng thêm rule thất bại."
            else:
                # Lỗi ngay từ bước thêm template/variation
                approval_error = "Thêm template/variation mới thất bại (Template Ref có thể bị lỗi?)."

        except Exception as e:
            approval_error = f"Lỗi không mong muốn trong quá trình phê duyệt: {e}"
            print(f"Lỗi nghiêm trọng khi phê duyệt suggestion {suggestion_id}: {e}")
            print(traceback.format_exc())

        # Nếu có lỗi trong quá trình phê duyệt
        if approval_error:
            flash(f"Phê duyệt thất bại: {approval_error}", "error")
            # Hiển thị lại form với dữ liệu người dùng vừa nhập
            return render_template('admin_edit_suggestion.html',
                                   title=f"Sửa & Phê duyệt Đề xuất #{suggestion_id}",
                                   suggestion=suggestion,
                                   current_data=request.form)

    # --- Xử lý GET Request ---
    # Truyền suggestion gốc vào template để hiển thị giá trị AI đề xuất ban đầu
    return render_template('admin_edit_suggestion.html',
                           title=f"Sửa & Phê duyệt Đề xuất #{suggestion_id}",
                           suggestion=suggestion)

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

@admin_bp.route('/suggestions/<int:suggestion_id>/approve-direct', methods=['POST'])
def approve_suggestion_direct(suggestion_id):
    """Xử lý phê duyệt trực tiếp suggestion mà không cần sửa đổi."""
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_suggestions'))

    # 1. Lấy thông tin suggestion gốc từ DB
    suggestion = db.get_suggestion_by_id(suggestion_id)
    if not suggestion:
        flash(f"Không tìm thấy đề xuất ID {suggestion_id}.", "error")
        return redirect(url_for('admin.view_suggestions'))
    if suggestion.get('status') != 'pending':
        flash(f"Đề xuất ID {suggestion_id} không ở trạng thái 'pending'.", "warning")
        return redirect(url_for('admin.view_suggestions'))

    # 2. Lấy các giá trị AI đã đề xuất (KHÔNG lấy từ form)
    keywords = suggestion.get('suggested_keywords')
    category = suggestion.get('suggested_category') # Lấy category AI đề xuất
    template_ref = suggestion.get('suggested_template_ref') # Lấy ref AI đề xuất
    template_text = suggestion.get('suggested_template_text')
    priority = 0 # Hoặc bạn có thể đặt một priority mặc định khác
    notes = f"Approved directly from AI suggestion #{suggestion_id}."

    # Validate dữ liệu đề xuất tối thiểu
    if not keywords or not template_ref or not template_text:
        flash(f"Đề xuất ID {suggestion_id} thiếu thông tin Keywords, Template Ref hoặc Template Text. Không thể phê duyệt trực tiếp.", "error")
        # Có thể nên chuyển suggestion này sang status 'error' hoặc 'needs_edit'
        # db.update_suggestion_status(suggestion_id, 'error_missing_data')
        return redirect(url_for('admin.view_suggestions'))

    # ----- Thực hiện logic phê duyệt -----
    approval_error = None
    try:
        # 1. Thêm Template và Variation mới
        added_template_ref = db.add_new_template(
            template_ref=template_ref,
            first_variation_text=template_text,
            description=f"AI suggested, direct approval #{suggestion_id}", # Mô tả tự động
            category=category if category else None # Dùng category AI đề xuất
        )

        if added_template_ref:
            # 2. Thêm Rule mới
            rule_added = db.add_new_rule(
                keywords=keywords,
                category=category if category else None,
                template_ref=added_template_ref, # Dùng ref có thể đã tồn tại hoặc mới tạo
                priority=priority,
                notes=notes
            )

            if rule_added:
                # 3. Cập nhật trạng thái suggestion thành 'approved'
                status_updated = db.update_suggestion_status(suggestion_id, 'approved')
                if status_updated:
                    flash(f"Đã phê duyệt trực tiếp đề xuất #{suggestion_id} và tạo rule/template.", "success")
                else:
                    flash(f"Đã tạo rule/template cho đề xuất #{suggestion_id}, nhưng lỗi cập nhật trạng thái đề xuất.", "warning")
                return redirect(url_for('admin.view_suggestions'))
            else:
                approval_error = "Đã thêm template/variation nhưng thêm rule thất bại."
        else:
            approval_error = "Thêm template/variation mới thất bại (Template Ref có thể bị lỗi?)."

    except Exception as e:
        approval_error = f"Lỗi không mong muốn khi phê duyệt trực tiếp: {e}"
        print(f"Lỗi nghiêm trọng khi phê duyệt trực tiếp suggestion {suggestion_id}: {e}")
        print(traceback.format_exc())

    # Nếu có lỗi trong quá trình phê duyệt
    if approval_error:
        flash(f"Phê duyệt trực tiếp thất bại: {approval_error}", "error")

    return redirect(url_for('admin.view_suggestions'))

# --- === ROUTE DUYỆT TẤT CẢ ĐỀ XUẤT (SỬ DỤNG COMMAND QUEUE) === ---
@admin_bp.route('/suggestions/approve-all-start-job', methods=['POST'])
def start_approve_all_job():
    """Thêm lệnh yêu cầu chạy tác vụ duyệt tất cả suggestions vào queue."""
    command_type_to_add = 'approve_all_suggestions' # <<< Định nghĩa loại lệnh mới
    print(f"INFO: Received request to start task '{command_type_to_add}'.")

    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_suggestions'))
    # Tùy chọn: Kiểm tra xem hàm tác vụ có tồn tại không
    if not approve_all_suggestions_task:
         flash("Lỗi: Không tìm thấy hàm tác vụ nền 'approve_all_suggestions_task'.", "error")
         return redirect(url_for('admin.view_suggestions'))

    try:
        # Payload có thể rỗng vì tác vụ này không cần tham số cụ thể từ UI
        payload = {'source': 'approve_all_button'}

        # Thêm lệnh vào hàng đợi
        command_id = db.add_scheduler_command(
            command_type=command_type_to_add,
            payload=payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy tác vụ duyệt tất cả đề xuất. Scheduler sẽ xử lý (Command ID: {command_id}).", 'success')
        else:
             flash("Lỗi khi thêm yêu cầu vào hàng đợi CSDL.", "error")

    # Bỏ phần gọi live_scheduler.add_job trực tiếp và các except liên quan đến nó
    # except (ImportError, AttributeError) as ie: ...
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu duyệt tất cả: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn: {e}", "error")

    return redirect(url_for('admin.view_suggestions'))



# =============================================
# === CÁC ROUTE MỚI THÊM VÀO ===
# =============================================

# === Quản lý Tài khoản ===
@admin_bp.route('/accounts')
def view_accounts():
    title = "Quản lý Tài khoản"
    accounts = []
    pagination = None # <<< Biến phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            print(f"DEBUG (view_accounts): Requesting page {page}")

            # Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            accounts, total_items = db.get_all_accounts(page=page, per_page=PER_PAGE_ACCOUNTS)

            if accounts is None or total_items is None:
                 flash("Lỗi khi tải danh sách tài khoản từ CSDL.", "error")
                 accounts = []; total_items = 0
                 pagination = None
            else:
                 # Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_ACCOUNTS)
                     if page > total_pages and total_pages > 0: page = total_pages
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_ACCOUNTS, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else:
                     pagination = {'page': 1, 'per_page': PER_PAGE_ACCOUNTS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_accounts): Calculated pagination = {pagination}")

        except Exception as e:
            print(f"Lỗi nghiêm trọng load accounts: {e}")
            flash("Lỗi không mong muốn khi tải danh sách tài khoản.", "error")
            accounts = []; pagination = None

    # Truyền accounts (của trang hiện tại) và pagination vào template
    return render_template('admin_accounts.html',
                           title=title,
                           accounts=accounts,
                           pagination=pagination) # <<< Truyền pagination


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
    """Hiển thị danh sách Templates & Variations có bộ lọc và phân trang."""
    title="Quản lý Templates & Variations"
    templates_data = [] # Danh sách template cho trang hiện tại
    distinct_categories = [] # Danh sách category cho dropdown lọc
    active_filters = {} # Lưu các filter đang áp dụng
    pagination = None # Thông tin phân trang

    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # 1. Lấy tham số trang và bộ lọc từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            filter_ref = request.args.get('filter_ref', '').strip()
            filter_category = request.args.get('filter_category', '').strip()
            # Lưu lại các filter đang được dùng để truyền về template
            active_filters = {k.replace('filter_', ''): v for k, v in request.args.items() if v and k.startswith('filter_')}
            print(f"DEBUG (view_templates): Page={page}, Active Filters = {active_filters}")

            # 2. Gọi hàm DB để lấy dữ liệu đã lọc và phân trang
            # Hàm này trả về (list_items_page, total_items)
            templates_data, total_items = db.get_filtered_templates_with_details(
                filter_ref=filter_ref if filter_ref else None,
                filter_category=filter_category if filter_category else None,
                page=page,
                per_page=PER_PAGE_TEMPLATES
            )

            if templates_data is None or total_items is None:
                 flash("Lỗi khi tải danh sách template từ CSDL.", "error")
                 templates_data = []; total_items = 0
                 pagination = None # Lỗi DB -> không có phân trang
                 print("DEBUG (view_templates): DB query failed, pagination set to None.")
            else:
                 # 3. Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_TEMPLATES)
                     if page > total_pages and total_pages > 0: page = total_pages # Đảm bảo page hợp lệ
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_TEMPLATES, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else: # total_items = 0
                     pagination = {'page': 1, 'per_page': PER_PAGE_TEMPLATES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_templates): Calculated pagination = {pagination}")

            # 4. Lấy danh sách category duy nhất cho dropdown lọc
            distinct_categories = db.get_distinct_template_categories() or []
            print(f"DEBUG (view_templates): Fetched {len(distinct_categories)} distinct categories.")

        except Exception as e:
            print(f"Lỗi nghiêm trọng load templates page data: {e}")
            flash("Lỗi không mong muốn khi tải danh sách template.", "error")
            templates_data = []; distinct_categories = []; pagination = None
            print(f"DEBUG (view_templates): Exception occurred, pagination set to None.")

    # 5. Render template với đầy đủ dữ liệu
    print(f"DEBUG (view_templates): Final pagination object being passed = {pagination}")
    return render_template('admin_templates.html',
                           title=title,
                           templates=templates_data,              # <<< Danh sách template của trang này
                           distinct_categories=distinct_categories, # <<< Danh sách category cho filter
                           filters=active_filters,                # <<< Filter đang áp dụng
                           pagination=pagination) 


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
    conn = db.get_db_connection()
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
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_templates'))

    # Lấy details cho GET và để kiểm tra sự tồn tại cho POST
    template_details = db.get_template_ref_details(template_ref)
    if not template_details:
        flash(f"Không tìm thấy template ref '{template_ref}'.", "error")
        return redirect(url_for('admin.view_templates'))

    # --- Xử lý POST Request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu mới từ form
            new_description = request.form.get('description', '').strip()
            new_category = request.form.get('category', '').strip()

            # Validate đơn giản (ví dụ: category không nên quá dài)
            if len(new_category) > 50:
                 flash("Tên Category quá dài (tối đa 50 ký tự).", "warning")
                 # Cần lấy lại distinct_categories để render lại form lỗi
                 distinct_categories = db.get_distinct_template_categories() or []
                 return render_template('admin_edit_template_details.html',
                                        title=f"Sửa Chi tiết Template '{template_ref}' (Lỗi)",
                                        template=template_details,
                                        distinct_categories=distinct_categories,
                                        current_data=request.form), 400 # Giữ lại dữ liệu đã nhập

            # Gọi hàm DB để cập nhật
            success = db.update_template_details(
                template_ref=template_ref,
                description=new_description or None, # Chuyển rỗng thành None nếu DB cho phép NULL
                category=new_category or None      # Chuyển rỗng thành None nếu DB cho phép NULL
            )

            if success:
                flash(f"Đã cập nhật chi tiết cho template '{template_ref}' thành công!", 'success')
                return redirect(url_for('admin.view_templates')) # <<< Redirect về trang danh sách
            else:
                # Lỗi này ít xảy ra nếu template_ref tồn tại
                flash(f"Cập nhật chi tiết cho template '{template_ref}' thất bại.", 'error')
                # Render lại form với dữ liệu người dùng vừa nhập
                distinct_categories = db.get_distinct_template_categories() or []
                return render_template('admin_edit_template_details.html',
                                       title=f"Sửa Chi tiết Template '{template_ref}'",
                                       template=template_details,
                                       distinct_categories=distinct_categories,
                                       current_data=request.form) # Hiển thị lại lỗi

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật template details {template_ref}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật: {e}", "error")
            # Render lại form với dữ liệu gốc ban đầu khi có lỗi nghiêm trọng
            distinct_categories = db.get_distinct_template_categories() or []
            return render_template('admin_edit_template_details.html',
                                   title=f"Sửa Chi tiết Template '{template_ref}'",
                                   template=template_details, # Dùng data gốc
                                   distinct_categories=distinct_categories)


    # --- Xử lý GET Request ---
    # Chỉ cần lấy dữ liệu và hiển thị form
    distinct_categories = []
    try:
        # Lấy danh sách category cho datalist/dropdown
        distinct_categories = db.get_distinct_template_categories() or []
    except Exception as e:
         flash("Lỗi khi tải danh sách category cho form.", "warning")

    # template_details đã được lấy ở đầu hàm
    return render_template('admin_edit_template_details.html',
                           title=f"Sửa Chi tiết Template '{template_ref}'",
                           template=template_details, # Dữ liệu hiện tại của template
                           distinct_categories=distinct_categories)


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

@admin_bp.route('/strategies/control') # <<< Đổi URL
def view_strategies_control(): # <<< Đổi tên hàm
    """Hiển thị danh sách các chiến lược loại 'control'."""
    title = "Quản lý Chiến lược Điều khiển" # <<< Đổi Title
    control_strategies = []
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Gọi hàm DB với bộ lọc type='control'
            control_strategies = db.get_all_strategies(strategy_type_filter='control')
            if control_strategies is None:
                flash("Lỗi khi tải danh sách chiến lược điều khiển.", "error")
                control_strategies = []
        except Exception as e:
            print(f"Lỗi load control strategies: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            control_strategies = []
    # Render template đã ĐỔI TÊN
    return render_template('admin_strategies_control.html',
                           title=title,
                           strategies=control_strategies)



@admin_bp.route('/strategies/<strategy_id>/stages-language')
def view_strategy_stages_language(strategy_id):
    """Hiển thị stages và language transitions cho một Language Strategy."""
    strategy = None
    strategy_stages_list = []
    transitions_list = []
    all_templates = [] # Cần cho nút Add Transition

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            strategy = db.get_strategy_details(strategy_id)
            print(f"DEBUG (view_strategy_stages_language): Fetched strategy details for '{strategy_id}': {strategy}")
            # <<< Kiểm tra strategy tồn tại và đúng type 'language' >>>
            if strategy is None or strategy.get('strategy_type') != 'language':
                flash(f"Không tìm thấy Language Strategy ID {strategy_id} hoặc loại không đúng.", "warning")
                return redirect(url_for('admin.view_strategies_language')) # Redirect về list language

            strategy_stages_list = db.get_stages_for_strategy(strategy_id) or []
            # Hàm này lấy tất cả transition thô, template sẽ lọc ra cái cần hiển thị
            transitions_list = db.get_strategy_action_sequence(strategy_id) or []
            all_templates = db.get_all_template_refs() or [] # Lấy templates cho nút Add

        except Exception as e:
            print(f"Lỗi tải stages/transitions cho language strategy {strategy_id}: {e}")
            flash("Lỗi tải chi tiết chiến lược hội thoại.", "error")
            # Reset về list rỗng khi lỗi
            strategy = strategy or {'strategy_id': strategy_id, 'name': 'Lỗi tải tên'} # Để tránh lỗi template
            strategy_stages_list = []
            transitions_list = []
            all_templates = []

    # <<< Render template MỚI: admin_strategy_stages_language.html >>>
    return render_template('admin_strategy_stages_language.html',
                           title=f"Language Stages & Transitions cho '{strategy.get('name', strategy_id)}'",
                           strategy=strategy,
                           strategy_stages=strategy_stages_list,
                           transitions=transitions_list, # Truyền list transitions thô
                           all_templates=all_templates) # Truyền cho nút Add

# --- Đảm bảo route cho CONTROL đã được đổi tên đúng ---
@admin_bp.route('/strategies/<strategy_id>/stages-control')
def view_strategy_stages_control(strategy_id):
    # ... (Code của hàm này giữ nguyên như đã cung cấp trước đó) ...
    strategy = None
    strategy_stages_list = []
    transitions_list = []
    all_macros = []
    if not db: flash("Lỗi DB.", "error")
    else:
        try:
            strategy = db.get_strategy_details(strategy_id)
            if strategy is None or strategy.get('strategy_type') != 'control':
                flash(f"Không tìm thấy Control Strategy ID {strategy_id} hoặc loại không đúng.", "warning")
                return redirect(url_for('admin.view_strategies_control'))
            strategy_stages_list = db.get_stages_for_strategy(strategy_id) or []
            transitions_list = db.get_strategy_action_sequence(strategy_id) or []
            all_macros = db.get_all_macro_definitions() or []
        except Exception as e:
            print(f"Lỗi tải stages/transitions cho control strategy {strategy_id}: {e}")
            flash("Lỗi tải chi tiết chiến lược điều khiển.", "error")
            strategy = strategy or {'strategy_id': strategy_id, 'name': 'Lỗi tải tên'}
            strategy_stages_list = []; transitions_list = []; all_macros = []
    print(f"DEBUG Route (view_strategy_stages_control): Passing transitions to template: {transitions_list}")
    return render_template('admin_strategy_stages_control.html', # <<< Đảm bảo tên đúng
                           title=f"Control Stages & Transitions cho '{strategy.get('name', strategy_id)}'",
                           strategy=strategy,
                           strategy_stages=strategy_stages_list,
                           transitions=transitions_list,
                           all_macros=all_macros)

@admin_bp.route('/stages/add', methods=['GET', 'POST'])
def add_stage():
    """Hiển thị form thêm stage và xử lý việc thêm stage mới."""
    # Lấy strategy_id từ query param của URL (ví dụ: /admin/stages/add?strategy_id=my_strategy)
    strategy_id = request.args.get('strategy_id')

    # --- Kiểm tra các điều kiện ban đầu ---
    if not strategy_id:
        flash("Lỗi: Cần cung cấp strategy_id trong URL để thêm stage.", "error")
        # Không biết quay về đâu, tạm về dashboard
        return redirect(url_for('admin.index'))

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.index')) # Về Dashboard nếu lỗi DB

    # --- Lấy thông tin strategy gốc để xác định loại và tạo link Hủy ---
    strategy_details = None
    strategy_type = 'language' # Mặc định nếu không tìm thấy strategy
    redirect_endpoint = 'admin.view_strategy_stages_language' # Endpoint redirect mặc định sau khi POST thành công
    cancel_url = url_for('admin.view_strategies_language') # URL mặc định cho nút Hủy

    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if strategy_details:
            strategy_type = strategy_details.get('strategy_type', 'language')
            redirect_endpoint = 'admin.view_strategy_stages_language' if strategy_type == 'language' else 'admin.view_strategy_stages_control'
            # Tạo URL chính xác cho nút Hủy (trỏ về trang chi tiết strategy gốc)
            cancel_url = url_for(redirect_endpoint, strategy_id=strategy_id)
        else:
             # Strategy không tồn tại trong DB
             flash(f"Lỗi: Không tìm thấy chiến lược với ID '{strategy_id}'.", "error")
             return redirect(url_for('admin.view_strategies_language')) # Redirect về list language làm mặc định

    except Exception as e:
        print(f"Lỗi khi lấy strategy details trong add_stage (GET): {e}")
        flash("Lỗi khi đọc thông tin strategy gốc.", "error")
        # Nếu lỗi nặng, có thể quay về dashboard
        # return redirect(url_for('admin.index'))
        # Hoặc vẫn tiếp tục với cancel_url mặc định

    # --- Xử lý POST request (Khi người dùng submit form) ---
    if request.method == 'POST':
        # Lấy dữ liệu từ form
        stage_id = request.form.get('stage_id', '').strip()
        description = request.form.get('description', '').strip()
        order_str = request.form.get('stage_order', '0').strip()
        identifying_elements_str = request.form.get('identifying_elements', '{}').strip() # Lấy cả trường này
        # Lấy lại strategy_id từ hidden input để đối chiếu
        form_strategy_id = request.form.get('strategy_id')

        # --- Validate dữ liệu ---
        errors = []
        if not stage_id: errors.append("Stage ID là bắt buộc.")
        if not form_strategy_id: errors.append("Lỗi: Thiếu Strategy ID trong form.")
        if form_strategy_id != strategy_id: errors.append("Lỗi không khớp Strategy ID.")
        try:
            order = int(order_str)
        except ValueError:
            errors.append("Stage Order phải là số nguyên.")
        # Validate JSON cho identifying_elements nếu có nhập (khác '{}' và không rỗng)
        if identifying_elements_str and identifying_elements_str.strip() != '{}':
            try:
                json.loads(identifying_elements_str)
            except json.JSONDecodeError:
                errors.append("Identifying Elements không phải là định dạng JSON hợp lệ.")
        else:
            # Nếu rỗng hoặc chỉ có '{}', chuẩn hóa thành None để lưu NULL vào DB
             identifying_elements_str = None


        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # Render lại form với lỗi và dữ liệu người dùng đã nhập
            return render_template('admin_add_stage.html',
                                   title=f"Thêm Stage cho {strategy_id} (Lỗi)",
                                   strategy_id=strategy_id,
                                   cancel_url=cancel_url, # Truyền URL Hủy đúng
                                   current_data=request.form), 400 # Giữ lại dữ liệu form

        # --- Gọi hàm DB để thêm stage ---
        try:
            # Giả sử hàm add_new_stage nhận đủ các tham số này và trả về (success, error_msg)
            success, error_msg = db.add_new_stage(
                stage_id=stage_id,
                strategy_id=form_strategy_id,
                description=description,
                stage_order=order,
                identifying_elements_str=identifying_elements_str # Truyền chuỗi JSON (hoặc None)
            )

            if success:
                flash(f"Thêm stage '{stage_id}' vào chiến lược '{form_strategy_id}' thành công!", 'success')
                # <<< Redirect về trang chi tiết tương ứng >>>
                print(f"DEBUG (add_stage): Redirecting to '{redirect_endpoint}' with strategy_id '{form_strategy_id}'")
                return redirect(url_for(redirect_endpoint, strategy_id=form_strategy_id))
            else:
                flash(f"Thêm stage '{stage_id}' thất bại: {error_msg or '(ID đã tồn tại cho strategy này?)'}", 'error')
                # Render lại form với lỗi DB
                return render_template('admin_add_stage.html',
                                       title=f"Thêm Stage cho {strategy_id} (Lỗi DB)",
                                       strategy_id=strategy_id,
                                       cancel_url=cancel_url,
                                       current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi gọi db.add_new_stage: {e}")
            flash(f"Lỗi không mong muốn khi thêm stage: {e}", "error")
            return render_template('admin_add_stage.html',
                                   title=f"Thêm Stage cho {strategy_id} (Lỗi)",
                                   strategy_id=strategy_id,
                                   cancel_url=cancel_url,
                                   current_data=request.form)

    # --- Xử lý GET request (Hiển thị form lần đầu) ---
    # Truyền strategy_id và cancel_url vào template
    return render_template('admin_add_stage.html',
                           title=f"Thêm Stage Mới cho Strategy {strategy_id}",
                           strategy_id=strategy_id,
                           cancel_url=cancel_url)

@admin_bp.route('/stages/<stage_id>/edit', methods=['GET', 'POST'])
def edit_stage(stage_id):
    """Sửa description, order, và identifying_elements của stage."""
    if not db:
        flash("Lỗi DB.", "error")
        return redirect(url_for('admin.index')) # Về Dashboard nếu lỗi DB

    # --- Lấy thông tin stage và strategy ngay từ đầu ---
    stage = None
    strategy_id_redirect = None
    strategy_details = None
    strategy_type = 'language' # Default
    redirect_endpoint = 'admin.view_strategy_stages_language' # Default
    # <<< Đặt giá trị mặc định an toàn cho cancel_url >>>
    cancel_url = url_for('admin.index') # Default về Dashboard nếu có lỗi nghiêm trọng

    try:
        stage = db.get_stage_details(stage_id) # Hàm này cần trả về dict có strategy_id
        if not stage:
            flash(f"Không tìm thấy stage ID {stage_id}.", "error")
            return redirect(url_for('admin.index')) # Về Dashboard nếu không tìm thấy stage

        strategy_id_redirect = stage.get('strategy_id')
        if strategy_id_redirect:
            strategy_details = db.get_strategy_details(strategy_id_redirect)
            if strategy_details:
                strategy_type = strategy_details.get('strategy_type', 'language')
                redirect_endpoint = 'admin.view_strategy_stages_language' if strategy_type == 'language' else 'admin.view_strategy_stages_control'
                # <<< TÍNH TOÁN cancel_url CHÍNH XÁC Ở ĐÂY >>>
                cancel_url = url_for(redirect_endpoint, strategy_id=strategy_id_redirect)
            else:
                # Không tìm thấy strategy gốc, đặt cancel về list chung
                flash(f"Cảnh báo: Không tìm thấy strategy gốc ID '{strategy_id_redirect}' của stage này.", "warning")
                cancel_url = url_for('admin.view_strategies_control') if strategy_type=='control' else url_for('admin.view_strategies_language')
        else:
            # Stage không có strategy_id? (Lỗi dữ liệu) - Đặt cancel về list chung
             flash(f"Cảnh báo: Stage '{stage_id}' không có strategy_id liên kết.", "warning")
             cancel_url = url_for('admin.view_strategies_language') # Tạm về language list

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi lấy thông tin stage/strategy: {e}")
        flash("Lỗi khi đọc thông tin stage/strategy gốc.", "error")
        return redirect(url_for('admin.index')) # Redirect về index khi có lỗi nghiêm trọng

    # --- Đã có stage và cancel_url hợp lệ ở đây ---
    title = f"Sửa Stage '{stage_id}'"

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        description = request.form.get('description')
        order_str = request.form.get('stage_order', '0')
        identifying_elements_str = request.form.get('identifying_elements', '{}')

        # --- Validate dữ liệu ---
        errors = []
        try:
            order = int(order_str)
        except ValueError:
            errors.append("Stage Order phải là số nguyên.")

        # Validate JSON Identifying Elements
        validated_identifying_elements_str = '{}' # Default
        if identifying_elements_str and identifying_elements_str.strip() and identifying_elements_str != '{}':
            try:
                json.loads(identifying_elements_str) # Chỉ validate
                validated_identifying_elements_str = identifying_elements_str # Giữ lại nếu hợp lệ
            except json.JSONDecodeError:
                errors.append("Identifying Elements không phải là định dạng JSON hợp lệ. Vui lòng nhập đúng định dạng hoặc để trống/ {}.")
        elif identifying_elements_str is not None and (not identifying_elements_str.strip() or identifying_elements_str == '{}'):
             validated_identifying_elements_str = None # Lưu NULL nếu rỗng hoặc chỉ {}

        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # <<< Luôn truyền cancel_url khi render lại >>>
            return render_template('admin_edit_stage.html', title=title + " (Lỗi)",
                                   stage=stage, # stage gốc đã lấy ở trên
                                   cancel_url=cancel_url,
                                   current_data=request.form), 400

        # --- Gọi hàm DB để cập nhật ---
        try:
            # Hàm update_stage nhận identifying_elements_str (có thể là None)
            success, error_msg = db.update_stage(stage_id, description, order, validated_identifying_elements_str)

            if success:
                flash(f"Cập nhật stage '{stage_id}' thành công!", 'success')
                # Redirect về trang chi tiết strategy gốc dùng cancel_url đã tính
                return redirect(cancel_url)
            else:
                flash(f"Cập nhật stage '{stage_id}' thất bại: {error_msg or 'Không có gì thay đổi?'}", 'error')
                # <<< Luôn truyền cancel_url khi render lại >>>
                return render_template('admin_edit_stage.html', title=title + " (Lỗi DB)",
                                       stage=stage, # stage gốc
                                       cancel_url=cancel_url,
                                       current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi sửa stage {stage_id}: {e}")
            flash(f"Lỗi không mong muốn khi sửa stage: {e}", "error")
            # <<< Luôn truyền cancel_url khi render lại >>>
            return render_template('admin_edit_stage.html', title=title,
                                   stage=stage, # stage gốc
                                   cancel_url=cancel_url,
                                   current_data=request.form)

    # --- Xử lý GET request ---
    # Hiển thị form lần đầu
    # <<< Luôn truyền cancel_url vào template >>>
    return render_template('admin_edit_stage.html', title=title, stage=stage, cancel_url=cancel_url)

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

@admin_bp.route('/strategies/add', methods=['GET', 'POST'])
def add_strategy():
    title="Thêm Chiến lược Mới"
    # Lấy type từ URL để biết đang thêm loại nào
    strategy_type_from_url = request.args.get('type', 'language') # Mặc định là language
    if strategy_type_from_url not in ['language', 'control']:
        strategy_type_from_url = 'language' # Đảm bảo giá trị hợp lệ

    # Lấy stages cho dropdown initial_stage
    stages = []
    try: stages = db.get_all_stages() or []
    except Exception: flash("Lỗi tải stages", "error")

    if request.method == 'POST':
        strategy_id = request.form.get('strategy_id')
        name = request.form.get('name')
        description = request.form.get('description')
        initial_stage_id = request.form.get('initial_stage_id')
        # <<< Lấy strategy_type từ hidden input >>>
        strategy_type = request.form.get('strategy_type')

        # Validate
        if not strategy_id or not name or not initial_stage_id or not strategy_type:
            flash("Strategy ID, Name, Initial Stage ID, và Strategy Type (ẩn) là bắt buộc.", "warning")
            # <<< Bỏ valid_types, truyền strategy_type >>>
            return render_template('admin_add_strategy.html', title=title, stages=stages,
                                   strategy_type=strategy_type_from_url, # Dùng type từ URL cho hidden input khi lỗi
                                   current_data=request.form), 400
        if strategy_type not in ['language', 'control']:
             flash("Strategy Type (ẩn) không hợp lệ.", "warning")
             return render_template('admin_add_strategy.html', title=title, stages=stages,
                                    strategy_type=strategy_type_from_url,
                                    current_data=request.form), 400

        # Gọi hàm DB đã sửa (vẫn nhận strategy_type)
        success, error_msg = db.add_new_strategy(strategy_id, name, description, initial_stage_id, strategy_type)

        if success:
            flash('Thêm chiến lược thành công!', 'success')
            # Redirect đến trang danh sách tương ứng
            if strategy_type == 'control':
                 return redirect(url_for('admin.view_strategies_control'))
            else:
                 return redirect(url_for('admin.view_strategies_language'))
        else:
            flash(f'Thêm chiến lược thất bại: {error_msg or "Lỗi."}', 'error')
            # <<< Bỏ valid_types, truyền strategy_type >>>
            return render_template('admin_add_strategy.html', title=title, stages=stages,
                                   strategy_type=strategy_type, # Giữ type đã submit
                                   current_data=request.form)

    # GET request
    # <<< Bỏ valid_types, truyền strategy_type vào template >>>
    return render_template('admin_add_strategy.html', title=f"Thêm {strategy_type_from_url.capitalize()} Strategy Mới",
                           stages=stages, strategy_type=strategy_type_from_url)

@admin_bp.route('/strategies/<strategy_id>/edit', methods=['GET', 'POST'])
def edit_strategy(strategy_id):
    # Lấy strategy details (bao gồm cả strategy_type)
    strategy = db.get_strategy_details(strategy_id)
    if not strategy:
        flash(f"Không tìm thấy strategy ID {strategy_id}.", "error")
        # Cố gắng redirect thông minh hơn nếu biết type, nếu không về language
        # Tuy nhiên ở đây chưa biết type, nên tạm về language list
        return redirect(url_for('admin.view_strategies_language'))

    # Lấy stages cho dropdown
    stages = []
    try: stages = db.get_all_stages() or []
    except Exception: flash("Lỗi tải stages", "error")

    # Xác định type để redirect sau khi POST thành công
    current_strategy_type = strategy.get('strategy_type', 'language')

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        initial_stage_id = request.form.get('initial_stage_id')
        # <<< KHÔNG lấy strategy_type từ form nữa >>>

        # Validate
        if not name or not initial_stage_id:
             flash("Name và Initial Stage ID là bắt buộc.", "warning")
             # <<< Bỏ valid_types khỏi render_template >>>
             return render_template('admin_edit_strategy.html', title=f"Sửa Chiến lược {strategy_id} (Lỗi)",
                                    strategy=strategy, stages=stages,
                                    current_data=request.form), 400

        # <<< Gọi hàm db.update_strategy đã sửa (KHÔNG còn tham số strategy_type) >>>
        success, error_msg = db.update_strategy(strategy_id, name, description, initial_stage_id)

        if success:
            flash('Cập nhật chiến lược thành công!', 'success')
             # <<< Redirect đến trang danh sách tương ứng dựa trên type đã lấy lúc GET >>>
            if current_strategy_type == 'control':
                 return redirect(url_for('admin.view_strategies_control'))
            else:
                 return redirect(url_for('admin.view_strategies_language'))
        else:
            flash(f'Cập nhật chiến lược thất bại: {error_msg or "Lỗi."}', 'error')
            # <<< Bỏ valid_types khỏi render_template >>>
            return render_template('admin_edit_strategy.html', title=f"Sửa Chiến lược {strategy_id} (Lỗi DB)",
                                   strategy=strategy, stages=stages,
                                   current_data=request.form)

    # GET request
    # <<< Bỏ valid_types khỏi render_template >>>
    return render_template('admin_edit_strategy.html', title=f"Sửa Chiến lược {strategy_id}",
                           strategy=strategy, stages=stages)
# --- Sửa Route Xóa Strategy ---
@admin_bp.route('/strategies/<strategy_id>/delete', methods=['POST'])
def delete_strategy(strategy_id):
    """Xử lý xóa chiến lược và redirect về đúng trang danh sách."""
    # Lấy type trước khi xóa để redirect đúng
    strategy_details = db.get_strategy_details(strategy_id)
    strategy_type_redirect = strategy_details.get('strategy_type') if strategy_details else 'language' # Default redirect về language

    try:
        success, error_msg = db.delete_strategy(strategy_id) # Giả sử hàm delete trả về lỗi
        if success:
            flash(f"Đã xóa chiến lược ID {strategy_id}.", 'success')
        else:
            flash(f"Xóa chiến lược ID {strategy_id} thất bại: {error_msg or 'ID không tồn tại?'}", 'error')
    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa strategy {strategy_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa chiến lược: {e}", "error")

    # Redirect về trang danh sách tương ứng
    if strategy_type_redirect == 'control':
         return redirect(url_for('admin.view_strategies_control'))
    else:
         return redirect(url_for('admin.view_strategies_language'))
# --- Route MỚI cho Danh sách Chiến lược Hội thoại ---
@admin_bp.route('/strategies/language')
def view_strategies_language():
    """Hiển thị danh sách các chiến lược loại 'language'."""
    title = "Quản lý Chiến lược Hội thoại"
    language_strategies = []
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Gọi hàm DB với bộ lọc type='language'
            language_strategies = db.get_all_strategies(strategy_type_filter='language')
            if language_strategies is None:
                flash("Lỗi khi tải danh sách chiến lược hội thoại.", "error")
                language_strategies = []
        except Exception as e:
            print(f"Lỗi load language strategies: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            language_strategies = []
    # Render template MỚI
    return render_template('admin_strategies_language.html',
                           title=title,
                           strategies=language_strategies) # Đổi tên biến truyền vào thành 'strategies'

# --- ĐỔI TÊN Route và Hàm cho Danh sách Chiến lược Điều khiển ---

@admin_bp.route('/ai-playground', methods=['GET', 'POST'])
def ai_playground():
    """Trang tiện ích để chat trực tiếp với AI."""
    personas = []
    ai_response = None
    user_prompt = ""
    selected_persona_id = ""
    error_message = None

    # Luôn lấy danh sách persona cho dropdown
    try:
        personas = db.get_all_personas() or []
    except Exception as e:
        print(f"Lỗi khi lấy danh sách personas cho playground: {e}")
        flash("Không thể tải danh sách AI Personas.", "error")
        personas = []

    if request.method == 'POST':
        user_prompt = request.form.get('user_prompt', '').strip()
        selected_persona_id = request.form.get('persona_id', '').strip()
        persona_id_to_use = selected_persona_id if selected_persona_id else None # Dùng None nếu chọn default

        if not user_prompt:
            flash("Vui lòng nhập yêu cầu/prompt.", "warning")
        else:
            try:
                # Gọi hàm AI service tổng quát
                ai_response_text, status = ai_service.call_generative_model(
                    prompt=user_prompt,
                    persona_id=persona_id_to_use
                )
                if status == 'success':
                    ai_response = ai_response_text
                else:
                    error_message = f"AI Error: {status}"
                    if ai_response_text: error_message += f"\nDetails: {ai_response_text}"
                    ai_response = None
                    flash(f"AI không thể xử lý yêu cầu (Status: {status}).", "error")

            except Exception as e:
                print(f"Lỗi nghiêm trọng khi gọi AI trong playground: {e}")
                flash(f"Lỗi không mong muốn khi gọi AI: {e}", "error")
                error_message = f"Server Error: {e}"
                ai_response = None

    # Render template cho cả GET và POST
    return render_template('admin_ai_playground.html',
                           title="AI Playground",
                           personas=personas,
                           user_prompt=user_prompt,
                           ai_response=ai_response,
                           error_message=error_message,
                           selected_persona_id=selected_persona_id)

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

@admin_bp.route('/_get_templates') # Route nội bộ (ví dụ)
def get_templates_for_select():
     # Hàm này có thể được gọi bằng AJAX để cập nhật dropdown
     templates = db.get_all_template_refs()
     # Trả về JSON
     from flask import jsonify
     return jsonify(templates or [])

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
    """Hiển thị danh sách các AI Personas với phân trang."""
    title = "Quản lý AI Personas"
    personas = []
    pagination = None # <<< Biến phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            print(f"DEBUG (view_personas): Requesting page {page}")

            # Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            personas, total_items = db.get_all_personas(page=page, per_page=PER_PAGE_PERSONAS)

            if personas is None or total_items is None:
                 flash("Lỗi khi tải danh sách AI Personas từ CSDL.", "error")
                 personas = []; total_items = 0
                 pagination = None
            else:
                 # Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_PERSONAS)
                     if page > total_pages and total_pages > 0: page = total_pages
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_PERSONAS, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else:
                     pagination = {'page': 1, 'per_page': PER_PAGE_PERSONAS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_personas): Calculated pagination = {pagination}")

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load personas: {e}")
            flash("Lỗi không mong muốn khi tải AI Personas.", "error")
            personas = []; pagination = None

    # Truyền personas (của trang hiện tại) và pagination vào template
    return render_template('admin_personas.html',
                           title=title,
                           personas=personas,
                           pagination=pagination) 


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
    """Hiển thị danh sách các Prompt Templates với phân trang."""
    title = "Quản lý Prompt Templates"
    templates = []
    pagination = None # <<< Biến phân trang

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy page từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            print(f"DEBUG (view_prompt_templates): Requesting page {page}")

            # Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            templates, total_items = db.get_all_prompt_templates(page=page, per_page=PER_PAGE_PROMPT_TEMPLATES)

            if templates is None or total_items is None:
                 flash("Lỗi khi tải danh sách Prompt Templates từ CSDL.", "error")
                 templates = []; total_items = 0
                 pagination = None
            else:
                 # Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_PROMPT_TEMPLATES)
                     if page > total_pages and total_pages > 0: page = total_pages
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_PROMPT_TEMPLATES, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else:
                     pagination = {'page': 1, 'per_page': PER_PAGE_PROMPT_TEMPLATES, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}
                 print(f"DEBUG (view_prompt_templates): Calculated pagination = {pagination}")

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load prompt templates: {e}")
            flash("Lỗi không mong muốn khi tải Prompt Templates.", "error")
            templates = []; pagination = None

    # Truyền templates (của trang hiện tại) và pagination vào template
    return render_template('admin_prompt_templates.html',
                           title=title,
                           templates=templates,
                           pagination=pagination) # <<< Truyền pagination


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



@admin_bp.route('/scheduled-jobs')
def view_scheduled_jobs():
    """
    Hiển thị trang quản lý cấu hình job định kỳ và trạng thái live của chúng.
    """
    title = "Quản lý Cấu hình Tác vụ Định Kỳ"
    db_jobs_config = []   # Danh sách cấu hình từ DB
    live_job_statuses = [] # Danh sách trạng thái live để hiển thị ở bảng 2
    pending_counts = {}   # Đếm pending cho suggestion_job

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # 1. Lấy danh sách cấu hình từ bảng scheduled_jobs
            db_jobs_config = db.get_all_job_configs() or []
            if db_jobs_config is None: # Phân biệt lỗi DB và không có job
                 flash("Lỗi khi tải danh sách cấu hình jobs từ Database.", "error")
                 db_jobs_config = [] # Gán list rỗng nếu lỗi

            # 2. Lấy thời gian chạy thực tế từ bảng apscheduler_jobs
            live_run_times = _get_live_next_run_times() # Dùng lại hàm helper đã có

            # 3. Tạo danh sách trạng thái live cho Bảng 2
            server_tz = _get_configured_timezone() # Dùng hàm helper lấy timezone

            # Chỉ xử lý trạng thái live cho các job có trong cấu hình
            configured_job_ids = {job['job_id'] for job in db_jobs_config}

            for job_id, next_run_timestamp in live_run_times.items():
                # Chỉ quan tâm đến job ID có trong cấu hình
                if job_id in configured_job_ids:
                    status_info = {'id': job_id, 'next_run_time_str': 'N/A', 'status': 'Unknown'}
                    if next_run_timestamp is not None:
                        try:
                            utc_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
                            local_dt = utc_dt.astimezone(server_tz)
                            status_info['next_run_time_str'] = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
                            status_info['status'] = 'Scheduled' # Hoặc 'Running' nếu có thể xác định
                        except Exception as fmt_err:
                            print(f"Error formatting live timestamp for {job_id}: {fmt_err}")
                            status_info['next_run_time_str'] = 'Lỗi Format'
                    else:
                        # Timestamp là None có nghĩa là job đang PAUSED trong scheduler
                        status_info['next_run_time_str'] = '---'
                        status_info['status'] = 'Paused'
                    live_job_statuses.append(status_info)

            # Thêm các job có config nhưng không có trong apscheduler_jobs (Not Scheduled)
            live_job_ids_found = {s['id'] for s in live_job_statuses}
            for cfg_job in db_jobs_config:
                 cfg_job_id = cfg_job['job_id']
                 if cfg_job_id not in live_job_ids_found:
                      live_job_statuses.append({
                           'id': cfg_job_id,
                           'next_run_time_str': '---',
                           'status': 'Not Scheduled' if not cfg_job.get('is_enabled') else 'Error/Not Found'
                      })

            # Sắp xếp danh sách trạng thái live theo ID (tùy chọn)
            live_job_statuses.sort(key=lambda x: x['id'])


            # 4. Logic đếm pending cho suggestion_job (giữ nguyên và đảm bảo đúng)
            for job_conf in db_jobs_config:
                if job_conf.get('job_id') == 'suggestion_job':
                    try:
                        last_id = db.get_task_state('suggestion_job') or 0
                        # Đảm bảo dùng đúng filter bao gồm cả sim status
                        status_filter = current_app.config.get(
                            'STATUS_TO_ANALYZE_SUGGEST',
                            ['success_ai', 'success_ai_sim_A', 'success_ai_sim_B'] # Default đúng
                        )
                        count = db.get_pending_suggestion_interaction_count(last_id, status_filter)
                        pending_counts['suggestion_job'] = count if count is not None else 'Lỗi'
                    except Exception as count_err:
                        print(f"Lỗi khi đếm pending items cho suggestion_job: {count_err}")
                        pending_counts['suggestion_job'] = 'Lỗi'
                    break # Chỉ cần đếm 1 lần

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi tải dữ liệu jobs: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu trang.", "error")
            db_jobs_config, live_job_statuses = [], [] # Reset về rỗng khi lỗi

    # Render template, truyền cả hai danh sách
    return render_template('admin_scheduled_jobs.html',
                           title=title,
                           jobs_config=db_jobs_config,       # <<< Danh sách cấu hình
                           live_statuses=live_job_statuses, # <<< Danh sách trạng thái live
                           pending_counts=pending_counts)   # <<< Số lượng chờ xử lý

@admin_bp.route('/scheduled-jobs/add', methods=['GET', 'POST'])
def add_scheduled_job():
    """Chỉ thêm cấu hình Job mới vào DB."""
    title = "Thêm Tác vụ Nền Mới"
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.index'))

    if request.method == 'POST':
        # Lấy dữ liệu từ form
        job_id = request.form.get('job_id', '').strip()
        function_path = request.form.get('job_function_path', '').strip()
        trigger_type = request.form.get('trigger_type', '').strip()
        trigger_args_str = request.form.get('trigger_args', '{}').strip()
        is_enabled_str = request.form.get('is_enabled')
        is_enabled = True if is_enabled_str == 'on' else False
        description = request.form.get('description', '').strip()

        # Validate Input (giữ nguyên logic validate)
        error = False
        error_msg = []
        if not job_id: error_msg.append("Job ID là bắt buộc.")
        if not function_path: error_msg.append("Function Path là bắt buộc.")
        if not trigger_type or trigger_type not in TRIGGER_TYPES: error_msg.append("Trigger Type không hợp lệ.")
        if error_msg: # Nếu có lỗi validation
            for msg in error_msg: flash(msg, "warning")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ (Lỗi)",
                                   trigger_types=TRIGGER_TYPES,
                                   available_tasks=AVAILABLE_SCHEDULED_TASKS, # <<< Truyền cả khi lỗi POST
                                   current_data=request.form), 400
        try: # Validate JSON và kiểu số
            if not trigger_args_str: trigger_args_str = '{}'
            trigger_args_dict = json.loads(trigger_args_str)
            if not isinstance(trigger_args_dict, dict): raise ValueError("phải là JSON object.")
            numeric_keys = ['weeks', 'days', 'hours', 'minutes', 'seconds', 'jitter', 'year', 'month', 'day', 'week', 'hour', 'minute', 'second']
            args_to_check = trigger_args_dict.copy()
            for key in numeric_keys:
                if key in args_to_check and isinstance(args_to_check[key], str):
                    value_str = args_to_check[key].strip()
                    if not value_str: del trigger_args_dict[key]; continue
                    if '.' in value_str: _ = float(value_str) # Chỉ kiểm tra convert được không
                    else: _ = int(value_str)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
             error_msg.append(f"Trigger Args không hợp lệ: {e}")

        if not error_msg: # Validate function path nếu các lỗi trước chưa xảy ra
            try:
                 module_path, func_name = function_path.rsplit('.', 1)
                 module = importlib.import_module(module_path)
                 func = getattr(module, func_name)
                 if not callable(func): raise AttributeError("Path không trỏ đến hàm.")
            except (ValueError, ImportError, AttributeError) as import_err:
                 error_msg.append(f"Function Path '{function_path}' không hợp lệ: {import_err}")

        if error_msg: # Nếu có bất kỳ lỗi nào
            for msg in error_msg: flash(msg, "warning")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ (Lỗi)",
                                   trigger_types=TRIGGER_TYPES, current_data=request.form), 400

        # ----- Chỉ Lưu vào DB -----
        db_success, db_error = db.add_job_config(job_id, function_path, trigger_type, trigger_args_str, is_enabled, description)

        if db_success:
            flash(f"Thêm cấu hình tác vụ '{job_id}' thành công! Khởi động lại server để áp dụng.", 'success')
            return redirect(url_for('admin.view_scheduled_jobs'))
        else:
            flash(f"Lỗi lưu vào DB: {db_error or 'Lỗi không xác định.'}", "error")
            return render_template('admin_add_scheduled_job.html', title="Thêm Tác vụ (Lỗi DB)",
                                   trigger_types=TRIGGER_TYPES, current_data=request.form)

    # --- Xử lý GET Request ---
    return render_template('admin_add_scheduled_job.html',
                           title=title,
                           trigger_types=TRIGGER_TYPES,
                           available_tasks=AVAILABLE_SCHEDULED_TASKS)

@admin_bp.route('/scheduled-jobs/<job_id>/edit', methods=['GET', 'POST'])
def edit_scheduled_job(job_id):
    """Chỉ sửa cấu hình một Job trong DB."""
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    job_details = db.get_job_config_details(job_id)
    if not job_details:
        flash(f"Không tìm thấy cấu hình cho job ID '{job_id}'.", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))

    if request.method == 'POST':
        trigger_type = request.form.get('trigger_type', '').strip()
        trigger_args_str = request.form.get('trigger_args', '{}').strip()
        is_enabled_str = request.form.get('is_enabled')
        is_enabled = True if is_enabled_str == 'on' else False
        description = request.form.get('description', '').strip()

        # ----- Validate Input -----
        error = False
        error_msg = []
        if not trigger_type or trigger_type not in TRIGGER_TYPES:
            error_msg.append("Trigger Type không hợp lệ.")
        try: # Validate JSON và kiểu số
            if not trigger_args_str: trigger_args_str = '{}'
            trigger_args_dict = json.loads(trigger_args_str)
            if not isinstance(trigger_args_dict, dict): raise ValueError("phải là JSON object.")
            numeric_keys = ['weeks', 'days', 'hours', 'minutes', 'seconds', 'jitter', 'year', 'month', 'day', 'week', 'hour', 'minute', 'second']
            args_to_check = trigger_args_dict.copy()
            for key in numeric_keys:
                if key in args_to_check and isinstance(args_to_check[key], str):
                    value_str = args_to_check[key].strip();
                    if not value_str: del trigger_args_dict[key]; continue
                    if '.' in value_str: _ = float(value_str)
                    else: _ = int(value_str)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
             error_msg.append(f"Trigger Args không hợp lệ: {e}")

        if error_msg: # Nếu có lỗi validation
            for msg in error_msg: flash(msg, "warning")
            return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}' (Lỗi)",
                                   job=job_details, trigger_types=TRIGGER_TYPES, current_data=request.form), 400

        # --- Chỉ Cập nhật DB ---
        db_success, db_error = db.update_job_config(job_id, trigger_type, trigger_args_str, is_enabled, description)

        if db_success:
             flash(f"Cập nhật cấu hình tác vụ '{job_id}' thành công! Khởi động lại server để thay đổi có hiệu lực.", 'success')
        else:
             flash(f"Lỗi cập nhật DB: {db_error or 'Unknown DB error'}", "error")
             # Hiển thị lại form với lỗi
             return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}' (Lỗi DB)",
                                    job=job_details, trigger_types=TRIGGER_TYPES, current_data=request.form)

        # <<< KHÔNG CÒN PHẦN CẬP NHẬT SCHEDULER LIVE >>>
        return redirect(url_for('admin.view_scheduled_jobs'))

    # --- Xử lý GET Request ---
    # job_details đã được lấy ở đầu hàm
    return render_template('admin_edit_scheduled_job.html', title=f"Sửa Tác vụ '{job_id}'",
                           job=job_details, trigger_types=TRIGGER_TYPES)


@admin_bp.route('/scheduled-jobs/<job_id>/delete', methods=['POST'])
def delete_scheduled_job(job_id):
    """Chỉ xóa cấu hình Job khỏi DB."""
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    # <<< KHÔNG CÒN PHẦN XÓA KHỎI SCHEDULER LIVE >>>

    # --- Chỉ Xóa khỏi DB ---
    db_success, db_error = db.delete_job_config(job_id)
    if db_success:
        flash(f"Đã xóa cấu hình job '{job_id}' khỏi DB. Thay đổi sẽ có hiệu lực sau khi khởi động lại server.", 'success')
    else:
        flash(f"Lỗi xóa cấu hình job '{job_id}' khỏi DB: {db_error or 'Unknown DB error'}.", "error")

    return redirect(url_for('admin.view_scheduled_jobs'))


@admin_bp.route('/scheduled-jobs/<job_id>/toggle', methods=['POST'])
def toggle_scheduled_job(job_id):
    """Chỉ Bật/Tắt cấu hình is_enabled trong DB."""
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    job_details = db.get_job_config_details(job_id)
    if not job_details:
        flash(f"Không tìm thấy job '{job_id}' để thay đổi trạng thái.", "error")
        return redirect(url_for('admin.view_scheduled_jobs'))

    current_enabled_state = job_details.get('is_enabled', False)
    new_enabled_state = not current_enabled_state

    # --- Chỉ Cập nhật trạng thái trong DB ---
    db_success, db_error = db.update_job_enabled_status(job_id, new_enabled_state)

    if db_success:
        action_text = "bật" if new_enabled_state else "tắt"
        flash(f"Đã đặt trạng thái '{action_text}' cho job '{job_id}' trong cấu hình DB. Khởi động lại server để áp dụng.", 'success')
    else:
        flash(f"Lỗi cập nhật trạng thái DB cho job '{job_id}': {db_error or 'Unknown DB error'}", "error")

    # <<< KHÔNG CÒN PHẦN TƯƠNG TÁC VỚI SCHEDULER LIVE >>>
    return redirect(url_for('admin.view_scheduled_jobs'))



@admin_bp.route('/scheduled-jobs/suggestion_job/run-now', methods=['POST'])
def run_suggestion_job_now():
    """Yêu cầu chạy suggestion_job ngay lập tức thông qua command queue."""
    job_name_to_run = 'suggestion_job' # Tên job cần chạy ngay
    print(f"INFO: Received request to run job '{job_name_to_run}' now.")

    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_scheduled_jobs'))

    try:
        # Tạo một payload đơn giản (có thể trống hoặc chứa thông tin nguồn gốc)
        payload = {'source': 'manual_run_now_button'}
        # Thêm lệnh vào hàng đợi CSDL với một command_type riêng
        command_id = db.add_scheduler_command(
            command_type='run_suggestion_job_now', # <<< Loại lệnh mới
            payload=payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy tác vụ '{job_name_to_run}' ngay lập tức. Scheduler sẽ xử lý (Command ID: {command_id}).", 'success')
        else:
             flash(f"Lỗi khi thêm yêu cầu chạy tác vụ '{job_name_to_run}' vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu chạy '{job_name_to_run}' ngay: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi yêu cầu chạy tác vụ: {e}", "error")

    # <<< QUAN TRỌNG: Luôn trả về một response hợp lệ >>>
    return redirect(url_for('admin.view_scheduled_jobs'))

def _get_live_next_run_times():
    live_times = {}
    conn = None
    cur = None
    # !!! Sử dụng lại hàm get_db_connection từ module database !!!
    # Đảm bảo bạn đã import: from . import database as db
    if not db:
        print("ERROR (_get_live_next_run_times): Database module 'db' not available.")
        return {} # Trả về dict rỗng nếu không import được db

    try:
        conn = db.get_db_connection() # Dùng hàm kết nối từ database.py
        if not conn:
            print("ERROR (_get_live_next_run_times): Failed to get DB connection.")
            return {}

        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Dùng DictCursor
        # Lấy id (là job_id) và next_run_time (là Unix timestamp float)
        cur.execute("SELECT id, next_run_time FROM public.apscheduler_jobs;")
        rows = cur.fetchall()
        live_times = {row['id']: row['next_run_time'] for row in rows} if rows else {}
        # print(f"DEBUG: Fetched live run times: {live_times}") # Log nếu cần debug

    except psycopg2.Error as db_err:
        print(f"ERROR (_get_live_next_run_times): DB Error querying apscheduler_jobs: {db_err}")
        # Không nên flash ở đây vì đây là hàm helper
    except Exception as e:
        print(f"ERROR (_get_live_next_run_times): Unexpected error querying apscheduler_jobs: {e}")
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return live_times

@admin_bp.route('/_get_live_job_statuses')
def get_live_job_statuses_for_ajax():
    """Trả về trạng thái next_run_time của các job dưới dạng JSON cho AJAX."""
    live_times_raw = _get_live_next_run_times() # Gọi hàm helper đã tạo
    live_statuses = {}
    server_tz_str = 'Asia/Ho_Chi_Minh' # Cần nhất quán với cấu hình scheduler
    try:
        server_tz = pytz.timezone(server_tz_str)
    except pytz.UnknownTimeZoneError:
        server_tz = pytz.utc

    for job_id, timestamp in live_times_raw.items():
        status_str = 'N/A'
        if timestamp is not None:
            try:
                utc_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                local_dt = utc_dt.astimezone(server_tz)
                # Dùng định dạng đơn giản hơn cho AJAX nếu muốn
                status_str = local_dt.strftime('%H:%M:%S %d/%m/%Y')
                if job_id == 'suggestion_job':
                 print(f"AJAX DEBUG: Formatted time for {job_id} = {status_str}")
                # Hoặc giữ định dạng cũ:
                # status_str = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
            except Exception:
                status_str = 'Lỗi Format'
        else:
            status_str = 'Paused'
        live_statuses[job_id] = status_str

    # Cũng cần trả về trạng thái cho những job có config nhưng không chạy
    try:
        all_config_jobs = db.get_all_job_configs() or []
        for cfg_job in all_config_jobs:
            job_id = cfg_job.get('job_id')
            if job_id and job_id not in live_statuses:
                live_statuses[job_id] = 'Not Scheduled' # Hoặc dựa vào cfg_job['is_enabled']
    except Exception as e:
         print(f"Error fetching all configs for AJAX status: {e}")


    return jsonify(live_statuses)

# =============================================================
# === QUẢN LÝ MÔ PHỎNG HỘI THOẠI AI ===
# =============================================================


@admin_bp.route('/ai-simulations', methods=['GET'])
def view_ai_simulations():
    """
    Hiển thị trang quản lý mô phỏng AI:
    - Danh sách cấu hình đã lưu (có phân trang)
    - Danh sách các lần chạy/lệnh gần đây (từ commands và live jobs)
    """
    title = "Quản lý Mô phỏng AI"
    # Khởi tạo các list và dict cần thiết
    personas, strategies, accounts, saved_configs = [], [], [], []
    simulations_display_list = []
    saved_configs_pagination = None

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # --- 1. Lấy dữ liệu cho các Dropdown (cần cho form Thêm/Sửa sau này) ---
            personas = db.get_all_personas() or []
            strategies = db.get_all_strategies() or []
            accounts = db.get_all_accounts() or [] # Hàm này cần hỗ trợ phân trang nếu danh sách quá lớn

            # --- 2. Lấy danh sách Cấu hình Đã Lưu (có phân trang) ---
            page_saved = request.args.get('page_saved', 1, type=int) # Dùng param riêng cho pagination này
            if page_saved < 1: page_saved = 1

            saved_configs, total_saved_configs = db.get_all_simulation_configs(
                page=page_saved, per_page=PER_PAGE_SAVED_SIM_CONFIGS
            )

            if saved_configs is None or total_saved_configs is None:
                 flash("Lỗi khi tải danh sách cấu hình đã lưu.", "error")
                 saved_configs = []; total_saved_configs = 0
                 saved_configs_pagination = None
            else:
                 # Tính toán pagination cho cấu hình đã lưu
                 if total_saved_configs > 0:
                     total_pages_saved = ceil(total_saved_configs / PER_PAGE_SAVED_SIM_CONFIGS)
                     if page_saved > total_pages_saved and total_pages_saved > 0: page_saved = total_pages_saved
                     saved_configs_pagination = {
                        'page': page_saved, 'per_page': PER_PAGE_SAVED_SIM_CONFIGS, 'total_items': total_saved_configs,
                        'total_pages': total_pages_saved, 'has_prev': page_saved > 1, 'has_next': page_saved < total_pages_saved,
                        'prev_num': page_saved - 1 if page_saved > 1 else None,
                        'next_num': page_saved + 1 if page_saved < total_pages_saved else None,
                        'page_param': 'page_saved' # Thêm tên tham số page để dùng trong url_for
                     }
                 else:
                     saved_configs_pagination = {'page': 1, 'per_page': PER_PAGE_SAVED_SIM_CONFIGS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False, 'page_param': 'page_saved'}
                 print(f"DEBUG (view_ai_simulations): Calculated Saved Configs pagination = {saved_configs_pagination}")


            # === 3. TẠO DANH SÁCH HIỂN THỊ CÁC LẦN CHẠY/LỆNH GẦN ĐÂY ===
            server_tz = _get_configured_timezone()

            # 3.1 Lấy các Lệnh mô phỏng gần đây (pending, processing, error, done)
            recent_commands = db.get_recent_simulation_commands(
                status_list=['pending', 'processing', 'error', 'done'],
                command_type='run_simulation', limit=30
            ) or []
            command_map = {cmd['command_id']: cmd for cmd in recent_commands}
            print(f"DEBUG: Fetched {len(recent_commands)} recent simulation commands (incl. done).")

            # 3.2 Lấy các Job mô phỏng đang được lên lịch
            live_job_times = _get_live_next_run_times() or {} # dict {job_id: timestamp}
            live_sim_jobs_dict = {job_id: ts for job_id, ts in live_job_times.items() if job_id.startswith('sim_run_')}
            print(f"DEBUG: Found {len(live_sim_jobs_dict)} live simulation jobs.")

            processed_command_ids = set() # Theo dõi command ID đã được liên kết

            # 3.3 Tạo danh sách hiển thị - Ưu tiên xử lý các Job Live trước
            for job_id, next_run_timestamp in live_sim_jobs_dict.items():
                sim_info = {'id': job_id, 'type': 'job', 'command_id': None, 'config_info': '(Live Job - Config N/A)', 'status_text': 'Unknown', 'created_at': None, 'next_run_time_str': 'N/A', 'error_message': None}
                config_info_str = sim_info['config_info'] # Default

                # Trích xuất command_id từ job_id
                command_id_from_job = None
                parts = job_id.split('_')
                if len(parts) >= 3 and parts[0] == 'sim' and parts[1] == 'run':
                     try: command_id_from_job = int(parts[2]); sim_info['command_id'] = command_id_from_job
                     except ValueError: pass

                # Nếu tìm được command_id, lấy thông tin config từ command_map
                if command_id_from_job and command_id_from_job in command_map:
                    command_data = command_map[command_id_from_job]
                    payload = command_data.get('payload', {})
                    cfg_pa = payload.get('persona_a_id','?'); cfg_pb = payload.get('persona_b_id','?')
                    cfg_stra = payload.get('strategy_id','?'); cfg_turns = payload.get('max_turns','?')
                    cfg_goal = payload.get('sim_goal','?')
                    config_info_str = f"A: {cfg_pa} <-> B: {cfg_pb}<br>" \
                                      f"<small>Strat: {cfg_stra} | Goal: {cfg_goal} | Turns: {cfg_turns}</small>"
                    sim_info['created_at'] = command_data.get('created_at')
                    processed_command_ids.add(command_id_from_job)

                sim_info['config_info'] = config_info_str

                # Format thời gian và status
                if next_run_timestamp is not None:
                    try:
                        utc_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
                        local_dt = utc_dt.astimezone(server_tz)
                        sim_info['next_run_time_str'] = local_dt.strftime('%Y-%m-%d %H:%M:%S %z')
                        sim_info['status_text'] = 'Scheduled'
                    except Exception: sim_info['next_run_time_str'] = 'Lỗi Format'
                else:
                    sim_info['next_run_time_str'] = '---'; sim_info['status_text'] = 'Paused/Finished?'

                simulations_display_list.append(sim_info)

            # 3.4 Xử lý các Command chưa được liên kết hoặc có trạng thái cuối cùng
            for cmd_id, command_data in command_map.items():
                if cmd_id not in processed_command_ids:
                    payload = command_data.get('payload', {})
                    status = command_data.get('status', 'unknown')
                    status_text = status.capitalize()
                    if status == 'pending': status_text = 'Pending Queue'
                    elif status == 'processing': status_text = 'Processing Cmd'
                    elif status == 'done': status_text = 'Command Done'
                    elif status == 'error': status_text = f"Command Error: {command_data.get('error_message', '')[:100]}" if command_data.get('error_message') else 'Command Error'

                    cfg_pa=payload.get('persona_a_id','?'); cfg_pb=payload.get('persona_b_id','?')
                    cfg_stra=payload.get('strategy_id','?'); cfg_turns=payload.get('max_turns','?')
                    cfg_goal=payload.get('sim_goal','?')
                    config_info_str = f"A: {cfg_pa} <-> B: {cfg_pb}<br>" \
                                      f"<small>Strat: {cfg_stra} | Goal: {cfg_goal} | Turns: {cfg_turns}</small>"

                    sim_info = {
                        'id': f"cmd_{cmd_id}", 'type': 'command', 'command_id': cmd_id,
                        'job_id': None, 'config_info': config_info_str,
                        'status_text': status_text, 'created_at': command_data.get('created_at'),
                        'next_run_time_str': '---', 'error_message': command_data.get('error_message')
                    }
                    simulations_display_list.append(sim_info)

            # 3.5 Sắp xếp danh sách hiển thị cuối cùng (theo thời gian tạo lệnh giảm dần)
            def get_sort_key(item):
                 if item.get('created_at'): return item['created_at']
                 return datetime.now(timezone.utc) # Fallback để sort
            simulations_display_list.sort(key=get_sort_key, reverse=True)

        except Exception as e:
            print(f"Lỗi khi tải dữ liệu trang mô phỏng AI: {e}")
            print(traceback.format_exc()) # In traceback để dễ debug
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            personas, strategies, accounts, saved_configs, simulations_display_list, saved_configs_pagination = [], [], [], [], [], None


    # Render template với tất cả dữ liệu cần thiết
    return render_template('admin_ai_simulations.html',
                           title=title,
                           personas=personas,
                           strategies=strategies,
                           accounts=accounts,
                           saved_configs=saved_configs,                 # Danh sách config trang hiện tại
                           saved_configs_pagination=saved_configs_pagination, # Pagination cho config
                           simulations_display=simulations_display_list) 
@admin_bp.route('/ai-simulations/run-adhoc', methods=['POST'])
def run_adhoc_simulation():
    """Xử lý yêu cầu chạy mô phỏng ad-hoc bằng cách thêm lệnh vào DB queue."""
    # Bây giờ không cần kiểm tra live_scheduler ở đây nữa
    # Chỉ cần kiểm tra module db có sẵn không
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # --- Lấy dữ liệu từ form ---
        persona_a_id = request.form.get('persona_a_id')
        persona_b_id = request.form.get('persona_b_id')
        log_account_id_a = request.form.get('log_account_id_a') # <<< Lấy account log A
        log_account_id_b = request.form.get('log_account_id_b') # <<< Lấy account log B
        strategy_id = request.form.get('strategy_id')
        max_turns_str = request.form.get('max_turns', '5')
        starting_prompt = request.form.get('starting_prompt', '').strip()
        sim_goal = request.form.get('sim_goal', 'simulation').strip()
        # sim_thread_id_base không cần lấy từ form nữa

        # --- Validate dữ liệu ---
        errors = []
        if not persona_a_id: errors.append("Vui lòng chọn Persona A.")
        if not persona_b_id: errors.append("Vui lòng chọn Persona B.")
        if persona_a_id == persona_b_id: errors.append("Persona A và Persona B phải khác nhau.")
        if not log_account_id_a: errors.append("Vui lòng chọn Account ID cho Log Persona A.") # <<< Validate A
        if not log_account_id_b: errors.append("Vui lòng chọn Account ID cho Log Persona B.") # <<< Validate B
        # Tùy chọn: Kiểm tra log_account_id_a != log_account_id_b nếu muốn
        # if log_account_id_a == log_account_id_b: errors.append("Account ID cho Log A và B nên khác nhau.")
        if not strategy_id: errors.append("Vui lòng chọn Chiến lược.")

        max_turns = 5 # Giá trị mặc định
        try:
            max_turns = int(max_turns_str)
            if not (1 <= max_turns <= 20):
                 raise ValueError("Số lượt phải từ 1 đến 20.")
        except ValueError as e:
            errors.append(f"Số lượt nói tối đa không hợp lệ: {e}")

        if errors:
            for error in errors: flash(error, 'warning')
            # Cần lấy lại danh sách để render lại form
            personas = db.get_all_personas() or []
            strategies = db.get_all_strategies() or []
            accounts = db.get_all_accounts() or [] # <<< Lấy lại accounts
            return render_template('admin_ai_simulations.html',
                                   title="Chạy Mô phỏng (Lỗi)",
                                   personas=personas, strategies=strategies, accounts=accounts, # <<< Truyền lại accounts
                                   current_data=request.form), 400

        # --- Chuẩn bị Payload cho Lệnh ---
        # Tạo tiền tố thread dựa trên account ID
        sim_thread_id_base = f"sim_{log_account_id_a[:5]}_vs_{log_account_id_b[:5]}"

        command_payload = {
            'persona_a_id': persona_a_id,
            'persona_b_id': persona_b_id,
            'log_account_id_a': log_account_id_a, # <<< Thêm
            'log_account_id_b': log_account_id_b, # <<< Thêm
            'strategy_id': strategy_id,
            'max_turns': max_turns,
            'starting_prompt': starting_prompt if starting_prompt else "Xin chào!",
            'sim_thread_id_base': sim_thread_id_base, # <<< Dùng tiền tố mới
            'sim_goal': sim_goal
            # 'sim_account_id' không cần nữa
        }

        print(f"INFO: Adding 'run_simulation' command with payload: {command_payload}")

        # --- Thêm Lệnh vào Hàng Đợi DB ---
        command_id = db.add_scheduler_command(
            command_type='run_simulation',
            payload=command_payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy mô phỏng '{sim_goal}' giữa {persona_a_id} và {persona_b_id}. Tác vụ sẽ được xử lý (Command ID: {command_id}).", 'success')
        else:
             flash("Lỗi khi thêm yêu cầu chạy mô phỏng vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu mô phỏng: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi yêu cầu chạy mô phỏng: {e}", "error")

    # Luôn redirect về trang quản lý sau khi xử lý
    return redirect(url_for('admin.view_ai_simulations'))


# --- === ROUTE HỦY BỎ MỘT LẦN CHẠY MÔ PHỎNG === ---
@admin_bp.route('/simulations/<job_id>/cancel', methods=['POST'])
def cancel_simulation_job(job_id):
    """Thêm lệnh 'cancel_job' vào queue để yêu cầu scheduler hủy job."""
    print(f"INFO: Received request to cancel simulation job ID: {job_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))
    if not job_id:
         flash("Lỗi: Cần cung cấp Job ID để hủy bỏ.", "warning")
         return redirect(url_for('admin.view_ai_simulations'))

    # --- Tạo Payload cho lệnh Hủy ---
    # Payload chỉ cần chứa job_id cần hủy
    command_payload = {
        'job_id_to_cancel': job_id
    }

    try:
        # --- Thêm Lệnh 'cancel_job' vào Hàng Đợi DB ---
        command_id = db.add_scheduler_command(
            command_type='cancel_job', # <<< Loại lệnh mới
            payload=command_payload
        )

        if command_id:
            flash(f"Đã yêu cầu hủy bỏ job '{job_id}'. Scheduler sẽ xử lý (Command ID: {command_id}).", 'success')
        else:
             flash(f"Lỗi khi thêm yêu cầu hủy job '{job_id}' vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu hủy job {job_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi yêu cầu hủy job: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE CHẠY MÔ PHỎNG TỪ CẤU HÌNH ĐÃ LƯU === ---
@admin_bp.route('/ai-simulations/configs/<int:config_id>/run', methods=['POST'])
def run_saved_simulation(config_id):
    """Đọc cấu hình đã lưu và thêm lệnh chạy mô phỏng vào queue."""
    print(f"INFO: Received request to run saved simulation config ID: {config_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # 1. Lấy chi tiết cấu hình từ CSDL
        config_details = db.get_simulation_config(config_id)

        if not config_details:
            flash(f"Lỗi: Không tìm thấy cấu hình mô phỏng có ID {config_id}.", "error")
            return redirect(url_for('admin.view_ai_simulations'))

        # Kiểm tra xem config có được enable không (tùy chọn)
        if not config_details.get('is_enabled', True):
             flash(f"Cấu hình mô phỏng '{config_details.get('config_name')}' đang bị tắt (disabled).", "warning")
             return redirect(url_for('admin.view_ai_simulations'))

        # 2. Trích xuất tham số từ cấu hình đã lưu
        # Đảm bảo tên key khớp với các cột trong bảng ai_simulation_configs
        # và khớp với các tham số mà run_ai_conversation_simulation mong đợi
        command_payload = {
            'persona_a_id': config_details.get('persona_a_id'),
            'persona_b_id': config_details.get('persona_b_id'),
            'log_account_id_a': config_details.get('log_account_id_a'),
            'log_account_id_b': config_details.get('log_account_id_b'),
            'strategy_id': config_details.get('strategy_id'),
            'max_turns': config_details.get('max_turns', 5), # Lấy giá trị từ DB hoặc default
            'starting_prompt': config_details.get('starting_prompt'), # Có thể là None
            # Tạo tiền tố thread ID dựa trên tên config để dễ nhận biết
            'sim_thread_id_base': f"sim_{config_details.get('config_name', str(config_id)).replace(' ', '_')[:15]}",
            'sim_goal': config_details.get('simulation_goal') or 'saved_config_run'
        }

        # Kiểm tra lại các giá trị bắt buộc
        if not all([command_payload['persona_a_id'], command_payload['persona_b_id'],
                    command_payload['log_account_id_a'], command_payload['log_account_id_b'],
                    command_payload['strategy_id']]):
            flash(f"Lỗi: Cấu hình ID {config_id} thiếu thông tin Persona, Account Log hoặc Strategy.", "error")
            return redirect(url_for('admin.view_ai_simulations'))


        print(f"INFO: Adding 'run_simulation' command from saved config '{config_details.get('config_name')}' with payload: {command_payload}")

        # 3. Thêm Lệnh vào Hàng Đợi DB
        command_id = db.add_scheduler_command(
            command_type='run_simulation',
            payload=command_payload
        )

        if command_id:
            flash(f"Đã yêu cầu chạy mô phỏng theo cấu hình '{config_details.get('config_name')}'. Tác vụ sẽ được xử lý (Command ID: {command_id}).", 'success')
        else:
             flash(f"Lỗi khi thêm yêu cầu chạy cấu hình '{config_details.get('config_name')}' vào hàng đợi CSDL.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi yêu cầu chạy cấu hình đã lưu ID {config_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE THÊM CẤU HÌNH MÔ PHỎNG MỚI === ---
@admin_bp.route('/ai-simulations/configs/add', methods=['GET', 'POST'])
def add_simulation_config_view():
    """Hiển thị form thêm và xử lý lưu cấu hình mô phỏng mới."""
    title = "Thêm Cấu hình Mô phỏng AI"
    # Dữ liệu cần cho dropdowns
    personas = []
    strategies = []
    accounts = []
    if db:
        try:
            personas = db.get_all_personas() or []
            strategies = db.get_all_strategies() or []
            accounts = db.get_all_accounts() or []
        except Exception as e:
            flash(f"Lỗi tải dữ liệu cho form: {e}", "error")

    # --- Xử lý POST request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            config_name = request.form.get('config_name', '').strip()
            description = request.form.get('description', '').strip()
            persona_a_id = request.form.get('persona_a_id')
            persona_b_id = request.form.get('persona_b_id')
            log_account_id_a = request.form.get('log_account_id_a')
            log_account_id_b = request.form.get('log_account_id_b')
            strategy_id = request.form.get('strategy_id')
            max_turns_str = request.form.get('max_turns', '5')
            starting_prompt = request.form.get('starting_prompt', '').strip()
            simulation_goal = request.form.get('simulation_goal', 'general_chat').strip()
            is_enabled = request.form.get('is_enabled') == 'on' # Checkbox trả về 'on' nếu được chọn

            # --- Validate dữ liệu ---
            errors = []
            if not config_name: errors.append("Tên cấu hình là bắt buộc.")
            if not persona_a_id: errors.append("Vui lòng chọn Persona A.")
            if not persona_b_id: errors.append("Vui lòng chọn Persona B.")
            if persona_a_id == persona_b_id: errors.append("Persona A và Persona B phải khác nhau.")
            if not log_account_id_a: errors.append("Vui lòng chọn Account Log cho A.")
            if not log_account_id_b: errors.append("Vui lòng chọn Account Log cho B.")
            if not strategy_id: errors.append("Vui lòng chọn Chiến lược.")
            max_turns = 5
            try:
                max_turns = int(max_turns_str)
                if not (1 <= max_turns <= 50): # Giới hạn trong DB là 50
                    raise ValueError("Số lượt phải từ 1 đến 50.")
            except ValueError as e:
                errors.append(f"Số lượt nói tối đa không hợp lệ: {e}")

            if errors: # Nếu có lỗi validation
                for error in errors: flash(error, 'warning')
                # Render lại form với dữ liệu cũ và lỗi
                return render_template('admin_add_simulation_config.html',
                                       title=title + " (Lỗi)",
                                       personas=personas, strategies=strategies, accounts=accounts,
                                       current_data=request.form), 400

            # --- Gọi hàm DB để thêm ---
            success = db.add_simulation_config(
                config_name=config_name, description=description or None, # Chuyển chuỗi rỗng thành None nếu cần
                persona_a_id=persona_a_id, persona_b_id=persona_b_id,
                log_account_id_a=log_account_id_a, log_account_id_b=log_account_id_b,
                strategy_id=strategy_id, max_turns=max_turns,
                starting_prompt=starting_prompt or None, # Chuyển chuỗi rỗng thành None
                simulation_goal=simulation_goal or None,
                is_enabled=is_enabled
            )

            if success:
                flash(f"Đã thêm cấu hình mô phỏng '{config_name}' thành công!", 'success')
                return redirect(url_for('admin.view_ai_simulations')) # Redirect về trang quản lý chính
            else:
                flash(f"Thêm cấu hình '{config_name}' thất bại! (Tên có thể đã tồn tại hoặc ID liên kết không hợp lệ?)", 'error')
                # Render lại form với dữ liệu cũ
                return render_template('admin_add_simulation_config.html',
                                       title=title,
                                       personas=personas, strategies=strategies, accounts=accounts,
                                       current_data=request.form)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm cấu hình mô phỏng: {e}")
            print(traceback.format_exc())
            flash(f"Đã xảy ra lỗi không mong muốn: {e}", "error")
            # Render lại form với dữ liệu cũ
            return render_template('admin_add_simulation_config.html',
                                   title=title,
                                   personas=personas, strategies=strategies, accounts=accounts,
                                   current_data=request.form)

    # --- Xử lý GET request ---
    # Chỉ cần render template với dữ liệu cho dropdowns
    return render_template('admin_add_simulation_config.html',
                           title=title,
                           personas=personas,
                           strategies=strategies,
                           accounts=accounts)

@admin_bp.route('/ai-simulations/configs/<int:config_id>/edit', methods=['GET', 'POST'])
def edit_simulation_config_view(config_id):
    """Hiển thị form và xử lý cập nhật cấu hình mô phỏng đã lưu."""
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    # Lấy thông tin cấu hình hiện tại để hiển thị form (cho cả GET và POST lỗi)
    config_details = db.get_simulation_config(config_id)
    if not config_details:
        flash(f"Không tìm thấy cấu hình mô phỏng có ID {config_id}.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    title = f"Sửa Cấu hình Mô phỏng '{config_details.get('config_name', config_id)}'"

    # --- Xử lý POST request ---
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            config_name = request.form.get('config_name', '').strip()
            description = request.form.get('description', '').strip()
            persona_a_id = request.form.get('persona_a_id')
            persona_b_id = request.form.get('persona_b_id')
            log_account_id_a = request.form.get('log_account_id_a')
            log_account_id_b = request.form.get('log_account_id_b')
            strategy_id = request.form.get('strategy_id')
            max_turns_str = request.form.get('max_turns', '5')
            starting_prompt = request.form.get('starting_prompt', '').strip()
            simulation_goal = request.form.get('simulation_goal', 'general_chat').strip()
            is_enabled = request.form.get('is_enabled') == 'on'

            # --- Validate dữ liệu (tương tự như khi thêm) ---
            errors = []
            if not config_name: errors.append("Tên cấu hình là bắt buộc.")
            # Kiểm tra trùng tên (ngoại trừ chính ID hiện tại) - Cần hàm DB `check_config_name_exists(name, exclude_id)` hoặc xử lý ở DB
            # Tạm thời bỏ qua kiểm tra trùng tên khi sửa
            if not persona_a_id: errors.append("Vui lòng chọn Persona A.")
            if not persona_b_id: errors.append("Vui lòng chọn Persona B.")
            if persona_a_id == persona_b_id: errors.append("Persona A và Persona B phải khác nhau.")
            if not log_account_id_a: errors.append("Vui lòng chọn Account Log cho A.")
            if not log_account_id_b: errors.append("Vui lòng chọn Account Log cho B.")
            if not strategy_id: errors.append("Vui lòng chọn Chiến lược.")
            max_turns = 5
            try:
                max_turns = int(max_turns_str)
                if not (1 <= max_turns <= 50): raise ValueError("Số lượt phải từ 1 đến 50.")
            except ValueError as e: errors.append(f"Số lượt nói tối đa không hợp lệ: {e}")

            if errors:
                for error in errors: flash(error, 'warning')
                # Cần lấy lại dropdown data để render lại form lỗi
                personas = db.get_all_personas() or []
                strategies = db.get_all_strategies() or []
                accounts = db.get_all_accounts() or []
                # Dùng config_details cũ nhưng truyền current_data=request.form để giữ giá trị nhập lỗi
                return render_template('admin_edit_simulation_config.html',
                                       title=title + " (Lỗi)",
                                       config=config_details, # config gốc để lấy ID
                                       personas=personas, strategies=strategies, accounts=accounts,
                                       current_data=request.form), 400

            # --- Gọi hàm DB để cập nhật ---
            success = db.update_simulation_config(
                config_id=config_id, # ID từ URL
                config_name=config_name, description=description or None,
                persona_a_id=persona_a_id, persona_b_id=persona_b_id,
                log_account_id_a=log_account_id_a, log_account_id_b=log_account_id_b,
                strategy_id=strategy_id, max_turns=max_turns,
                starting_prompt=starting_prompt or None,
                simulation_goal=simulation_goal or None,
                is_enabled=is_enabled
            )

            if success:
                flash(f"Đã cập nhật cấu hình mô phỏng '{config_name}' thành công!", 'success')
                return redirect(url_for('admin.view_ai_simulations')) # Redirect về trang quản lý chính
            else:
                flash(f"Cập nhật cấu hình '{config_name}' thất bại! (Tên có thể đã tồn tại hoặc ID liên kết không hợp lệ?)", 'error')
                # Render lại form với dữ liệu cũ và lỗi
                personas = db.get_all_personas() or []
                strategies = db.get_all_strategies() or []
                accounts = db.get_all_accounts() or []
                return render_template('admin_edit_simulation_config.html',
                                       title=title,
                                       config=config_details, # config gốc
                                       personas=personas, strategies=strategies, accounts=accounts,
                                       current_data=request.form) # Giữ lại giá trị form lỗi

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật cấu hình mô phỏng ID {config_id}: {e}")
            print(traceback.format_exc())
            flash(f"Đã xảy ra lỗi không mong muốn: {e}", "error")
            # Render lại form với dữ liệu gốc
            personas = db.get_all_personas() or []
            strategies = db.get_all_strategies() or []
            accounts = db.get_all_accounts() or []
            return render_template('admin_edit_simulation_config.html',
                                   title=title,
                                   config=config_details, # config gốc
                                   personas=personas, strategies=strategies, accounts=accounts)


    # --- Xử lý GET request ---
    # Lấy dữ liệu cho dropdowns
    personas = []
    strategies = []
    accounts = []
    try:
        personas = db.get_all_personas() or []
        strategies = db.get_all_strategies() or []
        accounts = db.get_all_accounts() or []
    except Exception as e:
        flash(f"Lỗi tải dữ liệu cho form sửa: {e}", "error")
        # config_details đã được lấy ở trên, vẫn render form nhưng dropdown có thể trống

    # Render template với dữ liệu cấu hình hiện tại và dữ liệu cho dropdowns
    return render_template('admin_edit_simulation_config.html',
                           title=title,
                           config=config_details, # <<< Dữ liệu cấu hình cần sửa
                           personas=personas,
                           strategies=strategies,
                           accounts=accounts)


@admin_bp.route('/ai-simulations/configs/<int:config_id>/delete', methods=['POST'])
def delete_simulation_config_view(config_id):
    """Xử lý xóa một cấu hình mô phỏng đã lưu."""
    print(f"INFO: Received request to delete simulation config ID: {config_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # Gọi hàm xóa trong database.py
        success = db.delete_simulation_config(config_id)

        if success:
            flash(f"Đã xóa thành công cấu hình mô phỏng ID {config_id}.", 'success')
        else:
            # Có thể do ID không tồn tại
            flash(f"Xóa cấu hình mô phỏng ID {config_id} thất bại (ID không tồn tại?).", 'warning')

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa cấu hình mô phỏng ID {config_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa cấu hình: {e}", "error")

    # Luôn redirect về trang quản lý chính
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE XÓA MỘT LỆNH SCHEDULER KHỎI HÀNG ĐỢI/LỊCH SỬ LỆNH === ---
@admin_bp.route('/commands/<int:command_id>/delete', methods=['POST'])
def delete_scheduler_command_view(command_id):
    """Xử lý xóa một command khỏi bảng scheduler_commands."""
    print(f"INFO: Received request to delete scheduler command ID: {command_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations')) # Hoặc trang thích hợp khác

    try:
        # Gọi hàm xóa trong database.py
        success = db.delete_scheduler_command(command_id)

        if success:
            flash(f"Đã xóa thành công lệnh ID {command_id}.", 'success')
        else:
            flash(f"Xóa lệnh ID {command_id} thất bại (ID không tồn tại?).", 'warning')

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa lệnh ID {command_id}: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa lệnh: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng (nơi hiển thị danh sách lệnh/job)
    return redirect(url_for('admin.view_ai_simulations'))

@admin_bp.route('/ai-simulations/commands/clear-finished', methods=['POST'])
def clear_finished_simulation_commands():
    """Xóa các lệnh run_simulation có status 'done' hoặc 'error'."""
    print("INFO: Received request to clear finished simulation commands.")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_ai_simulations'))

    try:
        # Gọi hàm xóa hàng loạt trong database.py
        success, deleted_count, error_msg = db.delete_completed_or_errored_commands(
            command_type='run_simulation' # Chỉ xóa lệnh loại run_simulation
        )

        if success:
            flash(f"Đã xóa thành công {deleted_count or 0} lệnh mô phỏng đã hoàn thành hoặc bị lỗi.", 'success')
        else:
            flash(f"Xóa lệnh thất bại: {error_msg or 'Lỗi không xác định'}.", "error")

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa hàng loạt lệnh: {e}")
        print(traceback.format_exc())
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa lệnh: {e}", "error")

    # Luôn redirect về trang quản lý mô phỏng
    return redirect(url_for('admin.view_ai_simulations'))

# --- === ROUTE XEM CHI TIẾT KẾT QUẢ MÔ PHỎNG === ---
@admin_bp.route('/simulations/results/<int:command_id>')
def view_simulation_results(command_id):
    """Hiển thị chi tiết cuộc hội thoại của một lần chạy mô phỏng."""
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_ai_simulations'))

    command_details = None
    conversation_turns = []
    title = f"Kết quả Mô phỏng (Lệnh #{command_id})"

    try:
        # 1. Lấy thông tin lệnh gốc để biết cấu hình và thread_id_base
        command_details = db.get_command_details(command_id)
        if not command_details or command_details.get('command_type') != 'run_simulation':
            flash(f"Không tìm thấy lệnh chạy mô phỏng hợp lệ với ID {command_id}.", "error")
            return redirect(url_for('admin.view_ai_simulations'))

        payload = command_details.get('payload', {})
        thread_id_base = payload.get('sim_thread_id_base')
        # Hoặc lấy từ trường 'run_details' nếu bạn đã implement lưu thread_id đầy đủ

        if not thread_id_base:
            flash(f"Không thể xác định Thread ID gốc cho lệnh {command_id}.", "error")
            # Vẫn render trang nhưng không có hội thoại
        else:
            # Tạo pattern để tìm kiếm (cần khớp với cách tạo trong background_tasks)
            thread_id_pattern = f"sim_thread_{thread_id_base}_%"
            print(f"DEBUG: Finding conversation with thread_id LIKE '{thread_id_pattern}'")
            conversation_turns = db.get_simulation_conversation(thread_id_pattern) or []
            if conversation_turns is None: # Phân biệt lỗi DB và không có dữ liệu
                 flash("Lỗi khi tải dữ liệu hội thoại từ CSDL.", "error")
                 conversation_turns = []
            print(f"DEBUG: Found {len(conversation_turns)} turns.")

        title = f"Kết quả: {payload.get('persona_a_id','?')} vs {payload.get('persona_b_id','?')}"

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi tải kết quả mô phỏng {command_id}: {e}")
        flash(f"Lỗi không mong muốn khi tải kết quả: {e}", "error")
        conversation_turns = [] # Đảm bảo list rỗng khi lỗi

    # Render template mới (sẽ tạo ở bước sau)
    return render_template('admin_simulation_results.html',
                           title=title,
                           command=command_details, # Truyền thông tin lệnh gốc
                           conversation=conversation_turns) # Truyền các lượt hội thoại

# =============================================
# === QUẢN LÝ API KEYS ===
# =============================================

@admin_bp.route('/api-keys', methods=['GET'])
def view_api_keys():
    """Hiển thị danh sách các API Keys đã lưu."""
    title = "Quản lý API Keys"
    api_keys_list = []
    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # Lấy danh sách keys (hàm này không trả về giá trị key thực tế)
            api_keys_list = db.get_all_api_keys()
            if api_keys_list is None:
                 flash("Lỗi khi tải danh sách API keys từ CSDL.", "error")
                 api_keys_list = []
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi load API keys: {e}")
            flash("Lỗi không mong muốn khi tải danh sách API Keys.", "error")
            api_keys_list = []

    return render_template('admin_api_keys.html',
                           title=title,
                           api_keys=api_keys_list)

# --- === ROUTE THÊM API KEY MỚI === ---
@admin_bp.route('/api-keys/add', methods=['GET', 'POST'])
def add_api_key_view():
    """Hiển thị form và xử lý thêm API Key mới."""
    title="Thêm API Key Mới"
    # Danh sách provider có thể lấy từ config hoặc định nghĩa cứng ở đây
    providers = ['google_gemini'] # Mở rộng sau

    if request.method == 'POST':
        if not db:
            flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error");
            return render_template('admin_add_api_key.html', title=title, providers=providers, current_data=request.form), 500

        key_name = request.form.get('key_name', '').strip()
        provider = request.form.get('provider', '').strip()
        api_key_value = request.form.get('api_key_value', '').strip() # Lấy giá trị key gốc
        status = request.form.get('status', 'active').strip()
        notes = request.form.get('notes', '').strip()

        # Validate
        errors = []
        if not key_name: errors.append("Tên Key là bắt buộc.")
        if not provider: errors.append("Nhà cung cấp là bắt buộc.")
        if provider not in providers: errors.append("Nhà cung cấp không hợp lệ.")
        if not api_key_value: errors.append("Giá trị API Key là bắt buộc.")
        if status not in ['active', 'inactive']: errors.append("Trạng thái không hợp lệ.")

        if errors:
            for error in errors: flash(error, 'warning')
            return render_template('admin_add_api_key.html', title=title + " (Lỗi)",
                                   providers=providers, current_data=request.form), 400

        try:
            # Gọi hàm DB để thêm (hàm này đã bao gồm mã hóa)
            success = db.add_api_key(key_name, provider, api_key_value, status, notes or None)
            if success:
                flash(f"Đã thêm API Key '{key_name}' thành công!", 'success')
                return redirect(url_for('admin.view_api_keys'))
            else:
                # Lỗi có thể do tên key trùng hoặc lỗi DB khác
                flash(f"Thêm API Key '{key_name}' thất bại! (Tên Key có thể đã tồn tại?)", 'error')
                return render_template('admin_add_api_key.html', title=title,
                                       providers=providers, current_data=request.form)
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi thêm API Key: {e}")
            flash(f"Lỗi không mong muốn khi thêm key: {e}", "error")
            return render_template('admin_add_api_key.html', title=title,
                                   providers=providers, current_data=request.form)

    # GET request
    return render_template('admin_add_api_key.html', title=title, providers=providers)

# --- === ROUTE SỬA THÔNG TIN API KEY === ---
@admin_bp.route('/api-keys/<int:key_id>/edit', methods=['GET', 'POST'])
def edit_api_key_view(key_id):
    """Hiển thị form và xử lý cập nhật thông tin API Key (không bao gồm giá trị key)."""
    title = f"Sửa API Key #{key_id}"
    valid_statuses = ['active', 'inactive', 'rate_limited']

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
        return redirect(url_for('admin.view_api_keys'))

    # Lấy chi tiết key cho cả GET và POST lỗi
    key_details = db.get_api_key_details(key_id)
    if not key_details:
        flash(f"Không tìm thấy API Key có ID {key_id}.", "error")
        return redirect(url_for('admin.view_api_keys'))

    if request.method == 'POST':
        try:
            key_name = request.form.get('key_name', '').strip()
            status = request.form.get('status', '').strip()
            notes = request.form.get('notes', '').strip()

            # Validate
            errors = []
            if not key_name: errors.append("Tên Key là bắt buộc.")
            if status not in valid_statuses: errors.append("Trạng thái không hợp lệ.")

            if errors:
                for error in errors: flash(error, 'warning')
                # Render lại form với lỗi, giữ lại dữ liệu nhập
                return render_template('admin_edit_api_key.html', title=title + " (Lỗi)",
                                       key_details=key_details, # Truyền key gốc để lấy ID, provider
                                       current_data=request.form), 400 # Truyền dữ liệu lỗi

            # Gọi hàm DB để cập nhật (không cập nhật giá trị key)
            success = db.update_api_key(key_id, key_name, status, notes or None)

            if success:
                flash(f"Đã cập nhật thông tin cho API Key '{key_name}' (ID: {key_id}).", 'success')
                return redirect(url_for('admin.view_api_keys'))
            else:
                # Lỗi có thể do tên key trùng hoặc lỗi DB khác
                flash(f"Cập nhật API Key '{key_name}' thất bại! (Tên Key mới có thể đã tồn tại?)", 'error')
                return render_template('admin_edit_api_key.html', title=title,
                                       key_details=key_details, current_data=request.form)

        except Exception as e:
            print(f"Lỗi nghiêm trọng khi cập nhật API Key {key_id}: {e}")
            flash(f"Lỗi không mong muốn khi cập nhật key: {e}", "error")
            return render_template('admin_edit_api_key.html', title=title,
                                   key_details=key_details, current_data=request.form)

    # GET request: Hiển thị form với dữ liệu hiện tại
    return render_template('admin_edit_api_key.html', title=title, key_details=key_details)

# --- === ROUTE XÓA API KEY === ---
@admin_bp.route('/api-keys/<int:key_id>/delete', methods=['POST'])
def delete_api_key_view(key_id):
    """Xử lý xóa một API Key."""
    print(f"INFO: Received request to delete API Key ID: {key_id}")
    if not db:
         flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
         return redirect(url_for('admin.view_api_keys'))

    try:
        # Lấy tên key trước khi xóa để hiển thị thông báo (tùy chọn)
        key_details = db.get_api_key_details(key_id)
        key_name = key_details.get('key_name', f'ID {key_id}') if key_details else f'ID {key_id}'

        # Gọi hàm xóa trong database.py
        success = db.delete_api_key(key_id)

        if success:
            flash(f"Đã xóa thành công API Key '{key_name}'.", 'success')
        else:
            flash(f"Xóa API Key '{key_name}' thất bại (ID không tồn tại?).", 'warning')

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi xóa API Key {key_id}: {e}")
        flash(f"Đã xảy ra lỗi không mong muốn khi xóa key: {e}", "error")

    # Luôn redirect về trang quản lý API Key
    return redirect(url_for('admin.view_api_keys'))

# =============================================
# === QUẢN LÝ MACRO DEFINITIONS ===
# =============================================
@admin_bp.route('/macro-definitions')
def view_macro_definitions():
    """Hiển thị danh sách Macro Definitions với filter và pagination."""
    title = "Quản lý Định nghĩa Macro Code"
    macros_page = []
    pagination = None
    # Danh sách các target có thể có cho dropdown lọc
    app_targets = ['system', 'generic', 'tiktok', 'zalo', 'facebook'] # Hoặc lấy động từ DB
    active_filters = {}

    if not db:
        flash("Lỗi nghiêm trọng: Database module chưa sẵn sàng.", "error")
    else:
        try:
            # 1. Lấy tham số trang và bộ lọc từ URL
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1

            # Lấy giá trị filter từ request.args
            filter_code = request.args.get('filter_code', '').strip()
            filter_desc = request.args.get('filter_desc', '').strip()
            filter_target = request.args.get('filter_target', '__all__').strip() # Dùng '__all__' làm giá trị mặc định (không lọc)

            # Lưu lại các filter đang áp dụng để điền lại form
            active_filters = {
                'filter_code': filter_code,
                'filter_desc': filter_desc,
                'filter_target': filter_target
            }
            # Tạo dict filters để truyền vào hàm DB (chỉ chứa filter có giá trị và loại bỏ giá trị default '__all__')
            db_filters = {k.replace('filter_', ''): v for k, v in active_filters.items() if v and (k != 'filter_target' or v != '__all__')}

            # 2. Gọi hàm DB mới để lấy dữ liệu trang và tổng số
            macros_page, total_items = db.get_all_macro_definitions(
                filters=db_filters,
                page=page,
                per_page=PER_PAGE_MACROS
            )

            if macros_page is None or total_items is None:
                 flash("Lỗi khi tải danh sách định nghĩa macro từ CSDL.", "error")
                 macros_page = []; total_items = 0
                 pagination = None
            else:
                 # 3. Tính toán thông tin phân trang
                 if total_items > 0:
                     total_pages = ceil(total_items / PER_PAGE_MACROS)
                     if page > total_pages and total_pages > 0: page = total_pages # Đảm bảo page hợp lệ
                     pagination = {
                        'page': page, 'per_page': PER_PAGE_MACROS, 'total_items': total_items,
                        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
                        'prev_num': page - 1 if page > 1 else None,
                        'next_num': page + 1 if page < total_pages else None
                     }
                 else: # total_items = 0
                     pagination = {'page': 1, 'per_page': PER_PAGE_MACROS, 'total_items': 0, 'total_pages': 0, 'has_prev': False, 'has_next': False}

            # 4. Lấy danh sách app_targets cho dropdown (đã định nghĩa ở trên)

        except Exception as e:
            print(f"Lỗi nghiêm trọng load macro definitions: {e}")
            flash("Lỗi không mong muốn khi tải dữ liệu.", "error")
            macros_page = []; pagination = None; app_targets = []

    # 5. Render template với đầy đủ dữ liệu
    return render_template('admin_macro_definitions.html',
                           title=title,
                           macros=macros_page,       # Danh sách macro của trang này
                           pagination=pagination,    # Thông tin phân trang
                           filters=active_filters,   # Filter đang áp dụng để điền lại form
                           app_targets=app_targets)


@admin_bp.route('/macro-definitions/add', methods=['GET', 'POST'])
def add_macro_definition_view():
    """Thêm định nghĩa Macro Code mới."""
    # ... (Code đã cung cấp ở lần trước) ...
    title="Thêm Định nghĩa Macro Mới"
    app_targets = ['system', 'generic', 'tiktok', 'zalo', 'facebook'] # Hoặc lấy động từ DB
    if request.method == 'POST':
        if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_macro_definitions'))
        macro_code = request.form.get('macro_code', '').strip()
        description = request.form.get('description', '').strip()
        app_target = request.form.get('app_target', '').strip()
        params_schema_str = request.form.get('params_schema', '').strip()
        notes = request.form.get('notes', '').strip()
        if not macro_code:
            flash("Macro Code là bắt buộc.", "warning")
            return render_template('admin_add_macro_definition.html', title=title, app_targets=app_targets, current_data=request.form), 400
        success, error_msg = db.add_macro_definition(macro_code, description, app_target, params_schema_str, notes)
        if success:
            flash(f"Thêm định nghĩa macro '{macro_code}' thành công!", 'success')
            return redirect(url_for('admin.view_macro_definitions'))
        else:
            flash(f"Thêm thất bại: {error_msg}", 'error')
            return render_template('admin_add_macro_definition.html', title=title, app_targets=app_targets, current_data=request.form)
    return render_template('admin_add_macro_definition.html', title=title, app_targets=app_targets)


@admin_bp.route('/macro-definitions/<path:macro_code>/edit', methods=['GET', 'POST']) # Dùng <path:> để xử lý '/' trong macro code nếu có
def edit_macro_definition_view(macro_code):
    """Sửa định nghĩa Macro Code."""
    # ... (Code đã cung cấp ở lần trước, nhớ dùng current_data khi POST lỗi) ...
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_macro_definitions'))
    macro_def = db.get_macro_definition(macro_code)
    if not macro_def:
        flash(f"Không tìm thấy Macro Code '{macro_code}'.", "error")
        return redirect(url_for('admin.view_macro_definitions'))
    title = f"Sửa Định nghĩa Macro '{macro_code}'"
    app_targets = ['system', 'generic', 'tiktok', 'zalo', 'facebook']
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        app_target = request.form.get('app_target', '').strip()
        params_schema_str = request.form.get('params_schema', '').strip()
        notes = request.form.get('notes', '').strip()
        success, error_msg = db.update_macro_definition(macro_code, description, app_target, params_schema_str, notes)
        if success:
            flash(f"Cập nhật định nghĩa macro '{macro_code}' thành công!", 'success')
            return redirect(url_for('admin.view_macro_definitions'))
        else:
            flash(f"Cập nhật thất bại: {error_msg}", 'error')
            current_data = request.form.copy()
            current_data['macro_code'] = macro_code
            return render_template('admin_edit_macro_definition.html', title=title, macro_def=macro_def, app_targets=app_targets, current_data=current_data)
    return render_template('admin_edit_macro_definition.html', title=title, macro_def=macro_def, app_targets=app_targets)


@admin_bp.route('/macro-definitions/<path:macro_code>/delete', methods=['POST'])
def delete_macro_definition_view(macro_code):
    """Xóa định nghĩa Macro Code."""
    # ... (Code đã cung cấp ở lần trước) ...
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_macro_definitions'))
    success, error_msg = db.delete_macro_definition(macro_code)
    if success: flash(f"Đã xóa định nghĩa macro '{macro_code}'.", 'success')
    else: flash(f"Xóa thất bại: {error_msg}", 'error')
    return redirect(url_for('admin.view_macro_definitions'))


# --- Sửa Route Thêm/Sửa Transition ---


@admin_bp.route('/transitions/<int:transition_id>/edit', methods=['GET', 'POST'])
def edit_transition(transition_id):
    # ... (Phần lấy transition details và strategy_id_redirect giữ nguyên) ...
    VALID_CONDITION_TYPES = [
        '', # Luôn chạy (mặc định)
        'current_stage_equals',
        'element_exists_text',
        'element_exists_id',
        'variable_equals' # Ví dụ
        # Thêm các loại điều kiện khác client có thể kiểm tra
    ]
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_strategies'))
    transition = db.get_transition_details(transition_id) # Hàm này đã sửa
    if not transition: flash(f"Ko tìm thấy transition ID {transition_id}.", "error"); return redirect(url_for('admin.view_strategies'))
    strategy_id_redirect = transition.get('strategy_id')
    if not strategy_id_redirect: flash(f"Ko tìm thấy strategy gốc cho transition {transition_id}.", "error"); return redirect(url_for('admin.view_strategies'))

    # --- Lấy dữ liệu dropdown (cho cả GET và POST lỗi) ---
    strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
    all_stages = db.get_all_stages() or []
    all_macros = db.get_all_macro_definitions() or [] # <<< Lấy macros

    if request.method == 'POST':
        # ... (Lấy current_stage_id, user_intent, condition_logic, next_stage_id, priority_str như cũ) ...
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_logic = request.form.get('condition_logic')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        # <<< Lấy macro_code và params_str >>>
        action_macro_code = request.form.get('action_macro_code')
        action_params_str = request.form.get('action_params_str', '{}')

        # <<< Validate >>>
        if not current_stage_id or not user_intent:
             flash("Current Stage và User Intent là bắt buộc.", "warning")
             return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id} (Lỗi)",
                                    transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_macros=all_macros, # <<< Truyền macros
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form), 400
        try: priority = int(priority_str)
        except ValueError:
             flash("Priority phải là số nguyên.", "warning")
             return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id} (Lỗi)",
                                    transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                    all_macros=all_macros, valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form), 400

        # <<< Gọi hàm db.update_transition đã sửa >>>
        success, error_msg = db.update_transition(
            transition_id, current_stage_id, user_intent, condition_logic, next_stage_id, priority,
            action_macro_code, action_params_str
        )

        if success:
            flash('Cập nhật transition thành công!', 'success')
            return redirect(url_for('admin.view_strategy_stages', strategy_id=strategy_id_redirect))
        else:
            flash(f'Cập nhật transition thất bại: {error_msg}', 'error')
            # <<< Render lại form với lỗi, truyền đủ dữ liệu dropdown và current_data >>>
            return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id} (Lỗi DB)",
                                   transition=transition, strategy_stages=strategy_stages, all_stages=all_stages,
                                   all_macros=all_macros, valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form)

    # <<< GET request: Truyền đủ dữ liệu dropdown >>>
    return render_template('admin_edit_transition.html', title=f"Sửa Transition {transition_id}",
                           transition=transition, # Đã chứa action_macro_code và action_params_str
                           strategy_stages=strategy_stages,
                           all_stages=all_stages,
                           all_macros=all_macros, # <<< Truyền macros
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)

@admin_bp.route('/transitions/add-control', methods=['GET', 'POST'])
def add_transition_control():
    """Thêm transition cho Control Strategy (dùng Macro Code, Conditions, Loops)."""
    strategy_id = request.args.get('strategy_id')
    current_stage_id_prefill = request.args.get('current_stage_id')

    # --- Kiểm tra ban đầu ---
    if not strategy_id:
        flash("Cần cung cấp strategy_id.", "error")
        return redirect(url_for('admin.view_strategies_control'))
    if not db:
         flash("Lỗi DB.", "error")
         return redirect(url_for('admin.view_strategies_control'))

    # --- Lấy dữ liệu cần thiết cho form (cho cả GET và POST lỗi) ---
    strategy_details = None
    strategy_stages = []
    all_stages = []
    all_macros = []
    try:
        strategy_details = db.get_strategy_details(strategy_id)
        if not strategy_details or strategy_details.get('strategy_type') != 'control':
            flash("Strategy không hợp lệ hoặc không phải loại 'control'.", "error")
            return redirect(url_for('admin.view_strategies_control'))
        strategy_stages = db.get_stages_for_strategy(strategy_id) or []
        all_stages = db.get_all_stages() or []
        temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000) # Lấy nhiều cho dropdown
        all_macros = temp_macros or []
    except Exception as e:
        flash(f"Lỗi tải dữ liệu cho form: {e}", "error")
        # Vẫn tiếp tục để render form rỗng nếu có thể

    title = f"Thêm Control Transition cho Strategy {strategy_id}"

    # --- Xử lý POST ---
    if request.method == 'POST':
        # --- Lấy dữ liệu cơ bản ---
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type')
        condition_value = request.form.get('condition_value')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        action_macro_code = request.form.get('action_macro_code')
        action_params_str = request.form.get('action_params_str', '{}')
        form_strategy_id = request.form.get('strategy_id') # Lấy từ hidden input

        # --- Lấy dữ liệu LOOP mới từ form ---
        loop_type = request.form.get('loop_type', '').strip()
        loop_count_str = request.form.get('loop_count', '').strip()
        loop_condition_type = request.form.get('loop_condition_type', '').strip()
        loop_condition_value = request.form.get('loop_condition_value', '').strip()
        loop_target_selector_str = request.form.get('loop_target_selector', '').strip() # Chưa dùng tới
        loop_variable_name = request.form.get('loop_variable_name', '').strip() # Chưa dùng tới

        # --- Validate ---
        errors = []
        if not current_stage_id: errors.append("Current Stage là bắt buộc.")
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        if not form_strategy_id or form_strategy_id != strategy_id: errors.append("Lỗi Strategy ID.")
        priority = 0 # Default
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")

        # Validate JSON Params
        params_dict = {}
        if action_params_str and action_params_str.strip() and action_params_str != '{}':
             try:
                  params_dict = json.loads(action_params_str)
                  if not isinstance(params_dict, dict): errors.append("Action Params phải là JSON object.")
             except json.JSONDecodeError: errors.append("Action Params JSON không hợp lệ.")

        # <<< Validate dữ liệu Loop >>>
        loop_count = None
        if loop_type == 'repeat_n':
            if not loop_count_str: errors.append("Cần nhập Số lần lặp khi chọn loại 'Repeat N'.")
            else:
                try: loop_count = int(loop_count_str); assert loop_count >= 1
                except (ValueError, AssertionError): errors.append("Số lần lặp phải là số nguyên lớn hơn 0.")
        elif loop_type == 'while_condition_met':
            if not loop_condition_type: errors.append("Cần chọn Điều kiện Lặp khi chọn loại 'While'.")
            # Condition value có thể rỗng tùy loại điều kiện
        # elif loop_type == 'for_each_element': # Tạm thời chưa validate
        #     if not loop_target_selector_str: errors.append("Cần nhập Target Selector cho 'For Each'.")
        #     else: try: json.loads(loop_target_selector_str) # Chỉ check JSON
        #           except json.JSONDecodeError: errors.append("Target Selector không phải JSON hợp lệ.")
        #     if not loop_variable_name: errors.append("Cần nhập Tên biến lưu Element cho 'For Each'.")
        elif loop_type: # Nếu chọn loại loop khác mà chưa hỗ trợ
            errors.append(f"Loại vòng lặp '{loop_type}' chưa được hỗ trợ.")


        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # <<< SỬA RENDER_TEMPLATE: Truyền đủ dữ liệu dropdown và current_data >>>
            return render_template('admin_add_transition_control.html',
                                   title=title + " (Lỗi)",
                                   strategy_id=strategy_id,
                                   current_stage_id_prefill=current_stage_id, # Giữ lại stage đã chọn
                                   strategy_stages=strategy_stages,
                                   all_stages=all_stages,
                                   all_macros=all_macros,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                   valid_condition_types=VALID_CONDITION_TYPES,
                                   current_data=request.form), 400 # current_data chứa cả loop_* values

        # --- Gọi hàm DB (đã cập nhật ở bước trước) ---
        try:
            # <<< Truyền TẤT CẢ tham số, bao gồm cả loop_* >>>
            success, error_msg = db.add_new_transition(
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                next_stage_id=next_stage_id if next_stage_id else None,
                priority=priority,
                response_template_ref=None, # Control không dùng
                action_macro_code=action_macro_code if action_macro_code else None,
                action_params_str=action_params_str if (action_params_str and action_params_str.strip() and action_params_str != '{}') else None,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                # --- Truyền các giá trị loop ---
                loop_type=loop_type if loop_type else None,
                loop_count=loop_count, # Truyền giá trị int đã chuyển đổi (hoặc None)
                loop_condition_type=loop_condition_type if loop_condition_type else None,
                loop_condition_value=loop_condition_value if loop_condition_value else None,
                loop_target_selector_str=None, # Tạm thời chưa hỗ trợ lưu
                loop_variable_name=None # Tạm thời chưa hỗ trợ lưu
            )

            if success:
                flash('Thêm control transition (kèm loop config nếu có) thành công!', 'success')
                return redirect(url_for('admin.view_strategy_stages_control', strategy_id=strategy_id))
            else:
                flash(f'Thêm control transition thất bại: {error_msg or "Lỗi."}', 'error')
                # <<< SỬA RENDER_TEMPLATE: Truyền đủ dữ liệu dropdown và current_data >>>
                return render_template('admin_add_transition_control.html',
                                       title=title + " (Lỗi DB)",
                                       strategy_id=strategy_id,
                                       current_stage_id_prefill=current_stage_id,
                                       strategy_stages=strategy_stages,
                                       all_stages=all_stages,
                                       all_macros=all_macros,
                                       valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                       valid_condition_types=VALID_CONDITION_TYPES,
                                       current_data=request.form)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi thêm control transition: {e}")
             flash(f"Lỗi không mong muốn: {e}", "error")
             # <<< SỬA RENDER_TEMPLATE: Truyền đủ dữ liệu dropdown và current_data >>>
             return render_template('admin_add_transition_control.html',
                                    title=title + " (Lỗi Exception)",
                                    strategy_id=strategy_id,
                                    current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages,
                                    all_stages=all_stages,
                                    all_macros=all_macros,
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                    valid_condition_types=VALID_CONDITION_TYPES,
                                    current_data=request.form)


    # --- GET request ---
    # <<< SỬA RENDER_TEMPLATE: Truyền đủ dữ liệu dropdown >>>
    return render_template('admin_add_transition_control.html',
                           title=title,
                           strategy_id=strategy_id,
                           current_stage_id_prefill=current_stage_id_prefill,
                           strategy_stages=strategy_stages,
                           all_stages=all_stages,
                           all_macros=all_macros,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION,
                           valid_condition_types=VALID_CONDITION_TYPES)



@admin_bp.route('/transitions/<int:transition_id>/edit-control', methods=['GET', 'POST'])
def edit_transition_control(transition_id):
    """Sửa một Control Transition, bao gồm cả các trường loop."""
    if not db: flash("Lỗi DB.", "error"); return redirect(url_for('admin.view_strategies_control'))

    # --- Lấy dữ liệu gốc của transition (cho cả GET và POST lỗi) ---
    # Hàm get_transition_details đã được sửa để lấy cả strategy_id và loop_* fields
    transition = db.get_transition_details(transition_id)
    if not transition:
        flash(f"Không tìm thấy transition ID {transition_id}.", "error")
        return redirect(url_for('admin.view_strategies_control'))

    strategy_id = transition.get('strategy_id')
    if not strategy_id: # Should not happen if data is consistent
        flash("Lỗi: Transition không có strategy_id liên kết.", "error")
        return redirect(url_for('admin.view_strategies_control'))

    # Kiểm tra lại type cho chắc chắn
    strategy_details = db.get_strategy_details(strategy_id)
    if not strategy_details or strategy_details.get('strategy_type') != 'control':
         flash("Transition này không thuộc về một Control Strategy hợp lệ.", "error")
         return redirect(url_for('admin.view_strategies_control'))

    # --- Lấy dữ liệu cho các dropdown (cho cả GET và POST lỗi) ---
    strategy_stages = []
    all_stages = []
    all_macros = []
    try:
        strategy_stages = db.get_stages_for_strategy(strategy_id) or []
        all_stages = db.get_all_stages() or []
        temp_macros, _ = db.get_all_macro_definitions(page=1, per_page=1000)
        all_macros = temp_macros or []
    except Exception as e:
        flash(f"Lỗi tải dữ liệu form: {e}", "error")

    title = f"Sửa Control Transition #{transition_id}"
    # URL Hủy sẽ trỏ về trang chi tiết control strategy
    cancel_url = url_for('admin.view_strategy_stages_control', strategy_id=strategy_id)

    # --- Xử lý POST ---
    if request.method == 'POST':
        # --- Lấy dữ liệu cơ bản ---
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        condition_type = request.form.get('condition_type')
        condition_value = request.form.get('condition_value')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        action_macro_code = request.form.get('action_macro_code')
        action_params_str = request.form.get('action_params_str', '{}')

        # --- Lấy dữ liệu LOOP mới từ form ---
        loop_type = request.form.get('loop_type', '').strip()
        loop_count_str = request.form.get('loop_count', '').strip()
        loop_condition_type = request.form.get('loop_condition_type', '').strip()
        loop_condition_value = request.form.get('loop_condition_value', '').strip()
        loop_target_selector_str = request.form.get('loop_target_selector', '').strip() # Chưa dùng
        loop_variable_name = request.form.get('loop_variable_name', '').strip() # Chưa dùng

        # --- Validate (tương tự như add) ---
        errors = []
        if not current_stage_id: errors.append("Current Stage là bắt buộc.")
        if not user_intent: errors.append("User Intent/Trigger là bắt buộc.")
        priority = 0
        try: priority = int(priority_str)
        except ValueError: errors.append("Priority phải là số nguyên.")
        # Validate JSON Params
        params_dict = {}
        if action_params_str and action_params_str.strip() and action_params_str != '{}':
             try:
                  params_dict = json.loads(action_params_str)
                  if not isinstance(params_dict, dict): errors.append("Action Params phải là JSON object.")
             except json.JSONDecodeError: errors.append("Action Params JSON không hợp lệ.")

        # <<< Validate dữ liệu Loop >>>
        loop_count = None
        if loop_type == 'repeat_n':
            if not loop_count_str: errors.append("Cần nhập Số lần lặp khi chọn loại 'Repeat N'.")
            else:
                try: loop_count = int(loop_count_str); assert loop_count >= 1
                except (ValueError, AssertionError): errors.append("Số lần lặp phải là số nguyên lớn hơn 0.")
        elif loop_type == 'while_condition_met':
            if not loop_condition_type: errors.append("Cần chọn Điều kiện Lặp khi chọn loại 'While'.")
        elif loop_type: errors.append(f"Loại vòng lặp '{loop_type}' chưa được hỗ trợ.")

        # Nếu có lỗi validation
        if errors:
            for error in errors: flash(error, "warning")
            # <<< SỬA RENDER_TEMPLATE: Truyền đủ dropdowns và current_data >>>
            return render_template('admin_edit_transition_control.html',
                                   title=title + " (Lỗi)",
                                   transition=transition, # Dữ liệu gốc để lấy ID
                                   strategy_id=strategy_id, # <<< Cần truyền strategy_id
                                   cancel_url=cancel_url, # <<< Truyền cancel_url
                                   strategy_stages=strategy_stages,
                                   all_stages=all_stages,
                                   all_macros=all_macros,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                   valid_condition_types=VALID_CONDITION_TYPES,
                                   current_data=request.form), 400 # current_data chứa cả loop_*

        # --- Gọi hàm DB Update (đã cập nhật ở bước trước) ---
        try:
            # <<< Truyền TẤT CẢ tham số, bao gồm loop_* >>>
            success, error_msg = db.update_transition(
                transition_id=transition_id, # ID của transition đang sửa
                current_stage_id=current_stage_id,
                user_intent=user_intent,
                next_stage_id=next_stage_id if next_stage_id else None,
                priority=priority,
                response_template_ref=None, # Control không dùng
                action_macro_code=action_macro_code if action_macro_code else None,
                action_params_str=action_params_str if (action_params_str and action_params_str.strip() and action_params_str != '{}') else None,
                condition_type=condition_type if condition_type else None,
                condition_value=condition_value if condition_value else None,
                # --- Truyền các giá trị loop ---
                loop_type=loop_type if loop_type else None,
                loop_count=loop_count,
                loop_condition_type=loop_condition_type if loop_condition_type else None,
                loop_condition_value=loop_condition_value if loop_condition_value else None,
                loop_target_selector_str=None, # Tạm thời chưa hỗ trợ
                loop_variable_name=None # Tạm thời chưa hỗ trợ
            )

            if success:
                flash(f'Cập nhật transition #{transition_id} thành công!', 'success')
                # Redirect về trang chi tiết control strategy
                return redirect(url_for('admin.view_strategy_stages_control', strategy_id=strategy_id))
            else:
                flash(f'Cập nhật transition thất bại: {error_msg or "Lỗi không xác định."}', 'error')
                 # <<< SỬA RENDER_TEMPLATE: Truyền đủ dropdowns và current_data >>>
                return render_template('admin_edit_transition_control.html',
                                       title=title + " (Lỗi DB)",
                                       transition=transition, # Dữ liệu gốc
                                       strategy_id=strategy_id,
                                       cancel_url=cancel_url,
                                       strategy_stages=strategy_stages,
                                       all_stages=all_stages,
                                       all_macros=all_macros,
                                       valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                       valid_condition_types=VALID_CONDITION_TYPES,
                                       current_data=request.form)
        except Exception as e:
             print(f"Lỗi nghiêm trọng khi sửa control transition {transition_id}: {e}")
             flash(f"Lỗi không mong muốn: {e}", "error")
             # <<< SỬA RENDER_TEMPLATE: Truyền đủ dropdowns và current_data >>>
             return render_template('admin_edit_transition_control.html',
                                    title=title + " (Lỗi Exception)",
                                    transition=transition, # Dữ liệu gốc
                                    strategy_id=strategy_id,
                                    cancel_url=cancel_url,
                                    strategy_stages=strategy_stages,
                                    all_stages=all_stages,
                                    all_macros=all_macros,
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION,
                                    valid_condition_types=VALID_CONDITION_TYPES,
                                    current_data=request.form)

    # --- GET request ---
    # transition, strategy_stages, all_stages, all_macros đã được lấy ở trên
    # <<< SỬA RENDER_TEMPLATE: Truyền đủ dropdowns và cancel_url >>>
    return render_template('admin_edit_transition_control.html',
                           title=title,
                           transition=transition, # Đã chứa các giá trị loop_* từ db
                           strategy_id=strategy_id,
                           cancel_url=cancel_url,
                           strategy_stages=strategy_stages,
                           all_stages=all_stages,
                           all_macros=all_macros,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION,
                           valid_condition_types=VALID_CONDITION_TYPES)

# --- Routes cho LANGUAGE Transitions ---

@admin_bp.route('/transitions/add-language', methods=['GET', 'POST'])
def add_transition_language():
    """Thêm transition cho Language Strategy (dùng Template Ref)."""
    strategy_id = request.args.get('strategy_id')
    current_stage_id_prefill = request.args.get('current_stage_id')
    if not strategy_id: flash("Cần strategy_id.", "error"); return redirect(url_for('admin.view_strategies_language'))

    # Kiểm tra type của strategy
    strategy_details = db.get_strategy_details(strategy_id)
    if not strategy_details or strategy_details.get('strategy_type') != 'language':
         flash("Strategy không hợp lệ hoặc không phải loại 'language'.", "error")
         return redirect(url_for('admin.view_strategies_language'))

    # Lấy dữ liệu cho form (chỉ cần stages và templates)
    strategy_stages = db.get_stages_for_strategy(strategy_id) or []
    all_stages = db.get_all_stages() or []
    all_templates = db.get_all_template_refs() or [] # Lấy danh sách template refs

    if request.method == 'POST':
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        response_template_ref = request.form.get('response_template_ref') # <<< Lấy template ref

        # Validate
        if not current_stage_id or not user_intent:
             flash("Current Stage và User Intent là bắt buộc.", "warning")
             return render_template('admin_add_transition_language.html', title="Thêm Language Transition (Lỗi)",
                                    strategy_id=strategy_id, current_stage_id_prefill=current_stage_id,
                                    strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                                    valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form), 400
        try: priority = int(priority_str)
        except ValueError: flash("Priority phải là số.", "warning"); #... return render_template ...

        # Gọi hàm DB (truyền None cho các trường control)
        success, error_msg = db.add_new_transition(
            current_stage_id, user_intent, next_stage_id, priority,
            response_template_ref if response_template_ref else None, # <<< Truyền template ref
            None, None, None, None # action_macro_code, params, condition = None
        )

        if success:
            flash('Thêm language transition thành công!', 'success')
            # Redirect về trang chi tiết language
            return redirect(url_for('admin.view_strategy_stages_language', strategy_id=strategy_id))
        else:
            flash(f'Thêm language transition thất bại: {error_msg or "Lỗi."}', 'error')
            # Render lại form language
            return render_template('admin_add_transition_language.html', title="Thêm Language Transition (Lỗi DB)",
                                   strategy_id=strategy_id, current_stage_id_prefill=current_stage_id,
                                   strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form)

    # GET request
    return render_template('admin_add_transition_language.html', title=f"Thêm Language Transition cho Strategy {strategy_id}",
                           strategy_id=strategy_id, current_stage_id_prefill=current_stage_id_prefill,
                           strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)


@admin_bp.route('/transitions/<int:transition_id>/edit-language', methods=['GET', 'POST'])
def edit_transition_language(transition_id):
    """Sửa transition cho Language Strategy."""
    transition = db.get_transition_details(transition_id) # Hàm này đã lấy cả template_ref
    if not transition: flash(f"Ko tìm thấy transition ID {transition_id}.", "error"); return redirect(url_for('admin.view_strategies_language'))
    strategy_id_redirect = transition.get('strategy_id')
    strategy_details = db.get_strategy_details(strategy_id_redirect)
    if not strategy_details or strategy_details.get('strategy_type') != 'language':
         flash("Transition này không thuộc về Language Strategy.", "error")
         return redirect(url_for('admin.view_strategies_language'))

    # Lấy dữ liệu dropdown
    strategy_stages = db.get_stages_for_strategy(strategy_id_redirect) or []
    all_stages = db.get_all_stages() or []
    all_templates = db.get_all_template_refs() or []

    if request.method == 'POST':
        current_stage_id = request.form.get('current_stage_id')
        user_intent = request.form.get('user_intent')
        next_stage_id = request.form.get('next_stage_id')
        priority_str = request.form.get('priority', '0')
        response_template_ref = request.form.get('response_template_ref') # <<< Lấy template ref

        # Validate
        if not current_stage_id or not user_intent: flash("Current Stage, Intent bắt buộc.", "warning"); #... return render_template ...
        try: priority = int(priority_str)
        except ValueError: flash("Priority phải là số.", "warning"); #... return render_template ...

        # Gọi hàm update DB (truyền None cho các trường control)
        success, error_msg = db.update_transition(
            transition_id, current_stage_id, user_intent, next_stage_id, priority,
            response_template_ref if response_template_ref else None, # <<< Truyền template ref
            None, None, None, None # action_macro_code, params, condition = None
        )

        if success:
            flash('Cập nhật language transition thành công!', 'success')
            return redirect(url_for('admin.view_strategy_stages_language', strategy_id=strategy_id_redirect))
        else:
            flash(f'Cập nhật language transition thất bại: {error_msg or "Lỗi."}', 'error')
            # Render lại form language edit
            return render_template('admin_edit_transition_language.html', title=f"Sửa Language Transition {transition_id} (Lỗi DB)",
                                   transition=transition, strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                                   valid_intents=VALID_INTENTS_FOR_TRANSITION, current_data=request.form)

    # GET request
    return render_template('admin_edit_transition_language.html', title=f"Sửa Language Transition {transition_id}",
                           transition=transition, # Đã chứa response_template_ref
                           strategy_stages=strategy_stages, all_stages=all_stages, all_templates=all_templates,
                           valid_intents=VALID_INTENTS_FOR_TRANSITION)


# --- Route Xóa Transition (Có thể dùng chung) ---
# app/admin_routes.py


@admin_bp.route('/transitions/<int:transition_id>/delete', methods=['POST'])
def delete_transition(transition_id):
    """Xóa một transition và redirect về trang chi tiết strategy phù hợp."""
    print(f"\n--- DEBUG (delete_transition): Received request for transition ID: {transition_id} ---")
    strategy_id_redirect = None
    strategy_type_redirect = 'unknown' # Khởi tạo là unknown
    redirect_endpoint = None # Khởi tạo endpoint

    # --- Cố gắng lấy thông tin STRATEGY GỐC TRƯỚC KHI XÓA ---
    try:
        transition_details = db.get_transition_details(transition_id) # Hàm này cần trả về dict có strategy_id
        print(f"DEBUG (delete_transition): Fetched transition_details: {transition_details}")

        if transition_details:
            strategy_id_redirect = transition_details.get('strategy_id')
            print(f"DEBUG (delete_transition): Found parent strategy_id: {strategy_id_redirect}")
            if strategy_id_redirect:
                 # Lấy thêm thông tin strategy để biết type
                 strategy_info = db.get_strategy_details(strategy_id_redirect)
                 print(f"DEBUG (delete_transition): Fetched strategy_info: {strategy_info}")
                 if strategy_info:
                      strategy_type_redirect = strategy_info.get('strategy_type', 'unknown') # Lấy type
                      print(f"DEBUG (delete_transition): Determined strategy_type: {strategy_type_redirect}")
                      # Xác định endpoint chi tiết dựa trên type
                      if strategy_type_redirect == 'control':
                           redirect_endpoint = 'admin.view_strategy_stages_control'
                      elif strategy_type_redirect == 'language':
                           redirect_endpoint = 'admin.view_strategy_stages_language'
                      else: # Nếu strategy_type không xác định
                           print(f"WARN (delete_transition): Unknown strategy type '{strategy_type_redirect}'. Cannot redirect to detail.")
                           redirect_endpoint = None
                 else: # Không tìm thấy strategy details
                      print(f"WARN (delete_transition): Could not find strategy details for ID '{strategy_id_redirect}'. Cannot redirect to detail.")
                      strategy_id_redirect = None # Đặt lại ID nếu strategy không tồn tại
                      # Giữ lại strategy_type_redirect='unknown'
            else: # Transition không có strategy_id
                 print(f"WARN (delete_transition): Transition {transition_id} has no associated strategy_id.")
                 strategy_id_redirect = None
        else: # Không tìm thấy transition
            print(f"ERROR (delete_transition): Could not find transition details for ID {transition_id}. Cannot determine redirect target.")
            strategy_id_redirect = None

    except Exception as e_fetch:
        print(f"ERROR (delete_transition): Exception while fetching details before delete: {e_fetch}")
        print(traceback.format_exc())
        strategy_id_redirect = None # Reset nếu có lỗi khi fetch

    # --- Thực hiện Xóa ---
    delete_success = False # Đặt tên biến khác để tránh nhầm lẫn
    error_msg_delete = None
    try:
        # Hàm db.delete_transition nên trả về tuple (success, error_msg)
        delete_success, error_msg_delete = db.delete_transition(transition_id)
        if delete_success:
            flash(f"Đã xóa transition ID {transition_id}.", 'success')
            print(f"INFO (delete_transition): Successfully deleted transition {transition_id}.")
        else:
            flash(f"Xóa transition ID {transition_id} thất bại: {error_msg_delete or 'ID không tồn tại?'}", 'error')
            print(f"ERROR (delete_transition): Failed to delete transition {transition_id}: {error_msg_delete}")
    except Exception as e_delete:
        print(f"Lỗi nghiêm trọng khi xóa transition {transition_id}: {e_delete}")
        print(traceback.format_exc())
        flash(f"Lỗi không mong muốn khi xóa transition: {e_delete}", "error")

    # --- Logic Chuyển hướng ---
    # Ưu tiên redirect về trang chi tiết nếu có đủ thông tin
    if strategy_id_redirect and redirect_endpoint:
        print(f"INFO (delete_transition): Redirecting to detail page: {redirect_endpoint} for strategy {strategy_id_redirect}")
        # <<<< REDIRECT VỀ TRANG CHI TIẾT ĐÚNG >>>>
        return redirect(url_for(redirect_endpoint, strategy_id=strategy_id_redirect))
    else:
        # Nếu không đủ thông tin về trang chi tiết, fallback về trang danh sách
        print(f"WARN (delete_transition): Fallback redirect needed. strategy_id={strategy_id_redirect}, type={strategy_type_redirect}, detail_endpoint={redirect_endpoint}")
        flash("Đã xóa transition. Không thể xác định chính xác trang chi tiết để quay lại.", "info")
        # <<< FALLBACK VỀ TRANG DANH SÁCH PHÙ HỢP HƠN >>>
        if strategy_type_redirect == 'control':
             print("INFO (delete_transition): Fallback redirecting to Control List.")
             return redirect(url_for('admin.view_strategies_control'))
        else: # Default, language, hoặc unknown type -> về language list
             print("INFO (delete_transition): Fallback redirecting to Language List.")
             return redirect(url_for('admin.view_strategies_language'))

# --- ROUTE MỚI ĐỂ XEM JSON PACKAGE ---
@admin_bp.route('/strategies/<strategy_id>/package', methods=['GET'])
def view_strategy_package_json(strategy_id):
    """
    API Endpoint trả về Gói Chiến lược JSON đã biên dịch cho một Control Strategy.
    """
    if not db:
        return jsonify({"error": "Database module not available"}), 500
    if not phone_controller:
        return jsonify({"error": "Phone controller module not available"}), 500

    # Kiểm tra xem strategy có tồn tại và là loại 'control' không
    strategy_details = db.get_strategy_details(strategy_id)
    if not strategy_details:
        return jsonify({"error": f"Strategy ID '{strategy_id}' not found."}), 404
    if strategy_details.get('strategy_type') != 'control':
        return jsonify({"error": f"Strategy '{strategy_id}' is not a 'control' strategy."}), 400

    # Gọi hàm biên dịch gói chiến lược từ phone controller
    try:
        strategy_package = phone_controller.compile_strategy_package(strategy_id)

        if strategy_package:
            # Trả về JSON thành công
            # jsonify sẽ tự động đặt header Content-Type là application/json
            return jsonify(strategy_package)
        else:
            # Lỗi xảy ra trong quá trình biên dịch
            print(f"ERROR: compile_strategy_package returned None for strategy {strategy_id}")
            return jsonify({"error": "Failed to compile strategy package."}), 500

    except Exception as e:
        print(f"ERROR generating strategy package JSON for {strategy_id}: {e}")
        print(traceback.format_exc())
        return jsonify({"error": f"Internal server error: {e}"}), 500


