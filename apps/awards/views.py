from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossManagerOrAdmin
from .models import Award
from .serializers import AwardSerializer, AwardCreateSerializer


class AwardViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    """
    Rule 1 exception: Award CAN be deleted.
    GET/POST/PATCH/DELETE all allowed.
    """
    queryset = Award.objects.select_related('issued_to').order_by('-issued_at')
    filterset_fields = ['issued_to']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return AwardCreateSerializer
        return AwardSerializer

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company())
