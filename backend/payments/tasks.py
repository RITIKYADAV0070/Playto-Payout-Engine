from playto.celery import app

from .services import process_due_payouts


@app.task
def process_payouts():
    return [payout.id for payout in process_due_payouts()]
