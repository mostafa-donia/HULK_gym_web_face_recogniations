from django.urls import path
from apps.expenses import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list_view, name="expense_list"),
    path("create/", views.expense_create_view, name="expense_create"),
    path("<int:expense_id>/delete/", views.expense_delete_view, name="expense_delete"),
]
