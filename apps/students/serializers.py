from rest_framework import serializers
from .models import Student
 
 
class StudentSerializer(serializers.ModelSerializer):
    course_name  = serializers.CharField(source='course.name', read_only=True)
    course_price = serializers.SerializerMethodField()
    current_group    = serializers.SerializerMethodField()
    current_group_id = serializers.SerializerMethodField()
    last_group       = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            'id', 'company', 'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'course', 'course_name', 'course_price',
            'current_group', 'current_group_id', 'last_group',
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

    def get_course_price(self, obj):
        try:
            return float(obj.course.price) if obj.course and obj.course.price else None
        except Exception:
            return None
 
 
class StudentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'course', 'referral_source',
        )

        extra_kwargs = {
            'course': {'required': True, 'allow_null': False},
            'birth_date': {'required': True, 'allow_null': False},
        }
        
        read_only_fields = ('id',)
 
 
class StudentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'course', 'referral_source', 'status',
        )