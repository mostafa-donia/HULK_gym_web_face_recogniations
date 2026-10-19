from django.urls import path
from apps.messaging import views

app_name = "messaging"

urlpatterns = [
    path("", views.whatsapp_queue_view, name="whatsapp_queue"),
    path("compose/", views.whatsapp_compose_view, name="whatsapp_compose"),
    path("dispatch/", views.whatsapp_dispatch_now_view, name="whatsapp_dispatch"),
    path("bulk/", views.whatsapp_bulk_send_view, name="whatsapp_bulk_send"),
    path("api/count-recipients/", views.whatsapp_count_recipients_api, name="whatsapp_count_recipients"),
    path("api/pending-summary/", views.whatsapp_pending_summary_api, name="whatsapp_pending_summary"),
    path("api/pending-messages/", views.whatsapp_pending_messages_api, name="whatsapp_pending_messages"),
    path("api/dispatch-batch/", views.whatsapp_dispatch_batch_api, name="whatsapp_dispatch_batch"),
    path("api/dispatch-single/", views.whatsapp_dispatch_single_api, name="whatsapp_dispatch_single"),
    path("api/return-focus/", views.whatsapp_return_focus_api, name="whatsapp_return_focus"),
    path("api/pin-overlay/", views.whatsapp_pin_overlay_api, name="whatsapp_pin_overlay"),
    path("overlay-window/", views.whatsapp_overlay_window_view, name="whatsapp_overlay_window"),
    path("api/test-search-coords/", views.whatsapp_test_search_coords_api, name="whatsapp_test_search_coords"),
    path("prepare-reminders/", views.whatsapp_prepare_reminders_view, name="whatsapp_prepare_reminders"),
    path("manager-report/", views.whatsapp_manager_report_view, name="whatsapp_manager_report"),
    path("batch-action/", views.whatsapp_batch_action_view, name="whatsapp_batch_action"),
    path("<int:message_id>/retry/", views.whatsapp_retry_view, name="whatsapp_retry"),
    path("<int:message_id>/delete/", views.whatsapp_delete_view, name="whatsapp_delete"),
    path("message-bank/", views.whatsapp_message_bank_view, name="whatsapp_message_bank"),
    path("api/message-bank/preview/", views.whatsapp_message_bank_preview_api, name="whatsapp_message_bank_preview"),

    # Telegram Bot Routes
    path("telegram/webhook/", views.telegram_webhook_view, name="telegram_webhook"),
    path("telegram/test-connection/", views.telegram_test_connection_view, name="telegram_test_connection"),
    path("telegram/set-webhook/", views.telegram_set_webhook_view, name="telegram_set_webhook"),
    path("telegram/send-test/", views.telegram_send_test_message_view, name="telegram_send_test_message"),
]

