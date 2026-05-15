from django.db.models import Case, IntegerField, When
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.filters import SearchFilter

from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossManagerOrAdmin
from .models import Group, GroupStudent
from .serializers import GroupSerializer, GroupCreateSerializer


class GroupViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Group.objects.select_related('course', 'teacher__user').annotate(
        status_order=Case(
            When(status='active', then=1),
            When(status='frozen', then=2),
            When(status='archived', then=99),
            default=5,
            output_field=IntegerField(),
        )
    ).order_by('status_order', 'number')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'course', 'teacher']
    search_fields = ['number', 'gender_type', 'teacher__user__first_name', 'teacher__user__last_name']

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(status__in=['active', 'archived', 'frozen'])

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return GroupCreateSerializer
        return GroupSerializer

    def _check_room_conflict(self, room, start_time, end_time, company_id, exclude_id=None):
        if not start_time or not end_time:
            return None
        conflicts = Group.objects.filter(
            company_id=company_id,
            room=room,
            status='active',
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_id:
            conflicts = conflicts.exclude(id=exclude_id)
        return conflicts.first()

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        company = self.request.user.company
        data = serializer.validated_data
        conflict = self._check_room_conflict(
            room=data.get('room', ''),
            start_time=data.get('start_time'),
            end_time=data.get('end_time'),
            company_id=company.id,
        )
        if conflict:
            raise ValidationError({
                'room': (
                    f"Bu xona {conflict.start_time.strftime('%H:%M')}-"
                    f"{conflict.end_time.strftime('%H:%M')} orasida band. "
                    f"{conflict.display_name} guruhi o'qiyapti."
                )
            })
        serializer.save(company=company)

    def perform_update(self, serializer):
        from rest_framework.exceptions import ValidationError
        instance = serializer.instance
        data = serializer.validated_data
        conflict = self._check_room_conflict(
            room=data.get('room', instance.room),
            start_time=data.get('start_time', instance.start_time),
            end_time=data.get('end_time', instance.end_time),
            company_id=instance.company_id,
            exclude_id=instance.id,
        )
        if conflict:
            raise ValidationError({
                'room': (
                    f"Bu xona {conflict.start_time.strftime('%H:%M')}-"
                    f"{conflict.end_time.strftime('%H:%M')} orasida band. "
                    f"{conflict.display_name} guruhi o'qiyapti."
                )
            })
        serializer.save()

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
        from apps.leads.models import Lead
        group = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'detail': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(id=student_id, company=group.company).first()

        if student is None:
            try:
                lead = Lead.objects.get(id=student_id, company=group.company)
            except Lead.DoesNotExist:
                return Response({'detail': 'Student not found in this company.'}, status=status.HTTP_404_NOT_FOUND)
            # Keep lead in leads table as trial; create linked trial student
            lead.status = 'trial'
            lead.save(update_fields=['status'])
            student = Student.objects.create(
                company=lead.company,
                first_name=lead.first_name,
                last_name=lead.last_name,
                phone=lead.phone,
                second_phone=lead.second_phone,
                course=lead.course,
                birth_date=lead.birth_date,
                referral_source=lead.referral_source,
                status='trial',
                lead=lead,
            )

        # If already active in this group, no-op
        if GroupStudent.objects.filter(group=group, student=student, left_at__isnull=True).exists():
            return Response({'detail': 'Student is already in this group.'}, status=status.HTTP_400_BAD_REQUEST)

        GroupStudent.objects.create(group=group, student=student, joined_at=timezone.now())

        return Response({'status': 'student added', 'student_id': str(student.id)}, status=status.HTTP_201_CREATED)

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

        # Removed from group → archived (stays in students list, not leads)
        student = membership.student
        if student.status != 'archived':
            student.status = 'archived'
            student.archived_at = timezone.now()
            student.save(update_fields=['status', 'archived_at'])

        return Response({'status': 'student removed'})

    @action(detail=True, methods=['post'], url_path='transfer-student')
    def transfer_student(self, request, pk=None):
        """POST /api/v1/groups/{id}/transfer-student/  body: {student_id, new_group_id}"""
        student_id = request.data.get('student_id')
        new_group_id = request.data.get('new_group_id')
        if not student_id or not new_group_id:
            return Response({'detail': 'student_id and new_group_id are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            gs = GroupStudent.objects.get(group_id=pk, student_id=student_id, left_at__isnull=True)
        except GroupStudent.DoesNotExist:
            return Response({'detail': 'Active membership not found.'}, status=status.HTTP_404_NOT_FOUND)

        gs.left_at = timezone.now()
        gs.save(update_fields=['left_at'])

        GroupStudent.objects.create(
            group_id=new_group_id,
            student_id=student_id,
            joined_at=timezone.now(),
        )
        return Response({'status': 'transferred'})

    @action(detail=True, methods=['post'])
    def freeze(self, request, pk=None):
        group = self.get_object()
        if group.status != 'active':
            return Response({'detail': 'Only active groups can be frozen.'}, status=status.HTTP_400_BAD_REQUEST)
        group.status = 'frozen'
        group.save(update_fields=['status'])
        enrollments = GroupStudent.objects.filter(
            group=group, left_at__isnull=True
        ).select_related('student')
        for gs in enrollments:
            if gs.student.status == 'active':
                gs.student.status = 'frozen'
                gs.student.save(update_fields=['status'])
        return Response({'status': 'frozen', 'frozen_students': enrollments.count()})

    @action(detail=True, methods=['post'])
    def unfreeze(self, request, pk=None):
        group = self.get_object()
        if group.status != 'frozen':
            return Response({'detail': 'Group is not frozen.'}, status=status.HTTP_400_BAD_REQUEST)
        group.status = 'active'
        group.save(update_fields=['status'])
        enrollments = GroupStudent.objects.filter(
            group=group, left_at__isnull=True
        ).select_related('student')
        for gs in enrollments:
            if gs.student.status == 'frozen':
                gs.student.status = 'active'
                gs.student.save(update_fields=['status'])
        return Response({'status': 'active'})
