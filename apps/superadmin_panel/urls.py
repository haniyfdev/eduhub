from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SuperadminCompanyListView,
    SuperadminCompanyDetailView,
    SuperadminCreateBossView,
    SuperadminCompanyArchiveView,
    SuperadminCompanyUnarchiveView,
    SuperadminDebtListView,
    SuperadminDebtPayView,
    SuperadminPaymentListView,
    SuperadminPlanView,
    SuperadminRevenueView,
    SuperadminSubscriptionView,
    SuperadminLogViewSet,
)

router = DefaultRouter()
router.register('logs', SuperadminLogViewSet, basename='superadmin-logs')

urlpatterns = [
    path('companies/', SuperadminCompanyListView.as_view(), name='superadmin-companies'),
    path('companies/<uuid:pk>/', SuperadminCompanyDetailView.as_view(), name='superadmin-company-detail'),
    path('companies/<uuid:pk>/create-boss/', SuperadminCreateBossView.as_view(), name='superadmin-create-boss'),
    path('companies/<uuid:pk>/archive/', SuperadminCompanyArchiveView.as_view(), name='superadmin-company-archive'),
    path('companies/<uuid:pk>/unarchive/', SuperadminCompanyUnarchiveView.as_view(), name='superadmin-company-unarchive'),
    path('debts/', SuperadminDebtListView.as_view(), name='superadmin-debts'),
    path('debts/<int:pk>/pay/', SuperadminDebtPayView.as_view(), name='superadmin-debt-pay'),
    path('payments/', SuperadminPaymentListView.as_view(), name='superadmin-payments'),
    path('plan/', SuperadminPlanView.as_view(), name='superadmin-plan'),
    path('revenue/', SuperadminRevenueView.as_view(), name='superadmin-revenue'),
    path('subscriptions/', SuperadminSubscriptionView.as_view(), name='superadmin-subscriptions'),
    path('', include(router.urls)),
]
