from decimal import Decimal, InvalidOperation
from datetime import date

from django.db.models import Sum
from rest_framework import mixins, viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404
from utils.permissions import IsSuperAdmin
from apps.companies.models import Company
from apps.payments.models import Payment
from apps.users.models import User
from .models import SuperadminLog, SubscriptionPlan, CompanySubscriptionDebt, CompanySubscriptionPayment
from .serializers import (
    SuperadminLogSerializer,
    SuperadminLogCreateSerializer,
    CompanyCardSerializer,
    CompanyDetailSerializer,
    CompanySubscriptionDebtSerializer,
    CompanySubscriptionPaymentSerializer,
    SubscriptionPlanSerializer,
)


class SuperadminCompanyListView(APIView):
    """GET /api/superadmin/companies/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        companies = Company.objects.prefetch_related(
            'subscription_debts', 'branches'
        ).order_by('created_at')
        return Response(CompanyCardSerializer(companies, many=True).data)

    def post(self, request):
        from apps.companies.serializers import CompanyCreateSerializer
        from apps.companies.models import CompanySettings

        serializer = CompanyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.save()
        CompanySettings.objects.get_or_create(company=company)
        return Response(
            CompanyCardSerializer(company).data,
            status=status.HTTP_201_CREATED,
        )


class SuperadminCompanyDetailView(APIView):
    """GET /api/superadmin/companies/{id}/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk):
        company = get_object_or_404(
            Company.objects.prefetch_related('subscription_debts', 'branches'),
            pk=pk,
        )
        return Response(CompanyDetailSerializer(company).data)


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
            return Response({'detail': "Barcha maydonlar to'ldirilishi shart."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(phone=phone, company=company).exists():
            return Response({'detail': "Bu telefon raqam allaqachon ro'yxatdan o'tgan."}, status=status.HTTP_400_BAD_REQUEST)

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


class SuperadminDebtListView(APIView):
    """GET /api/superadmin/debts/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = CompanySubscriptionDebt.objects.select_related('company').prefetch_related('payments')
        status_filter = request.query_params.get('status')
        company_filter = request.query_params.get('company')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if company_filter:
            qs = qs.filter(company_id=company_filter)
        return Response(CompanySubscriptionDebtSerializer(qs, many=True).data)


class SuperadminDebtPayView(APIView):
    """POST /api/superadmin/debts/{id}/pay/"""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        debt = get_object_or_404(CompanySubscriptionDebt, pk=pk)

        if debt.status == 'paid':
            return Response({'error': "Bu qarz allaqachon to'langan."}, status=400)

        try:
            amount = Decimal(str(request.data.get('amount', 0)))
        except (InvalidOperation, TypeError):
            return Response({'error': "Noto'g'ri summa."}, status=400)

        if amount <= 0:
            return Response({'error': "Summa musbat bo'lishi kerak."}, status=400)

        paid_so_far = debt.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        remaining = debt.amount - paid_so_far

        if amount > remaining:
            return Response({'error': f"Summa qarzdan oshib ketdi. Qolgan qarz: {remaining}"}, status=400)

        method = request.data.get('payment_method', 'cash')
        if method not in ('cash', 'card', 'transfer'):
            method = 'cash'

        CompanySubscriptionPayment.objects.create(
            company=debt.company,
            debt=debt,
            amount=amount,
            payment_method=method,
            recorded_by=request.user,
        )

        new_paid = paid_so_far + amount
        if new_paid >= debt.amount:
            debt.status = 'paid'
        else:
            debt.status = 'partial'
        debt.save(update_fields=['status'])

        return Response(CompanySubscriptionDebtSerializer(debt).data)


class SuperadminPaymentListView(APIView):
    """GET /api/superadmin/payments/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        qs = CompanySubscriptionPayment.objects.select_related('company', 'recorded_by', 'debt')
        return Response(CompanySubscriptionPaymentSerializer(qs, many=True).data)


class SuperadminPlanView(APIView):
    """GET /PUT /api/superadmin/plan/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        plan = SubscriptionPlan.objects.first()
        if not plan:
            return Response({'price': None})
        return Response(SubscriptionPlanSerializer(plan).data)

    def put(self, request):
        try:
            price = Decimal(str(request.data.get('price', 0)))
        except (InvalidOperation, TypeError):
            return Response({'error': "Noto'g'ri narx."}, status=400)

        if price <= 0:
            return Response({'error': "Narx musbat bo'lishi kerak."}, status=400)

        plan = SubscriptionPlan.objects.first()
        if plan:
            plan.price = price
            plan.updated_by = request.user
            plan.save(update_fields=['price', 'updated_by', 'updated_at'])
        else:
            plan = SubscriptionPlan.objects.create(price=price, updated_by=request.user)

        return Response(SubscriptionPlanSerializer(plan).data)


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
        try:
            from apps.subscriptions.models import Subscription
            from apps.subscriptions.serializers import SubscriptionSerializer
            subs = Subscription.objects.select_related('company').order_by('-started_at')
            return Response(SubscriptionSerializer(subs, many=True).data)
        except Exception:
            return Response([])


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
