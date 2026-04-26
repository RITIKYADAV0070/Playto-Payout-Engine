import threading
import time

from django.core.management.base import BaseCommand

from payments.services import process_due_payouts


class Command(BaseCommand):
    help = "Run the payout processor loop in-process for free-tier demo deployments."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5)

    def handle(self, *args, **options):
        interval = options["interval"]
        self.stdout.write(self.style.SUCCESS(f"Inline payout worker running every {interval}s"))
        while True:
            processed = process_due_payouts()
            if processed:
                self.stdout.write(f"Processed {len(processed)} payouts")
            time.sleep(interval)


def start_inline_worker(interval=5):
    thread = threading.Thread(target=_worker_loop, args=(interval,), daemon=True)
    thread.start()
    return thread


def _worker_loop(interval):
    while True:
        process_due_payouts()
        time.sleep(interval)
