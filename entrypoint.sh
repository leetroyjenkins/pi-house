#!/bin/sh
set -e

echo "Running database migrations..."
flask init-db
flask migrate-v2
flask migrate-task-expenses
flask migrate-task-dates
flask migrate-task-fields
flask migrate-locations
flask migrate-bills
flask migrate-project-dates
flask migrate-timeline-values
flask migrate-expense-cost-fields
echo "Migrations complete."

exec gunicorn --bind 0.0.0.0:5000 --workers 2 wsgi:application
