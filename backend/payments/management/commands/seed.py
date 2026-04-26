from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce

from payments.models import BankAccount, LedgerEntry, Merchant, MerchantBalance, Payout


class Command(BaseCommand):
    help = "Seed merchants, bank accounts, and credit ledger history."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rich",
            action="store_true",
            help="Include extra demo studios beyond the 3 merchants required by the challenge.",
        )

    def handle(self, *args, **options):
        core_fixtures = [
            {
                "name": "Acme Studio",
                "email": "ops@acme.example",
                "credits": [1250000, 450000, 300000],
                "accounts": [
                    ("HDFC Bank", "1111", "HDFC0000001"),
                ],
            },
            {
                "name": "Northstar Freelance",
                "email": "hello@northstar.example",
                "credits": [800000, 225000],
                "accounts": [
                    ("HDFC Bank", "2222", "HDFC0000002"),
                ],
            },
            {
                "name": "Pixel Partners",
                "email": "finance@pixel.example",
                "credits": [2200000, 650000, 180000],
                "accounts": [
                    ("HDFC Bank", "3333", "HDFC0000003"),
                ],
            },
        ]
        rich_fixtures = [
            {
                "name": "Blue Kite Studio",
                "email": "accounts@bluekite.example",
                "credits": [9400000, 2750000, 6100000],
                "accounts": [
                    ("Yes Bank", "4404", "YESB0004404"),
                    ("HDFC Bank", "5404", "HDFC0005404"),
                ],
            },
            {
                "name": "Mango Labs",
                "email": "money@mangolabs.example",
                "credits": [15500000, 4300000, 2650000],
                "accounts": [
                    ("ICICI Bank", "5505", "ICIC0005505"),
                    ("Axis Bank", "6505", "UTIB0006505"),
                ],
            },
            {
                "name": "Orbit Creative",
                "email": "billing@orbitcreative.example",
                "credits": [7200000, 3800000, 1950000],
                "accounts": [
                    ("HDFC Bank", "6606", "HDFC0006606"),
                    ("Kotak Mahindra Bank", "7606", "KKBK0007606"),
                ],
            },
            {
                "name": "Stackline Agency",
                "email": "finance@stackline.example",
                "credits": [18900000, 6700000, 5300000],
                "accounts": [
                    ("Axis Bank", "7707", "UTIB0007707"),
                    ("ICICI Bank", "8707", "ICIC0008707"),
                    ("HDFC Bank", "9707", "HDFC0009707"),
                ],
            },
            {
                "name": "Kaveri Design Co.",
                "email": "hello@kaveridesign.example",
                "credits": [11200000, 3400000, 2400000],
                "accounts": [
                    ("HDFC Bank", "8808", "HDFC0008808"),
                    ("Yes Bank", "9808", "YESB0009808"),
                ],
            },
        ]
        fixtures = core_fixtures + (rich_fixtures if options["rich"] else [])
        for fixture in fixtures:
            name = fixture["name"]
            email = fixture["email"]
            merchant, _ = Merchant.objects.get_or_create(email=email, defaults={"name": name})
            if merchant.name != name:
                merchant.name = name
                merchant.save(update_fields=["name"])

            for bank_name, account_last4, ifsc in fixture["accounts"]:
                BankAccount.objects.get_or_create(
                    merchant=merchant,
                    account_last4=account_last4,
                    defaults={
                        "account_holder_name": name,
                        "bank_name": bank_name,
                        "ifsc": ifsc,
                    },
                )

            for credit_idx, amount in enumerate(fixture["credits"], start=1):
                LedgerEntry.objects.get_or_create(
                    merchant=merchant,
                    kind=LedgerEntry.Kind.CUSTOMER_PAYMENT,
                    description=f"Seed credit {credit_idx} for {name}",
                    defaults={"amount_paise": amount},
                )

            balance, _ = MerchantBalance.objects.get_or_create(merchant=merchant)
            available = LedgerEntry.objects.filter(merchant=merchant).aggregate(
                value=Coalesce(Sum("amount_paise"), 0)
            )["value"]
            held = Payout.objects.filter(
                merchant=merchant,
                status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING],
            ).aggregate(value=Coalesce(Sum("amount_paise"), 0))["value"]
            balance.available_paise = available
            balance.held_paise = held
            balance.save(update_fields=["available_paise", "held_paise"])
        fixture_type = "rich demo" if options["rich"] else "challenge"
        self.stdout.write(self.style.SUCCESS(f"Seeded Playto Pay {fixture_type} data"))
