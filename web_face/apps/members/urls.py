from django.urls import path
from apps.members import views

app_name = "members"

urlpatterns = [
    path("", views.member_list_view, name="member_list"),
    path("create/", views.member_create_view, name="member_create"),
    path("<int:member_id>/", views.member_detail_view, name="member_detail"),
    path("<int:member_id>/edit/", views.member_edit_view, name="member_edit"),
    path("<int:member_id>/quick-private/", views.member_quick_private_update_view, name="member_quick_private"),
    path("<int:member_id>/freeze/", views.member_freeze_view, name="member_freeze"),
    path("<int:member_id>/unfreeze/", views.member_unfreeze_view, name="member_unfreeze"),
    path("<int:member_id>/cancel-refund/", views.member_cancel_refund_view, name="member_cancel_refund"),
    path("<int:member_id>/delete/", views.member_delete_view, name="member_delete"),
    path("plan/<int:plan_id>/edit/", views.plan_edit_view, name="plan_edit"),
    path("plan/<int:plan_id>/delete/", views.plan_delete_view, name="plan_delete"),
    path("operations/", views.smart_operations_view, name="smart_operations"),
    path("subscription/create/", views.subscription_create_view, name="subscription_create"),
    path("subscription/<int:subscription_id>/edit/", views.subscription_edit_view, name="subscription_edit"),
    path("api/search/", views.member_search_api, name="member_search_api"),
]
