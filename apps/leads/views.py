from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Lead
from .serializers import LeadSerializer, LeadCreateSerializer


class LeadViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'course']
    search_fields = ['first_name', 'last_name', 'phone']

    def get_queryset(self):
        qs = Lead.objects.select_related('course').prefetch_related('group_memberships__group')
        user = self.request.user
        if user.role == 'superadmin':
            return qs.order_by('-created_at')
        return qs.filter(company_id=user.company_id).order_by('-created_at')

    def get_permissions(self):
        if self.action in ('promote', 'demote', 'partial_update', 'update', 'create'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return LeadCreateSerializer
        return LeadSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, status='pending')

    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        """Promote: pending → trial, trial → active."""
        lead = self.get_object()
        if lead.status == 'pending':
            lead.status = 'trial'
        elif lead.status == 'trial':
            lead.status = 'active'
        else:
            return Response({'detail': 'Cannot promote from current status.'}, status=status.HTTP_400_BAD_REQUEST)
        lead.save(update_fields=['status'])
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=['post'])
    def demote(self, request, pk=None):
        """Demote: trial → pending, active → trial."""
        lead = self.get_object()
        if lead.status == 'trial':
            lead.status = 'pending'
        elif lead.status == 'active':
            lead.status = 'trial'
        else:
            return Response({'detail': 'Cannot demote from current status.'}, status=status.HTTP_400_BAD_REQUEST)
        lead.save(update_fields=['status'])
        return Response(LeadSerializer(lead).data)
