from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_login import login_required
import json
from app import db
from app.models import HouseExpense, HouseProject, Vendor, Bank, Location, HOUSE_EXPENSE_CATEGORIES
from app.forms import HouseExpenseForm, HouseProjectForm, VendorForm, BankForm, LocationForm
from datetime import date, datetime
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

    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()
    form.retailer_id.choices = [(0, '— None —')] + [(r.id, r.name) for r in vendors]

    banks = Bank.query.filter_by(is_active=True).order_by(Bank.name).all()
    form.bank_id.choices = [(0, '— None —')] + [(b.id, b.name) for b in banks]


def _populate_project_form_choices(form):
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    form.location_id.choices = [(0, '— None —')] + [(loc.id, loc.name) for loc in locations]


# ---------------------------------------------------------------------------
# Dashboard / Tally
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    # --- filter params ---
    project_id = request.args.get('project_id', type=int)
    year       = request.args.get('year',       type=int)
    month      = request.args.get('month',      type=int)
    quarter    = request.args.get('quarter',    type=int)
    category   = request.args.get('category',   type=str)
    section    = request.args.get('section',    type=str, default='all')
    # section: all | project | bill | maintenance

    query = HouseExpense.query.filter_by(is_active=True)

    if project_id:
        query = query.filter(HouseExpense.project_id == project_id)
    if year:
        query = query.filter(extract('year', HouseExpense.expenditure_date) == year)
    if month:
        query = query.filter(extract('month', HouseExpense.expenditure_date) == month)
    if quarter:
        start_month = (quarter - 1) * 3 + 1
        end_month   = start_month + 2
        query = query.filter(
            extract('month', HouseExpense.expenditure_date) >= start_month,
            extract('month', HouseExpense.expenditure_date) <= end_month,
        )
    if category:
        query = query.filter(HouseExpense.category == category)

    expenses = query.order_by(HouseExpense.expenditure_date.desc()).all()

    # Filter by section (project_type of parent project)
    if section and section != 'all':
        expenses = [e for e in expenses if e.project and e.project.project_type == section]

    # --- totals ---
    total_price    = sum((e.price        for e in expenses), Decimal('0'))
    total_tax      = sum((e.effective_tax for e in expenses), Decimal('0'))
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
    by_month       = sorted(by_month.items())
    by_month_labels = [f"{MONTH_NAMES[k[1]-1]} {k[0]}" for k, _ in by_month]
    by_month_values = [float(v) for _, v in by_month]

    # --- section totals (for tab badges) ---
    all_expenses = HouseExpense.query.filter_by(is_active=True).all()
    section_totals = {}
    for stype in ('project', 'bill', 'maintenance'):
        subtotal = sum(
            e.total_with_tax for e in all_expenses
            if e.project and e.project.project_type == stype
        )
        section_totals[stype] = subtotal

    # --- filter options ---
    all_projects    = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
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
        section_totals=section_totals,
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
        filter_section=section,
        all_categories=HOUSE_EXPENSE_CATEGORIES,
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@bp.route('/expenses')
def expenses():
    # --- filter params ---
    project_id  = request.args.get('project_id',  type=int)
    vendor_id   = request.args.get('vendor_id',   type=int)
    bank_id     = request.args.get('bank_id',     type=int)
    category    = request.args.get('category',    type=str)
    date_from   = request.args.get('date_from',   type=str)
    date_to     = request.args.get('date_to',     type=str)
    sort_col    = request.args.get('sort',        type=str, default='date')
    sort_dir    = request.args.get('dir',         type=str, default='desc')

    query = HouseExpense.query.filter_by(is_active=True)

    if project_id:
        query = query.filter(HouseExpense.project_id == project_id)
    if vendor_id:
        query = query.filter(HouseExpense.retailer_id == vendor_id)
    if bank_id:
        query = query.filter(HouseExpense.bank_id == bank_id)
    if category:
        query = query.filter(HouseExpense.category == category)
    if date_from:
        try:
            query = query.filter(HouseExpense.expenditure_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(HouseExpense.expenditure_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    # Sorting
    sort_map = {
        'date':  HouseExpense.expenditure_date,
        'item':  HouseExpense.item,
        'price': HouseExpense.price,
    }
    sort_field = sort_map.get(sort_col, HouseExpense.expenditure_date)
    if sort_dir == 'asc':
        query = query.order_by(sort_field.asc())
    else:
        query = query.order_by(sort_field.desc())

    expense_list = query.all()

    all_projects = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    all_vendors  = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()
    all_banks    = Bank.query.filter_by(is_active=True).order_by(Bank.name).all()

    return render_template(
        'house/expenses.html',
        expenses=expense_list,
        all_projects=all_projects,
        all_vendors=all_vendors,
        all_banks=all_banks,
        all_categories=HOUSE_EXPENSE_CATEGORIES,
        filter_project_id=project_id,
        filter_vendor_id=vendor_id,
        filter_bank_id=bank_id,
        filter_category=category,
        filter_date_from=date_from or '',
        filter_date_to=date_to or '',
        sort_col=sort_col,
        sort_dir=sort_dir,
    )


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
            bank_id=form.bank_id.data if form.bank_id.data else None,
            check_number=form.check_number.data.strip() if form.check_number.data else None,
        )
        db.session.add(expense)
        db.session.commit()
        flash(f'Expense "{expense.item}" added.', 'success')
        return redirect(url_for('house.expenses'))

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
        expense.price        = form.price.data
        expense.tax          = form.tax.data if form.tax.data is not None else None
        expense.item         = form.item.data.strip()
        expense.description  = form.description.data.strip() if form.description.data else None
        expense.category     = form.category.data
        expense.project_id   = form.project_id.data
        expense.retailer_id  = form.retailer_id.data if form.retailer_id.data else None
        expense.bank_id      = form.bank_id.data if form.bank_id.data else None
        expense.check_number = form.check_number.data.strip() if form.check_number.data else None
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
    all_projects  = HouseProject.query.filter_by(is_active=True).order_by(HouseProject.name).all()
    all_locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    return render_template('house/projects.html', projects=all_projects, all_locations=all_locations)


@bp.route('/projects/add', methods=['GET', 'POST'])
def add_project():
    form = HouseProjectForm()
    _populate_project_form_choices(form)
    popup = request.args.get('popup') or request.form.get('popup', '')
    if form.validate_on_submit():
        project = HouseProject(
            name=form.name.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            status=form.status.data,
            project_type=form.project_type.data,
            budget=form.budget.data,
            location_id=form.location_id.data if form.location_id.data else None,
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
    _populate_project_form_choices(form)

    if form.validate_on_submit():
        project.name         = form.name.data.strip()
        project.description  = form.description.data.strip() if form.description.data else None
        project.status       = form.status.data
        project.project_type = form.project_type.data
        project.budget       = form.budget.data
        project.location_id  = form.location_id.data if form.location_id.data else None
        project.start_date   = form.start_date.data
        project.due_date     = form.due_date.data
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
    )
    db.session.add(project)
    db.session.commit()
    return jsonify({'id': project.id, 'name': project.name})


@bp.route('/projects/<int:project_id>/update', methods=['POST'])
def update_project(project_id):
    project = HouseProject.query.get_or_404(project_id)
    data = request.get_json()

    def parse_date(s):
        return date.fromisoformat(s) if s else None

    project.name         = (data.get('name') or '').strip() or project.name
    project.description  = (data.get('description') or '').strip() or None
    project.status       = data.get('status') or project.status
    project.project_type = data.get('project_type') or project.project_type
    budget = data.get('budget')
    project.budget       = float(budget) if budget else None
    lid = data.get('location_id')
    project.location_id  = int(lid) if lid else None
    project.start_date   = parse_date(data.get('start_date'))
    project.due_date     = parse_date(data.get('due_date'))
    project.completed_date = parse_date(data.get('completed_date'))
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Vendors (formerly Retailers)
# ---------------------------------------------------------------------------

@bp.route('/vendors')
def retailers():
    vendors = Vendor.query.filter_by(is_active=True).order_by(Vendor.name).all()
    return render_template('house/retailers.html', vendors=vendors)


@bp.route('/vendors/add', methods=['GET', 'POST'])
def add_retailer():
    form = VendorForm()
    popup = request.args.get('popup') or request.form.get('popup', '')
    if form.validate_on_submit():
        vendor = Vendor(
            name=form.name.data.strip(),
            website=form.website.data.strip() if form.website.data else None,
        )
        db.session.add(vendor)
        db.session.commit()
        if popup:
            payload = json.dumps({'type': 'newVendor', 'id': vendor.id, 'name': vendor.name})
            return make_response(f'''<!doctype html><html><body>
                <script>window.opener&&window.opener.postMessage({payload},"*");setTimeout(function(){{window.close();}},150);</script>
                <p>Vendor added. You may close this tab.</p></body></html>''')
        flash(f'Vendor "{vendor.name}" added.', 'success')
        return redirect(url_for('house.retailers'))
    return render_template('house/retailer_form.html', form=form, title='Add Vendor', popup=popup)


@bp.route('/vendors/<int:retailer_id>/edit', methods=['GET', 'POST'])
def edit_retailer(retailer_id):
    vendor = Vendor.query.get_or_404(retailer_id)
    form = VendorForm(obj=vendor)
    if form.validate_on_submit():
        vendor.name    = form.name.data.strip()
        vendor.website = form.website.data.strip() if form.website.data else None
        db.session.commit()
        flash(f'Vendor "{vendor.name}" updated.', 'success')
        return redirect(url_for('house.retailers'))
    return render_template('house/retailer_form.html', form=form, title='Edit Vendor', vendor=vendor)


@bp.route('/vendors/<int:retailer_id>/delete', methods=['POST'])
def delete_retailer(retailer_id):
    vendor = Vendor.query.get_or_404(retailer_id)
    vendor.is_active = False
    db.session.commit()
    flash(f'Vendor "{vendor.name}" removed.', 'info')
    return redirect(url_for('house.retailers'))


# ---------------------------------------------------------------------------
# Banks
# ---------------------------------------------------------------------------

@bp.route('/banks')
def banks():
    banks = Bank.query.filter_by(is_active=True).order_by(Bank.name).all()
    return render_template('house/banks.html', banks=banks)


@bp.route('/banks/add', methods=['GET', 'POST'])
def add_bank():
    form = BankForm()
    popup = request.args.get('popup') or request.form.get('popup', '')
    if form.validate_on_submit():
        bank = Bank(
            name=form.name.data.strip(),
            account_number=form.account_number.data.strip() if form.account_number.data else None,
        )
        db.session.add(bank)
        db.session.commit()
        if popup:
            payload = json.dumps({'type': 'newBank', 'id': bank.id, 'name': bank.name})
            return make_response(f'''<!doctype html><html><body>
                <script>window.opener&&window.opener.postMessage({payload},"*");setTimeout(function(){{window.close();}},150);</script>
                <p>Bank added. You may close this tab.</p></body></html>''')
        flash(f'Bank "{bank.name}" added.', 'success')
        return redirect(url_for('house.banks'))
    return render_template('house/bank_form.html', form=form, title='Add Bank', popup=popup)


@bp.route('/banks/<int:bank_id>/edit', methods=['GET', 'POST'])
def edit_bank(bank_id):
    bank = Bank.query.get_or_404(bank_id)
    form = BankForm(obj=bank)
    if form.validate_on_submit():
        bank.name           = form.name.data.strip()
        bank.account_number = form.account_number.data.strip() if form.account_number.data else None
        db.session.commit()
        flash(f'Bank "{bank.name}" updated.', 'success')
        return redirect(url_for('house.banks'))
    return render_template('house/bank_form.html', form=form, title='Edit Bank', bank=bank)


@bp.route('/banks/<int:bank_id>/delete', methods=['POST'])
def delete_bank(bank_id):
    bank = Bank.query.get_or_404(bank_id)
    bank.is_active = False
    db.session.commit()
    flash(f'Bank "{bank.name}" removed.', 'info')
    return redirect(url_for('house.banks'))


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@bp.route('/locations')
def locations():
    locs = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    return render_template('house/locations.html', locations=locs)


@bp.route('/locations/add', methods=['GET', 'POST'])
def add_location():
    form = LocationForm()
    popup = request.args.get('popup') or request.form.get('popup', '')
    if form.validate_on_submit():
        loc = Location(name=form.name.data.strip())
        db.session.add(loc)
        db.session.commit()
        if popup:
            payload = json.dumps({'type': 'newLocation', 'id': loc.id, 'name': loc.name})
            return make_response(f'''<!doctype html><html><body>
                <script>window.opener&&window.opener.postMessage({payload},"*");setTimeout(function(){{window.close();}},150);</script>
                <p>Location added. You may close this tab.</p></body></html>''')
        flash(f'Location "{loc.name}" added.', 'success')
        return redirect(url_for('house.locations'))
    return render_template('house/location_form.html', form=form, title='Add Location', popup=popup)


@bp.route('/locations/<int:location_id>/edit', methods=['GET', 'POST'])
def edit_location(location_id):
    loc = Location.query.get_or_404(location_id)
    form = LocationForm(obj=loc)
    if form.validate_on_submit():
        loc.name = form.name.data.strip()
        db.session.commit()
        flash(f'Location "{loc.name}" updated.', 'success')
        return redirect(url_for('house.locations'))
    return render_template('house/location_form.html', form=form, title='Edit Location', location=loc)


@bp.route('/locations/<int:location_id>/delete', methods=['POST'])
def delete_location(location_id):
    loc = Location.query.get_or_404(location_id)
    loc.is_active = False
    db.session.commit()
    flash(f'Location "{loc.name}" removed.', 'info')
    return redirect(url_for('house.locations'))


@bp.route('/locations/quick-add', methods=['POST'])
def quick_add_location():
    data = request.get_json()
    if not data or not (data.get('name') or '').strip():
        return jsonify({'error': 'Name is required'}), 400
    loc = Location(name=data['name'].strip())
    db.session.add(loc)
    db.session.commit()
    return jsonify({'id': loc.id, 'name': loc.name})
