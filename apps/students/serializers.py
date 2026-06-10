from rest_framework import serializers
from .models import Student


class GroupMembershipSerializer(serializers.Serializer):
    group_student_id = serializers.UUIDField(source='id')
    group_id = serializers.UUIDField(source='group.id')
    group_name = serializers.SerializerMethodField()
    course_name = serializers.CharField(source='group.course.name', read_only=True)
    course_id = serializers.UUIDField(source='group.course_id', read_only=True)
    course_price = serializers.DecimalField(
        source='group.course.price', max_digits=15, decimal_places=2, read_only=True, allow_null=True
    )
    status    = serializers.CharField(read_only=True)
    joined_at = serializers.DateTimeField()
    left_at   = serializers.DateTimeField()

    def get_group_name(self, obj):
        return f"{obj.group.number}{(obj.group.gender_type or '').upper()}"


class StudentSerializer(serializers.ModelSerializer):
    current_group    = serializers.SerializerMethodField()
    current_group_id = serializers.SerializerMethodField()
    last_group       = serializers.SerializerMethodField()
    group_memberships_data = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            'id', 'company', 'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'telegram_chat_id',
            'current_group', 'current_group_id', 'last_group',
            'group_memberships_data',
            'referral_source', 'status', 'archive_reason', 'created_at', 'archived_at',
        )
        read_only_fields = ('id', 'company', 'created_at', 'archived_at')

    def _active_membership(self, obj):
        return obj.group_memberships.filter(left_at__isnull=True).select_related('group__course').first()

    def get_current_group(self, obj):
        m = self._active_membership(obj)
        return m.group.display_name if m else None

    def get_current_group_id(self, obj):
        m = self._active_membership(obj)
        return str(m.group.id) if m else None

    def get_last_group(self, obj):
        from apps.groups.models import GroupStudent
        gs = GroupStudent.objects.filter(student=obj).select_related('group').order_by('-joined_at').first()
        if gs:
            return f"{gs.group.number}{(gs.group.gender_type or '').upper()}"
        return '—'

    def get_group_memberships_data(self, obj):
        if obj.status == 'archived':
            memberships = obj.group_memberships.select_related(
                'group__course'
            ).order_by('-joined_at')[:1]
        else:
            memberships = obj.group_memberships.filter(
                left_at__isnull=True
            ).select_related('group__course')
        return GroupMembershipSerializer(memberships, many=True).data


class StudentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'referral_source',
        )
        extra_kwargs = {
            'birth_date': {'required': True, 'allow_null': False},
        }
        read_only_fields = ('id',)


class StudentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'referral_source', 'status',
        )
