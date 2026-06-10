from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, SmsSendView

router = DefaultRouter()
router.register('', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('', include(router.urls)),
    path('send-sms/', SmsSendView.as_view(), name='send-sms'),
]

