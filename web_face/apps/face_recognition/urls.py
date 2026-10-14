from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "face_recognition"

urlpatterns = [
    path("", RedirectView.as_view(url="kiosk/", permanent=False)),
    path("kiosk/", views.face_kiosk_view, name="kiosk"),
    path("kiosk", RedirectView.as_view(url="kiosk/", permanent=False)),
    path("verify/", views.api_face_verify, name="verify"),
    path("verify/api/", views.api_face_verify, name="api_verify"),
    path("enroll/<int:member_id>/", views.api_enroll_face, name="enroll"),
    path("enroll/<int:member_id>/api/", views.api_enroll_face, name="api_enroll_face"),
    path("delete/<int:member_id>/", views.api_delete_face, name="delete"),
    path("delete/<int:member_id>/api/", views.api_delete_face, name="api_delete_face"),
    path("recent-checkins/", views.api_kiosk_recent_checkins, name="recent_checkins"),
    path("recent-checkins/api/", views.api_kiosk_recent_checkins, name="api_recent_checkins"),
    path("video-feed/", views.video_feed_view, name="video_feed"),
    path("video_feed/", views.video_feed_view),
    path("video-feed", views.video_feed_view),
    path("video_feed", views.video_feed_view),
    path("camera-window/", views.independent_camera_window_view, name="camera_window"),
    path("camera_window/", views.independent_camera_window_view),
    path("camera-window", views.independent_camera_window_view),
    path("camera_window", views.independent_camera_window_view),
    path("camera/", views.independent_camera_window_view),
    path("camera", views.independent_camera_window_view),
    path("api/live-events/", views.api_live_events_view, name="api_live_events"),
    path("api/live_events/", views.api_live_events_view),
    path("api/capture-frame/", views.api_capture_frame_view, name="api_capture_frame"),
    path("api/capture_frame/", views.api_capture_frame_view),
]
