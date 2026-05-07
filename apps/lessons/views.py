from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsTeacher
from .models import Lesson
from .serializers import LessonSerializer, LessonCreateSerializer


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
        return qs.filter(group__company_id=user.company_id)

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return LessonCreateSerializer
        return LessonSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == 'teacher':
            teacher = user.teacher
        else:
            # boss/manager/admin providing a group — derive teacher from group
            group = serializer.validated_data['group']
            teacher = group.teacher
        serializer.save(teacher=teacher)

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

        created = []
        for item in items_serializer.validated_data:
            obj, _ = Attendance.objects.update_or_create(
                lesson=lesson,
                student_id=item['student_id'],
                defaults={'status': item['status'], 'note': item.get('note', '')},
            )
            created.append(obj)

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
