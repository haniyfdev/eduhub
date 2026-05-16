from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Group


class RoomsView(APIView):
    """GET /api/v1/rooms/
    Returns active groups grouped by room with parsed day schedules."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.user.company if request.user.role != 'superadmin' else None
        cf = {} if company is None else {'company': company}

        groups = (
            Group.objects
            .filter(**cf, status__in=['active', 'frozen'])
            .select_related('course', 'teacher__user')
            .prefetch_related('memberships')
            .order_by('room', 'start_time')
        )

        by_room: dict = {}
        for g in groups:
            room = (g.room or 'Nomsiz xona').strip()
            if room not in by_room:
                by_room[room] = []

            raw_days = g.schedule.split(' ')[0] if g.schedule else ''
            days = [d.strip() for d in raw_days.split(',') if d.strip()]

            by_room[room].append({
                'id':             str(g.id),
                'group_name':     g.display_name,
                'course':         g.course.name if g.course else None,
                'days':           days,
                'start_time':     g.start_time.strftime('%H:%M') if g.start_time else None,
                'end_time':       g.end_time.strftime('%H:%M') if g.end_time else None,
                'status':         g.status,
                'students_count': g.memberships.filter(left_at__isnull=True).count(),
            })

        return Response([
            {'room': room, 'groups': grps}
            for room, grps in sorted(by_room.items())
        ])
