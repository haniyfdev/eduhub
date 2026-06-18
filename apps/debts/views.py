from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Concat
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsBossOrManagerOrAdmin
from .models import Debt
from .serializers import DebtSerializer, DebtUpdateSerializer


class DebtViewSet(
    CompanyFilterMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Debt.objects.select_related(
        'group_student__student', 'group_student__group__course', 'discount'
    ).order_by('due_date', '-amount', 'group_student__student__first_name')
    filter_backends = [OrderingFilter]
    ordering_fields = ['due_date', 'amount', 'group_student__student__first_name']
    ordering = ['due_date', '-amount', 'group_student__student__first_name']
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action in ('update', 'partial_update'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return DebtUpdateSerializer
        return DebtSerializer

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        existing_order = [f for f in queryset.query.order_by if f.lstrip('-') != 'is_archived']
        return queryset.order_by('is_archived', *existing_order)

    def get_queryset(self):
        qs = super().get_queryset()

        qs = qs.annotate(
            is_archived=Case(
                When(group_student__student__status='archived', then=0),
                default=1,
                output_field=IntegerField(),
            )
        )

        status_param = self.request.query_params.get('status', '')
        if status_param:
            statuses = [s.strip() for s in status_param.split(',') if s.strip()]
            qs = qs.filter(status__in=statuses)

        due_date = self.request.query_params.get('due_date')
        if due_date:
            qs = qs.filter(due_date=due_date)

        search = self.request.query_params.get('search', '')
        if search:
            q = (
                Q(group_student__student__first_name__icontains=search) |
                Q(group_student__student__last_name__icontains=search) |
                Q(group_student__group__gender_type__icontains=search)
            )
            # Phone search only for 4+ char queries — a single digit like '2'
            # matches almost every phone number and swamps the group filter.
            if len(search) >= 4:
                q |= Q(group_student__student__phone__icontains=search)
            if search.isdigit():
                q |= Q(group_student__group__number=int(search))
            else:
                q |= Q(id__in=Debt.objects.annotate(
                    full_name=Concat(
                        'group_student__student__first_name', Value(' '), 'group_student__student__last_name'
                    )
                ).filter(full_name__icontains=search).values('id'))
            qs = qs.filter(q).distinct()

        return qs

    @action(detail=True, methods=['get'], url_path='last-month-attendance')
    def last_month_attendance(self, request, pk=None):
        from apps.attendance.models import Attendance
        from apps.lessons.models import Lesson
        from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR

        debt = self.get_object()
        gs   = debt.group_student

        if gs.left_at is None:
            # Frozen student: still in group — use today and company freeze billing type
            from apps.companies.models import CompanySettings
            from django.utils import timezone as tz
            end_date = tz.now().date()
            company_settings, _ = CompanySettings.objects.get_or_create(company=gs.group.company)
            billing_type = company_settings.freeze_billing_type
        else:
            end_date     = gs.left_at.date()
            billing_type = gs.archive_billing_type or 'manual'

        joined_at       = gs.joined_at.date()
        month_start     = end_date.replace(day=1)
        effective_start = max(joined_at, month_start)

        course_price = Decimal(str(gs.group.course.price)) if gs.group.course else Decimal('0')

        lessons = Lesson.objects.filter(
            group=gs.group,
            date__gte=month_start,
            date__lte=end_date,
        ).order_by('date')

        attendance_data = []
        for lesson in lessons:
            att = Attendance.objects.filter(lesson=lesson, student=gs.student).first()
            attendance_data.append({
                'lesson_id': str(lesson.id),
                'date':      lesson.date.strftime('%d/%m/%Y'),
                'status':    att.status if att else 'absent',
            })

        calculated_amount = None
        raw_amount        = None
        per_unit          = None
        units_count       = None
        total_units       = None
        unit_label        = None

        if billing_type == 'per_day':
            days_in_month = 30
            days_in_group = (end_date - effective_start).days + 1
            per_unit          = (course_price / days_in_month).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            units_count       = days_in_group
            total_units       = days_in_month
            raw_amount        = per_unit * days_in_group
            calculated_amount = (raw_amount / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000
            unit_label        = 'day'

        elif billing_type == 'per_lesson':
            from dateutil.relativedelta import relativedelta
            import datetime

            # Map Uzbek day abbreviations → Python weekday numbers (Mon=0 … Sun=6)
            DAY_MAP = {
                'du': 0, 'dushanba': 0,
                'se': 1, 'seshanba': 1,
                'ch': 2, 'cho': 2, 'chorshanba': 2,
                'pa': 3, 'payshanba': 3,
                'ju': 4, 'juma': 4,
                'sh': 5, 'sha': 5, 'shanba': 5,
                'ya': 6, 'yakshanba': 6,
            }

            # Parse group schedule: "Du,Se,Ch 16:00" → {0, 1, 2}
            lesson_weekdays: set[int] = set()
            schedule_str = gs.group.schedule or ''
            days_part = schedule_str.split(' ')[0]  # "Du,Se,Ch"
            for abbr in days_part.split(','):
                key = abbr.strip().lower()
                if key in DAY_MAP:
                    lesson_weekdays.add(DAY_MAP[key])

            # One full billing cycle: joined_at → joined_at + 1 month
            cycle_start = joined_at
            cycle_end   = cycle_start + relativedelta(months=1)

            # Count lesson days in [cycle_start, cycle_end)
            total_lessons_in_cycle = 0
            if lesson_weekdays:
                d = cycle_start
                while d < cycle_end:
                    if d.weekday() in lesson_weekdays:
                        total_lessons_in_cycle += 1
                    d += datetime.timedelta(days=1)

            if total_lessons_in_cycle == 0:
                total_lessons_in_cycle = 12  # fallback

            attended = sum(1 for a in attendance_data if a['status'] in ['present', 'late'])

            per_unit          = (course_price / total_lessons_in_cycle).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            units_count       = attended
            total_units       = total_lessons_in_cycle
            raw_amount        = per_unit * attended
            calculated_amount = (raw_amount / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000
            unit_label        = 'lesson'

        return Response({
            'lessons':           attendance_data,
            'period_start':      effective_start.strftime('%d/%m/%Y'),
            'left_at':           end_date.strftime('%d/%m/%Y'),
            'course_price':      float(course_price),
            'course_name':       gs.group.course.name if gs.group.course else '—',
            'group_name':        gs.group.display_name,
            'student_name':      f"{gs.student.first_name} {gs.student.last_name}",
            'billing_type':      billing_type,
            'raw_amount':        float(raw_amount) if raw_amount is not None else None,
            'calculated_amount': float(calculated_amount) if calculated_amount is not None else None,
            'per_unit':          float(per_unit) if per_unit is not None else None,
            'units_count':       units_count,
            'total_units':       total_units,
            'unit_label':        unit_label,
        })

    @action(detail=True, methods=['post'], url_path='send-sms')
    def send_sms(self, request, pk=None):
        from apps.notifications.tasks import send_sms_task
        from apps.notifications.models import SmsTemplate

        debt = self.get_object()
        template = SmsTemplate.objects.filter(
            company=debt.company,
            type='debt',
        ).first()

        if not template:
            return Response(
                {'detail': 'No debt SMS template found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        student = debt.group_student.student
        phone = request.data.get('phone') or student.second_phone or student.phone
        if not phone:
            return Response(
                {'detail': 'Student has no phone number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = template.body.format(
            student_name=f"{student.first_name} {student.last_name}",
            amount=debt.amount,
            due_date=debt.due_date,
        )

        send_sms_task.delay(
            company_id=str(debt.company_id),
            phone=phone,
            message=message,
            notification_type='sms',
        )
        return Response({'status': 'sms queued'})


class SchedulerStatusView(APIView):
    permission_classes = []

    def get(self, _request):
        return Response({'status': 'disabled', 'message': 'Scheduler managed by Celery Beat'})
