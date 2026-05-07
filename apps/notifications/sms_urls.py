from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SmsTemplateViewSet

router = DefaultRouter()
router.register('', SmsTemplateViewSet, basename='sms-templates')

urlpatterns = [path('', include(router.urls))]

