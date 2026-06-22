from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManagerOrAdmin
from .models import Refund
from .serializers import RefundSerializer, RefundCreateSerializer, RefundUpdateSerializer


class RefundViewSet(
    CompanyFilterMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Refund.objects.select_related(
        'group_student__student', 'group_student__group__course', 'debt'
    ).order_by('-created_at')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['group_student']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return RefundCreateSerializer
        if self.action in ('update', 'partial_update'):
            return RefundUpdateSerializer
        return RefundSerializer

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company())

    @action(detail=False, methods=['get'], url_path='candidates')
    def candidates(self, request):
        """Former students whose total payments exceed what they actually
        earned (per the same proration math as the Sobiq debt-confirmation
        flow), with no Refund record created yet.
        """
        from apps.groups.models import GroupStudent
        from .services import get_refund_candidate_info

        company = self._get_active_company()
        gs_filter = {} if company is None else {'group__company': company}

        left_gs = GroupStudent.objects.filter(
            status='left', **gs_filter
        ).exclude(
            id__in=Refund.objects.values('group_student_id')
        ).select_related('student', 'group__course', 'group__company')

        results = []
        for gs in left_gs:
            info = get_refund_candidate_info(gs)
            if info is None:
                continue

            debt = info['debt']
            results.append({
                'group_student_id': str(gs.id),
                'student_name':     f"{gs.student.first_name} {gs.student.last_name}",
                'student_phone':    gs.student.phone,
                'group_name':       gs.group.display_name,
                'course_name':      gs.group.course.name if gs.group.course else None,
                'total_paid':       float(info['total_paid']),
                'earned_amount':    float(info['earned_amount']) if info['earned_amount'] is not None else None,
                'refund_amount':    float(info['refund_amount']) if info['refund_amount'] is not None else None,
                'debt_id':          str(debt.id) if debt else None,
                'billing_type':     info['billing_type'],
                'breakdown':        info['breakdown'],
                'course_price':     float(info['course_price']) if info['course_price'] is not None else None,
                'total_lessons':    info['total_lessons'],
                'attended_lessons': info['attended_lessons'],
                'per_lesson_price': float(info['per_lesson_price']) if info['per_lesson_price'] is not None else None,
            })

        return Response(results)
