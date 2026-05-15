from rest_framework import serializers
from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    course = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'second_phone',
            'course', 'birth_date', 'referral_source', 'status',
            'created_at', 'archived_at', 'notes',
        )

    def get_course(self, obj):
        if obj.course_id:
            return {'id': str(obj.course.id), 'name': obj.course.name}
        return None


class LeadCreateSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Lead
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'second_phone',
            'course_id', 'birth_date', 'referral_source', 'notes',
        )
        read_only_fields = ('id',)

    def validate_course_id(self, value):
        if value is None:
            return value
        from apps.courses.models import Course
        if not Course.objects.filter(id=value).exists():
            raise serializers.ValidationError('Course not found.')
        return value

    def create(self, validated_data):
        course_id = validated_data.pop('course_id', None)
        return Lead.objects.create(course_id=course_id, **validated_data)
