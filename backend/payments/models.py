from django.db import models
from django.utils import timezone


class Merchant(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BankAccount(models.Model):
    merchant = models.ForeignKey(Merchant, related_name="bank_accounts", on_delete=models.CASCADE)
    account_holder_name = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=120)
    account_last4 = models.CharField(max_length=4)
    ifsc = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bank_name} ****{self.account_last4}"


class MerchantBalance(models.Model):
    merchant = models.OneToOneField(Merchant, related_name="balance", on_delete=models.CASCADE)
    available_paise = models.BigIntegerField(default=0)
    held_paise = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class LedgerEntry(models.Model):
    class Kind(models.TextChoices):
        CUSTOMER_PAYMENT = "customer_payment", "Customer payment"
        PAYOUT_HOLD = "payout_hold", "Payout hold"
        PAYOUT_RELEASE = "payout_release", "Payout release"

    merchant = models.ForeignKey(Merchant, related_name="ledger_entries", on_delete=models.CASCADE)
    payout = models.ForeignKey(
        "Payout", related_name="ledger_entries", null=True, blank=True, on_delete=models.PROTECT
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    amount_paise = models.BigIntegerField()
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["merchant", "-created_at"]),
            models.Index(fields=["payout", "kind"]),
        ]


class Payout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    merchant = models.ForeignKey(Merchant, related_name="payouts", on_delete=models.CASCADE)
    bank_account = models.ForeignKey(BankAccount, related_name="payouts", on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["merchant", "-created_at"]),
        ]


class IdempotencyKey(models.Model):
    merchant = models.ForeignKey(Merchant, related_name="idempotency_keys", on_delete=models.CASCADE)
    key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["merchant", "key"], name="uniq_idempotency_key_per_merchant")
        ]
        indexes = [models.Index(fields=["merchant", "key", "expires_at"])]
