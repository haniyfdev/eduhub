
from django.db.models import Case, When, IntegerField, Prefetch
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
 
from django_filters.rest_framework import DjangoFilterBackend
from utils.mixins import ArchiveMixin, CompanyFilterMixin
from .models import Student
from .serializers import StudentSerializer, StudentCreateSerializer, StudentUpdateSerializer
 
 
class StudentViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Student.objects.select_related('course').prefetch_related(
        Prefetch(
            'group_memberships',
            queryset=__import__(
                'apps.groups.models', fromlist=['GroupStudent']
            ).GroupStudent.objects.filter(
                left_at__isnull=True
            ).select_related('group__course'),
        )
    ).annotate(
        status_order=Case(
            When(status='active', then=1),
            When(status='trial', then=2),
            When(status='pending', then=3),
            When(status='frozen', then=4),
            When(status='archived', then=99),
            default=5,
            output_field=IntegerField(),
        )
    ).order_by('status_order', 'created_at')
 
    filter_backends   = [DjangoFilterBackend]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields  = ['status', 'course', 'referral_source']
    search_fields     = ['first_name', 'last_name']
 
    def get_permissions(self):
        return [IsAuthenticated()]
    
    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset().filter(status__in=['active', 'archived', 'frozen'])
        search = self.request.query_params.get('search', '')
        if search:
            q = (
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(group_memberships__group__gender_type__icontains=search)
            )
            if search.isdigit():
                q |= Q(group_memberships__group__number=int(search))
            qs = qs.filter(q).distinct()
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return StudentCreateSerializer
        if self.action in ('update', 'partial_update'):
            return StudentUpdateSerializer
        return StudentSerializer
 
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
 
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        student = self.get_object()
        student.status = 'archived'
        student.archived_at = timezone.now()
        student.save()
        return Response({'status': 'archived'})
 
    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        from apps.payments.models import Payment
        from apps.payments.serializers import PaymentSerializer
        student = self.get_object()
        qs = Payment.objects.filter(student=student).order_by('-paid_at')
        return Response(PaymentSerializer(qs, many=True).data)
 
    @action(detail=True, methods=['get'])
    def debt(self, request, pk=None):
        from apps.debts.models import Debt
        from apps.debts.serializers import DebtSerializer
        student = self.get_object()
        try:
            debt = Debt.objects.get(student=student)
            return Response(DebtSerializer(debt).data)
        except Debt.DoesNotExist:
            return Response({'detail': 'No debt record found.'}, status=status.HTTP_404_NOT_FOUND)
 
    @action(detail=True, methods=['get'])
    def attendance(self, request, pk=None):
        from apps.attendance.models import Attendance
        from apps.attendance.serializers import AttendanceSerializer
        student = self.get_object()
        qs = Attendance.objects.filter(student=student).select_related('lesson').order_by('-lesson__date')
        date_from = request.query_params.get('date_from')
        date_to   = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(lesson__date__gte=date_from)
        if date_to:
            qs = qs.filter(lesson__date__lte=date_to)
        return Response(AttendanceSerializer(qs, many=True).data)
 
    @action(detail=True, methods=['get'])
    def grades(self, request, pk=None):
        from apps.grades.models import Grade
        from apps.grades.serializers import GradeSerializer
        student = self.get_object()
        qs = Grade.objects.filter(student=student).select_related('lesson').order_by('-lesson__date')
        date_from = request.query_params.get('date_from')
        date_to   = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(lesson__date__gte=date_from)
        if date_to:
            qs = qs.filter(lesson__date__lte=date_to)
        return Response(GradeSerializer(qs, many=True).data)
 
    @action(detail=True, methods=['get'])
    def groups(self, request, pk=None):
        from apps.groups.models import GroupStudent
        from apps.groups.serializers import GroupStudentHistorySerializer
        student = self.get_object()
        qs = GroupStudent.objects.filter(student=student).select_related(
            'group__course', 'group__teacher__user'
        ).order_by('-joined_at')
        return Response(GroupStudentHistorySerializer(qs, many=True).data)
 
    @action(detail=True, methods=['get', 'post'], url_path='notes')
    def notes(self, request, pk=None):
        from apps.notes.models import StudentNote
        from apps.notes.serializers import StudentNoteSerializer, StudentNoteCreateSerializer
        student = self.get_object()
        if request.method == 'GET':
            qs = StudentNote.objects.filter(student=student).select_related('author').order_by('-created_at')
            return Response(StudentNoteSerializer(qs, many=True).data)
        serializer = StudentNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(student=student, author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
 