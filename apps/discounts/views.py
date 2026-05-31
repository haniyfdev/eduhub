from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Discount
from .serializers import DiscountSerializer, DiscountCreateSerializer


class DiscountViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Discount.objects.select_related('student', 'course', 'created_by').order_by('-created_at')
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    filterset_fields = ['student', 'course']

    def get_permissions(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role == 'admin':
            if self.action in ['list', 'retrieve']:
                return [IsAuthenticated()]
        return [IsBossOrManager()]

    def get_serializer_class(self):
        if self.action == 'create':
            return DiscountCreateSerializer
        return DiscountSerializer

    def perform_create(self, serializer):
        from datetime import date
        from dateutil.relativedelta import relativedelta
        next_month = date.today().replace(day=1) + relativedelta(months=1)
        serializer.save(
            company=self._get_active_company(),
            created_by=self.request.user,
            start_month=next_month,
        )
