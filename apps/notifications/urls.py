from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, SmsSendView
from .telegram_views import (
    SendToStudentView,
    SendToGroupView,
    SendToAllView,
    SendCustomView,
)

router = DefaultRouter()
router.register('', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('', include(router.urls)),
    path('send-sms/', SmsSendView.as_view(), name='send-sms'),
    path('send-to-student/', SendToStudentView.as_view(), name='send-to-student'),
    path('send-to-group/', SendToGroupView.as_view(), name='send-to-group'),
    path('send-to-all/', SendToAllView.as_view(), name='send-to-all'),
    path('send-custom/', SendCustomView.as_view(), name='send-custom'),
]

