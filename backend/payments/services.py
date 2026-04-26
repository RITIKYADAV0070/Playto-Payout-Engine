import hashlib
import json
import random
from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status

from .models import BankAccount, IdempotencyKey, LedgerEntry, Merchant, MerchantBalance, Payout


class PayoutError(Exception):
    def __init__(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def request_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ledger_available_balance(merchant):
    return (
        LedgerEntry.objects.filter(merchant=merchant)
        .aggregate(balance=Coalesce(Sum("amount_paise"), 0))
        .get("balance")
    )


def create_payout_idempotently(merchant_id, idempotency_key, payload):
    try:
        key_uuid = UUID(str(idempotency_key))
    except ValueError as exc:
        raise PayoutError("Idempotency-Key must be a UUID.", status.HTTP_400_BAD_REQUEST) from exc

    hashed_request = request_hash(payload)
    expires_at = timezone.now() + timedelta(hours=24)

    with transaction.atomic():
        merchant = Merchant.objects.get(id=merchant_id)
        idem = _locked_idempotency_row(merchant, key_uuid, hashed_request, expires_at)

        if idem.response_body is not None:
            if idem.expires_at <= timezone.now():
                raise PayoutError("Idempotency-Key has expired. Use a new key.", status.HTTP_409_CONFLICT)
            if idem.request_hash != hashed_request:
                raise PayoutError("Idempotency-Key was already used with a different payload.", status.HTTP_409_CONFLICT)
            return idem.response_body, idem.status_code

        if idem.request_hash != hashed_request:
            raise PayoutError("Idempotency-Key was already used with a different payload.", status.HTTP_409_CONFLICT)

        response_body, status_code = _create_payout_locked(merchant, payload)
        idem.response_body = response_body
        idem.status_code = status_code
        idem.expires_at = expires_at
        idem.save(update_fields=["response_body", "status_code", "expires_at"])
        return response_body, status_code


def _locked_idempotency_row(merchant, key_uuid, hashed_request, expires_at):
    try:
        idem, created = IdempotencyKey.objects.get_or_create(
            merchant=merchant,
            key=key_uuid,
            defaults={"request_hash": hashed_request, "expires_at": expires_at},
        )
    except IntegrityError:
        idem = IdempotencyKey.objects.get(merchant=merchant, key=key_uuid)
        created = False

    if created:
        return idem
    return IdempotencyKey.objects.select_for_update().get(pk=idem.pk)


def _create_payout_locked(merchant, payload):
    amount = int(payload["amount_paise"])
    bank_account_id = int(payload["bank_account_id"])

    try:
        bank_account = BankAccount.objects.get(id=bank_account_id, merchant=merchant)
    except BankAccount.DoesNotExist as exc:
        raise PayoutError("Bank account does not belong to this merchant.", status.HTTP_400_BAD_REQUEST) from exc

    balance = MerchantBalance.objects.select_for_update().get(merchant=merchant)
    if balance.available_paise < amount:
        raise PayoutError("Insufficient available balance.", status.HTTP_422_UNPROCESSABLE_ENTITY)

    payout = Payout.objects.create(
        merchant=merchant,
        bank_account=bank_account,
        amount_paise=amount,
        status=Payout.Status.PENDING,
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        payout=payout,
        kind=LedgerEntry.Kind.PAYOUT_HOLD,
        amount_paise=-amount,
        description=f"Funds held for payout #{payout.id}",
    )
    MerchantBalance.objects.filter(pk=balance.pk).update(
        available_paise=F("available_paise") - amount,
        held_paise=F("held_paise") + amount,
    )
    payout.refresh_from_db()
    return serialize_payout(payout), status.HTTP_201_CREATED


LEGAL_TRANSITIONS = {
    Payout.Status.PENDING: {Payout.Status.PROCESSING},
    Payout.Status.PROCESSING: {Payout.Status.COMPLETED, Payout.Status.FAILED},
    Payout.Status.COMPLETED: set(),
    Payout.Status.FAILED: set(),
}


def transition_payout(payout_id, new_status, failure_reason=""):
    with transaction.atomic():
        payout = Payout.objects.select_for_update().select_related("merchant").get(pk=payout_id)
        if new_status not in LEGAL_TRANSITIONS[payout.status]:
            raise PayoutError(f"Illegal payout transition {payout.status} -> {new_status}.", status.HTTP_409_CONFLICT)

        now = timezone.now()
        updates = {"status": new_status}
        if new_status == Payout.Status.PROCESSING:
            updates["attempts"] = F("attempts") + 1
            updates["processing_started_at"] = now
            updates["next_attempt_at"] = now + timedelta(seconds=2**payout.attempts)
        elif new_status == Payout.Status.COMPLETED:
            updates["completed_at"] = now
            MerchantBalance.objects.select_for_update().get(merchant=payout.merchant)
            MerchantBalance.objects.filter(merchant=payout.merchant).update(
                held_paise=F("held_paise") - payout.amount_paise
            )
        elif new_status == Payout.Status.FAILED:
            updates["failed_at"] = now
            updates["failure_reason"] = failure_reason or "Bank settlement failed."
            MerchantBalance.objects.select_for_update().get(merchant=payout.merchant)
            MerchantBalance.objects.filter(merchant=payout.merchant).update(
                available_paise=F("available_paise") + payout.amount_paise,
                held_paise=F("held_paise") - payout.amount_paise,
            )
            LedgerEntry.objects.create(
                merchant=payout.merchant,
                payout=payout,
                kind=LedgerEntry.Kind.PAYOUT_RELEASE,
                amount_paise=payout.amount_paise,
                description=f"Returned funds for failed payout #{payout.id}",
            )

        Payout.objects.filter(pk=payout.pk).update(**updates)
        payout.refresh_from_db()
        return payout


def process_due_payouts(limit=25):
    now = timezone.now()
    stale_processing_cutoff = now - timedelta(seconds=30)
    due_ids = list(
        Payout.objects.filter(status=Payout.Status.PENDING, next_attempt_at__lte=now)
        .values_list("id", flat=True)[:limit]
    )
    due_ids += list(
        Payout.objects.filter(
            status=Payout.Status.PROCESSING,
            processing_started_at__lte=stale_processing_cutoff,
            next_attempt_at__lte=now,
        ).values_list("id", flat=True)[:limit]
    )

    processed = []
    for payout_id in due_ids[:limit]:
        try:
            with transaction.atomic():
                payout = Payout.objects.select_for_update(skip_locked=True).get(pk=payout_id)
                if payout.status == Payout.Status.PROCESSING and payout.attempts >= 3:
                    processed.append(transition_payout(payout.id, Payout.Status.FAILED, "Max retry attempts reached."))
                    continue
                if payout.status == Payout.Status.PENDING:
                    payout = transition_payout(payout.id, Payout.Status.PROCESSING)
                elif payout.status == Payout.Status.PROCESSING:
                    if (
                        not payout.processing_started_at
                        or payout.processing_started_at > stale_processing_cutoff
                        or payout.next_attempt_at > now
                    ):
                        continue
                    payout = retry_processing_payout(payout.id)
                else:
                    continue

                outcome = random.choices(["completed", "failed", "hang"], weights=[70, 20, 10], k=1)[0]
                if outcome == "completed":
                    processed.append(transition_payout(payout.id, Payout.Status.COMPLETED))
                elif outcome == "failed":
                    processed.append(transition_payout(payout.id, Payout.Status.FAILED, "Simulated bank failure."))
                else:
                    processed.append(payout)
        except Payout.DoesNotExist:
            continue
        except PayoutError:
            continue
    return processed


def retry_processing_payout(payout_id):
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout_id)
        if payout.status != Payout.Status.PROCESSING:
            raise PayoutError("Only processing payouts can be retried.", status.HTTP_409_CONFLICT)
        if payout.attempts >= 3:
            return transition_payout(payout.id, Payout.Status.FAILED, "Max retry attempts reached.")
        now = timezone.now()
        Payout.objects.filter(pk=payout.pk).update(
            attempts=F("attempts") + 1,
            processing_started_at=now,
            next_attempt_at=now + timedelta(seconds=2**payout.attempts),
        )
        payout.refresh_from_db()
        return payout


def serialize_payout(payout):
    return {
        "id": payout.id,
        "amount_paise": payout.amount_paise,
        "bank_account_id": payout.bank_account_id,
        "status": payout.status,
        "failure_reason": payout.failure_reason,
        "attempts": payout.attempts,
        "created_at": payout.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": payout.updated_at.isoformat().replace("+00:00", "Z"),
    }
