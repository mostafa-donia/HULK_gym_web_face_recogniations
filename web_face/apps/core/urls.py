from django.urls import path
from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("index/", views.dashboard_view, name="index"),
    path("mobile/", views.manager_mobile_dashboard_view, name="manager_mobile_dashboard"),
    path("manager/", views.manager_dashboard_view, name="manager_dashboard"),
    path("quick-search/", views.quick_search_view, name="quick_search"),
    path("checkin/<int:member_id>/", views.quick_checkin_view, name="quick_checkin"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/updates/check/", views.api_check_system_updates_view, name="check_updates"),
    path("settings/updates/perform/", views.api_perform_system_update_view, name="perform_update"),
    path("settings/updates/progress/", views.api_update_progress_view, name="update_progress"),
    path("license/activate/", views.license_activate_api, name="license_activate"),
    path("license/sync/", views.license_sync_remote_api, name="license_sync"),
    path("license/status/", views.license_status_api, name="license_status"),
    path("support/ticket/", views.submit_support_ticket_api, name="submit_support_ticket"),
    path("api/heartbeat/", views.api_heartbeat_view, name="api_heartbeat"),
    path("api/shutdown/", views.api_shutdown_system_view, name="api_shutdown"),
]

