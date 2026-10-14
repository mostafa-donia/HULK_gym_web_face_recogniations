"""
URL configuration for Multi-Gym Management & Face Recognition Attendance System.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

from django.http import HttpResponse

def ping_view(request):
    response = HttpResponse("PONG", content_type="text/plain")
    response["Access-Control-Allow-Origin"] = "*"
    return response

urlpatterns = [
    path('ping/', ping_view, name='health_ping'),
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('face/', include('apps.face_recognition.urls')),
    path('kiosk/', RedirectView.as_view(url='/face/kiosk/', permanent=False)),
    path('kiosk', RedirectView.as_view(url='/face/kiosk/', permanent=False)),
    path('camera/', RedirectView.as_view(url='/face/camera-window/', permanent=False)),
    path('camera', RedirectView.as_view(url='/face/camera-window/', permanent=False)),
    path('video-feed/', RedirectView.as_view(url='/face/video-feed/', permanent=False)),
    path('video_feed/', RedirectView.as_view(url='/face/video-feed/', permanent=False)),
    path('members/', include('apps.members.urls')),
    path('operations/', RedirectView.as_view(url='/members/operations/', permanent=False)),
    path('operations', RedirectView.as_view(url='/members/operations/', permanent=False)),
    path('payments/', include('apps.payments.urls')),
    path('expenses/', include('apps.expenses.urls')),
    path('payroll/', include('apps.payroll.urls')),
    path('trainers/', RedirectView.as_view(url='/payroll/trainers/', permanent=False)),
    path('trainers', RedirectView.as_view(url='/payroll/trainers/', permanent=False)),
    path('reports/', include('apps.reports.urls')),
    path('messaging/', include('apps.messaging.urls')),
    path('', include('apps.core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
