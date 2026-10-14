from django.urls import path
from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_list_view, name="payment_list"),
    path("<int:payment_id>/", views.payment_detail_view, name="payment_detail"),
    path("settle-debt/<int:member_id>/", views.settle_debt_view, name="settle_debt"),
]
