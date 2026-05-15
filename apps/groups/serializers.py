from rest_framework import serializers
from .models import Group, GroupStudent


def generate_group_number(company):
    last = Group.objects.filter(company=company).order_by('-number').first()
    return (last.number + 1) if last else 1


class GroupSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    course = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    students_count = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = (
            'id', 'name', 'number', 'gender_type', 'course', 'teacher',
            'students_count', 'schedule', 'room', 'start_time', 'end_time',
            'status', 'created_at', 'archived_at',
        )

    def get_name(self, obj):
        return f"{obj.number}{(obj.gender_type or '').upper()}"

    def get_start_time(self, obj):
        return obj.start_time.strftime('%H:%M') if obj.start_time else None

    def get_end_time(self, obj):
        return obj.end_time.strftime('%H:%M') if obj.end_time else None

    def get_course(self, obj):
        if obj.course_id:
            return {'id': str(obj.course.id), 'name': obj.course.name}
        return None

    def get_teacher(self, obj):
        if obj.teacher_id:
            t = obj.teacher
            return {
                'id': str(t.id),
                'first_name': t.user.first_name,
                'last_name': t.user.last_name,
            }
        return None

    def get_students_count(self, obj):
        return obj.memberships.filter(left_at__isnull=True).count()


class GroupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ('id', 'gender_type', 'room', 'schedule', 'start_time', 'end_time')
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.courses.models import Course
        from apps.teachers.models import Teacher
        self.fields['course_id'] = serializers.PrimaryKeyRelatedField(
            queryset=Course.objects.all(), source='course'
        )
        self.fields['teacher_id'] = serializers.PrimaryKeyRelatedField(
            queryset=Teacher.objects.all(), source='teacher'
        )

    def validate_gender_type(self, value):
        return value

    def create(self, validated_data):
        company = validated_data['company']
        number = generate_group_number(company)
        return Group.objects.create(number=number, **validated_data)


class GroupStudentHistorySerializer(serializers.ModelSerializer):
    group_display = serializers.CharField(source='group.display_name', read_only=True)
    course_name = serializers.CharField(source='group.course.name', read_only=True)
    teacher_name = serializers.CharField(source='group.teacher.user.get_full_name', read_only=True)

    class Meta:
        model = GroupStudent
        fields = ('id', 'group', 'group_display', 'course_name', 'teacher_name', 'joined_at', 'left_at')
