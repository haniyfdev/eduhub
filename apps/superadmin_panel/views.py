from decimal import Decimal, InvalidOperation
from datetime import date

from django.db.models import Sum
from rest_framework import mixins, viewsets, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
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
    """GET/POST /api/superadmin/companies/"""
    permission_classes = [IsSuperAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        status_filter = request.query_params.get('status', 'active')
        qs = Company.objects.prefetch_related('subscription_debts', 'branches').order_by('created_at')
        if status_filter == 'archived':
            qs = qs.filter(status='archived')
        elif status_filter == 'all':
            pass
        else:
            qs = qs.filter(status='active')
        return Response(CompanyCardSerializer(qs, many=True).data)

    def post(self, request):
        import os
        import re
        import uuid as uuid_lib
        from apps.companies.models import CompanySettings

        PHONE_RE = re.compile(r'^\+998\d{9}$')

        name = (request.data.get('name') or '').strip()
        phone = (request.data.get('phone') or '').strip()
        address = (request.data.get('address') or '').strip()
        logo_file = request.FILES.get('logo')
        parent_id = (request.data.get('parent') or '').strip() or None

        boss_first_name = (request.data.get('boss_first_name') or '').strip()
        boss_last_name = (request.data.get('boss_last_name') or '').strip()
        boss_phone = (request.data.get('boss_phone') or '').strip()
        boss_password = (request.data.get('boss_password') or '').strip()

        errors = {}
        if not name:
            errors['name'] = "Nom majburiy."
        if not address:
            errors['address'] = "Manzil majburiy."
        if not boss_first_name:
            errors['boss_first_name'] = "Ism majburiy."
        if not boss_last_name:
            errors['boss_last_name'] = "Familiya majburiy."
        if not boss_password:
            errors['boss_password'] = "Parol majburiy."

        # Validate company phone
        if not phone:
            errors['phone'] = "Telefon majburiy."
        elif not PHONE_RE.match(phone):
            errors['phone'] = "Telefon raqami noto'g'ri (+998XXXXXXXXX)."
        elif Company.objects.filter(phone=phone).exists():
            errors['phone'] = "Bu telefon raqam allaqachon mavjud."

        # Validate boss phone
        if not boss_phone:
            errors['boss_phone'] = "Telefon majburiy."
        elif not PHONE_RE.match(boss_phone):
            errors['boss_phone'] = "Telefon raqami noto'g'ri (+998XXXXXXXXX)."

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        parent = None
        if parent_id:
            try:
                parent = Company.objects.get(id=parent_id, branch_of__isnull=True)
            except (Company.DoesNotExist, ValueError):
                return Response(
                    {'parent': "Asosiy markaz topilmadi yoki o'zi filialdir."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Handle logo file upload
        logo_url = None
        if logo_file:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            ext = os.path.splitext(logo_file.name)[1].lower() or '.jpg'
            file_path = f'company_logos/{uuid_lib.uuid4()}{ext}'
            saved = default_storage.save(file_path, ContentFile(logo_file.read()))
            logo_url = request.build_absolute_uri(default_storage.url(saved))

        # Ensure a SubscriptionPlan exists so the post_save signal can create a debt
        if not SubscriptionPlan.objects.exists():
            SubscriptionPlan.objects.create(price=0)

        # Create company — post_save signal auto-creates CompanySubscriptionDebt
        company = Company.objects.create(
            name=name,
            phone=phone,
            address=address,
            branch_of=parent,
            logo=logo_url,
        )
        CompanySettings.objects.get_or_create(company=company)

        try:
            User.objects.create_user(
                phone=boss_phone,
                password=boss_password,
                first_name=boss_first_name,
                last_name=boss_last_name,
                role='boss',
                company=company,
            )
        except Exception:
            company.delete()
            return Response(
                {'boss_phone': "Bu telefon raqam allaqachon mavjud."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company.refresh_from_db()
        return Response(
            CompanyDetailSerializer(company).data,
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


class SuperadminCompanyArchiveView(APIView):
    """POST /api/superadmin/companies/{pk}/archive/"""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        from django.utils import timezone
        from apps.groups.models import GroupStudent

        company = get_object_or_404(Company, pk=pk)
        if company.status == 'archived':
            return Response({'detail': "Kompaniya allaqachon arxivlangan."}, status=400)

        # Soft-archive the company
        company.status = 'archived'
        company.archived_at = timezone.now()
        company.save(update_fields=['status', 'archived_at'])

        # Cascade 1: deactivate all company users
        User.objects.filter(company=company).update(is_active=False)

        # Cascade 2: mark active/trial/frozen group memberships as left
        GroupStudent.objects.filter(
            group__company=company,
            status__in=('trial', 'active', 'frozen'),
        ).update(status='left', left_at=timezone.now())

        # Cascade 3: mark pending subscription debts as overdue
        CompanySubscriptionDebt.objects.filter(
            company=company, status='pending'
        ).update(status='overdue')

        # Audit log
        SuperadminLog.objects.create(
            user=request.user,
            action='archive',
            description=f"Company {company.name} archived by superadmin",
        )

        company.refresh_from_db()
        return Response(CompanyCardSerializer(company).data)


class SuperadminCompanyUnarchiveView(APIView):
    """POST /api/superadmin/companies/{pk}/unarchive/"""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        if company.status != 'archived':
            return Response({'detail': "Kompaniya arxivlanmagan."}, status=400)

        company.status = 'active'
        company.archived_at = None
        company.save(update_fields=['status', 'archived_at'])

        # Re-activate all company users
        User.objects.filter(company=company).update(is_active=True)

        # Audit log
        SuperadminLog.objects.create(
            user=request.user,
            action='unarchive',
            description=f"Company {company.name} unarchived by superadmin",
        )

        company.refresh_from_db()
        return Response(CompanyCardSerializer(company).data)


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
