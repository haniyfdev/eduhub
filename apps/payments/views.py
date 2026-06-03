from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsBossOrManagerOrAdmin
from .models import Payment
from .serializers import PaymentSerializer, PaymentCreateSerializer


class PaymentViewSet(CompanyFilterMixin, mixins.CreateModelMixin,
                     mixins.RetrieveModelMixin, mixins.ListModelMixin,
                     viewsets.GenericViewSet):
    """
    Rule 3 — PATCH and DELETE are forbidden on payments.
    Only GET + POST allowed.
    """
    queryset = Payment.objects.select_related(
        'group_student__student', 'group_student__group__course', 'discount'
    ).order_by('-paid_at')
    filterset_fields = ['group_student', 'payment_type']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'create':
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset()
        month = self.request.query_params.get('month')
        if month:
            try:
                year, mon = month.split('-')
                qs = qs.filter(paid_at__year=int(year), paid_at__month=int(mon))
            except ValueError:
                pass
        search = self.request.query_params.get('search', '')
        if search:
            q = (
                Q(group_student__student__first_name__icontains=search) |
                Q(group_student__student__last_name__icontains=search) |
                Q(group_student__group__gender_type__icontains=search)
            )
            if search.isdigit():
                q |= Q(group_student__group__number=int(search))
            qs = qs.filter(q).distinct()
        return qs

    def create(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Payment create data: {request.data}")
        serializer = PaymentCreateSerializer(
            data=request.data,
            context={'company': self._get_active_company(), 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            payment = serializer.save()
        except Exception as e:
            logger.error(f"Payment save error: {e}", exc_info=True)
            raise
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
