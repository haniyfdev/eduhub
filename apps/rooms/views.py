from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from utils.mixins import CompanyFilterMixin
from .models import Room
from .serializers import RoomSerializer


class RoomViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Room.objects.order_by('name')
    serializer_class = RoomSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.query_params.get('status', 'active')
        if status == 'all':
            return qs
        return qs.filter(status=status)

    def get_permissions(self):
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company())
