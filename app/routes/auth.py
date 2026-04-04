from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import timedelta
from app import db
from app.models import User
from app.forms import LoginForm, ProfileForm

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            session.permanent = True
            login_user(user, remember=False)
            next_url = request.args.get('next') or url_for('honey_do.index')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import jsonify
                return jsonify({'ok': True, 'redirect': next_url})
            return redirect(next_url)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({'ok': False, 'error': 'Invalid username or password.'}), 401
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html', form=form)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        # Verify current password first
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/profile.html', form=form)

        # Check username isn't taken by someone else
        new_username = form.username.data.strip()
        if new_username != current_user.username:
            existing = User.query.filter_by(username=new_username).first()
            if existing:
                flash('That username is already taken.', 'danger')
                return render_template('auth/profile.html', form=form)
            current_user.username = new_username

        current_user.email = form.email.data.strip() if form.email.data else None

        if form.new_password.data:
            current_user.set_password(form.new_password.data)

        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', form=form)
