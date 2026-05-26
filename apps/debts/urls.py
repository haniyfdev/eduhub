from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DebtViewSet, SchedulerStatusView

router = DefaultRouter()
router.register('', DebtViewSet, basename='debts')

urlpatterns = [
    path('', include(router.urls)),
    path('scheduler/status/', SchedulerStatusView.as_view(), name='scheduler-status'),
]

