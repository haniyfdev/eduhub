from django.db.models import Case, IntegerField, Q, When
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.filters import SearchFilter

from utils.mixins import ArchiveMixin, CompanyFilterMixin
from utils.permissions import IsBossManagerOrAdmin, IsBossOrManager, IsBossOrManagerOrAdmin
from .models import Group, GroupStudent
from .serializers import GroupSerializer, GroupCreateSerializer


class GroupViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Group.objects.select_related('course', 'teacher__user', 'room').annotate(
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
        qs = qs.filter(status__in=['active', 'archived', 'frozen']).annotate(
            status_order=Case(
                When(status='active', then=1),
                When(status='frozen', then=2),
                When(status='archived', then=3),
                default=4,
                output_field=IntegerField(),
            )
        ).order_by('status_order', 'course__name', '-created_at')
        user = self.request.user
        if user.role == 'teacher':
            qs = qs.filter(teacher__user=user)
        return qs

    def get_permissions(self):
        if self.action in ('unfreeze',):
            return [IsBossOrManager()]
        if self.action in ('create', 'update', 'partial_update', 'archive', 'freeze',
                           'add_student', 'remove_student', 'transfer_student'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return GroupCreateSerializer
        return GroupSerializer

    def _parse_days(self, schedule):
        if not schedule:
            return set()
        return {d.strip() for d in schedule.split(' ')[0].split(',') if d.strip()}

    def _get_conflicting_group(self, room, schedule, start_time, end_time, company_id, exclude_id=None):
        if not room or not start_time or not end_time:
            return None
        new_days = self._parse_days(schedule)
        candidates = Group.objects.filter(
            company_id=company_id,
            room_id=room.id if hasattr(room, 'id') else room,
            status__in=['active', 'frozen'],
        )
        if exclude_id:
            candidates = candidates.exclude(id=exclude_id)
        for group in candidates:
            existing_days = self._parse_days(group.schedule)
            # If days are known on both sides, require common days for a conflict
            if new_days and existing_days and not (new_days & existing_days):
                continue
            if group.start_time and group.end_time:
                if start_time < group.end_time and end_time > group.start_time:
                    return group
        return None

    def _conflict_msg(self, conflict):
        t = (
            f"{conflict.start_time.strftime('%H:%M')}-{conflict.end_time.strftime('%H:%M')}"
            if conflict.start_time and conflict.end_time else ''
        )
        days = conflict.schedule.split(' ')[0] if conflict.schedule else ''
        return f"Bu xona {days} {t} da band. {conflict.display_name} guruhi o'qiyapti.".strip()

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        company = self._get_active_company()
        data = serializer.validated_data
        conflict = self._get_conflicting_group(
            room=data.get('room'),
            schedule=data.get('schedule', ''),
            start_time=data.get('start_time'),
            end_time=data.get('end_time'),
            company_id=company.id,
        )
        if conflict:
            raise ValidationError({'room': self._conflict_msg(conflict)})
        last = Group.objects.filter(company=company).order_by('-number').first()
        next_number = (last.number + 1) if last else 1
        serializer.save(company=company, number=next_number)

    def perform_update(self, serializer):
        from rest_framework.exceptions import ValidationError
        instance = serializer.instance
        data = serializer.validated_data
        conflict = self._get_conflicting_group(
            room=data.get('room', instance.room),
            schedule=data.get('schedule', instance.schedule),
            start_time=data.get('start_time', instance.start_time),
            end_time=data.get('end_time', instance.end_time),
            company_id=instance.company_id,
            exclude_id=instance.id,
        )
        if conflict:
            raise ValidationError({'room': self._conflict_msg(conflict)})
        serializer.save()

    def retrieve(self, request, *args, **kwargs):
        """Detail: include all memberships — active first, then departed."""
        from apps.students.serializers import StudentSerializer
        group = self.get_object()
        data = GroupSerializer(group).data

        active_student_ids = GroupStudent.objects.filter(
            group=group,
            left_at__isnull=True,
        ).values_list('student_id', flat=True)

        all_members = GroupStudent.objects.filter(
            group=group,
        ).exclude(
            left_at__isnull=False,
            student_id__in=active_student_ids,
        ).select_related('student').order_by(
            Case(When(left_at__isnull=True, then=0), default=1, output_field=IntegerField()),
            'joined_at',
        )
        students_data = []
        for m in all_members:
            s_data = StudentSerializer(m.student).data
            s_data['joined_at'] = m.joined_at.isoformat() if m.joined_at else None
            s_data['left_at']   = m.left_at.isoformat() if m.left_at else None
            s_data['gs_status'] = m.status
            if m.left_at is not None:
                current = GroupStudent.objects.filter(
                    student=m.student,
                    left_at__isnull=True,
                    student__status__in=['active', 'trial']
                ).select_related('group').first()
                if current:
                    gender = (current.group.gender_type or '').upper()
                    s_data['current_group'] = f"{current.group.number}{gender}"
                else:
                    s_data['current_group'] = None
            else:
                s_data['current_group'] = None
            students_data.append(s_data)
        data['students'] = students_data
        return Response(data)

    @action(detail=True, methods=['post'], url_path='add-student')
    def add_student(self, request, pk=None):
        """POST /api/v1/groups/{id}/add-student/  body: {student_id}"""
        if request.user.role == 'teacher':
            return Response({'error': "Bu amal uchun huquqingiz yo'q. Admin orqali murojaat qiling."}, status=403)
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

            if lead.status != 'pending':
                return Response(
                    {'error': f"Faqat kutilmoqda statusidagi leadlarni guruhga qo'shish mumkin. Hozirgi status: {lead.status}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Keep lead in leads table as trial; create linked trial student
            lead.status = 'trial'
            lead.save(update_fields=['status'])
            student = Student.objects.create(
                company=lead.company,
                first_name=lead.first_name,
                last_name=lead.last_name,
                phone=lead.phone,
                second_phone=lead.second_phone,
                birth_date=lead.birth_date,
                referral_source=lead.referral_source,
                status='trial',
                lead=lead,
            )

        # If already active in this group, no-op
        if GroupStudent.objects.filter(group=group, student=student, left_at__isnull=True).exists():
            return Response({'detail': 'Student is already in this group.'}, status=status.HTTP_400_BAD_REQUEST)

        GroupStudent.objects.create(group=group, student=student, joined_at=timezone.now(), status='trial')

        return Response({'status': 'student added', 'student_id': str(student.id)}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='remove-student')
    def remove_student(self, request, pk=None):
        """POST /api/v1/groups/{id}/remove-student/  body: {student_id, reason?}"""
        if request.user.role == 'teacher':
            return Response({'error': "Bu amal uchun huquqingiz yo'q. Admin orqali murojaat qiling."}, status=403)
        from apps.students.models import Student
        from django.db import transaction
        group = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'detail': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        gs = GroupStudent.objects.filter(
            group=group, student_id=student_id, left_at__isnull=True
        ).first()
        if not gs:
            return Response({'detail': 'Active membership not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            gs.status = 'left'
            gs.left_at = timezone.now()
            gs.save(update_fields=['status', 'left_at'])

            other_active = GroupStudent.objects.filter(
                student_id=student_id,
                left_at__isnull=True,
                status__in=['active', 'trial'],
            ).exclude(id=gs.id).exists()

            student_archived = False
            if not other_active:
                student = Student.objects.get(id=student_id)
                reason = request.data.get('reason', 'dropped_out')
                if reason not in ['graduated', 'dropped_out']:
                    reason = 'dropped_out'

                student.status = 'archived'
                student.archive_reason = reason
                student.archived_at = timezone.now()
                student.save(update_fields=['status', 'archive_reason', 'archived_at'])

                if student.lead_id:
                    from apps.leads.models import Lead
                    if reason == 'dropped_out':
                        Lead.objects.filter(id=student.lead_id).update(status='ignored')
                    else:
                        Lead.objects.filter(id=student.lead_id).delete()
                    Student.objects.filter(id=student.id).update(lead=None)

                student_archived = True

        return Response({'status': 'removed', 'student_archived': student_archived})

    @action(detail=True, methods=['post'], url_path='transfer-student')
    def transfer_student(self, request, pk=None):
        if request.user.role == 'teacher':
            return Response({'error': "Bu amal uchun huquqingiz yo'q. Admin orqali murojaat qiling."}, status=403)
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
            status='trial',
        )
        return Response({'status': 'transferred'})

    @action(detail=True, methods=['post'])
    def freeze(self, request, pk=None):
        if request.user.role == 'teacher':
            return Response({'error': "Bu amal uchun huquqingiz yo'q. Admin orqali murojaat qiling."}, status=403)
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
        if request.user.role == 'teacher':
            return Response({'error': "Bu amal uchun huquqingiz yo'q. Admin orqali murojaat qiling."}, status=403)
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

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        group = self.get_object()
        if group.status != 'archived':
            return Response({'error': 'Only archived groups can be restored'}, status=400)
        group.status = 'active'
        group.archived_at = None
        group.save(update_fields=['status', 'archived_at'])
        return Response({'status': 'active'})

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        DAY_MAP = {
            0: ['Du', 'Dushanba'],
            1: ['Se', 'Seshanba'],
            2: ['Ch', 'Cho', 'Chorshanba'],
            3: ['Pa', 'Payshanba'],
            4: ['Ju', 'Juma'],
            5: ['Sh', 'Sha', 'Shanba'],
            6: ['Ya', 'Yakshanba'],
        }
        today_variants = DAY_MAP[timezone.now().weekday()]

        user = request.user
        qs = Group.objects.filter(status='active')
        if user.role != 'superadmin':
            qs = qs.filter(company_id=self._resolve_company_id())

        day_filter = Q()
        for variant in today_variants:
            day_filter |= Q(schedule__icontains=variant)

        qs = qs.filter(day_filter).select_related(
            'course', 'teacher__user', 'room'
        ).order_by('start_time')

        from apps.lessons.models import Lesson

        today_date = timezone.now().date()

        result = []
        for group in qs:
            today_lesson = Lesson.objects.filter(
                group=group,
                date=today_date,
            ).first()

            lesson_status = today_lesson.status if today_lesson else None

            result.append({
                'id': str(group.id),
                'display_name': group.display_name,
                'course_name': group.course.name if group.course else '—',
                'teacher_name': (
                    f"{group.teacher.user.first_name} {group.teacher.user.last_name}".strip()
                    if group.teacher and group.teacher.user else '—'
                ),
                'room_name': group.room.name if group.room else '—',
                'start_time': str(group.start_time)[:5] if group.start_time else '—',
                'end_time': str(group.end_time)[:5] if group.end_time else '—',
                'schedule': group.schedule or '—',
                'students_count': group.memberships.filter(left_at__isnull=True).count(),
                'lesson_status': lesson_status,
            })

        return Response(result)
