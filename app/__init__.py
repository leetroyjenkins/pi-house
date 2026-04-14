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
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.house import bp as house_bp
    from app.routes.honey_do import bp as honey_do_bp
    from app.routes.bills import bp as bills_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(house_bp)
    app.register_blueprint(honey_do_bp)
    app.register_blueprint(bills_bp)

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

    # CLI command: flask migrate-bills
    @app.cli.command('migrate-bills')
    def migrate_bills():
        """Create bills and bill_payments tables."""
        with db.engine.connect() as conn:
            sqls = [
                '''CREATE TABLE IF NOT EXISTS bills (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    provider VARCHAR(150),
                    account_number VARCHAR(50),
                    auto_pay BOOLEAN NOT NULL DEFAULT FALSE,
                    bank_id INTEGER REFERENCES banks(id),
                    notes TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )''',
                '''CREATE TABLE IF NOT EXISTS bill_payments (
                    id SERIAL PRIMARY KEY,
                    bill_id INTEGER NOT NULL REFERENCES bills(id),
                    period_year INTEGER NOT NULL,
                    period_month INTEGER NOT NULL,
                    amount NUMERIC(12,2),
                    paid_date DATE,
                    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
                    check_number VARCHAR(20),
                    bank_id INTEGER REFERENCES banks(id),
                    notes TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )''',
            ]
            for sql in sqls:
                try:
                    conn.execute(db.text(sql))
                    conn.commit()
                    click.echo(f'OK: {sql.split()[2]}')
                except Exception as e:
                    conn.rollback()
                    click.echo(f'Skipped: {e}')

    # CLI command: flask migrate-locations
    @app.cli.command('migrate-locations')
    def migrate_locations():
        """Create locations table and add location_id to tasks and projects."""
        with db.engine.connect() as conn:
            try:
                conn.execute(db.text('''
                    CREATE TABLE IF NOT EXISTS locations (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                '''))
                conn.commit()
                click.echo('Created locations table.')
            except Exception as e:
                conn.rollback()
                click.echo(f'locations table: {e}')

            for table, col, sql in [
                ('house_todos',    'location_id', 'ALTER TABLE house_todos    ADD COLUMN location_id INTEGER REFERENCES locations(id)'),
                ('house_projects', 'location_id', 'ALTER TABLE house_projects ADD COLUMN location_id INTEGER REFERENCES locations(id)'),
            ]:
                try:
                    conn.execute(db.text(sql))
                    conn.commit()
                    click.echo(f'Added location_id to {table}.')
                except Exception as e:
                    conn.rollback()
                    click.echo(f'Skipped location_id on {table} (may already exist): {e}')

    # CLI command: flask migrate-v2
    @app.cli.command('migrate-v2')
    def migrate_v2():
        """Add banks table, check_number/bank_id to expenses, room to tasks, project_type to projects."""
        with db.engine.connect() as conn:
            # Create banks table
            try:
                conn.execute(db.text('''
                    CREATE TABLE IF NOT EXISTS banks (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        account_number VARCHAR(50),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                '''))
                conn.commit()
                click.echo('Created banks table.')
            except Exception as e:
                click.echo(f'banks table: {e}')

            migrations = [
                ('house_expenses', 'check_number', 'ALTER TABLE house_expenses ADD COLUMN check_number VARCHAR(20)'),
                ('house_expenses', 'bank_id',      'ALTER TABLE house_expenses ADD COLUMN bank_id INTEGER REFERENCES banks(id)'),
                ('house_todos',    'room',          'ALTER TABLE house_todos ADD COLUMN room VARCHAR(100)'),
                ('house_projects', 'project_type',  "ALTER TABLE house_projects ADD COLUMN project_type VARCHAR(20) NOT NULL DEFAULT 'project'"),
            ]
            for table, col, sql in migrations:
                try:
                    conn.execute(db.text(sql))
                    conn.commit()
                    click.echo(f'Added {col} to {table}.')
                except Exception as e:
                    conn.rollback()
                    click.echo(f'Skipped {col} on {table} (may already exist): {e}')

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
                conn.rollback()
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
                    conn.rollback()
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
                    conn.rollback()
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
                    conn.rollback()
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
