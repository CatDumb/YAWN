from django.urls import path

from apps.accounts.views import (
    AccessRequestView,
    CSRFTokenView,
    CurrentUserView,
    LogoutView,
    OTPRequestView,
    OTPVerifyView,
    UserPreferenceView,
)

app_name = "accounts"

urlpatterns = [
    path("auth/sign-up/", AccessRequestView.as_view(), name="sign-up"),
    path("auth/csrf/", CSRFTokenView.as_view(), name="csrf"),
    path("auth/otp/request/", OTPRequestView.as_view(), name="otp-request"),
    path("auth/otp/verify/", OTPVerifyView.as_view(), name="otp-verify"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("users/me/", CurrentUserView.as_view(), name="current-user"),
    path("preferences/", UserPreferenceView.as_view(), name="preferences"),
]
