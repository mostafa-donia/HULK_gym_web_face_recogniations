from django.urls import path
from apps.messaging import views

app_name = "messaging"

urlpatterns = [
    path("", views.whatsapp_queue_view, name="whatsapp_queue"),
    path("compose/", views.whatsapp_compose_view, name="whatsapp_compose"),
    path("dispatch/", views.whatsapp_dispatch_now_view, name="whatsapp_dispatch"),
    path("<int:message_id>/retry/", views.whatsapp_retry_view, name="whatsapp_retry"),
    path("<int:message_id>/delete/", views.whatsapp_delete_view, name="whatsapp_delete"),
]
