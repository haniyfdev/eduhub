from django.utils import timezone
from rest_framework import serializers
from .models import Refund


class RefundSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    group_name   = serializers.SerializerMethodField()
    course_name  = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = (
            'id', 'company', 'group_student', 'debt',
            'student_name', 'group_name', 'course_name',
            'original_paid', 'earned_amount', 'refund_amount',
            'status', 'confirmed_at', 'paid_at', 'note', 'created_at',
        )
        read_only_fields = ('id', 'company', 'created_at')

    def get_student_name(self, obj):
        s = obj.group_student.student
        return f"{s.first_name} {s.last_name}"

    def get_group_name(self, obj):
        return obj.group_student.group.display_name

    def get_course_name(self, obj):
        course = obj.group_student.group.course
        return course.name if course else None


class RefundCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = (
            'id', 'group_student', 'debt',
            'original_paid', 'earned_amount', 'refund_amount', 'note',
        )
        read_only_fields = ('id',)

    def validate_group_student(self, value):
        if value.status != 'left':
            raise serializers.ValidationError("Faqat guruhdan chiqgan o'quvchilar uchun qaytim yaratish mumkin")
        if Refund.objects.filter(group_student=value).exists():
            raise serializers.ValidationError("Bu o'quvchi uchun qaytim allaqachon yaratilgan")
        return value

    def create(self, validated_data):
        # Confirming directly on creation — the admin's "Tasdiqlash" click in
        # the modal both creates and confirms this amount in one step.
        validated_data['status'] = 'confirmed'
        validated_data['confirmed_at'] = timezone.now()
        return super().create(validated_data)


class RefundUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ('status',)

    def validate_status(self, value):
        if value not in ('confirmed', 'paid'):
            raise serializers.ValidationError("Faqat 'confirmed' yoki 'paid' holatiga o'tkazish mumkin")
        if value == 'paid' and self.instance.status != 'confirmed':
            raise serializers.ValidationError("Avval qaytim tasdiqlanishi kerak")
        return value

    def update(self, instance, validated_data):
        new_status = validated_data['status']
        if new_status == 'confirmed' and instance.status == 'pending':
            instance.confirmed_at = timezone.now()
        elif new_status == 'paid':
            instance.paid_at = timezone.now()
        instance.status = new_status
        instance.save(update_fields=['status', 'confirmed_at', 'paid_at'])
        return instance
