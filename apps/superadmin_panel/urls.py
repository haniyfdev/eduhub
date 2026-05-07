from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SuperadminCompanyView,
    SuperadminCreateBossView,
    SuperadminRevenueView,
    SuperadminSubscriptionView,
    SuperadminLogViewSet,
)

router = DefaultRouter()
router.register('logs', SuperadminLogViewSet, basename='superadmin-logs')

urlpatterns = [
    path('companies/', SuperadminCompanyView.as_view(), name='superadmin-companies'),
    path('companies/<uuid:pk>/create-boss/', SuperadminCreateBossView.as_view(), name='superadmin-create-boss'),
    path('revenue/', SuperadminRevenueView.as_view(), name='superadmin-revenue'),
    path('subscriptions/', SuperadminSubscriptionView.as_view(), name='superadmin-subscriptions'),
    path('', include(router.urls)),
]

