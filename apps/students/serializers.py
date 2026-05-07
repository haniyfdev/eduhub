from rest_framework import serializers
from .models import Student


class StudentSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = Student
        fields = (
            'id', 'company', 'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'course', 'course_name', 'referral_source', 'status', 'created_at', 'archived_at',
        )
        read_only_fields = ('id', 'company', 'created_at', 'archived_at')


class StudentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'second_phone',
            'birth_date', 'course', 'referral_source',
        )
        read_only_fields = ('id',)


class StudentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ('first_name', 'last_name', 'phone', 'second_phone', 'birth_date', 'course', 'referral_source', 'status')
