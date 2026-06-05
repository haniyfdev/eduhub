from django.db.models import Q
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
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
    ).order_by('due_date')
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action in ('update', 'partial_update'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return DebtUpdateSerializer
        return DebtSerializer

    def get_queryset(self):
        qs = super().get_queryset()

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
            if search.isdigit():
                q |= Q(group_student__group__number=int(search))
            qs = qs.filter(q).distinct()

        return qs

    @action(detail=True, methods=['get'], url_path='last-month-attendance')
    def last_month_attendance(self, request, pk=None):
        from apps.attendance.models import Attendance
        from apps.lessons.models import Lesson
        from apps.companies.models import CompanySettings
        from decimal import Decimal, ROUND_HALF_UP

        debt = self.get_object()
        gs   = debt.group_student

        if not gs.left_at:
            return Response({'error': 'Student has not left the group'}, status=400)

        left_at         = gs.left_at.date()
        joined_at       = gs.joined_at.date()
        month_start     = left_at.replace(day=1)
        effective_start = max(joined_at, month_start)

        settings, _  = CompanySettings.objects.get_or_create(company=gs.group.company)
        billing_type = settings.archive_billing_type
        course_price = Decimal(str(gs.group.course.price)) if gs.group.course else Decimal('0')

        lessons = Lesson.objects.filter(
            group=gs.group,
            date__gte=month_start,
            date__lte=left_at,
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
        per_unit          = None
        units_count       = None
        total_units       = None
        unit_label        = None

        if billing_type == 'per_day':
            days_in_month = 30
            days_in_group = (left_at - effective_start).days + 1
            per_unit          = (course_price / days_in_month).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            units_count       = days_in_group
            total_units       = days_in_month
            calculated_amount = (per_unit * days_in_group).quantize(Decimal('1000'), rounding=ROUND_HALF_UP)
            unit_label        = 'day'

        elif billing_type == 'per_lesson':
            total_lessons_count = lessons.count()
            attended            = sum(1 for a in attendance_data if a['status'] in ['present', 'late'])
            if total_lessons_count > 0:
                per_unit          = (course_price / total_lessons_count).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                units_count       = attended
                total_units       = total_lessons_count
                calculated_amount = (per_unit * attended).quantize(Decimal('1000'), rounding=ROUND_HALF_UP)
            unit_label = 'lesson'

        # Auto-update debt for non-manual modes
        if billing_type != 'manual' and calculated_amount is not None:
            debt.amount = calculated_amount
            debt.save(update_fields=['amount'])

        return Response({
            'lessons':           attendance_data,
            'period_start':      effective_start.strftime('%d/%m/%Y'),
            'left_at':           left_at.strftime('%d/%m/%Y'),
            'course_price':      float(course_price),
            'course_name':       gs.group.course.name if gs.group.course else '—',
            'group_name':        gs.group.display_name,
            'student_name':      f"{gs.student.first_name} {gs.student.last_name}",
            'billing_type':      billing_type,
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
