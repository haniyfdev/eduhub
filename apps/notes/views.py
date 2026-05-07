from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import StudentNote
from .serializers import StudentNoteSerializer


class StudentNoteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/v1/student-notes/
    Lists all student notes for the user's company, ordered by -created_at.
    Supports ?ordering=-created_at and ?student=<id>.
    """
    serializer_class = StudentNoteSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['student']

    def get_queryset(self):
        user = self.request.user
        qs = StudentNote.objects.select_related('student', 'author').order_by('-created_at')
        if user.role == 'superadmin':
            return qs
        return qs.filter(student__company_id=user.company_id)
