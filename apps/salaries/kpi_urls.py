from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StaffKpiRuleViewSet

router = DefaultRouter()
router.register('', StaffKpiRuleViewSet, basename='staff-kpi-rules')

urlpatterns = [path('', include(router.urls))]
