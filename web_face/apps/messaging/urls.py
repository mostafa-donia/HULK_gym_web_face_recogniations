from django.urls import path
from apps.messaging import views

app_name = "messaging"

urlpatterns = [
    path("", views.whatsapp_queue_view, name="whatsapp_queue"),
    path("compose/", views.whatsapp_compose_view, name="whatsapp_compose"),
    path("dispatch/", views.whatsapp_dispatch_now_view, name="whatsapp_dispatch"),
    path("bulk/", views.whatsapp_bulk_send_view, name="whatsapp_bulk_send"),
    path("api/count-recipients/", views.whatsapp_count_recipients_api, name="whatsapp_count_recipients"),
    path("prepare-reminders/", views.whatsapp_prepare_reminders_view, name="whatsapp_prepare_reminders"),
    path("manager-report/", views.whatsapp_manager_report_view, name="whatsapp_manager_report"),
    path("batch-action/", views.whatsapp_batch_action_view, name="whatsapp_batch_action"),
    path("<int:message_id>/retry/", views.whatsapp_retry_view, name="whatsapp_retry"),
    path("<int:message_id>/delete/", views.whatsapp_delete_view, name="whatsapp_delete"),
]
