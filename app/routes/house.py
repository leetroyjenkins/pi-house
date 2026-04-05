from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_login import login_required
import json
from app import db
from app.models import HouseExpense, HouseProject, Retailer, HOUSE_EXPENSE_CATEGORIES
from app.forms import HouseExpenseForm, HouseProjectForm, RetailerForm
from datetime import date
from decimal import Decimal
from sqlalchemy import extract, func

bp = Blueprint('house', __name__, url_prefix='/house')

@bp.before_request
@login_required
def require_login():
    pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _populate_expense_form_choices(form):
    """Populate the dynamic SelectField choices from the database."""
    projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    form.project_id.choices = [(p.id, p.name) for p in projects]

    retailers = Retailer.query.filter_by(is_active=True).order_by(Retailer.name).all()
    form.retailer_id.choices = [(0, '— None —')] + [(r.id, r.name) for r in retailers]


# ---------------------------------------------------------------------------
# Dashboard / Tally
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    # --- filter params ---
    project_id = request.args.get('project_id', type=int)
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    quarter = request.args.get('quarter', type=int)
    category = request.args.get('category', type=str)

    query = HouseExpense.query.filter_by(is_active=True)

    if project_id:
        query = query.filter(HouseExpense.project_id == project_id)
    if year:
        query = query.filter(extract('year', HouseExpense.expenditure_date) == year)
    if month:
        query = query.filter(extract('month', HouseExpense.expenditure_date) == month)
    if quarter:
        # Q1=1-3, Q2=4-6, Q3=7-9, Q4=10-12
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        query = query.filter(
            extract('month', HouseExpense.expenditure_date) >= start_month,
            extract('month', HouseExpense.expenditure_date) <= end_month,
        )
    if category:
        query = query.filter(HouseExpense.category == category)

    expenses = query.order_by(HouseExpense.expenditure_date.desc()).all()

    # --- totals ---
    total_price = sum((e.price for e in expenses), Decimal('0'))
    total_tax = sum((e.effective_tax for e in expenses), Decimal('0'))
    total_with_tax = total_price + total_tax

    # --- breakdown by category ---
    by_category = {}
    for e in expenses:
        by_category.setdefault(e.category, Decimal('0'))
        by_category[e.category] += e.total_with_tax
    by_category = sorted(by_category.items(), key=lambda x: x[1], reverse=True)

    # --- breakdown by project ---
    by_project = {}
    for e in expenses:
        label = e.project.name
        by_project.setdefault(label, Decimal('0'))
        by_project[label] += e.total_with_tax
    by_project = sorted(by_project.items(), key=lambda x: x[1], reverse=True)

    # --- breakdown by month ---
    MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    by_month = {}
    for e in expenses:
        key = (e.expenditure_date.year, e.expenditure_date.month)
        by_month.setdefault(key, Decimal('0'))
        by_month[key] += e.total_with_tax
    by_month = sorted(by_month.items())
    by_month_labels = [f"{MONTH_NAMES[k[1]-1]} {k[0]}" for k, _ in by_month]
    by_month_values = [float(v) for _, v in by_month]

    # --- filter options ---
    all_projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    available_years = sorted(
        {e.expenditure_date.year for e in HouseExpense.query.filter_by(is_active=True).all()},
        reverse=True
    )

    return render_template(
        'house/index.html',
        expenses=expenses,
        total_price=total_price,
        total_tax=total_tax,
        total_with_tax=total_with_tax,
        by_category=by_category,
        by_project=by_project,
        all_projects=all_projects,
        available_years=available_years,
        # chart data (JSON-safe)
        chart_category_labels=[c for c, _ in by_category],
        chart_category_values=[float(v) for _, v in by_category],
        chart_project_labels=[p for p, _ in by_project],
        chart_project_values=[float(v) for _, v in by_project],
        chart_month_labels=by_month_labels,
        chart_month_values=by_month_values,
        # active filters
        filter_project_id=project_id,
        filter_year=year,
        filter_month=month,
        filter_quarter=quarter,
        filter_category=category,
        all_categories=HOUSE_EXPENSE_CATEGORIES,
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@bp.route('/expenses')
def expenses():
    expenses = HouseExpense.query.filter_by(is_active=True).order_by(HouseExpense.expenditure_date.desc()).all()
    return render_template('house/expenses.html', expenses=expenses)


@bp.route('/expenses/add', methods=['GET', 'POST'])
def add_expense():
    form = HouseExpenseForm()
    _populate_expense_form_choices(form)

    if form.validate_on_submit():
        expense = HouseExpense(
            expenditure_date=form.expenditure_date.data,
            entered_date=date.today(),
            price=form.price.data,
            tax=form.tax.data if form.tax.data is not None else None,
            item=form.item.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            category=form.category.data,
            project_id=form.project_id.data,
            retailer_id=form.retailer_id.data if form.retailer_id.data else None,
        )
        db.session.add(expense)
        db.session.commit()
        flash(f'Expense "{expense.item}" added.', 'success')
        return redirect(url_for('house.expenses'))

    # Default date to today
    if request.method == 'GET':
        form.expenditure_date.data = date.today()

    return render_template('house/expense_form.html', form=form, title='Add Expense')


@bp.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
def edit_expense(expense_id):
    expense = HouseExpense.query.get_or_404(expense_id)
    form = HouseExpenseForm(obj=expense)
    _populate_expense_form_choices(form)

    if form.validate_on_submit():
        expense.expenditure_date = form.expenditure_date.data
        expense.price = form.price.data
        expense.tax = form.tax.data if form.tax.data is not None else None
        expense.item = form.item.data.strip()
        expense.description = form.description.data.strip() if form.description.data else None
        expense.category = form.category.data
        expense.project_id = form.project_id.data
        expense.retailer_id = form.retailer_id.data if form.retailer_id.data else None
        db.session.commit()
        flash(f'Expense "{expense.item}" updated.', 'success')
        return redirect(url_for('house.expenses'))

    return render_template('house/expense_form.html', form=form, title='Edit Expense', expense=expense)


@bp.route('/expenses/<int:expense_id>/delete', methods=['POST'])
def delete_expense(expense_id):
    expense = HouseExpense.query.get_or_404(expense_id)
    expense.is_active = False
    db.session.commit()
    flash(f'Expense "{expense.item}" removed.', 'info')
    return redirect(url_for('house.expenses'))


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@bp.route('/projects')
def projects():
    projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    return render_template('house/projects.html', projects=projects)


@bp.route('/projects/add', methods=['GET', 'POST'])
def add_project():
    form = HouseProjectForm()
    popup = request.args.get('popup') or request.form.get('popup', '')
    if form.validate_on_submit():
        project = HouseProject(
            name=form.name.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            status=form.status.data,
            budget=form.budget.data,
            room=form.room.data.strip() if form.room.data else None,
            start_date=form.start_date.data,
            due_date=form.due_date.data,
            completed_date=form.completed_date.data,
        )
        db.session.add(project)
        db.session.commit()
        if popup:
            payload = json.dumps({'type': 'newProject', 'id': project.id, 'name': project.name})
            return make_response(f'''<!doctype html><html><body>
                <script>window.opener&&window.opener.postMessage({payload},"*");setTimeout(function(){{window.close();}},150);</script>
                <p>Project added. You may close this tab.</p></body></html>''')
        flash(f'Project "{project.name}" created.', 'success')
        return redirect(url_for('house.projects'))

    return render_template('house/project_form.html', form=form, title='Add Project', popup=popup)


@bp.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
def edit_project(project_id):
    project = HouseProject.query.get_or_404(project_id)
    form = HouseProjectForm(obj=project)

    if form.validate_on_submit():
        project.name = form.name.data.strip()
        project.description = form.description.data.strip() if form.description.data else None
        project.status = form.status.data
        project.budget = form.budget.data
        project.room = form.room.data.strip() if form.room.data else None
        project.start_date = form.start_date.data
        project.due_date = form.due_date.data
        project.completed_date = form.completed_date.data
        db.session.commit()
        flash(f'Project "{project.name}" updated.', 'success')
        return redirect(url_for('house.projects'))

    return render_template('house/project_form.html', form=form, title='Edit Project', project=project)


@bp.route('/projects/<int:project_id>/delete', methods=['POST'])
def delete_project(project_id):
    project = HouseProject.query.get_or_404(project_id)
    project.is_active = False
    db.session.commit()
    flash(f'Project "{project.name}" removed.', 'info')
    return redirect(url_for('house.projects'))


@bp.route('/projects/quick-add', methods=['POST'])
def quick_add_project():
    data = request.get_json()
    if not data or not (data.get('name') or '').strip():
        return jsonify({'error': 'Name is required'}), 400
    project = HouseProject(
        name=data['name'].strip(),
        status=data.get('status', 'planning'),
        room=data.get('room', '').strip() or None,
    )
    db.session.add(project)
    db.session.commit()
    return jsonify({'id': project.id, 'name': project.name})


@bp.route('/projects/<int:project_id>/update', methods=['POST'])
def update_project(project_id):
    project = HouseProject.query.get_or_404(project_id)
    data = request.get_json()

    def parse_date(s):
        from datetime import date as _date
        return _date.fromisoformat(s) if s else None

    project.name = (data.get('name') or '').strip() or project.name
    project.description = (data.get('description') or '').strip() or None
    project.status = data.get('status') or project.status
    budget = data.get('budget')
    project.budget = float(budget) if budget else None
    project.room = (data.get('room') or '').strip() or None
    project.start_date = parse_date(data.get('start_date'))
    project.due_date = parse_date(data.get('due_date'))
    project.completed_date = parse_date(data.get('completed_date'))
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Retailers
# ---------------------------------------------------------------------------

@bp.route('/retailers')
def retailers():
    retailers = Retailer.query.filter_by(is_active=True).order_by(Retailer.name).all()
    return render_template('house/retailers.html', retailers=retailers)


@bp.route('/retailers/add', methods=['GET', 'POST'])
def add_retailer():
    form = RetailerForm()
    popup = request.args.get('popup') or request.form.get('popup', '')
    if form.validate_on_submit():
        retailer = Retailer(
            name=form.name.data.strip(),
            website=form.website.data.strip() if form.website.data else None,
        )
        db.session.add(retailer)
        db.session.commit()
        if popup:
            payload = json.dumps({'type': 'newRetailer', 'id': retailer.id, 'name': retailer.name})
            return make_response(f'''<!doctype html><html><body>
                <script>window.opener&&window.opener.postMessage({payload},"*");setTimeout(function(){{window.close();}},150);</script>
                <p>Retailer added. You may close this tab.</p></body></html>''')
        flash(f'Retailer "{retailer.name}" added.', 'success')
        return redirect(url_for('house.retailers'))
    return render_template('house/retailer_form.html', form=form, title='Add Retailer', popup=popup)


@bp.route('/retailers/<int:retailer_id>/edit', methods=['GET', 'POST'])
def edit_retailer(retailer_id):
    retailer = Retailer.query.get_or_404(retailer_id)
    form = RetailerForm(obj=retailer)
    if form.validate_on_submit():
        retailer.name = form.name.data.strip()
        retailer.website = form.website.data.strip() if form.website.data else None
        db.session.commit()
        flash(f'Retailer "{retailer.name}" updated.', 'success')
        return redirect(url_for('house.retailers'))
    return render_template('house/retailer_form.html', form=form, title='Edit Retailer', retailer=retailer)


@bp.route('/retailers/<int:retailer_id>/delete', methods=['POST'])
def delete_retailer(retailer_id):
    retailer = Retailer.query.get_or_404(retailer_id)
    retailer.is_active = False
    db.session.commit()
    flash(f'Retailer "{retailer.name}" removed.', 'info')
    return redirect(url_for('house.retailers'))
