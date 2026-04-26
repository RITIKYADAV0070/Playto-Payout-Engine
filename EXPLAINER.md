# EXPLAINER

Live demo:

- Dashboard: https://playto-pay-dashboard.onrender.com
- API: https://playto-pay-api.onrender.com/api/v1/
- Health check: https://playto-pay-api.onrender.com/api/v1/health

## The Ledger

Balance calculation query from `backend/payments/services.py`:

```python
LedgerEntry.objects.filter(merchant=merchant).aggregate(
    balance=Coalesce(Sum("amount_paise"), 0)
)
```

Ledger entries are signed integer paise rows. Customer payments are positive credits, payout holds are negative debits, and failed payout releases are positive credits. This keeps the displayed available balance derivable from `SUM(amount_paise)` without floats or decimals. `MerchantBalance` stores the same available and held values as locked counters for fast concurrent writes; the ledger remains the audit trail and invariant source.

## The Lock

The overdraft prevention code is in `backend/payments/services.py`:

```python
balance = MerchantBalance.objects.select_for_update().get(merchant=merchant)
if balance.available_paise < amount:
    raise PayoutError("Insufficient available balance.", status.HTTP_422_UNPROCESSABLE_ENTITY)

MerchantBalance.objects.filter(pk=balance.pk).update(
    available_paise=F("available_paise") - amount,
    held_paise=F("held_paise") + amount,
)
```

It relies on PostgreSQL row-level locks via `SELECT ... FOR UPDATE`. Two concurrent payout requests for the same merchant must queue on the same `MerchantBalance` row. The second transaction sees the first transaction's committed deduction before it performs its own balance check.

## The Idempotency

The system stores one `IdempotencyKey` row per `(merchant, key)` with a unique constraint:

```python
models.UniqueConstraint(fields=["merchant", "key"], name="uniq_idempotency_key_per_merchant")
```

The request body is hashed and stored. When the same merchant sends the same key again, the code locks the existing idempotency row and returns the stored `response_body` and `status_code`. If the first request is still in flight, PostgreSQL's unique constraint makes the second insert wait; after the first transaction commits, the second request fetches the row and returns the exact saved response instead of creating a duplicate payout.

Keys expire after 24 hours through the `expires_at` column. A reused expired key is rejected so clients are forced to send a fresh UUID.

## The State Machine

Legal transitions are declared in `backend/payments/services.py`:

```python
LEGAL_TRANSITIONS = {
    Payout.Status.PENDING: {Payout.Status.PROCESSING},
    Payout.Status.PROCESSING: {Payout.Status.COMPLETED, Payout.Status.FAILED},
    Payout.Status.COMPLETED: set(),
    Payout.Status.FAILED: set(),
}
```

Every state change goes through this check:

```python
if new_status not in LEGAL_TRANSITIONS[payout.status]:
    raise PayoutError(f"Illegal payout transition {payout.status} -> {new_status}.", status.HTTP_409_CONFLICT)
```

That blocks failed-to-completed, completed-to-pending, and all backwards transitions. The failed transition also returns funds and writes the release ledger entry inside the same database transaction.

## Retry Logic

The worker selects pending payouts and processing payouts stuck for more than 30 seconds. Pending payouts move to processing. Stale processing payouts retry with exponential backoff. After 3 attempts, the payout moves to failed and held funds are released atomically.

## AI Audit

One subtle AI-generated version of the payout creation code used this pattern:

```python
balance = MerchantBalance.objects.get(merchant=merchant)
if balance.available_paise >= amount:
    balance.available_paise -= amount
    balance.held_paise += amount
    balance.save()
```

That is a classic check-then-write race. Two requests can both read the old balance and both pass the check before either save commits. I replaced it with a PostgreSQL row lock and database `F()` updates:

```python
balance = MerchantBalance.objects.select_for_update().get(merchant=merchant)
if balance.available_paise < amount:
    raise PayoutError("Insufficient available balance.", status.HTTP_422_UNPROCESSABLE_ENTITY)

MerchantBalance.objects.filter(pk=balance.pk).update(
    available_paise=F("available_paise") - amount,
    held_paise=F("held_paise") + amount,
)
```

This makes the balance check and hold creation part of one serialized transaction for that merchant balance row.
