import logging
import threading
from decimal import Decimal, InvalidOperation
from datetime import date

from django.db.models import Q, Sum, Exists, OuterRef
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

logger = logging.getLogger(__name__)


def _broadcast_telegram(chat_ids, text):
    """Sends `text` to every chat_id via the Telegram bot.
    One failure must not stop the rest."""
    import asyncio
    from aiogram import Bot
    from django.conf import settings

    async def _send():
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        for chat_id in chat_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"BROADCAST_ERROR: chat_id={chat_id}, error={e}")
        await bot.session.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_send())
    except Exception as e:
        logger.error(f"BROADCAST_LOOP_ERROR: {e}")
    finally:
        loop.close()


class SuperadminCompanyListView(APIView):
    """GET/POST /api/superadmin/companies/"""
    permission_classes = [IsSuperAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        import re
        status_filter = request.query_params.get('status', 'active')
        search = request.query_params.get('search', '').strip()
        qs = Company.objects.prefetch_related('subscription_debts', 'branches').order_by('created_at')
        if status_filter == 'archived':
            qs = qs.filter(status='archived')
        elif status_filter == 'all':
            pass
        else:
            qs = qs.filter(Q(status='active') | Q(status__isnull=True))

        if not search:
            return Response(CompanyCardSerializer(qs, many=True).data)

        # Evaluate to list so we can build the hierarchical index in Python
        all_companies = list(qs)
        parents = sorted(
            [c for c in all_companies if c.branch_of_id is None],
            key=lambda c: c.created_at,
        )
        index_map = {}  # company.id -> badge string e.g. "3" or "3.1"
        for p_idx, parent in enumerate(parents, 1):
            index_map[parent.id] = str(p_idx)
            branches = sorted(
                [c for c in all_companies if c.branch_of_id == parent.id],
                key=lambda c: c.created_at,
            )
            for b_idx, branch in enumerate(branches, 1):
                index_map[branch.id] = f'{p_idx}.{b_idx}'

        parent_name_by_id = {p.id: p.name for p in parents}
        search_lower = search.lower()
        # matches "4" or "4.1" exactly
        is_hier = bool(re.match(r'^\d+(\.\d+)?$', search))

        matched_ids = set()
        for company in all_companies:
            badge = index_map.get(company.id, '')
            # Name match: company's own name OR its parent's name
            name_hit = (
                search_lower in company.name.lower()
                or (company.branch_of_id
                    and search_lower in parent_name_by_id.get(company.branch_of_id, '').lower())
            )
            # Hierarchical number match
            hier_hit = is_hier and (
                badge == search
                or ('.' not in search and badge.startswith(search + '.'))
            )
            if name_hit or hier_hit:
                matched_ids.add(company.id)

        filtered = [c for c in all_companies if c.id in matched_ids]
        return Response(CompanyCardSerializer(filtered, many=True).data)

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

        is_branch = bool(parent_id)

        errors = {}
        if not name:
            errors['name'] = "Nom majburiy."
        if not address:
            errors['address'] = "Manzil majburiy."

        # Boss fields only required for independent companies
        if not is_branch:
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

        # Validate boss phone only for independent companies
        if not is_branch:
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

        if not is_branch:
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
        search = request.query_params.get('search', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        if company_filter:
            qs = qs.filter(company_id=company_filter)
        if search:
            qs = qs.filter(company__name__icontains=search)
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
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(company__name__icontains=search)
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


class SuperadminDashboardView(APIView):
    """GET /api/superadmin/dashboard/"""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from datetime import date, timedelta
        from decimal import Decimal
        from apps.students.models import Student

        today = date.today()

        # Date range for filtered stats — defaults to current calendar month
        date_from_str = request.query_params.get('date_from', '')
        date_to_str = request.query_params.get('date_to', '')
        try:
            date_from = date.fromisoformat(date_from_str) if date_from_str else today.replace(day=1)
            date_to = date.fromisoformat(date_to_str) if date_to_str else today
        except ValueError:
            date_from = today.replace(day=1)
            date_to = today

        active_qs = Company.objects.filter(Q(status='active') | Q(status__isnull=True))

        active_companies = active_qs.count()
        archived_companies = Company.objects.filter(status='archived').count()

        debt_company_count = (
            CompanySubscriptionDebt.objects
            .filter(company__in=active_qs, status__in=('pending', 'overdue'))
            .values('company_id').distinct().count()
        )

        total_active_students = Student.objects.filter(
            company__in=active_qs, status='active'
        ).count()

        total_revenue = (
            CompanySubscriptionPayment.objects.aggregate(t=Sum('amount'))['t']
            or Decimal('0')
        )

        period_revenue = (
            CompanySubscriptionPayment.objects.filter(
                paid_at__date__gte=date_from,
                paid_at__date__lte=date_to,
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )

        period_overdue_total = (
            CompanySubscriptionDebt.objects.filter(
                status='overdue',
                period_end__gte=date_from,
                period_end__lte=date_to,
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )

        # Revenue trend: 1 DB query — aggregate by date, fill gaps in Python
        start_date = today - timedelta(days=29)
        payments_by_date: dict = {
            str(row['paid_at__date']): row['total']
            for row in CompanySubscriptionPayment.objects.filter(
                paid_at__date__gte=start_date
            ).values('paid_at__date').annotate(total=Sum('amount'))
        }
        revenue_trend = [
            {
                'date': str(today - timedelta(days=i)),
                'revenue': payments_by_date.get(str(today - timedelta(days=i)), Decimal('0')),
            }
            for i in range(29, -1, -1)
        ]

        # Companies table
        companies_table = []
        for company in active_qs.prefetch_related('subscription_debts__payments').order_by('created_at'):
            active_students = Student.objects.filter(company=company, status='active').count()
            latest_debt = company.subscription_debts.order_by('-created_at').first()
            if latest_debt:
                paid_total = (
                    latest_debt.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
                )
                debt_remaining = latest_debt.amount - paid_total
                sub_status = latest_debt.status
            else:
                debt_remaining = Decimal('0')
                sub_status = None
            companies_table.append({
                'id': str(company.id),
                'name': company.name,
                'active_students': active_students,
                'subscription_status': sub_status,
                'debt_amount': debt_remaining,
            })

        return Response({
            'stats': {
                'active_companies': active_companies,
                'archived_companies': archived_companies,
                'debt_companies': debt_company_count,
                'total_active_students': total_active_students,
                'total_revenue': total_revenue,
                'period_revenue': period_revenue,
                'period_overdue_total': period_overdue_total,
            },
            'revenue_trend': revenue_trend,
            'companies_table': companies_table,
        })


class SuperadminBroadcastView(APIView):
    """POST /api/superadmin/broadcast/

    Sends a Telegram message to every student and staff member (across all
    companies) that has a linked Telegram chat.
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        message = (request.data.get('message') or '').strip()
        if not message:
            return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.students.models import Student

        student_chat_ids = list(
            Student.objects.filter(telegram_chat_id__isnull=False)
            .values_list('telegram_chat_id', flat=True)
        )
        staff_chat_ids = list(
            User.objects.filter(telegram_chat_id__isnull=False)
            .values_list('telegram_chat_id', flat=True)
        )

        all_chat_ids = student_chat_ids + staff_chat_ids
        formatted_message = f"📢 <b>EduHub ma'muriyati</b>\n\n{message}"

        if all_chat_ids:
            thread = threading.Thread(
                target=_broadcast_telegram,
                args=(all_chat_ids, formatted_message),
                daemon=True,
            )
            thread.start()

        return Response({'queued': len(all_chat_ids)})


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
