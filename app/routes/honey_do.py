from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required
from app import db
from app.models import HouseTask, HouseProject, HouseExpense, HOUSE_EXPENSE_CATEGORIES
from app.forms import HouseTaskForm
from datetime import datetime, date
from decimal import Decimal

bp = Blueprint('honey_do', __name__, url_prefix='/house/honey-do')


@bp.before_request
@login_required
def require_login():
    pass


def _populate_task_form_choices(form):
    projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    form.project_id.choices = [(0, '— No Project —')] + [(p.id, p.name) for p in projects]


def _expense_json(e):
    return {
        'id': e.id,
        'item': e.item,
        'price_raw': float(e.price),
        'tax_raw': float(e.tax) if e.tax is not None else None,
        'price': float(e.price),
        'tax': float(e.effective_tax),
        'total': float(e.total_with_tax),
        'date': e.expenditure_date.strftime('%Y-%m-%d'),
        'date_display': e.expenditure_date.strftime('%b %-d, %Y'),
        'category': e.category,
        'description': e.description or '',
    }


def _get_project_id_for_task(task):
    if task.project_id:
        return task.project_id
    general = HouseProject.query.filter_by(name='General House Expenses').first()
    if general:
        return general.id
    first = HouseProject.query.filter_by(is_active=True).first()
    return first.id if first else None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    project_id = request.args.get('project_id', type=int)

    query = HouseTask.query.filter_by(is_active=True)

    if project_id is not None:
        if project_id == 0:
            query = query.filter(HouseTask.project_id.is_(None))
        else:
            query = query.filter(HouseTask.project_id == project_id)

    # Completed items always sink to the bottom; active tasks ordered by drag-drop sort_order
    query = query.order_by(
        HouseTask.completed.asc(),
        HouseTask.sort_order.asc(),
        HouseTask.id.asc()
    )

    tasks = query.all()
    all_projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()

    return render_template(
        'house/honey_do.html',
        tasks=tasks,
        all_projects=all_projects,
        filter_project_id=project_id,
        today=date.today(),
        expense_categories=HOUSE_EXPENSE_CATEGORIES,
    )


# ---------------------------------------------------------------------------
# Add / Edit task
# ---------------------------------------------------------------------------

@bp.route('/add', methods=['GET', 'POST'])
def add_task():
    form = HouseTaskForm()
    _populate_task_form_choices(form)

    if form.validate_on_submit():
        max_order = db.session.query(db.func.max(HouseTask.sort_order)).scalar() or 0
        task = HouseTask(
            title=form.title.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            project_id=form.project_id.data if form.project_id.data else None,
            create_date=date.today(),
            start_date=form.start_date.data,
            due_date=form.due_date.data,
            completed_date=form.completed_date.data,
            priority=form.priority.data,
            timeline=form.timeline.data or None,
            sort_order=max_order + 1,
        )
        db.session.add(task)
        db.session.commit()
        flash(f'"{task.title}" added to your honey-do list.', 'success')
        return redirect(url_for('honey_do.index'))

    return render_template('house/honey_do_form.html', form=form, title='Add Task')


@bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    task = HouseTask.query.get_or_404(task_id)
    form = HouseTaskForm(obj=task)
    _populate_task_form_choices(form)

    if form.validate_on_submit():
        task.title = form.title.data.strip()
        task.description = form.description.data.strip() if form.description.data else None
        task.project_id = form.project_id.data if form.project_id.data else None
        task.start_date = form.start_date.data
        task.due_date = form.due_date.data
        task.completed_date = form.completed_date.data
        task.priority = form.priority.data
        task.timeline = form.timeline.data or None
        db.session.commit()
        flash(f'"{task.title}" updated.', 'success')
        return redirect(url_for('honey_do.index'))

    return render_template('house/honey_do_form.html', form=form, title='Edit Task', task=task)


# ---------------------------------------------------------------------------
# Inline AJAX update (from main list page)
# ---------------------------------------------------------------------------

