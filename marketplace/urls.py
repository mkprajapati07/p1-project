from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("join/", views.sign_up, name="signup"),
    path("become-a-companion/", views.companion_apply, name="companion_apply"),
    path("my-plans/", views.my_plans, name="my_plans"),
    path("my-plans/<int:booking_id>/<str:action>/", views.update_booking, name="update_booking"),
    path("companions/<slug:slug>/", views.profile_detail, name="profile_detail"),
    path("companions/<slug:slug>/request/", views.request_booking, name="request_booking"),
]