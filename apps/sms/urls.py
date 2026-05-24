from django.urls import path
from .views import SmsVariablesView

urlpatterns = [
    path('sms-variables/', SmsVariablesView.as_view(), name='sms-variables'),
]
