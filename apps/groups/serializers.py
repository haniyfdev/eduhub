from rest_framework import serializers
from .models import Group, GroupStudent



class GroupSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    course = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    students_count = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    room_id = serializers.UUIDField(source='room.id', read_only=True, allow_null=True)
    room_name = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = (
            'id', 'name', 'number', 'gender_type', 'course', 'teacher',
            'students_count', 'schedule', 'room_id', 'room_name',
            'start_time', 'end_time', 'status', 'created_at', 'archived_at',
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

    def get_room_name(self, obj):
        if obj.room_id:
            return f"Xona {obj.room.name}"
        return None

    def get_students_count(self, obj):
        return obj.memberships.filter(
            left_at__isnull=True,
            student__status__in=['active', 'trial', 'frozen'],
        ).count()


class GroupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ('id', 'gender_type', 'schedule', 'start_time', 'end_time')
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.courses.models import Course
        from apps.teachers.models import Teacher
        from apps.rooms.models import Room
        self.fields['course_id'] = serializers.PrimaryKeyRelatedField(
            queryset=Course.objects.all(), source='course'
        )
        self.fields['teacher_id'] = serializers.PrimaryKeyRelatedField(
            queryset=Teacher.objects.all(), source='teacher'
        )
        self.fields['room_id'] = serializers.PrimaryKeyRelatedField(
            queryset=Room.objects.all(), source='room',
        )

    def validate_gender_type(self, value):
        return value


class GroupStudentSerializer(serializers.ModelSerializer):
    student_name         = serializers.SerializerMethodField()
    student_phone        = serializers.CharField(source='student.phone', read_only=True)
    student_second_phone = serializers.CharField(source='student.second_phone', read_only=True)
    student_birth_date   = serializers.DateField(source='student.birth_date', read_only=True)
    student_status       = serializers.CharField(source='student.status', read_only=True)

    class Meta:
        model = GroupStudent
        fields = (
            'id', 'student', 'group', 'status',
            'student_name', 'student_phone', 'student_second_phone',
            'student_birth_date', 'student_status',
            'joined_at', 'left_at',
        )

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"


class GroupStudentHistorySerializer(serializers.ModelSerializer):
    group_display = serializers.CharField(source='group.display_name', read_only=True)
    course_name   = serializers.CharField(source='group.course.name', read_only=True)
    teacher_name  = serializers.CharField(source='group.teacher.user.get_full_name', read_only=True)

    class Meta:
        model = GroupStudent
        fields = ('id', 'group', 'group_display', 'course_name', 'teacher_name', 'status', 'joined_at', 'left_at')
