from django.core.management.base import BaseCommand

from payments.services import process_due_payouts


class Command(BaseCommand):
    help = "Process pending and retryable payouts once."

    def handle(self, *args, **options):
        processed = process_due_payouts()
        self.stdout.write(self.style.SUCCESS(f"Processed {len(processed)} payouts"))
