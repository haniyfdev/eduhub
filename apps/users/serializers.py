from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import User


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        phone = data.get('phone')
        password = data.get('password')

        # Django's ModelBackend resolves kwargs.get(USERNAME_FIELD), so pass phone= directly.
        user = authenticate(
            request=self.context.get('request'),
            phone=phone,
            password=password,
        )

        if user is None:
            raise serializers.ValidationError('Invalid phone number or password.')

        if user.status == 'archived':
            raise serializers.ValidationError('This account has been deactivated.')

        data['user'] = user
        return data


class UserMeSerializer(serializers.ModelSerializer):
    company_id = serializers.UUIDField(source='company.id', allow_null=True, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'phone', 'role', 'company_id', 'status', 'created_at')
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('id', 'company', 'first_name', 'last_name', 'phone', 'role', 'password')

    def validate_phone(self, value):
        normalized = value.strip().replace(' ', '').replace('-', '')
        if User.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError("Bu telefon raqam allaqachon ro'yxatdan o'tgan.")
        return normalized

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'role')

    def validate_phone(self, value):
        normalized = value.strip().replace(' ', '').replace('-', '')
        qs = User.objects.filter(phone=normalized)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu telefon raqam allaqachon ro'yxatdan o'tgan.")
        return normalized


class UserListSerializer(serializers.ModelSerializer):
    company_id = serializers.UUIDField(source='company.id', allow_null=True, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'phone', 'role', 'company_id', 'status', 'created_at')
