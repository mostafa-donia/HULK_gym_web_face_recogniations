from django.urls import path
from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_list_view, name="payment_list"),
    path("<int:payment_id>/", views.payment_detail_view, name="payment_detail"),
    path("<int:payment_id>/download-html/", views.download_invoice_html_view, name="download_invoice_html"),
    path("<int:payment_id>/send-whatsapp/", views.send_receipt_whatsapp_now_view, name="send_receipt_whatsapp"),
    path("settle-debt/<int:member_id>/", views.settle_debt_view, name="settle_debt"),
]

