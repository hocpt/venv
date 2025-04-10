# app/admin_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
# Import module database đúng với cấu trúc dự án
try:
    from . import database as db
except ImportError:
    import database as db  # Khi chạy file này riêng

admin_bp = Blueprint(
    'admin',
    __name__,
    static_folder='../static',
    template_folder='../templates',
    url_prefix='/admin'
)

# === Dashboard ===
@admin_bp.route('/')
def index():
    return render_template('admin_index.html', title="Admin Dashboard")


# === Quản lý Luật ===
@admin_bp.route('/rules')
def view_rules():
    try:
        rules = db.get_all_rules()
    except Exception as e:
        print(f"Lỗi load rules: {e}")
        flash("Không thể tải danh sách luật.", "error")
        rules = []
    return render_template('admin_rules.html', title="Quản lý Luật", rules=rules)


@admin_bp.route('/rules/add', methods=['GET', 'POST'],endpoint='add_rule_form')
def add_rule():
    if request.method == 'POST':
        try:
            data = {
                "keywords": request.form.get('keywords'),
                "category": request.form.get('category'),
                "template_ref": request.form.get('template_ref') or None,
                "priority": request.form.get('priority', type=int, default=0),
                "notes": request.form.get('notes')
            }
            success = db.add_new_rule(**data)
            flash('Thêm luật thành công!' if success else 'Thêm luật thất bại!', 'success' if success else 'error')
        except Exception as e:
            print(f"Lỗi khi thêm luật: {e}")
            flash("Đã xảy ra lỗi khi thêm luật.", "error")
        return redirect(url_for('admin.view_rules'))

    # GET method
    try:
        templates = db.get_all_template_refs()
    except Exception as e:
        print(f"Lỗi load templates: {e}")
        templates = []
        flash("Không thể tải danh sách template.", "error")
    return render_template('admin_add_rule.html', title="Thêm Luật Mới", templates=templates)


@admin_bp.route('/rules/<int:rule_id>/edit', methods=['GET', 'POST'])
def edit_rule(rule_id):
    if request.method == 'POST':
        try:
            data = {
                "keywords": request.form.get('keywords'),
                "category": request.form.get('category'),
                "template_ref": request.form.get('template_ref') or None,
                "priority": request.form.get('priority', type=int, default=0),
                "notes": request.form.get('notes')
            }
            success = db.update_rule(rule_id, **data)
            flash('Cập nhật thành công!' if success else 'Cập nhật thất bại!', 'success' if success else 'error')
        except Exception as e:
            print(f"Lỗi khi cập nhật luật: {e}")
            flash("Đã xảy ra lỗi khi cập nhật luật.", "error")
        return redirect(url_for('admin.view_rules'))

    # GET method
    try:
        rule = db.get_rule_by_id(rule_id)
        templates = db.get_all_template_refs()
    except Exception as e:
        print(f"Lỗi khi tải dữ liệu sửa luật: {e}")
        flash("Không thể tải dữ liệu sửa luật.", "error")
        return redirect(url_for('admin.view_rules'))

    if not rule:
        flash("Không tìm thấy luật cần sửa.", "error")
        return redirect(url_for('admin.view_rules'))

    return render_template('admin_edit_rule.html', title="Sửa Luật", rule=rule, templates=templates)


@admin_bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
def delete_rule(rule_id):
    try:
        success = db.delete_rule(rule_id)
        flash(f"Đã xóa luật #{rule_id}." if success else f"Xóa thất bại!", 'success' if success else 'error')
    except Exception as e:
        print(f"Lỗi xóa luật: {e}")
        flash("Đã xảy ra lỗi khi xóa luật.", "error")
    return redirect(url_for('admin.view_rules'))


# === Đề xuất AI ===
@admin_bp.route('/suggestions')
def view_suggestions():
    try:
        suggestions = db.get_pending_suggestions()
    except Exception as e:
        print(f"Lỗi load suggestions: {e}")
        suggestions = []
        flash("Không thể tải đề xuất.", "error")
    return render_template('admin_suggestions.html', title="Đề xuất từ AI", suggestions=suggestions)


@admin_bp.route('/suggestions/<int:suggestion_id>/approve', methods=['POST'])
def approve_suggestion(suggestion_id):
    try:
        suggestion = db.get_suggestion_by_id(suggestion_id)
        if not suggestion or suggestion.get('status') != 'pending':
            flash("Đề xuất không hợp lệ.", "warning")
            return redirect(url_for('admin.view_suggestions'))

        template_ref = request.form.get('template_ref') or f"ai_tpl_{suggestion_id}"
        category = request.form.get('category', 'ai_suggested')
        priority = request.form.get('priority', type=int, default=0)

        added_template = db.add_new_template(template_ref, suggestion['suggested_template_text'], category)
        if added_template:
            rule_added = db.add_new_rule(
                keywords=suggestion['suggested_keywords'],
                category=category,
                template_ref=added_template,
                priority=priority,
                notes=f"Phê duyệt từ AI suggestion #{suggestion_id}"
            )
            if rule_added:
                db.update_suggestion_status(suggestion_id, 'approved')
                flash("Đã phê duyệt và thêm luật/template!", "success")
                return redirect(url_for('admin.view_suggestions'))

        flash("Thêm luật/template thất bại.", "error")
    except Exception as e:
        print(f"Lỗi phê duyệt: {e}")
        flash("Đã xảy ra lỗi khi phê duyệt.", "error")

    return redirect(url_for('admin.view_suggestions'))


@admin_bp.route('/suggestions/<int:suggestion_id>/reject', methods=['POST'])
def reject_suggestion(suggestion_id):
    try:
        success = db.update_suggestion_status(suggestion_id, 'rejected')
        flash("Đã từ chối đề xuất." if success else "Từ chối thất bại!", 'info' if success else 'error')
    except Exception as e:
        print(f"Lỗi từ chối đề xuất: {e}")
        flash("Đã xảy ra lỗi khi từ chối.", "error")
    return redirect(url_for('admin.view_suggestions'))

# === TODO: Thêm route quản lý template, strategy, v.v. sau nếu cần ===
