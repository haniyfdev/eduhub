from rest_framework import serializers
from .models import Announcement, Notification, SmsTemplate


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'company', 'recipient_phone', 'message', 'type', 'status', 'sent_at', 'created_at')
        read_only_fields = fields


class SmsTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsTemplate
        fields = ('id', 'name', 'body', 'trigger', 'type', 'is_active', 'is_default', 'created_at')
        read_only_fields = ('id', 'is_default', 'created_at')


class AnnouncementSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source='created_by.get_full_name', read_only=True
    )

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'body', 'created_by_name',
            'is_active', 'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'created_by_name', 'created_at']

    def get_is_read(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        return obj.reads.filter(user=request.user).exists()
