from rest_framework import mixins, viewsets

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsSuperAdminOrBossOrManager
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(CompanyFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/v1/audit-logs/ — boss, manager, superadmin only."""
    queryset = AuditLog.objects.select_related('user').order_by('-created_at')
    serializer_class = AuditLogSerializer
    filterset_fields = ['model_name', 'user', 'action']
    http_method_names = ['get', 'head', 'options']

    def get_permissions(self):
        return [IsSuperAdminOrBossOrManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs
