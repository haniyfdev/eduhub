
from django.db.models import Q
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
 
from utils.mixins import CompanyFilterMixin
from .models import Debt
from .serializers import DebtSerializer, DebtUpdateSerializer
 
 
class DebtViewSet(
    CompanyFilterMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Debt.objects.select_related('student').prefetch_related(
        'student__group_memberships__group'
    ).order_by('due_date')
    http_method_names = ['get', 'patch', 'post', 'head', 'options']
 
    def get_permissions(self):
        return [IsAuthenticated()]
 
    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return DebtUpdateSerializer
        return DebtSerializer
 
    def get_queryset(self):
        qs = super().get_queryset()
 
        # Status filter — comma-separated: ?status=unpaid,overdue
        status_param = self.request.query_params.get('status', '')
        if status_param:
            statuses = [s.strip() for s in status_param.split(',') if s.strip()]
            qs = qs.filter(status__in=statuses)
 
        # Due date filter
        due_date = self.request.query_params.get('due_date')
        if due_date:
            qs = qs.filter(due_date=due_date)
 
        # Search — ism, familiya yoki guruh nomi
        search = self.request.query_params.get('search', '')
        if search:
            q = (
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(student__group_memberships__group__gender_type__icontains=search)
            )
            if search.isdigit():
                q |= Q(student__group_memberships__group__number=int(search))
            qs = qs.filter(q).distinct()
 
        return qs
 
    @action(detail=True, methods=['post'], url_path='send-sms')
    def send_sms(self, request, pk=None):
        from apps.notifications.tasks import send_sms_task
        from apps.notifications.models import SmsTemplate
 
        debt = self.get_object()
        template = SmsTemplate.objects.filter(
            company=debt.company,
            type='debt',
        ).first()
 
        if not template:
            return Response(
                {'detail': 'No debt SMS template found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
 
        # phone1 yoki phone2 — request dan keladi
        phone = request.data.get('phone') or debt.student.second_phone or debt.student.phone
        if not phone:
            return Response(
                {'detail': 'Student has no phone number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        message = template.body.format(
            student_name=f"{debt.student.first_name} {debt.student.last_name}",
            amount=debt.amount,
            due_date=debt.due_date,
        )
 
        send_sms_task.delay(
            company_id=str(debt.company_id),
            phone=phone,
            message=message,
            notification_type='sms',
        )
        return Response({'status': 'sms queued'})