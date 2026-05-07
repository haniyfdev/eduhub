from rest_framework import serializers
from .models import Course


class CourseSerializer(serializers.ModelSerializer):
    teacher_names = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            'id', 'company', 'teachers', 'teacher_names', 'name', 'description',
            'price', 'duration_months', 'duration_hours', 'status', 'created_at', 'closed_at',
        )
        read_only_fields = ('id', 'company', 'created_at')

    def get_teacher_names(self, obj):
        return [
            {'id': str(t.id), 'first_name': t.user.first_name, 'last_name': t.user.last_name}
            for t in obj.teachers.all()
        ]


class CourseCreateSerializer(serializers.ModelSerializer):
    teacher_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True
    )

    class Meta:
        model = Course
        fields = ('id', 'teacher_ids', 'name', 'description', 'price', 'duration_months', 'duration_hours')
        read_only_fields = ('id',)

    def create(self, validated_data):
        teacher_ids = validated_data.pop('teacher_ids', [])
        course = super().create(validated_data)
        if teacher_ids:
            from apps.teachers.models import Teacher
            course.teachers.set(Teacher.objects.filter(id__in=teacher_ids))
        return course
