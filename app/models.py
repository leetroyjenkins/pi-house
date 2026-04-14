from app import db
from flask_login import UserMixin
from datetime import datetime, date
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


# ---------------------------------------------------------------------------
# House Expense Tracker
# ---------------------------------------------------------------------------

class Vendor(db.Model):
    __tablename__ = 'retailers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    website = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    expenses = db.relationship('HouseExpense', backref='retailer', lazy=True)

    def __repr__(self):
        return f'<Vendor {self.name}>'


class Bank(db.Model):
    __tablename__ = 'banks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    expenses = db.relationship('HouseExpense', backref='bank', lazy=True)

    def __repr__(self):
        return f'<Bank {self.name}>'


class Location(db.Model):
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks    = db.relationship('HouseTask',    backref='location', lazy=True)
    projects = db.relationship('HouseProject', backref='location', lazy=True)

    def __repr__(self):
        return f'<Location {self.name}>'


class HouseProject(db.Model):
    __tablename__ = 'house_projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='planning')
    # planning, in-progress, on-hold, completed, abandoned
    project_type = db.Column(db.String(20), nullable=False, default='project')
    # project, bill, maintenance
    budget = db.Column(db.Numeric(12, 2), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    completed_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expenses = db.relationship('HouseExpense', backref='project', lazy=True)

    @property
    def total_spent(self):
        return sum((e.price for e in self.expenses if e.is_active), Decimal('0'))

    @property
    def total_with_tax(self):
        return sum((e.total_with_tax for e in self.expenses if e.is_active), Decimal('0'))

    def __repr__(self):
        return f'<HouseProject {self.name}>'


TASK_PRIORITIES = ['High', 'Medium', 'Low']
TASK_TIMELINES = ['Immediate', 'Urgent', 'Soonish', 'When Possible', 'Eventually']


class HouseTask(db.Model):
    __tablename__ = 'house_todos'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('house_projects.id'), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    create_date = db.Column(db.Date, nullable=True, default=date.today)
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    finish_date = db.Column(db.Date, nullable=True)
    completed_date = db.Column(db.Date, nullable=True)
    timeline = db.Column(db.String(20), nullable=True)
    priority = db.Column(db.String(10), nullable=False, default='Medium')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship('HouseProject', backref='tasks')
    task_expenses = db.relationship('HouseExpense', foreign_keys='[HouseExpense.task_id]', lazy=True)

    @property
    def expense_total(self):
        return sum((e.total_with_tax for e in self.task_expenses if e.is_active), Decimal('0'))

    def __repr__(self):
        return f'<HouseTask {self.title}>'


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

class Bill(db.Model):
    __tablename__ = 'bills'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)          # "Electric", "Mortgage"
    provider = db.Column(db.String(150), nullable=True)       # "DTE Energy", "Chase Bank"
    account_number = db.Column(db.String(50), nullable=True)
    auto_pay = db.Column(db.Boolean, nullable=False, default=False)
    bank_id = db.Column(db.Integer, db.ForeignKey('banks.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bank = db.relationship('Bank', backref='bills')
    payments = db.relationship('BillPayment', backref='bill', lazy=True,
                               order_by='BillPayment.period_year.desc(), BillPayment.period_month.desc()')

    def __repr__(self):
        return f'<Bill {self.name}>'


class BillPayment(db.Model):
    __tablename__ = 'bill_payments'

    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    period_year = db.Column(db.Integer, nullable=False)
    period_month = db.Column(db.Integer, nullable=False)   # 1-12
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    paid_date = db.Column(db.Date, nullable=True)
    is_paid = db.Column(db.Boolean, nullable=False, default=False)
    check_number = db.Column(db.String(20), nullable=True)
    bank_id = db.Column(db.Integer, db.ForeignKey('banks.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_bank = db.relationship('Bank', foreign_keys=[bank_id])

    def __repr__(self):
        return f'<BillPayment {self.bill_id} {self.period_year}-{self.period_month:02d}>'


HOUSE_EXPENSE_CATEGORIES = [
    'Materials',
    'Labor',
    'Permit',
    'Appliance',
    'Tool & Equipment',
    'Service & Inspection',
    'Other',
]

TAX_RATE = Decimal('0.055')


class HouseExpense(db.Model):
    __tablename__ = 'house_expenses'

    id = db.Column(db.Integer, primary_key=True)
    expenditure_date = db.Column(db.Date, nullable=False)
    entered_date = db.Column(db.Date, nullable=False, default=date.today)
    estimated_cost = db.Column(db.Numeric(12, 2), nullable=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    # NULL = calculate at 5.5%; explicit value overrides it; ignored when taxable=False
    tax = db.Column(db.Numeric(12, 2), nullable=True)
    taxable = db.Column(db.Boolean, nullable=False, default=True)
    item = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False, default='Materials')
    check_number = db.Column(db.String(20), nullable=True)
    retailer_id = db.Column(db.Integer, db.ForeignKey('retailers.id'), nullable=True)
    bank_id = db.Column(db.Integer, db.ForeignKey('banks.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('house_projects.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('house_todos.id'), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def effective_tax(self):
        """Return 0 if not taxable; stored tax if set; otherwise calculate at 5.5%."""
        if not self.taxable:
            return Decimal('0.00')
        if self.tax is not None:
            return self.tax
        return (self.price * TAX_RATE).quantize(Decimal('0.01'))

    @property
    def total_with_tax(self):
        return self.price + self.effective_tax

    def __repr__(self):
        return f'<HouseExpense {self.item} ${self.price}>'
