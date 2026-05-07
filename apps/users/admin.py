from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('phone', 'first_name', 'last_name', 'role', 'status')
    ordering = ('phone',)
    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'company', 'role')}),
        ('Status', {'fields': ('status', 'closed_at', 'is_active', 'is_staff')}),
        ('Permissions', {'fields': ('is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'first_name', 'last_name', 'role', 'company', 'password1', 'password2'),
        }),
    )
    search_fields = ('phone', 'first_name', 'last_name')
    filter_horizontal = ('groups', 'user_permissions')