@bp.route('/<int:task_id>/update', methods=['POST'])
def update_task(task_id):
    task = HouseTask.query.get_or_404(task_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400

    task.title = data.get('title', task.title).strip() or task.title
    task.description = data.get('description', '').strip() or None
    pid = int(data['project_id']) if data.get('project_id') else 0
    task.project_id = pid if pid else None
    task.priority = data.get('priority', task.priority)
    task.timeline = data.get('timeline') or None

    # Handle completed toggle
    if 'completed' in data:
        newly_completed = bool(data['completed'])
        if newly_completed and not task.completed:
            task.completed_at = datetime.utcnow()
            task.finish_date = date.today()
        elif not newly_completed and task.completed:
            task.completed_at = None
            task.finish_date = None
        task.completed = newly_completed

    for field in ('start_date', 'due_date', 'completed_date'):
        raw = data.get(field, '')
        if raw:
            try:
                setattr(task, field, datetime.strptime(raw, '%Y-%m-%d').date())
            except ValueError:
                pass
        else:
            setattr(task, field, None)

    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Expenses for a task (AJAX, used by inline panel)
# ---------------------------------------------------------------------------

@bp.route('/<int:task_id>/expenses', methods=['GET'])
def task_expenses(task_id):
    expenses = HouseExpense.query.filter_by(task_id=task_id, is_active=True)\
        .order_by(HouseExpense.expenditure_date.desc()).all()
    return jsonify([_expense_json(e) for e in expenses])


# ---------------------------------------------------------------------------
# Task detail page (full screen)
# ---------------------------------------------------------------------------

@bp.route('/<int:task_id>')
def detail(task_id):
    task = HouseTask.query.get_or_404(task_id)
    expenses = HouseExpense.query.filter_by(task_id=task_id, is_active=True)\
        .order_by(HouseExpense.expenditure_date.desc()).all()
    total = sum(e.total_with_tax for e in expenses)
    all_projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    return render_template(
        'house/honey_do_detail.html',
        task=task,
        expenses=expenses,
        total=total,
        today=date.today(),
        expense_categories=HOUSE_EXPENSE_CATEGORIES,
        all_projects=all_projects,
    )


# ---------------------------------------------------------------------------
# Expense CRUD tied to a task (AJAX)
# ---------------------------------------------------------------------------

@bp.route('/<int:task_id>/expenses/add', methods=['POST'])
def add_task_expense(task_id):
    task = HouseTask.query.get_or_404(task_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400

    project_id = _get_project_id_for_task(task)
    if not project_id:
        return jsonify({'error': 'No project available to attach expense'}), 400

    try:
        expense = HouseExpense(
            expenditure_date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            entered_date=date.today(),
            price=Decimal(str(data['price'])),
            tax=Decimal(str(data['tax'])) if data.get('tax') else None,
            item=data['item'].strip(),
            description=data.get('description', '').strip() or None,
            category=data.get('category', 'Materials'),
            project_id=project_id,
            task_id=task_id,
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify(_expense_json(expense))
    except (KeyError, ValueError) as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/expenses/<int:expense_id>/edit', methods=['POST'])
def edit_task_expense(expense_id):
    expense = HouseExpense.query.get_or_404(expense_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400

    try:
        expense.expenditure_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        expense.price = Decimal(str(data['price']))
        expense.tax = Decimal(str(data['tax'])) if data.get('tax') else None
        expense.item = data['item'].strip()
        expense.description = data.get('description', '').strip() or None
        expense.category = data.get('category', expense.category)
        db.session.commit()
        return jsonify(_expense_json(expense))
    except (KeyError, ValueError) as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/expenses/<int:expense_id>/delete', methods=['POST'])
def delete_task_expense(expense_id):
    expense = HouseExpense.query.get_or_404(expense_id)
    expense.is_active = False
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Complete toggle / reorder (AJAX)
# ---------------------------------------------------------------------------

@bp.route('/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    task = HouseTask.query.get_or_404(task_id)
    task.completed = not task.completed
    task.completed_at = datetime.utcnow() if task.completed else None
    task.finish_date = date.today() if task.completed else None
    db.session.commit()
    # AJAX from list page expects JSON; form submit from detail page expects redirect
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({'completed': task.completed, 'id': task.id})
    return redirect(url_for('honey_do.detail', task_id=task_id))


@bp.route('/reorder', methods=['POST'])
def reorder_tasks():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    for item in data:
        task = HouseTask.query.get(item['id'])
        if task:
            task.sort_order = item['sort_order']
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------

@bp.route('/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    task = HouseTask.query.get_or_404(task_id)
    task.is_active = False
    db.session.commit()
    flash(f'"{task.title}" removed.', 'info')
    return redirect(url_for('honey_do.index'))
