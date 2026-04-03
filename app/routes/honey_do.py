from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required
from app import db
from app.models import HouseTodo, HouseProject
from app.forms import HouseTodoForm
from datetime import datetime, date

bp = Blueprint('honey_do', __name__, url_prefix='/house/honey-do')


@bp.before_request
@login_required
def require_login():
    pass


def _populate_todo_form_choices(form):
    projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    form.project_id.choices = [(0, '— General House Upkeep —')] + [(p.id, p.name) for p in projects]


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    sort_by = request.args.get('sort', 'priority')
    project_id = request.args.get('project_id', type=int)
    show_completed = request.args.get('show_completed') == '1'

    query = HouseTodo.query.filter_by(is_active=True)

    if not show_completed:
        query = query.filter_by(completed=False)

    if project_id is not None:
        if project_id == 0:
            query = query.filter(HouseTodo.project_id.is_(None))
        else:
            query = query.filter(HouseTodo.project_id == project_id)

    if sort_by == 'due_date':
        query = query.order_by(
            HouseTodo.due_date.asc().nulls_last(),
            HouseTodo.sort_order.asc()
        )
    elif sort_by == 'start_date':
        query = query.order_by(
            HouseTodo.start_date.asc().nulls_last(),
            HouseTodo.sort_order.asc()
        )
    else:
        query = query.order_by(HouseTodo.sort_order.asc(), HouseTodo.id.asc())

    todos = query.all()
    all_projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()

    return render_template(
        'house/honey_do.html',
        todos=todos,
        all_projects=all_projects,
        sort_by=sort_by,
        filter_project_id=project_id,
        show_completed=show_completed,
        today=date.today(),
    )


# ---------------------------------------------------------------------------
# Add / Edit
# ---------------------------------------------------------------------------

@bp.route('/add', methods=['GET', 'POST'])
def add_todo():
    form = HouseTodoForm()
    _populate_todo_form_choices(form)

    if form.validate_on_submit():
        max_order = db.session.query(db.func.max(HouseTodo.sort_order)).scalar() or 0
        todo = HouseTodo(
            title=form.title.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            project_id=form.project_id.data if form.project_id.data else None,
            start_date=form.start_date.data,
            due_date=form.due_date.data,
            priority=form.priority.data,
            sort_order=max_order + 1,
        )
        db.session.add(todo)
        db.session.commit()
        flash(f'"{todo.title}" added to your honey-do list.', 'success')
        return redirect(url_for('honey_do.index'))

    return render_template('house/honey_do_form.html', form=form, title='Add Honey-Do')


@bp.route('/<int:todo_id>/edit', methods=['GET', 'POST'])
def edit_todo(todo_id):
    todo = HouseTodo.query.get_or_404(todo_id)
    form = HouseTodoForm(obj=todo)
    _populate_todo_form_choices(form)

    if form.validate_on_submit():
        todo.title = form.title.data.strip()
        todo.description = form.description.data.strip() if form.description.data else None
        todo.project_id = form.project_id.data if form.project_id.data else None
        todo.start_date = form.start_date.data
        todo.due_date = form.due_date.data
        todo.priority = form.priority.data
        db.session.commit()
        flash(f'"{todo.title}" updated.', 'success')
        return redirect(url_for('honey_do.index'))

    return render_template('house/honey_do_form.html', form=form, title='Edit Honey-Do', todo=todo)


# ---------------------------------------------------------------------------
# Actions (AJAX)
# ---------------------------------------------------------------------------

@bp.route('/<int:todo_id>/complete', methods=['POST'])
def complete_todo(todo_id):
    todo = HouseTodo.query.get_or_404(todo_id)
    todo.completed = not todo.completed
    todo.completed_at = datetime.utcnow() if todo.completed else None
    db.session.commit()
    return jsonify({'completed': todo.completed, 'id': todo.id})


@bp.route('/reorder', methods=['POST'])
def reorder_todos():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    for item in data:
        todo = HouseTodo.query.get(item['id'])
        if todo:
            todo.sort_order = item['sort_order']
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------

@bp.route('/<int:todo_id>/delete', methods=['POST'])
def delete_todo(todo_id):
    todo = HouseTodo.query.get_or_404(todo_id)
    todo.is_active = False
    db.session.commit()
    flash(f'"{todo.title}" removed.', 'info')
    return redirect(url_for('honey_do.index'))
