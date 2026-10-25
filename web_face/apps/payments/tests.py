from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.expenses.models import Expense, ExpenseCategory
from apps.payments.models import (
    FinancialAccount,
    MoneyTransfer,
    AccountType,
    Payment,
    PaymentOperationType,
)
from apps.payments.services import (
    get_account_balance_details,
    get_all_financial_accounts_summary,
    execute_money_transfer,
    resolve_account_for_payment_method,
)


class MultiTreasuryAndTransfersTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager_test",
            password="password123",
            role=UserRole.MANAGER,
        )
        self.client = Client()
        self.client.login(username="manager_test", password="password123")

        # Unlock manager session
        session = self.client.session
        session["manager_page_unlocked"] = True
        session.save()

        # Initialize default accounts
        accounts = FinancialAccount.get_default_accounts()
        self.cash_acc = next(a for a in accounts if a.account_type == AccountType.CASH)
        self.vodafone_acc = next(a for a in accounts if a.account_type == AccountType.VODAFONE_CASH)
        self.bank_acc = next(a for a in accounts if a.account_type == AccountType.BANK)

    def test_default_accounts_creation(self):
        """Verify the 3 core money accounts (Cash, Vodafone Cash, Bank) are initialized."""
        self.assertEqual(FinancialAccount.objects.count(), 3)
        self.assertTrue(self.cash_acc.is_default)
        self.assertEqual(self.vodafone_acc.account_type, AccountType.VODAFONE_CASH)
        self.assertEqual(self.bank_acc.account_type, AccountType.BANK)

    def test_payment_method_resolution_to_account(self):
        """Verify payment method strings map to the correct treasury account."""
        acc_voda = resolve_account_for_payment_method("فودافون كاش")
        self.assertEqual(acc_voda.id, self.vodafone_acc.id)

        acc_wallet = resolve_account_for_payment_method("محفظة الكترونية")
        self.assertEqual(acc_wallet.id, self.vodafone_acc.id)

        acc_bank = resolve_account_for_payment_method("انستا باي")
        self.assertEqual(acc_bank.id, self.bank_acc.id)

        acc_visa = resolve_account_for_payment_method("فيزا")
        self.assertEqual(acc_visa.id, self.bank_acc.id)

        acc_cash = resolve_account_for_payment_method("نقدي")
        self.assertEqual(acc_cash.id, self.cash_acc.id)

    def test_account_inflows_and_outflows(self):
        """Verify payments and expenses correctly adjust individual account balances."""
        # Record payment to Vodafone Cash
        Payment.objects.create(
            payment_id="PAY-TEST01",
            invoice_no="INV-TEST01",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            amount=Decimal("1500.00"),
            payment_method="فودافون كاش",
            account=self.vodafone_acc,
        )

        # Record payment to Bank
        Payment.objects.create(
            payment_id="PAY-TEST02",
            invoice_no="INV-TEST02",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            amount=Decimal("2000.00"),
            payment_method="انستا باي",
            account=self.bank_acc,
        )

        # Record payment to Cash
        Payment.objects.create(
            payment_id="PAY-TEST03",
            invoice_no="INV-TEST03",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            amount=Decimal("500.00"),
            payment_method="نقدي",
            account=self.cash_acc,
        )

        voda_bal = get_account_balance_details(self.vodafone_acc)["current_balance"]
        bank_bal = get_account_balance_details(self.bank_acc)["current_balance"]
        cash_bal = get_account_balance_details(self.cash_acc)["current_balance"]

        self.assertEqual(voda_bal, Decimal("1500.00"))
        self.assertEqual(bank_bal, Decimal("2000.00"))
        self.assertEqual(cash_bal, Decimal("500.00"))

        summary = get_all_financial_accounts_summary()
        self.assertEqual(summary["total_balance"], Decimal("4000.00"))

    def test_internal_money_transfer_with_fees(self):
        """
        Verify transferring from Vodafone Cash to Bank with transfer fees:
        1. Vodafone Cash balance drops by amount + fee.
        2. Bank balance increases by amount.
        3. A transfer fee Expense is automatically recorded.
        4. Total net treasury drops only by the transfer fee.
        """
        # Give Vodafone Cash 2,000 EGP inflow
        Payment.objects.create(
            payment_id="PAY-TEST04",
            invoice_no="INV-TEST04",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            amount=Decimal("2000.00"),
            payment_method="فودافون كاش",
            account=self.vodafone_acc,
        )

        # Transfer 1,000 EGP from Vodafone Cash to Bank with 10 EGP fee
        transfer = execute_money_transfer(
            from_account=self.vodafone_acc,
            to_account=self.bank_acc,
            amount=Decimal("1000.00"),
            fee=Decimal("10.00"),
            reference_no="REF-VF123",
            notes="تحويل إيراد فودافون كاش للبنك",
            user=self.manager,
        )

        self.assertIsNotNone(transfer.transfer_id)
        self.assertEqual(transfer.amount, Decimal("1000.00"))
        self.assertEqual(transfer.fee, Decimal("10.00"))

        # Verify fee expense was created
        fee_exp = Expense.objects.filter(
            category__name="رسوم ومصاريف تحويلات بنكية ومحافظ",
            amount=Decimal("10.00"),
            account=self.vodafone_acc,
        ).first()
        self.assertIsNotNone(fee_exp)
        self.assertIn(transfer.transfer_id, fee_exp.description)

        # Check balances
        voda_bal = get_account_balance_details(self.vodafone_acc)["current_balance"]
        bank_bal = get_account_balance_details(self.bank_acc)["current_balance"]

        # Vodafone: 2000 (inflow) - 1000 (transferred) - 10 (fee expense) = 990
        self.assertEqual(voda_bal, Decimal("990.00"))
        # Bank: 0 + 1000 = 1000
        self.assertEqual(bank_bal, Decimal("1000.00"))

        # Total Gym Net = 990 + 1000 = 1990 EGP (2000 revenue - 10 fee expense)
        summary = get_all_financial_accounts_summary()
        self.assertEqual(summary["total_balance"], Decimal("1990.00"))

    def test_transfer_validation(self):
        """Verify cannot transfer to same account or with invalid amounts."""
        with self.assertRaises(ValueError):
            execute_money_transfer(
                from_account=self.vodafone_acc,
                to_account=self.vodafone_acc,
                amount=Decimal("100.00"),
            )

        with self.assertRaises(ValueError):
            execute_money_transfer(
                from_account=self.vodafone_acc,
                to_account=self.bank_acc,
                amount=Decimal("0.00"),
            )

    def test_transfer_http_endpoints(self):
        """Verify the web views for listing accounts and performing transfers."""
        # 1. Accounts page loads
        resp = self.client.get(reverse("payments:accounts_index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "الخزائن والحسابات المالية والتحويلات")
        self.assertContains(resp, self.vodafone_acc.name)
        self.assertContains(resp, self.bank_acc.name)

        # 2. Perform transfer via POST
        post_data = {
            "from_account_id": self.cash_acc.id,
            "to_account_id": self.bank_acc.id,
            "amount": "500.00",
            "fee": "5.00",
            "notes": "إيداع بنكي من الكاش",
        }
        post_resp = self.client.post(reverse("payments:transfer_money"), post_data, follow=True)
        self.assertEqual(post_resp.status_code, 200)
        self.assertContains(post_resp, "تم تحويل 500.00 ج.م بنجاح")

        # 3. Transfer appears in history
        self.assertEqual(MoneyTransfer.objects.count(), 1)
        transfer = MoneyTransfer.objects.first()
        self.assertEqual(transfer.amount, Decimal("500.00"))
        self.assertEqual(transfer.fee, Decimal("5.00"))

        # 4. Delete transfer via POST
        del_resp = self.client.post(reverse("payments:transfer_delete", args=[transfer.id]), follow=True)
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(MoneyTransfer.objects.count(), 0)
