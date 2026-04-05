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


class RetailerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=150)])
    website = URLField('Website', validators=[Optional(), URL(), Length(max=255)])


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
    budget = DecimalField('Estimated Budget ($)', validators=[Optional(), NumberRange(min=0)], places=2)
    room = StringField('Room / Area', validators=[Optional(), Length(max=100)])
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
    project_id = SelectField('Project', coerce=int, validators=[Optional()])
    start_date = DateField('Start Date', validators=[Optional()])
    due_date = DateField('Due Date', validators=[Optional()])
    completed_date = DateField('Completed Date', validators=[Optional()])
    priority = SelectField('Priority', choices=[(p, p) for p in TASK_PRIORITIES], default='Low')
    timeline = SelectField('Timeline', choices=[('', '— None —')] + [(t, t) for t in TASK_TIMELINES], default='When Possible', validators=[Optional()])


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
    retailer_id = SelectField('Retailer', coerce=int, validators=[Optional()])
    description = TextAreaField('Description / Notes', validators=[Optional()])
