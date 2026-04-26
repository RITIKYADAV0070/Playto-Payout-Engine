#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate
python manage.py seed

exec gunicorn playto.wsgi:application
