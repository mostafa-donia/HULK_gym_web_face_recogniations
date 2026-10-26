from django.contrib import admin
from .models import (
    PaymentMethod,
    FinancialAccount,
    MoneyTransfer,
    Payment,
    BarProduct,
    BarSale,
    ReceptionCashHandover,
)

admin.site.register(PaymentMethod)
admin.site.register(FinancialAccount)
admin.site.register(MoneyTransfer)
admin.site.register(Payment)
admin.site.register(BarProduct)
admin.site.register(BarSale)
admin.site.register(ReceptionCashHandover)
