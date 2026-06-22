from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RefundViewSet

router = DefaultRouter()
router.register('', RefundViewSet, basename='refunds')

urlpatterns = [path('', include(router.urls))]
