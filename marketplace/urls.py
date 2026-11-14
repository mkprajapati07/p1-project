from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("join/", views.sign_up, name="signup"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("client/dashboard/", views.client_dashboard, name="client_dashboard"),
    path("companion/dashboard/", views.companion_dashboard, name="companion_dashboard"),
    path("companion/availability/", views.manage_availability, name="manage_availability"),
    path("become-a-companion/", views.companion_apply, name="companion_apply"),
    path("my-plans/", views.my_plans, name="my_plans"),
    path("my-plans/<int:booking_id>/<str:action>/", views.update_booking, name="update_booking"),
    path("companions/<slug:slug>/", views.profile_detail, name="profile_detail"),
    path("companions/<slug:slug>/request/", views.request_booking, name="request_booking"),
    path("companions/<slug:slug>/report/", views.report_profile, name="report_profile"),
    path("companions/<slug:slug>/block/", views.block_profile, name="block_profile"),
    path("safety/blocked/", views.blocked_users, name="blocked_users"),
    path("safety/blocked/<int:block_id>/remove/", views.unblock_user, name="unblock_user"),
]