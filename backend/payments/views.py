from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Count, Max, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta

from .models import LedgerEntry, Merchant, Payout
from .serializers import (
    BalanceSerializer,
    LedgerEntrySerializer,
    MerchantSerializer,
    PayoutCreateSerializer,
    PayoutSerializer,
)
from .services import PayoutError, create_payout_idempotently, ledger_available_balance


def _merchant_id(request):
    return int(request.headers.get("X-Merchant-ID", "1"))


@api_view(["GET"])
def api_index(request):
    return Response(
        {
            "service": "Playto Pay Payout Engine API",
            "version": "v1",
            "status": "ok",
            "endpoints": {
                "health": "/api/v1/health",
                "merchants": "/api/v1/merchants",
                "dashboard": "/api/v1/dashboard",
                "payouts": "/api/v1/payouts",
            },
        }
    )


@api_view(["GET"])
def merchants(request):
    return Response(MerchantSerializer(Merchant.objects.prefetch_related("bank_accounts"), many=True).data)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def dashboard(request):
    merchant = Merchant.objects.get(id=_merchant_id(request))
    balance = merchant.balance
    ledger_balance = ledger_available_balance(merchant)
    now = timezone.now()
    stale_processing_cutoff = now - timedelta(seconds=30)
    payouts = Payout.objects.filter(merchant=merchant)
    status_rows = payouts.values("status").annotate(
        count=Count("id"),
        amount_paise=Coalesce(Sum("amount_paise"), 0),
    )
    status_summary = {
        row["status"]: {"count": row["count"], "amount_paise": row["amount_paise"]}
        for row in status_rows
    }
    for payout_status in Payout.Status.values:
        status_summary.setdefault(payout_status, {"count": 0, "amount_paise": 0})

    pending_due = payouts.filter(status=Payout.Status.PENDING, next_attempt_at__lte=now).count()
    stale_processing = payouts.filter(
        status=Payout.Status.PROCESSING,
        processing_started_at__lte=stale_processing_cutoff,
        next_attempt_at__lte=now,
    ).count()
    final_count = status_summary[Payout.Status.COMPLETED]["count"] + status_summary[Payout.Status.FAILED]["count"]
    success_rate = (
        round(status_summary[Payout.Status.COMPLETED]["count"] * 100 / final_count)
        if final_count
        else None
    )

    return Response(
        {
            "merchant": MerchantSerializer(merchant).data,
            "balance": BalanceSerializer(balance).data,
            "ledger_available_paise": ledger_balance,
            "integrity": {
                "ledger_matches_balance": ledger_balance == balance.available_paise,
                "available_minus_ledger_paise": balance.available_paise - ledger_balance,
            },
            "summary": {
                "status": status_summary,
                "total_payouts": payouts.count(),
                "total_completed_paise": status_summary[Payout.Status.COMPLETED]["amount_paise"],
                "total_failed_paise": status_summary[Payout.Status.FAILED]["amount_paise"],
                "success_rate_percent": success_rate,
                "largest_payout_paise": payouts.aggregate(value=Coalesce(Max("amount_paise"), 0))["value"],
                "bank_account_count": merchant.bank_accounts.count(),
            },
            "worker": {
                "pending_due_count": pending_due,
                "stale_processing_count": stale_processing,
                "work_ready_count": pending_due + stale_processing,
                "retry_after_seconds": 30,
                "poll_seconds": 3,
            },
            "recent_ledger": LedgerEntrySerializer(
                LedgerEntry.objects.filter(merchant=merchant).order_by("-created_at")[:20], many=True
            ).data,
            "payouts": PayoutSerializer(
                Payout.objects.filter(merchant=merchant).select_related("bank_account").order_by("-created_at")[:50],
                many=True,
            ).data,
        }
    )


@api_view(["GET", "POST"])
def payouts(request):
    merchant_id = _merchant_id(request)
    if request.method == "GET":
        rows = Payout.objects.filter(merchant_id=merchant_id).select_related("bank_account").order_by("-created_at")
        return Response(PayoutSerializer(rows, many=True).data)

    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key:
        return Response({"detail": "Idempotency-Key header is required."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = PayoutCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        body, status_code = create_payout_idempotently(merchant_id, idem_key, serializer.validated_data)
    except PayoutError as exc:
        return Response({"detail": exc.message}, status=exc.status_code)
    return Response(body, status=status_code)
