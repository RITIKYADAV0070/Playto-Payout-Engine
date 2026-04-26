from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Merchant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="BankAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("account_holder_name", models.CharField(max_length=120)),
                ("bank_name", models.CharField(max_length=120)),
                ("account_last4", models.CharField(max_length=4)),
                ("ifsc", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_accounts", to="payments.merchant")),
            ],
        ),
        migrations.CreateModel(
            name="MerchantBalance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("available_paise", models.BigIntegerField(default=0)),
                ("held_paise", models.BigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("merchant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="balance", to="payments.merchant")),
            ],
        ),
        migrations.CreateModel(
            name="Payout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount_paise", models.BigIntegerField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("failure_reason", models.CharField(blank=True, max_length=255)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("bank_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payouts", to="payments.bankaccount")),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payouts", to="payments.merchant")),
            ],
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("customer_payment", "Customer payment"), ("payout_hold", "Payout hold"), ("payout_release", "Payout release")], max_length=32)),
                ("amount_paise", models.BigIntegerField()),
                ("description", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ledger_entries", to="payments.merchant")),
                ("payout", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="payments.payout")),
            ],
        ),
        migrations.CreateModel(
            name="IdempotencyKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.UUIDField()),
                ("request_hash", models.CharField(max_length=64)),
                ("status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="idempotency_keys", to="payments.merchant")),
            ],
        ),
        migrations.AddIndex(model_name="payout", index=models.Index(fields=["status", "next_attempt_at"], name="payments_pa_status_7b0adc_idx")),
        migrations.AddIndex(model_name="payout", index=models.Index(fields=["merchant", "-created_at"], name="payments_pa_merchan_41df17_idx")),
        migrations.AddIndex(model_name="ledgerentry", index=models.Index(fields=["merchant", "-created_at"], name="payments_le_merchan_229d72_idx")),
        migrations.AddIndex(model_name="ledgerentry", index=models.Index(fields=["payout", "kind"], name="payments_le_payout__10976d_idx")),
        migrations.AddConstraint(model_name="idempotencykey", constraint=models.UniqueConstraint(fields=("merchant", "key"), name="uniq_idempotency_key_per_merchant")),
        migrations.AddIndex(model_name="idempotencykey", index=models.Index(fields=["merchant", "key", "expires_at"], name="payments_id_merchan_43cb06_idx")),
    ]
