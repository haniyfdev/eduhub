from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.mixins import resolve_company_id
from .models import Group


class RoomsView(APIView):
    """GET /api/v1/rooms/
    Returns active groups grouped by room with parsed day schedules."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == 'superadmin':
            groups = Group.objects.filter(status='active')
        else:
            groups = Group.objects.filter(
                company_id=resolve_company_id(request),
                status__in=['active', 'frozen'],
            )

        groups = groups.select_related('course', 'teacher__user').order_by('room', 'start_time')

        rooms: dict = {}
        for g in groups:
            room = (g.room or 'Xona belgilanmagan').strip()
            if room not in rooms:
                rooms[room] = []

            days = []
            if g.schedule:
                days_part = g.schedule.split(' ')[0]
                days = [d.strip() for d in days_part.split(',') if d.strip()]

            teacher_name = '—'
            if g.teacher and g.teacher.user:
                teacher_name = f"{g.teacher.user.first_name} {g.teacher.user.last_name}".strip() or '—'

            rooms[room].append({
                'id':             str(g.id),
                'name':           f"{g.number}{(g.gender_type or '').upper()}",
                'course':         g.course.name if g.course else '—',
                'teacher':        teacher_name,
                'days':           days,
                'start_time':     g.start_time.strftime('%H:%M') if g.start_time else None,
                'end_time':       g.end_time.strftime('%H:%M') if g.end_time else None,
                'status':         g.status,
                'students_count': g.memberships.filter(left_at__isnull=True).count(),
            })

        return Response([
            {'room': room, 'groups': grps}
            for room, grps in sorted(rooms.items())
        ])
