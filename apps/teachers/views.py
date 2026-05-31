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
from utils.permissions import IsBossOrManager
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
        if self.action in ('create', 'archive'):
            return [IsBossOrManager()]
        if self.action in ('salary', 'partial_update', 'update'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return TeacherCreateSerializer
        return TeacherSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, hired_at=date.today())

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
        teacher = self.get_object()
        teacher.status = 'archived'
        teacher.archived_at = timezone.now()
        teacher.user.status = 'archived'
        teacher.user.is_active = False
        teacher.user.closed_at = timezone.now()
        teacher.user.save()
        teacher.save()
        return Response({'status': 'archived'})

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
