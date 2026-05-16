from django.urls import path
from .pl_views import (
    ProfitLossView, ProfitLossHistoryView, ProfitLossTeachersView,
    IncomeByCourseView, DebtForecastView,
)

urlpatterns = [
    path('', ProfitLossView.as_view(), name='profit-loss'),
    path('history/', ProfitLossHistoryView.as_view(), name='profit-loss-history'),
    path('teachers/', ProfitLossTeachersView.as_view(), name='profit-loss-teachers'),
    path('income-by-course/', IncomeByCourseView.as_view(), name='profit-loss-income-by-course'),
    path('debt-forecast/', DebtForecastView.as_view(), name='profit-loss-debt-forecast'),
]

