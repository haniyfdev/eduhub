from django.urls import path
from .views import LoginView, LogoutView, RefreshTokenView

# Mounted at /api/auth/
urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('token/refresh/', RefreshTokenView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
]
