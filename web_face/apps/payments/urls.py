from django.urls import path
from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_list_view, name="payment_list"),
    path("<int:payment_id>/", views.payment_detail_view, name="payment_detail"),
    path("<int:payment_id>/download-html/", views.download_invoice_html_view, name="download_invoice_html"),
    path("<int:payment_id>/download-image/", views.download_invoice_image_view, name="download_invoice_image"),
    path("<int:payment_id>/send-whatsapp/", views.send_receipt_whatsapp_now_view, name="send_receipt_whatsapp"),
    path("settle-debt/<int:member_id>/", views.settle_debt_view, name="settle_debt"),

    # Multi-Treasury & Financial Accounts Routes
    path("accounts/", views.financial_accounts_view, name="accounts_index"),
    path("accounts/transfer/", views.transfer_money_view, name="transfer_money"),
    path("accounts/transfer/<int:transfer_id>/delete/", views.transfer_delete_view, name="transfer_delete"),
    path("accounts/<int:account_id>/update/", views.account_update_view, name="account_update"),

    # Bar & Inventory Routes
    path("bar/", views.bar_inventory_view, name="bar_inventory"),
    path("bar/sale/", views.bar_quick_sale_view, name="bar_quick_sale"),
    path("bar/settle/<int:sale_id>/", views.bar_settle_sale_view, name="bar_settle_sale"),
    path("bar/cancel/<int:sale_id>/", views.bar_cancel_sale_view, name="bar_cancel_sale"),
    path("bar/product/create/", views.bar_product_create_view, name="bar_product_create"),
    path("bar/product/<int:product_id>/edit/", views.bar_product_edit_view, name="bar_product_edit"),
    path("bar/product/<int:product_id>/delete/", views.bar_product_delete_view, name="bar_product_delete"),
    path("bar/product/<int:product_id>/restock/", views.bar_product_restock_view, name="bar_product_restock"),
]


