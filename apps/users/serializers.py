from rest_framework import serializers
from .models import User


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
        return value.strip().replace(' ', '').replace('-', '')

    def validate(self, data):
        phone = data.get('phone')
        # company may come from the request body or be injected by the view via context
        company = data.get('company') or self.context.get('company')
        if phone is not None:
            qs = User.objects.filter(phone=phone, company=company)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'phone': "Bu telefon raqam allaqachon ro'yxatdan o'tgan."}
                )
        return data

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
        company = self.instance.company if self.instance else None
        qs = User.objects.filter(phone=normalized, company=company)
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
