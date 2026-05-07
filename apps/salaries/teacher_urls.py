from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeacherSalaryViewSet

router = DefaultRouter()
router.register('', TeacherSalaryViewSet, basename='teacher-salaries')

urlpatterns = [path('', include(router.urls))]

