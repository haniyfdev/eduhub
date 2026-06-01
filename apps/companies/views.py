from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.permissions import IsSuperAdmin, IsBoss, IsBossOrManager, IsBossManagerOrAdmin
from utils.mixins import ArchiveMixin, CompanyFilterMixin
from .models import Company, CompanySettings
from .serializers import CompanySerializer, CompanyCreateSerializer, CompanySettingsSerializer


class CompanyViewSet(ArchiveMixin, viewsets.ModelViewSet):
    """
    GET    /api/v1/companies/              superadmin + boss + manager
    POST   /api/v1/companies/              superadmin + boss + manager (branch creation)
    GET    /api/v1/companies/{id}/         superadmin + boss only
    PATCH  /api/v1/companies/{id}/         superadmin + boss only
    POST   /api/v1/companies/{id}/archive/ superadmin + boss only (own branches)
    """
    queryset = Company.objects.all().order_by('created_at')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action == 'list':
            return [(IsSuperAdmin | IsBossOrManager)()]
        if self.action == 'create':
            return [(IsSuperAdmin | IsBossOrManager)()]
        if self.action == 'archive':
            return [(IsSuperAdmin | IsBoss)()]
        if self.action in ('retrieve', 'update', 'partial_update'):
            return [(IsSuperAdmin | IsBossManagerOrAdmin)()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return CompanyCreateSerializer
        return CompanySerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'superadmin':
            qs = Company.objects.all().order_by('created_at')
        elif user.role in ['boss', 'manager'] and user.company_id:
            qs = Company.objects.filter(
                id__in=Company.objects.filter(
                    id=user.company_id
                ).values_list('id', flat=True)
                | Company.objects.filter(
                    branch_of_id=user.company_id
                ).values_list('id', flat=True)
            )
        else:
            qs = Company.objects.filter(id=user.company_id)

        branch_of = self.request.query_params.get('branch_of')
        if branch_of:
            qs = qs.filter(branch_of_id=branch_of)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        branch_of_id = self.request.data.get('branch_of') or None
        if user.role in ['boss', 'manager'] and branch_of_id is None:
            # boss creating a branch must link it to their own company
            branch_of_id = str(user.company_id) if user.company_id else None
        serializer.save(branch_of_id=branch_of_id)


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
        from utils.mixins import resolve_company_id
        return CompanySettings.objects.filter(company_id=resolve_company_id(self.request))

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

        from utils.mixins import get_active_company
        settings_obj, _ = CompanySettings.objects.get_or_create(company=get_active_company(request))

        if request.method == 'PATCH':
            serializer = CompanySettingsSerializer(
                settings_obj, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        return Response(CompanySettingsSerializer(settings_obj).data)
