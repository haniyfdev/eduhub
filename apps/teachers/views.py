from datetime import date

from django.db.models import Case, Count, IntegerField, Q, When
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsBossOrManagerOrAdmin, IsBossOrManagerOrAdmin
from .models import Teacher
from .serializers import TeacherSerializer, TeacherCreateSerializer, TeacherSalaryUpdateSerializer


class TeacherViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'subject']
    search_fields = ['user__first_name', 'user__last_name']

    def get_queryset(self):
        qs = Teacher.objects.select_related('user').annotate(
            all_students=Count(
                'groups__memberships__student',
                filter=Q(groups__memberships__left_at__isnull=True),
                distinct=True,
            ),
            status_order=Case(
                When(status='active', then=1),
                When(status='archived', then=99),
                default=5,
                output_field=IntegerField(),
            ),
        )
        user = self.request.user
        if user.role == 'superadmin':
            return qs.order_by('status_order', 'user__last_name')
        return qs.filter(company_id=self._resolve_company_id()).order_by('status_order', 'user__last_name')

    def get_permissions(self):
        if self.action in ('restore', 'unfreeze'):
            return [IsBossOrManager()]
        if self.action in ('create', 'update', 'partial_update', 'archive', 'freeze', 'salary'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return TeacherCreateSerializer
        return TeacherSerializer

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company(), hired_at=date.today())

    @action(detail=True, methods=['patch'], url_path='salary')
    def salary(self, request, pk=None):
        """PATCH /api/v1/teachers/{id}/salary/ — boss/manager only."""
        teacher = self.get_object()
        serializer = TeacherSalaryUpdateSerializer(teacher, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TeacherSerializer(teacher).data)

    @action(detail=True, methods=['get'], url_path='salary-history')
    def salary_history(self, request, pk=None):
        """GET /api/v1/teachers/{id}/salary-history/"""
        from apps.salaries.models import TeacherSalary
        from apps.salaries.serializers import TeacherSalarySerializer
        teacher = self.get_object()
        salaries = TeacherSalary.objects.filter(teacher=teacher).order_by('-month')
        serializer = TeacherSalarySerializer(salaries, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        from decimal import Decimal, ROUND_FLOOR
        teacher = self.get_object()
        now = timezone.now()

        teacher.status = 'archived'
        teacher.archived_at = now
        teacher.user.status = 'archived'
        teacher.user.is_active = False
        teacher.user.closed_at = now
        teacher.user.save()
        teacher.save()

        # Snapshot billing type and recalculate current-month salary if needed
        from apps.companies.models import CompanySettings
        from apps.salaries.models import TeacherSalary
        settings, _ = CompanySettings.objects.get_or_create(company=teacher.company)
        billing_type = settings.teacher_contract_break_policy  # full/per_lesson/per_day/manual

        current_month = now.date().replace(day=1)
        salaries = TeacherSalary.objects.filter(
            teacher=teacher,
            month=current_month,
            company=teacher.company,
        )

        for salary in salaries:
            salary.archive_billing_type = billing_type

            # Fixed salary has no per-lesson schedule; redirect to per_day proration
            effective_billing = billing_type
            if teacher.salary_type == 'fixed' and billing_type == 'per_lesson':
                effective_billing = 'per_day'

            if effective_billing == 'per_day' and salary.calculated_amount > 0:
                days_in_month = 30
                days_worked = (now.date() - current_month).days + 1
                per_day = salary.calculated_amount / days_in_month
                raw = per_day * days_worked
                salary.calculated_amount = (raw / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000

            elif effective_billing == 'per_lesson' and salary.calculated_amount > 0 and salary.group_id:
                from apps.lessons.models import Lesson
                from dateutil.relativedelta import relativedelta

                # Count lessons teacher actually taught this month
                taught = Lesson.objects.filter(
                    group_id=salary.group_id,
                    teacher=teacher,
                    date__gte=current_month,
                    date__lte=now.date(),
                    status='finished',
                ).count()

                # Count total scheduled lessons in full billing cycle via schedule string
                DAY_MAP = {
                    'du': 0, 'se': 1, 'ch': 2, 'cho': 2,
                    'pa': 3, 'ju': 4, 'sh': 5, 'sha': 5, 'ya': 6,
                }
                import datetime as dt
                schedule_str = salary.group.schedule or '' if salary.group else ''
                days_part = schedule_str.split(' ')[0]
                lesson_weekdays: set = set()
                for abbr in days_part.split(','):
                    key = abbr.strip().lower()
                    if key in DAY_MAP:
                        lesson_weekdays.add(DAY_MAP[key])

                total_in_cycle = 0
                if lesson_weekdays:
                    d = current_month
                    cycle_end = current_month + relativedelta(months=1)
                    while d < cycle_end:
                        if d.weekday() in lesson_weekdays:
                            total_in_cycle += 1
                        d += dt.timedelta(days=1)
                if total_in_cycle == 0:
                    total_in_cycle = 12

                per_lesson = salary.calculated_amount / total_in_cycle
                raw = per_lesson * taught
                salary.calculated_amount = (raw / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000

            salary.save(update_fields=['archive_billing_type', 'calculated_amount'])

        return Response({'status': 'archived', 'billing_type': billing_type})

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        teacher = self.get_object()
        if teacher.status != 'archived':
            return Response({'error': 'Only archived teachers can be restored'}, status=400)
        teacher.status = 'active'
        teacher.archived_at = None
        teacher.user.status = 'active'
        teacher.user.is_active = True
        teacher.user.closed_at = None
        teacher.user.save()
        teacher.save()
        return Response({'status': 'active'})

    @action(detail=True, methods=['post'])
    def freeze(self, request, pk=None):
        teacher = self.get_object()
        if teacher.status == 'frozen':
            return Response({'error': "O'qituvchi allaqachon muzlatilgan"}, status=400)
        if teacher.status == 'archived':
            return Response({'error': "Arxivlangan o'qituvchini muzlatib bo'lmaydi"}, status=400)
        from apps.groups.models import Group
        active_groups = Group.objects.filter(teacher=teacher, status='active')
        if active_groups.exists():
            group_names = ', '.join([g.display_name for g in active_groups])
            return Response({'error': f"Bu o'qituvchining faol guruhlari bor: {group_names}. Avval guruhlarni arxivlang yoki muzlating."}, status=400)
        teacher.status = 'frozen'
        teacher.save(update_fields=['status'])
        return Response({'status': 'frozen'})

    @action(detail=True, methods=['post'])
    def unfreeze(self, request, pk=None):
        teacher = self.get_object()
        if teacher.status != 'frozen':
            return Response({'error': "O'qituvchi muzlatilmagan"}, status=400)
        teacher.status = 'active'
        teacher.save(update_fields=['status'])
        return Response({'status': 'active'})

    @action(detail=False, methods=['get'], url_path='top')
    def top(self, request):
        from datetime import timedelta
        from django.db.models import Count, Q
        from apps.groups.models import Group, GroupStudent
        from apps.attendance.models import Attendance

        user = request.user
        company_filter = {} if user.role == 'superadmin' else {'company_id': self._resolve_company_id()}
        thirty_days_ago = timezone.now().date() - timedelta(days=30)

        teachers = Teacher.objects.filter(
            status='active',
            **company_filter,
        ).select_related('user')

        result = []
        for teacher in teachers:
            groups = Group.objects.filter(
                teacher=teacher,
                status='active',
                **company_filter,
            ).select_related('course')

            groups_count = groups.count()
            if groups_count == 0:
                continue

            group_names = [g.display_name for g in groups]

            students_count = GroupStudent.objects.filter(
                group__in=groups,
                left_at__isnull=True,
                student__status='active',
            ).count()

            attendance_qs = Attendance.objects.filter(
                lesson__group__in=groups,
                lesson__date__gte=thirty_days_ago,
            )
            total_records = attendance_qs.count()
            present_records = attendance_qs.filter(status__in=['present', 'late']).count()
            attendance_rate = round(present_records / total_records * 100) if total_records > 0 else 0

            result.append({
                'id': str(teacher.id),
                'name': f"{teacher.user.first_name} {teacher.user.last_name}".strip(),
                'groups_count': groups_count,
                'group_names': group_names,
                'students_count': students_count,
                'attendance_rate': attendance_rate,
            })

        result.sort(key=lambda x: (-x['students_count'], -x['attendance_rate']))
        return Response(result[:10])
