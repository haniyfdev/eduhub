from django.db.models import Case, IntegerField, When
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossManagerOrAdmin
from .models import Group, GroupStudent
from .serializers import GroupSerializer, GroupCreateSerializer


class GroupViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Group.objects.select_related('course', 'teacher__user').annotate(
        status_order=Case(
            When(status='active', then=1),
            When(status='archived', then=99),
            default=5,
            output_field=IntegerField(),
        )
    ).order_by('status_order', 'number')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['status', 'course', 'teacher']

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return GroupCreateSerializer
        return GroupSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    def retrieve(self, request, *args, **kwargs):
        """Detail: include current student list."""
        from apps.students.serializers import StudentSerializer
        group = self.get_object()
        data = GroupSerializer(group).data
        active_members = GroupStudent.objects.filter(
            group=group, left_at__isnull=True
        ).select_related('student')
        data['students'] = StudentSerializer(
            [m.student for m in active_members], many=True
        ).data
        return Response(data)

    @action(detail=True, methods=['post'], url_path='add-student')
    def add_student(self, request, pk=None):
        """POST /api/v1/groups/{id}/add-student/  body: {student_id}"""
        from apps.students.models import Student
        group = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'detail': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(id=student_id, company=group.company)
        except Student.DoesNotExist:
            return Response({'detail': 'Student not found in this company.'}, status=status.HTTP_404_NOT_FOUND)

        # If already active in this group, no-op
        if GroupStudent.objects.filter(group=group, student=student, left_at__isnull=True).exists():
            return Response({'detail': 'Student is already in this group.'}, status=status.HTTP_400_BAD_REQUEST)

        GroupStudent.objects.create(group=group, student=student, joined_at=timezone.now())

        return Response({'status': 'student added'}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='remove-student')
    def remove_student(self, request, pk=None):
        """POST /api/v1/groups/{id}/remove-student/  body: {student_id}"""
        from apps.students.models import Student
        group = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'detail': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        membership = GroupStudent.objects.filter(
            group=group, student_id=student_id, left_at__isnull=True
        ).first()
        if not membership:
            return Response({'detail': 'Active membership not found.'}, status=status.HTTP_404_NOT_FOUND)

        membership.left_at = timezone.now()
        membership.save(update_fields=['left_at'])
        return Response({'status': 'student removed'})
