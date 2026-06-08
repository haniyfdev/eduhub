from rest_framework import serializers
from .models import Teacher
from apps.users.serializers import UserListSerializer


class TeacherSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    all_students = serializers.IntegerField(read_only=True)

    class Meta:
        model = Teacher
        fields = (
            'id', 'user', 'company', 'first_name', 'last_name', 'phone',
            'subject', 'birth_date', 'salary_type', 'fixed_amount', 'salary_percent', 'per_student_amt',
            'kpi_bonus', 'status', 'hired_at', 'archived_at', 'created_at',
            'all_students',
        )
        read_only_fields = ('id', 'company', 'hired_at', 'created_at', 'archived_at')


class TeacherCreateSerializer(serializers.ModelSerializer):
    # user sub-fields for creating the linked User account at the same time
    phone = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = Teacher
        fields = (
            'id', 'phone', 'first_name', 'last_name', 'password',
            'subject', 'birth_date', 'salary_type', 'fixed_amount', 'salary_percent', 'per_student_amt',
            'kpi_bonus', 'hired_at',
        )
        read_only_fields = ('id', 'hired_at')

    def validate_phone(self, value):
        from apps.users.models import User
        company = self.context.get('company')
        if User.objects.filter(phone=value, company=company).exists():
            raise serializers.ValidationError("Bu telefon raqam allaqachon ro'yxatdan o'tgan.")
        return value

    def create(self, validated_data):
        from apps.users.models import User
        phone = validated_data.pop('phone')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        password = validated_data.pop('password')
        company = validated_data.pop('company')

        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='teacher',
            company=company,
        )
        return Teacher.objects.create(user=user, company=company, **validated_data)


class TeacherSalaryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ('salary_type', 'fixed_amount', 'salary_percent', 'per_student_amt', 'kpi_bonus')
