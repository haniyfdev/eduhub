from rest_framework import serializers
from .models import Room


class RoomSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            'id', 'name', 'gender_type', 'capacity',
            'floor', 'description', 'status', 'display_name',
        ]

    def get_display_name(self, obj):
        gender = f"-{obj.gender_type.upper()}" if obj.gender_type else ''
        return f"Xona {obj.name}{gender}"
