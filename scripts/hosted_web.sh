#!/bin/sh
set -eu
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 60 --error-logfile -
