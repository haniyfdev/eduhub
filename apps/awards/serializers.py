from rest_framework import serializers
from .models import Award


class AwardSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Award
        fields = ('id', 'company', 'title', 'description', 'image_url', 'issued_to', 'student_name', 'issued_at', 'created_at')
        read_only_fields = ('id', 'company', 'created_at')

    def get_student_name(self, obj):
        return f"{obj.issued_to.first_name} {obj.issued_to.last_name}"


class AwardCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Award
        fields = ('id', 'title', 'description', 'image_url', 'issued_to', 'issued_at')
        read_only_fields = ('id',)
