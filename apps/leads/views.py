from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone
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
        from django.db.models import Case, When, IntegerField, Value
        qs = Lead.objects.select_related('course').annotate(
            status_order=Case(
                When(status__in=['pending', 'trial'], then=Value(1)),
                When(status='ignored', then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        user = self.request.user
        if user.role == 'superadmin':
            return qs.order_by('status_order', 'created_at')
        return qs.filter(company_id=user.company_id).order_by('status_order', 'created_at')

    def get_permissions(self):
        if self.action in ('promote', 'demote', 'ignore', 'partial_update', 'update', 'create'):
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
        """pending → trial (update); trial → active (create Student, delete Lead)."""
        lead = self.get_object()

        if lead.status == 'pending':
            lead.status = 'trial'
            lead.save(update_fields=['status'])
            return Response(LeadSerializer(lead).data)

        if lead.status == 'trial':
            from apps.students.models import Student
            student = Student.objects.create(
                company=lead.company,
                first_name=lead.first_name,
                last_name=lead.last_name,
                phone=lead.phone,
                second_phone=lead.second_phone,
                course=lead.course,
                birth_date=lead.birth_date,
                referral_source=lead.referral_source,
                status='active',
                created_at=lead.created_at,
            )
            lead.delete()
            from apps.students.serializers import StudentSerializer
            return Response(StudentSerializer(student).data, status=status.HTTP_201_CREATED)

        return Response({'detail': 'Cannot promote from current status.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        lead = self.get_object()
        description = request.data.get('description', '')
        lead.status = 'ignored'
        if description:
            existing = lead.notes or ''
            lead.notes = f"{existing}\n{description}".strip()
        lead.save(update_fields=['status', 'notes'])
        return Response({'status': 'ignored'})

    @action(detail=False, methods=['get'], url_path='conversion-stats')
    def conversion_stats(self, request):
        """GET /api/v1/leads/conversion-stats/ — current lead counts by status."""
        from django.db.models import Count
        qs = self.get_queryset()
        counts = {row['status']: row['count'] for row in qs.values('status').annotate(count=Count('id'))}
        return Response({
            'pending': counts.get('pending', 0),
            'trial': counts.get('trial', 0),
            'ignored': counts.get('ignored', 0),
        })

    @action(detail=True, methods=['post'])
    def demote(self, request, pk=None):
        """trial → pending."""
        lead = self.get_object()
        if lead.status == 'trial':
            lead.status = 'pending'
            lead.save(update_fields=['status'])
            return Response(LeadSerializer(lead).data)
        return Response({'detail': 'Cannot demote from current status.'}, status=status.HTTP_400_BAD_REQUEST)
