from django.urls import path
from .pl_views import ProfitLossView, ProfitLossHistoryView, ProfitLossTeachersView

urlpatterns = [
    path('', ProfitLossView.as_view(), name='profit-loss'),
    path('history/', ProfitLossHistoryView.as_view(), name='profit-loss-history'),
    path('teachers/', ProfitLossTeachersView.as_view(), name='profit-loss-teachers'),
]

