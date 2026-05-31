from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from utils.mixins import resolve_company_id
from .models import Grade
from .serializers import GradeListSerializer


class GradeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/v1/grades/
    Lists all grades for the user's company, ordered by -created_at.
    Supports ?student=<id> and ?lesson=<id> filters.
    """
    serializer_class = GradeListSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['student', 'lesson']

    def get_queryset(self):
        user = self.request.user
        qs = Grade.objects.select_related(
            'student', 'lesson__group'
        ).order_by('-created_at')
        if user.role == 'superadmin':
            return qs
        return qs.filter(student__company_id=resolve_company_id(self.request))
