from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet

router = DefaultRouter()
router.register('', UserViewSet, basename='users')

# Mounted at /api/v1/users/
urlpatterns = [
    path('', include(router.urls)),
]
