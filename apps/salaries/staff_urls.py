from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StaffSalaryViewSet

router = DefaultRouter()
router.register('', StaffSalaryViewSet, basename='staff-salaries')

urlpatterns = [path('', include(router.urls))]

