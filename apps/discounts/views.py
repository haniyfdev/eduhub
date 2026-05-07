from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Discount
from .serializers import DiscountSerializer, DiscountCreateSerializer


class DiscountViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Discount.objects.select_related('course').order_by('name')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['status', 'course']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'update', 'archive'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return DiscountCreateSerializer
        return DiscountSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
