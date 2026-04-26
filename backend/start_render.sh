#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate
python manage.py seed

celery -A playto worker -B --loglevel=info &

exec gunicorn playto.wsgi:application
