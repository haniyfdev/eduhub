from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager, IsBossOrManagerOrAdmin
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
        return qs.filter(company_id=self._resolve_company_id()).order_by('status_order', 'created_at')

    def get_permissions(self):
        if self.action in ('promote', 'demote'):
            return [IsBossOrManager()]
        if self.action in ('create', 'update', 'partial_update', 'ignore'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return LeadCreateSerializer
        return LeadSerializer

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company(), status='pending')

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
        """GET /api/v1/leads/conversion-stats/ — current pipeline snapshot."""
        from apps.students.models import Student

        cf = {} if request.user.role == 'superadmin' else {'company_id': self._resolve_company_id()}

        total_leads    = Lead.objects.filter(**cf).count()
        total_students = Student.objects.filter(**cf).count()
        grand_total    = total_leads + total_students

        active   = Student.objects.filter(**cf, status='active').count()
        trial    = Student.objects.filter(**cf, status='trial').count()
        frozen   = Student.objects.filter(**cf, status='frozen').count()
        archived = Student.objects.filter(**cf, status='archived').count()
        pending  = Lead.objects.filter(**cf, status='pending').count()
        ignored  = Lead.objects.filter(**cf, status='ignored').count()

        def pct(n):
            return round(n / grand_total * 100, 1) if grand_total > 0 else 0

        return Response({
            'grand_total': grand_total,
            'active':   {'count': active,   'percent': pct(active)},
            'trial':    {'count': trial,    'percent': pct(trial)},
            'frozen':   {'count': frozen,   'percent': pct(frozen)},
            'archived': {'count': archived, 'percent': pct(archived)},
            'pending':  {'count': pending,  'percent': pct(pending)},
            'ignored':  {'count': ignored,  'percent': pct(ignored)},
        })

    @action(detail=False, methods=['get'], url_path='referral-stats')
    def referral_stats(self, request):
        """GET /api/v1/leads/referral-stats/ — referral source breakdown across leads+students.

        Only the 5 canonical sources are returned. Any dirty/legacy value in the DB
        (e.g. 'social', 'ads', 'recommendation') is folded into 'other' here so the
        frontend never needs to handle unknown keys.
        """
        from django.db.models import Count
        from apps.students.models import Student

        CANONICAL = {'banner', 'friend', 'parent', 'social_media', 'other'}
        LABELS = {
            'banner':       'Banner',
            'friend':       'Tanish orqali',
            'parent':       'Ota-ona',
            'social_media': 'Ijtimoiy tarmoq',
            'other':        'Boshqa',
        }

        cf = {} if request.user.role == 'superadmin' else {'company_id': self._resolve_company_id()}

        lead_refs = (
            Lead.objects.filter(**cf, referral_source__isnull=False)
            .exclude(referral_source='')
            .values('referral_source').annotate(count=Count('id'))
        )
        student_refs = (
            Student.objects.filter(**cf, referral_source__isnull=False)
            .exclude(referral_source='')
            .values('referral_source').annotate(count=Count('id'))
        )

        # Normalise: fold any non-canonical key into 'other'
        refs: dict = {k: 0 for k in CANONICAL}
        for item in list(lead_refs) + list(student_refs):
            key = item['referral_source'] if item['referral_source'] in CANONICAL else 'other'
            refs[key] += item['count']

        # Drop canonical buckets that are still zero so the chart stays clean
        refs = {k: v for k, v in refs.items() if v > 0}

        total = sum(refs.values())

        result = [
            {
                'source':  k,
                'label':   LABELS[k],
                'count':   v,
                'percent': round(v / total * 100, 1) if total > 0 else 0,
            }
            for k, v in sorted(refs.items(), key=lambda x: -x[1])
        ]

        return Response({'total': total, 'data': result})

    @action(detail=True, methods=['post'])
    def demote(self, request, pk=None):
        """trial → pending."""
        lead = self.get_object()
        if lead.status == 'trial':
            lead.status = 'pending'
            lead.save(update_fields=['status'])
            return Response(LeadSerializer(lead).data)
        return Response({'detail': 'Cannot demote from current status.'}, status=status.HTTP_400_BAD_REQUEST)
