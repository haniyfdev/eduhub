from decimal import Decimal
from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Expense
from .serializers import ExpenseSerializer, ExpenseCreateSerializer


class ExpenseViewSet(CompanyFilterMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'update'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return ExpenseCreateSerializer
        return ExpenseSerializer

    def perform_create(self, serializer):
        serializer.save(
            company=self._get_active_company(),
            source='manual',
            created_by=self.request.user,
        )

    def get_queryset(self):
            # Asosiy queryset (CompanyFilterMixin orqali faqat o'z kompaniyasini ko'radi)
            qs = Expense.objects.filter(company_id=self._resolve_company_id()) if self.request.user.role != 'superadmin' else Expense.objects.all()
            
            month = self.request.query_params.get('month')
            year_param = self.request.query_params.get('year')
            # accept both from_date/to_date (new standard) and date_from/date_to (legacy)
            date_from = (
                self.request.query_params.get('from_date') or
                self.request.query_params.get('date_from')
            )
            date_to = (
                self.request.query_params.get('to_date') or
                self.request.query_params.get('date_to')
            )
            source = self.request.query_params.get('source')

            # 1. Source bo'yicha filtr (manual/automatic)
            if source:
                qs = qs.filter(source=source)

            # 2. Oy bo'yicha filtr (YYYY-MM)
            if month:
                try:
                    year, mon = month.split('-')
                    qs = qs.filter(expense_date__year=int(year), expense_date__month=int(mon))
                except (ValueError, AttributeError):
                    pass
            
            # 3. Yil bo'yicha filtr (YYYY)
            elif year_param:
                try:
                    qs = qs.filter(expense_date__year=int(year_param))
                except ValueError:
                    pass

            # 4. Davr bo'yicha filtr (Date Range)
            elif date_from and date_to:
                try:
                    qs = qs.filter(expense_date__range=[date_from, date_to])
                except ValueError:
                    pass

            return qs.order_by('-expense_date')
