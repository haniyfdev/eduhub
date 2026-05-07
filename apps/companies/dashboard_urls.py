from django.urls import path
from .dashboard_views import (
    DashboardSummaryView,
    DashboardRevenueView,
    DashboardDebtsSummaryView,
    DashboardTeacherStatsView,
)

urlpatterns = [
    path('summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('revenue/', DashboardRevenueView.as_view(), name='dashboard-revenue'),
    path('debts-summary/', DashboardDebtsSummaryView.as_view(), name='dashboard-debts-summary'),
    path('teacher-stats/', DashboardTeacherStatsView.as_view(), name='dashboard-teacher-stats'),
]

