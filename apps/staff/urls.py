from rest_framework.routers import DefaultRouter
from .views import StaffViewSet, StaffSalaryViewSet

router = DefaultRouter()
router.register('staff', StaffViewSet, basename='staff')
router.register('staff-salaries', StaffSalaryViewSet, basename='staff-salaries')

urlpatterns = router.urls
