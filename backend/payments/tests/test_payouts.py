from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from django.db import connection, connections
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from payments.models import BankAccount, LedgerEntry, Merchant, MerchantBalance, Payout
from payments.services import PayoutError, create_payout_idempotently, transition_payout


def create_merchant_with_balance(amount_paise=10000):
    merchant = Merchant.objects.create(name="Test Merchant", email=f"{uuid4()}@example.com")
    bank = BankAccount.objects.create(
        merchant=merchant,
        account_holder_name="Test Merchant",
        bank_name="HDFC Bank",
        account_last4="4242",
        ifsc="HDFC0000123",
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        kind=LedgerEntry.Kind.CUSTOMER_PAYMENT,
        amount_paise=amount_paise,
        description="Test customer payment",
    )
    MerchantBalance.objects.create(merchant=merchant, available_paise=amount_paise)
    return merchant, bank


class IdempotencyTests(APITestCase):
    def test_same_idempotency_key_returns_exact_same_response(self):
        merchant, bank = create_merchant_with_balance()
        key = str(uuid4())
        payload = {"amount_paise": 4000, "bank_account_id": bank.id}

        first = self.client.post(
            "/api/v1/payouts",
            payload,
            format="json",
            HTTP_X_MERCHANT_ID=str(merchant.id),
            HTTP_IDEMPOTENCY_KEY=key,
        )
        second = self.client.post(
            "/api/v1/payouts",
            payload,
            format="json",
            HTTP_X_MERCHANT_ID=str(merchant.id),
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Payout.objects.filter(merchant=merchant).count(), 1)


class ConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_payouts_cannot_overdraw_balance(self):
        if connection.vendor != "postgresql":
            self.skipTest("select_for_update concurrency semantics require PostgreSQL")

        merchant, bank = create_merchant_with_balance(amount_paise=10000)
        payload = {"amount_paise": 6000, "bank_account_id": bank.id}

        def request_once():
            connections.close_all()
            try:
                body, code = create_payout_idempotently(merchant.id, uuid4(), payload)
                return code, body
            except PayoutError as exc:
                return exc.status_code, {"detail": exc.message}
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: request_once(), range(2)))

        status_codes = sorted(code for code, _ in results)
        self.assertEqual(status_codes, [201, 422])
        balance = MerchantBalance.objects.get(merchant=merchant)
        self.assertEqual(balance.available_paise, 4000)
        self.assertEqual(balance.held_paise, 6000)
        self.assertEqual(Payout.objects.filter(merchant=merchant).count(), 1)

    def test_failed_to_completed_transition_is_rejected(self):
        merchant, bank = create_merchant_with_balance()
        body, _ = create_payout_idempotently(
            merchant.id, uuid4(), {"amount_paise": 2500, "bank_account_id": bank.id}
        )
        transition_payout(body["id"], Payout.Status.PROCESSING)
        transition_payout(body["id"], Payout.Status.FAILED)

        with self.assertRaises(PayoutError):
            transition_payout(body["id"], Payout.Status.COMPLETED)
