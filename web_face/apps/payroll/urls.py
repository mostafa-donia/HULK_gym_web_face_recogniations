from django.urls import path
from apps.payroll import views

app_name = "payroll"

urlpatterns = [
    path("trainers/", views.trainers_index_view, name="trainers_index"),
    path("trainers/lock/", views.trainers_lock_view, name="trainers_lock"),
    path("coaches/<int:employee_id>/", views.coach_detail_view, name="coach_detail"),
    path("coaches/<int:employee_id>/salary-report/", views.coach_salary_report_view, name="coach_salary_report"),
    path("employees/", views.employee_list_view, name="employee_list"),
    path("employees/create/", views.employee_create_view, name="employee_create"),
    path("employees/<int:employee_id>/edit/", views.employee_edit_view, name="employee_edit"),
    path("trainer-assignments/", views.trainer_assignment_list_view, name="trainer_assignments"),
    path("private-training/", views.record_private_training_view, name="private_training_records"),
    path("adjustments/", views.salary_adjustment_list_view, name="adjustments_list"),
    path("adjustments/create/", views.salary_adjustment_create_view, name="adjustment_create"),
    path("adjustments/<int:adjustment_id>/action/", views.salary_adjustment_action_view, name="adjustment_action"),
    path("advances/create/", views.salary_advance_create_view, name="advance_create"),
    path("runs/", views.payroll_run_list_view, name="payroll_runs"),
    path("runs/<str:period>/", views.payroll_run_detail_view, name="payroll_run_detail"),
    path("runs/<str:period>/approve/", views.payroll_approve_view, name="payroll_approve"),
    path("statement/<int:item_id>/", views.payroll_statement_view, name="payroll_statement"),
    path("statement/<int:item_id>/send-whatsapp/", views.payroll_send_whatsapp_view, name="payroll_send_whatsapp"),
]
