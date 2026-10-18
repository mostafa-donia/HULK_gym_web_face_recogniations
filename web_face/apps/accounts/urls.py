from django.urls import path
from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("switch-branch/<str:branch_id>/", views.switch_branch, name="switch_branch"),
]
