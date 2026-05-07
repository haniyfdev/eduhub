from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            'id', 'company', 'user', 'user_name', 'action',
            'model_name', 'object_id', 'old_data', 'new_data',
            'description', 'created_at',
        )
        read_only_fields = fields
