from decimal import Decimal
from datetime import date
from django.db.models import Sum
from rest_framework import mixins, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404
from utils.permissions import IsSuperAdmin
from apps.companies.models import Company
from apps.payments.models import Payment
from apps.subscriptions.models import Subscription
from apps.users.models import User
from .models import SuperadminLog
from .serializers import (
    SuperadminLogSerializer,
    SuperadminLogCreateSerializer,
    CompanyWithSubscriptionSerializer,
)


class SuperadminCompanyView(APIView):
    """
    GET  /api/superadmin/companies/
    POST /api/superadmin/companies/
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        companies = Company.objects.prefetch_related('subscriptions', 'users').order_by('created_at')
        return Response(CompanyWithSubscriptionSerializer(companies, many=True).data)

    def post(self, request):
        from apps.companies.serializers import CompanyCreateSerializer
        from apps.companies.models import CompanySettings

        serializer = CompanyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()
        CompanySettings.objects.get_or_create(company=company)
        return Response(
            CompanyWithSubscriptionSerializer(company).data,
            status=status.HTTP_201_CREATED,
        )


class SuperadminCreateBossView(APIView):
    """POST /api/superadmin/companies/{pk}/create-boss/"""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        phone = request.data.get('phone', '').strip()
        password = request.data.get('password', '').strip()

        if not all([first_name, last_name, phone, password]):
            return Response({'detail': 'Barcha maydonlar to\'ldirilishi shart.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(phone=phone).exists():
            return Response({'detail': 'Bu telefon raqam allaqachon ro\'yxatdan o\'tgan.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='boss',
            company=company,
        )
        return Response({
            'id': str(user.id),
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone,
            'role': user.role,
        }, status=status.HTTP_201_CREATED)


class SuperadminRevenueView(APIView):
    """GET /api/superadmin/revenue/ — EduHub total revenue per month (last 12)."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from dateutil.relativedelta import relativedelta

        today = date.today()
        result = []
        for i in range(11, -1, -1):
            d = today - relativedelta(months=i)
            total = Payment.objects.filter(
                paid_at__year=d.year, paid_at__month=d.month
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            result.append({'period': f"{d.year}-{d.month:02d}", 'revenue': total})
        return Response(result)


class SuperadminSubscriptionView(APIView):
    """GET /api/superadmin/subscriptions/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from apps.subscriptions.serializers import SubscriptionSerializer
        subs = Subscription.objects.select_related('company').order_by('-started_at')
        return Response(SubscriptionSerializer(subs, many=True).data)


class SuperadminLogViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/superadmin/logs/
    POST /api/superadmin/logs/
    """
    queryset = SuperadminLog.objects.select_related('user').order_by('-created_at')
    permission_classes = [IsSuperAdmin]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return SuperadminLogCreateSerializer
        return SuperadminLogSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
