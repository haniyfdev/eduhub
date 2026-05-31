from django.db.models import Count, Q

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import resolve_company_id
from .models import Attendance
from .serializers import AttendanceSerializer


class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Attendance.objects.select_related('lesson__group__company', 'student')
        if user.role != 'superadmin':
            qs = qs.filter(lesson__group__company_id=resolve_company_id(self.request))
        student_id = self.request.query_params.get('student')
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs

    @action(detail=False, methods=['get'], url_path='notes')
    def notes(self, request):
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        group_id = request.query_params.get('group')

        qs = Attendance.objects.filter(
            lesson__group__company_id=resolve_company_id(request),
        ).exclude(
            note__isnull=True,
        ).exclude(
            note__exact='',
        ).select_related(
            'student',
            'lesson',
            'lesson__group',
            'lesson__group__teacher__user',
        ).order_by('-lesson__date', '-id')

        if from_date:
            qs = qs.filter(lesson__date__gte=from_date)
        if to_date:
            qs = qs.filter(lesson__date__lte=to_date)
        if group_id:
            qs = qs.filter(lesson__group_id=group_id)

        data = []
        for att in qs[:50]:
            teacher = att.lesson.group.teacher
            data.append({
                'id': str(att.id),
                'student_name': f"{att.student.first_name} {att.student.last_name}",
                'teacher_name': f"{teacher.user.first_name} {teacher.user.last_name}" if teacher and teacher.user else '—',
                'group_name': att.lesson.group.display_name if att.lesson.group else '—',
                'note': att.note,
                'date': att.lesson.date.strftime('%d/%m/%Y'),
                'status': att.status,
            })

        return Response(data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        GET /api/v1/attendance/summary/?search=query
        Returns students sorted by most absences, with attendance %.
        Only students with at least one absence are included.
        Filters by student name or group display name.
        """
        user = request.user
        search = request.query_params.get('search', '').strip()
        company_filter = {} if user.role == 'superadmin' else {'lesson__group__company_id': resolve_company_id(request)}

        rows = (
            Attendance.objects
            .filter(**company_filter)
            .values(
                'student__id', 'student__first_name', 'student__last_name',
                'student__phone', 'student__second_phone',
            )
            .annotate(
                total=Count('id'),
                present=Count('id', filter=Q(status__in=['present', 'late'])),
                absent=Count('id', filter=Q(status='absent')),
            )
            .filter(absent__gt=0)
            .order_by('-absent')
        )

        from apps.groups.models import GroupStudent
        if user.role == 'superadmin':
            memberships = GroupStudent.objects.filter(left_at__isnull=True).select_related('group__course')
        else:
            memberships = GroupStudent.objects.filter(
                left_at__isnull=True,
                group__company_id=resolve_company_id(request),
            ).select_related('group__course')

        group_map = {str(m.student_id): m.group.display_name for m in memberships}
        course_map = {str(m.student_id): m.group.course.name for m in memberships}

        result = []
        for row in rows:
            sid = str(row['student__id'])
            total = row['total']
            present = row['present']
            pct = round(present / total * 100) if total else 0
            result.append({
                'student_id': sid,
                'student_name': f"{row['student__first_name']} {row['student__last_name']}",
                'phone': row['student__phone'],
                'second_phone': row['student__second_phone'] or None,
                'group': group_map.get(sid, '—'),
                'course': course_map.get(sid, '—'),
                'total': total,
                'present': present,
                'absent': row['absent'],
                'attendance_pct': pct,
            })

        if search:
            q = search.lower()
            result = [
                r for r in result
                if q in r['student_name'].lower()
                or q in r['group'].lower()
            ]

        return Response(result)
