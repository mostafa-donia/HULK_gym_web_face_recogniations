from django.urls import path
from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.financial_report_view, name="financial_report"),
    path("retention/", views.member_retention_report_view, name="member_retention"),
]
