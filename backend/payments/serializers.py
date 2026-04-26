from rest_framework import serializers

from .models import BankAccount, LedgerEntry, Merchant, MerchantBalance, Payout


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ["id", "bank_name", "account_holder_name", "account_last4", "ifsc"]


class MerchantSerializer(serializers.ModelSerializer):
    bank_accounts = BankAccountSerializer(many=True)

    class Meta:
        model = Merchant
        fields = ["id", "name", "email", "bank_accounts"]


class BalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantBalance
        fields = ["available_paise", "held_paise", "updated_at"]


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ["id", "kind", "amount_paise", "description", "payout_id", "created_at"]


class PayoutSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)
    bank_account_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "amount_paise",
            "bank_account",
            "bank_account_id",
            "status",
            "failure_reason",
            "attempts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "failure_reason", "attempts", "created_at", "updated_at"]


class PayoutCreateSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.IntegerField(min_value=1)
