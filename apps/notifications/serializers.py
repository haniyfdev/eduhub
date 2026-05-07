from rest_framework import serializers
from .models import Notification, SmsTemplate


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'company', 'recipient_phone', 'message', 'type', 'status', 'sent_at', 'created_at')
        read_only_fields = fields


class SmsTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsTemplate
        fields = ('id', 'company', 'name', 'body', 'type', 'created_at')
        read_only_fields = ('id', 'company', 'created_at')


class SmsTemplateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsTemplate
        fields = ('id', 'name', 'body', 'type')
        read_only_fields = ('id',)
