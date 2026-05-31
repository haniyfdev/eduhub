from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsTeacher
from .models import Lesson
from .serializers import LessonSerializer, LessonCreateSerializer
from django.utils import timezone


class LessonViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['group', 'date', 'teacher']

    def get_queryset(self):
        qs = Lesson.objects.select_related('group__company', 'teacher__user').order_by('-date')
        user = self.request.user
        if user.role == 'superadmin':
            return qs
        if user.role == 'teacher':
            try:
                return qs.filter(teacher=user.teacher)
            except Exception:
                return qs.none()
        return qs.filter(group__company_id=self._resolve_company_id())

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return LessonCreateSerializer
        return LessonSerializer

    def perform_create(self, serializer):
        try:
            user = self.request.user
            if user.role == 'teacher':
                teacher = user.teacher
            else:
                # boss/manager/admin providing a group — derive teacher from group
                group = serializer.validated_data['group']
                teacher = group.teacher
            serializer.save(teacher=teacher)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Lesson create error: str({e})", exc_info=True)
            raise

    # ── student roster for attendance ────────────────────────────

    @action(detail=True, methods=['get'], url_path='students')
    def students(self, request, pk=None):
        from apps.groups.models import GroupStudent
        lesson = self.get_object()
        roster = GroupStudent.objects.filter(
            group=lesson.group,
            left_at__isnull=True,
            student__status__in=['active', 'trial'],
            joined_at__date__lte=lesson.date
        ).select_related('student')
        data = []
        for m in roster:
            s = m.student
            data.append({
                'id': str(s.id),
                'first_name': s.first_name,
                'last_name': s.last_name,
                'phone': s.phone or '',
                'birth_date': s.birth_date.isoformat() if s.birth_date else None,
                'status': s.status,
            })
        return Response(data)

    # ── nested attendance ────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'])
    def attendance(self, request, pk=None):
        from apps.attendance.models import Attendance
        from apps.attendance.serializers import AttendanceSerializer, AttendanceBulkItemSerializer
        from apps.students.models import Student

        lesson = self.get_object()

        if request.method == 'GET':
            qs = Attendance.objects.filter(lesson=lesson).select_related('student')
            return Response(AttendanceSerializer(qs, many=True).data)

        # POST — bulk create
        items_serializer = AttendanceBulkItemSerializer(data=request.data, many=True)
        items_serializer.is_valid(raise_exception=True)

        from apps.groups.models import GroupStudent
        required_count = GroupStudent.objects.filter(
            group=lesson.group,
            left_at__isnull=True,
            student__status__in=['active', 'trial'],
            joined_at__date__lte=lesson.date
        ).count()
        submitted_ids = [str(item['student_id']) for item in items_serializer.validated_data]
        if len(submitted_ids) < required_count:
            missing = required_count - len(submitted_ids)
            return Response(
                {'error': f"{missing} ta o'quvchi belgilanmagan. Barcha {required_count} ta o'quvchini keldi/kechikdi/kelmadi qilib belgilang."},
                status=status.HTTP_400_BAD_REQUEST
            )
        valid_statuses = ['present', 'late', 'absent']
        for item in items_serializer.validated_data:
            if item['status'] not in valid_statuses:
                return Response(
                    {'error': f"Noto'g'ri holat: {item['status']}. Faqat: keldi, kechikdi, kelmadi"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        created = []
        for item in items_serializer.validated_data:
            obj, created_flag = Attendance.objects.update_or_create(
                lesson=lesson,
                student_id=item['student_id'],
                defaults={'status': item['status'], 'note': item.get('note', '')},
            )
            from django.db.models.signals import post_save
            post_save.send(
                sender=obj.__class__,
                instance=obj,
                created=created_flag,
                using='default',
            )
            created.append(obj)

        lesson.finished_at = timezone.now()
        lesson.status = 'finished'
        lesson.save(update_fields=['finished_at', 'status'])

        return Response(AttendanceSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    # ── nested grades ────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'])
    def grades(self, request, pk=None):
        from apps.grades.models import Grade
        from apps.grades.serializers import GradeSerializer, GradeBulkItemSerializer

        lesson = self.get_object()

        if request.method == 'GET':
            qs = Grade.objects.filter(lesson=lesson).select_related('student')
            return Response(GradeSerializer(qs, many=True).data)

        # POST — bulk create (appends; multiple grades per student per lesson are allowed)
        items_serializer = GradeBulkItemSerializer(data=request.data, many=True)
        items_serializer.is_valid(raise_exception=True)

        created = []
        for item in items_serializer.validated_data:
            obj = Grade.objects.create(
                lesson=lesson,
                student_id=item['student_id'],
                score=item['score'],
                note=item.get('note', ''),
            )
            created.append(obj)

        return Response(GradeSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    # ── started/finished times ────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='start')
    def start(self, request, pk=None):
        from django.utils import timezone
        from apps.students.models import Student

        lesson = self.get_object()
        lesson.started_at = timezone.now()
        lesson.status = 'ongoing'
        lesson.save(update_fields=['started_at', 'status'])

        # Guruhda nechta tugallangan dars bor?
        finished_count = lesson.group.lessons.filter(status='finished').count()

        if finished_count == 0:
            # Bu birinchi dars — kelgan o'quvchilar trial ga o'tadi
            student_ids = lesson.group.memberships.filter(
                left_at__isnull=True
            ).values_list('student_id', flat=True)
            Student.objects.filter(
                id__in=student_ids, status='pending'
            ).update(status='trial')

        return Response(LessonSerializer(lesson).data)