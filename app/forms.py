from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, DecimalField, DateField,
    SelectField, URLField, BooleanField, PasswordField
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange, URL, ValidationError, Email, EqualTo
from app.models import HOUSE_EXPENSE_CATEGORIES, TASK_PRIORITIES, TASK_TIMELINES


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class ProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[Optional(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm New Password',
        validators=[EqualTo('new_password', message='Passwords must match.')]
    )


class VendorForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=150)])
    website = URLField('Website', validators=[Optional(), URL(), Length(max=255)])


class BankForm(FlaskForm):
    name = StringField('Bank Name', validators=[DataRequired(), Length(max=100)])
    account_number = StringField('Account / Last 4 Digits', validators=[Optional(), Length(max=50)])


class LocationForm(FlaskForm):
    name = StringField('Location Name', validators=[DataRequired(), Length(max=100)])


class HouseProjectForm(FlaskForm):
    name = StringField('Project Name', validators=[DataRequired(), Length(max=150)])
    description = TextAreaField('Description', validators=[Optional()])
    status = SelectField('Status', choices=[
        ('planning', 'Planning'),
        ('in-progress', 'In Progress'),
        ('on-hold', 'On Hold'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ], default='planning')
    project_type = SelectField('Type', choices=[
        ('project', 'Project'),
        ('bill', 'Bill'),
        ('maintenance', 'General Maintenance'),
    ], default='project')
    budget = DecimalField('Estimated Budget ($)', validators=[Optional(), NumberRange(min=0)], places=2)
    location_id = SelectField('Location', coerce=int, validators=[Optional()])
    start_date = DateField('Start Date', validators=[Optional()])
    due_date = DateField('Due Date', validators=[Optional()])
    completed_date = DateField('Completed Date', validators=[Optional()])

    def validate_due_date(self, field):
        if field.data and self.start_date.data and field.data < self.start_date.data:
            raise ValidationError('Due date must be on or after start date.')

    def validate_completed_date(self, field):
        if field.data and self.start_date.data and field.data < self.start_date.data:
            raise ValidationError('Completed date must be on or after start date.')


class HouseTaskForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    location_id = SelectField('Location', coerce=int, validators=[Optional()])
    project_id = SelectField('Project', coerce=int, validators=[Optional()])
    start_date = DateField('Start Date', validators=[Optional()])
    due_date = DateField('Due Date', validators=[Optional()])
    completed_date = DateField('Completed Date', validators=[Optional()])
    priority = SelectField('Priority', choices=[(p, p) for p in TASK_PRIORITIES], default='Low')
    timeline = SelectField('Timeline', choices=[('', '— None —')] + [(t, t) for t in TASK_TIMELINES], default='When Possible', validators=[Optional()])


class BillForm(FlaskForm):
    name = StringField('Bill Name', validators=[DataRequired(), Length(max=100)])
    provider = StringField('Provider / Company', validators=[Optional(), Length(max=150)])
    account_number = StringField('Account #', validators=[Optional(), Length(max=50)])
    auto_pay = BooleanField('Auto-Pay')
    bank_id = SelectField('Default Bank', coerce=int, validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])


class BillPaymentForm(FlaskForm):
    amount = DecimalField('Amount ($)', validators=[DataRequired(), NumberRange(min=0)], places=2)
    paid_date = DateField('Date Paid', validators=[Optional()])
    bank_id = SelectField('Bank', coerce=int, validators=[Optional()])
    check_number = StringField('Check #', validators=[Optional(), Length(max=20)])
    notes = TextAreaField('Notes', validators=[Optional()])


class HouseExpenseForm(FlaskForm):
    expenditure_date = DateField('Purchase Date', validators=[DataRequired()])
    item = StringField('Item', validators=[DataRequired(), Length(max=200)])
    price = DecimalField('Price ($)', validators=[DataRequired(), NumberRange(min=0)], places=2)
    tax = DecimalField(
        'Tax ($)',
        validators=[Optional(), NumberRange(min=0)],
        places=2,
        description='Leave blank to auto-calculate at 5.5%'
    )
    category = SelectField('Category', choices=[(c, c) for c in HOUSE_EXPENSE_CATEGORIES])
    project_id = SelectField('Project', coerce=int, validators=[DataRequired()])
    retailer_id = SelectField('Vendor', coerce=int, validators=[Optional()])
    bank_id = SelectField('Bank', coerce=int, validators=[Optional()])
    check_number = StringField('Check #', validators=[Optional(), Length(max=20)])
    description = TextAreaField('Description / Notes', validators=[Optional()])
