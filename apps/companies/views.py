from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.permissions import IsSuperAdmin, IsBossOrManager
from utils.mixins import ArchiveMixin, CompanyFilterMixin
from .models import Company, CompanySettings
from .serializers import CompanySerializer, CompanyCreateSerializer, CompanySettingsSerializer


class CompanyViewSet(ArchiveMixin, viewsets.ModelViewSet):
    """
    GET    /api/v1/companies/              superadmin only
    POST   /api/v1/companies/              superadmin only
    GET    /api/v1/companies/{id}/
    PATCH  /api/v1/companies/{id}/         superadmin + boss
    POST   /api/v1/companies/{id}/archive/ superadmin only
    """
    queryset = Company.objects.all().order_by('created_at')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('list', 'create', 'archive'):
            return [IsSuperAdmin()]
        if self.action in ('update', 'partial_update'):
            return [(IsSuperAdmin | IsBossOrManager)()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CompanyCreateSerializer
        return CompanySerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'superadmin':
            return Company.objects.all().order_by('created_at')
        # Boss / manager sees their own company + its branches
        if user.role in ['boss', 'manager'] and user.company_id:
            return Company.objects.filter(
                id__in=Company.objects.filter(
                    id=user.company_id
                ).values_list('id', flat=True)
                | Company.objects.filter(
                    branch_of_id=user.company_id
                ).values_list('id', flat=True)
            )
        return Company.objects.filter(id=user.company_id)


class CompanySettingsViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                              viewsets.GenericViewSet):
    """
    GET   /api/v1/company-settings/my/   — get own company settings (boss/manager)
    PATCH /api/v1/company-settings/my/   — update own company settings (boss/manager)
    GET   /api/v1/company-settings/{id}/ — superadmin only
    """
    serializer_class = CompanySettingsSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        return [(IsSuperAdmin | IsBossOrManager)()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'superadmin':
            return CompanySettings.objects.all()
        return CompanySettings.objects.filter(company_id=user.company_id)

    @action(detail=False, methods=['get', 'patch'], url_path='my')
    def my_settings(self, request):
        """Get or update settings for the current user's company."""
        user = request.user
        if user.role == 'superadmin':
            return Response({
                'billing_type': 'monthly',
                'absent_policy': 'ignore',
                'teacher_contract_break_policy': 'full',
            })

        settings_obj, _ = CompanySettings.objects.get_or_create(company=user.company)

        if request.method == 'PATCH':
            serializer = CompanySettingsSerializer(
                settings_obj, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        return Response(CompanySettingsSerializer(settings_obj).data)
