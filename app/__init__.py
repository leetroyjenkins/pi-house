from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import click
import os

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///budget.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = 300  # 5 minutes

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.house import bp as house_bp
    from app.routes.honey_do import bp as honey_do_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(house_bp)
    app.register_blueprint(honey_do_bp)

    # Simple home and health routes
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('honey_do.index'))

    @app.route('/health')
    def health():
        return {'status': 'healthy', 'database': 'connected'}

    # CLI command: flask init-db
    @app.cli.command('init-db')
    def init_db():
        """Create all tables and seed required data."""
        from app.models import HouseProject
        db.create_all()
        click.echo('Tables created.')

        # Seed the "General House Expenses" project if it doesn't exist
        general = HouseProject.query.filter_by(name='General House Expenses').first()
        if not general:
            general = HouseProject(
                name='General House Expenses',
                description='Catch-all project for house expenses not tied to a specific project.',
                status='in-progress',
            )
            db.session.add(general)
            db.session.commit()
            click.echo('Seeded "General House Expenses" project.')
        else:
            click.echo('"General House Expenses" project already exists.')

    # CLI command: flask migrate-task-expenses
    @app.cli.command('migrate-task-expenses')
    def migrate_task_expenses():
        """One-time migration: add task_id column to house_expenses."""
        with db.engine.connect() as conn:
            try:
                conn.execute(db.text(
                    'ALTER TABLE house_expenses ADD COLUMN task_id INTEGER REFERENCES house_todos(id)'
                ))
                conn.commit()
                click.echo('Added task_id column to house_expenses.')
            except Exception as e:
                click.echo(f'Migration may already be applied or failed: {e}')

    # CLI command: flask migrate-task-dates
    @app.cli.command('migrate-task-dates')
    def migrate_task_dates():
        """Add create_date and finish_date columns to house_todos."""
        with db.engine.connect() as conn:
            for col_sql in [
                'ALTER TABLE house_todos ADD COLUMN create_date DATE',
                'ALTER TABLE house_todos ADD COLUMN finish_date DATE',
            ]:
                try:
                    conn.execute(db.text(col_sql))
                    conn.commit()
                    click.echo(f'Applied: {col_sql}')
                except Exception as e:
                    click.echo(f'Skipped (may already exist): {e}')

    # CLI command: flask migrate-timeline-values
    @app.cli.command('migrate-timeline-values')
    def migrate_timeline_values():
        """Rename old timeline values to new ones."""
        mapping = {'Soon': 'Soonish', 'Someday': 'Eventually'}
        with db.engine.connect() as conn:
            for old, new in mapping.items():
                result = conn.execute(
                    db.text("UPDATE house_todos SET timeline = :new WHERE timeline = :old"),
                    {'new': new, 'old': old}
                )
                conn.commit()
                click.echo(f'Updated {result.rowcount} tasks: {old} → {new}')

    # CLI command: flask migrate-task-fields
    @app.cli.command('migrate-task-fields')
    def migrate_task_fields():
        """Add completed_date and timeline columns to house_todos."""
        with db.engine.connect() as conn:
            for col_sql in [
                'ALTER TABLE house_todos ADD COLUMN completed_date DATE',
                'ALTER TABLE house_todos ADD COLUMN timeline VARCHAR(20)',
            ]:
                try:
                    conn.execute(db.text(col_sql))
                    conn.commit()
                    click.echo(f'Applied: {col_sql}')
                except Exception as e:
                    click.echo(f'Skipped (may already exist): {e}')

    # CLI command: flask migrate-project-dates
    @app.cli.command('migrate-project-dates')
    def migrate_project_dates():
        """Rename estimated_end_date → due_date and actual_end_date → completed_date on house_projects."""
        with db.engine.connect() as conn:
            for old_col, new_col in [('estimated_end_date', 'due_date'), ('actual_end_date', 'completed_date')]:
                try:
                    conn.execute(db.text(
                        f'ALTER TABLE house_projects RENAME COLUMN {old_col} TO {new_col}'
                    ))
                    conn.commit()
                    click.echo(f'Renamed {old_col} → {new_col}')
                except Exception as e:
                    click.echo(f'Skipped {old_col} (may already be renamed): {e}')

    # CLI command: flask create-user
    @app.cli.command('create-user')
    @click.argument('username')
    @click.password_option()
    def create_user(username, password):
        """Create a user account. Usage: flask create-user <username>"""
        from app.models import User
        db.create_all()
        if User.query.filter_by(username=username).first():
            click.echo(f'User "{username}" already exists.')
            return
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f'User "{username}" created.')

    return app
