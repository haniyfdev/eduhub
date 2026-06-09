from django.urls import path
from .views import (
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RefreshTokenView,
    ResetPasswordView,
    SelectCompanyView,
    VerifyOtpView,
)

# Mounted at /api/auth/
urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('select-company/', SelectCompanyView.as_view(), name='auth-select-company'),
    path('token/refresh/', RefreshTokenView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('verify-otp/', VerifyOtpView.as_view(), name='auth-verify-otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='auth-reset-password'),
]
