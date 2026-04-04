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

class Retailer(db.Model):
    __tablename__ = 'retailers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    website = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    expenses = db.relationship('HouseExpense', backref='retailer', lazy=True)

    def __repr__(self):
        return f'<Retailer {self.name}>'


class HouseProject(db.Model):
    __tablename__ = 'house_projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='planning')
    # planning, in-progress, on-hold, completed, abandoned
    budget = db.Column(db.Numeric(12, 2), nullable=True)
    room = db.Column(db.String(100), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    estimated_end_date = db.Column(db.Date, nullable=True)
    actual_end_date = db.Column(db.Date, nullable=True)
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
    price = db.Column(db.Numeric(12, 2), nullable=False)
    # NULL = calculate at 5.5%; explicit value overrides it
    tax = db.Column(db.Numeric(12, 2), nullable=True)
    item = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False, default='Materials')
    retailer_id = db.Column(db.Integer, db.ForeignKey('retailers.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('house_projects.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('house_todos.id'), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def effective_tax(self):
        """Return stored tax if set, otherwise calculate at 5.5%."""
        if self.tax is not None:
            return self.tax
        return (self.price * TAX_RATE).quantize(Decimal('0.01'))

    @property
    def total_with_tax(self):
        return self.price + self.effective_tax

    def __repr__(self):
        return f'<HouseExpense {self.item} ${self.price}>'
