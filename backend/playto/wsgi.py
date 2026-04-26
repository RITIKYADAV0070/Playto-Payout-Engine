import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playto.settings")

application = get_wsgi_application()

if settings.RUN_INLINE_PAYOUT_WORKER:
    from payments.management.commands.run_inline_worker import start_inline_worker

    start_inline_worker()
