from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from .models import Payment
from .serializers import PaymentSerializer, PaymentCreateSerializer


class PaymentViewSet(CompanyFilterMixin, mixins.CreateModelMixin,
                     mixins.RetrieveModelMixin, mixins.ListModelMixin,
                     viewsets.GenericViewSet):
    """
    Rule 3 — PATCH and DELETE are forbidden on payments.
    Only GET + POST allowed.
    """
    queryset = Payment.objects.select_related('student', 'course', 'discount').order_by('-paid_at')
    filterset_fields = ['student', 'course', 'payment_type']
    # month filter is handled manually
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get('month')  # e.g. 2026-05
        if month:
            try:
                year, mon = month.split('-')
                qs = qs.filter(paid_at__year=int(year), paid_at__month=int(mon))
            except ValueError:
                pass
        return qs

    def create(self, request, *args, **kwargs):
        serializer = PaymentCreateSerializer(
            data=request.data,
            context={'company': request.user.company, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
