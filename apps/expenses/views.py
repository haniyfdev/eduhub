from decimal import Decimal
from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Expense
from .serializers import ExpenseSerializer, ExpenseCreateSerializer


class ExpenseViewSet(CompanyFilterMixin, mixins.CreateModelMixin,
                     mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/v1/expenses/
    POST /api/v1/expenses/   — manual entries only (auto ones created by signals)
    """
    queryset = Expense.objects.order_by('-expense_date')
    filterset_fields = ['category', 'source']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'create':
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return ExpenseCreateSerializer
        return ExpenseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get('month')
        if month:
            try:
                year, mon = month.split('-')
                qs = qs.filter(expense_date__year=int(year), expense_date__month=int(mon))
            except ValueError:
                pass
        return qs

    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company,
            source='manual',
            created_by=self.request.user,
        )
