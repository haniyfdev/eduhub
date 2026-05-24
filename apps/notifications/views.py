import logging
import re

from rest_framework import status, viewsets, mixins

logger = logging.getLogger(__name__)
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.mixins import CompanyFilterMixin
from .models import Announcement, AnnouncementRead, Notification, SmsTemplate
from .serializers import AnnouncementSerializer, NotificationSerializer, SmsTemplateSerializer


class NotificationViewSet(CompanyFilterMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/v1/notifications/ — read-only log."""
    queryset = Notification.objects.order_by('-created_at')
    serializer_class = NotificationSerializer
    filterset_fields = ['status', 'type']
    http_method_names = ['get', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]


class SmsTemplateViewSet(viewsets.ModelViewSet):
    """Rule 1 exception: SmsTemplate CAN be deleted."""
    queryset = SmsTemplate.objects.all()
    serializer_class = SmsTemplateSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        from django.db.models import Q
        user = self.request.user
        if user.role == 'superadmin':
            return SmsTemplate.objects.filter(
                company__isnull=True
            ).order_by('-is_default', 'name')
        company = user.company
        company_names = SmsTemplate.objects.filter(
            company=company
        ).values_list('name', flat=True)
        return SmsTemplate.objects.filter(
            Q(company=company) | Q(company__isnull=True, is_default=True)
        ).exclude(
            Q(company__isnull=True) & Q(name__in=company_names)
        ).order_by('-is_default', 'name')

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == 'superadmin':
            serializer.save(company=None, is_default=True)
        else:
            serializer.save(company=user.company, is_default=False)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if instance.company is None and user.role != 'superadmin':
            new_template = SmsTemplate.objects.create(
                company=user.company,
                name=instance.name,
                trigger=instance.trigger,
                body=request.data.get('body', instance.body),
                is_default=False,
                is_active=True,
            )
            return Response(SmsTemplateSerializer(new_template).data)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if instance.company is None and user.role != 'superadmin':
            return Response(
                {'error': "Standart shablonni o'chira olmaysiz"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if instance.company and instance.company != user.company:
            return Response({'error': "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


def resolve_variables(body: str, recipient_type: str, recipient_id: str, company, extra_data: dict = None) -> str:
    extra_data = extra_data or {}

    variables = {
        'company_name': company.name if company else '',
        'student_name': '',
        'course_name':  '',
        'group_name':   '',
        'teacher_name': '',
        'phone':        '',
        'amount':       extra_data.get('amount', ''),
        'due_date':     extra_data.get('due_date', ''),
        'lesson_time':  '',
        'room_number':  '',
    }

    if recipient_type in ('student', 'lead'):
        if recipient_type == 'student':
            from apps.students.models import Student
            try:
                student = Student.objects.select_related('course', 'company').get(id=recipient_id)
                variables['student_name'] = f"{student.first_name} {student.last_name}"
                variables['phone'] = student.phone or ''
                variables['course_name'] = student.course.name if student.course else ''
            except Student.DoesNotExist:
                return body

        elif recipient_type == 'lead':
            from apps.leads.models import Lead
            try:
                lead = Lead.objects.select_related('course').get(id=recipient_id)
                variables['student_name'] = f"{lead.first_name} {lead.last_name}"
                variables['phone'] = lead.phone or ''
                variables['course_name'] = lead.course.name if lead.course else ''
            except Lead.DoesNotExist:
                return body

        from apps.groups.models import GroupStudent
        gs = GroupStudent.objects.filter(
            student_id=recipient_id if recipient_type == 'student' else None,
            left_at__isnull=True,
        ).select_related(
            'group__course',
            'group__teacher__user',
            'group__room',
        ).first()

        if recipient_type == 'lead':
            from apps.leads.models import Lead
            try:
                lead = Lead.objects.get(id=recipient_id)
                gs = GroupStudent.objects.filter(
                    student__phone=lead.phone,
                    left_at__isnull=True,
                ).select_related(
                    'group__course',
                    'group__teacher__user',
                    'group__room',
                ).first()
            except Exception:
                gs = None

        if gs and gs.group:
            group = gs.group
            gender = (group.gender_type or '').upper()
            variables['group_name'] = f"{group.number}{gender}"
            if group.teacher and group.teacher.user:
                t = group.teacher.user
                variables['teacher_name'] = f"{t.first_name} {t.last_name}"
            if group.course:
                variables['course_name'] = group.course.name
            if group.start_time:
                variables['lesson_time'] = group.start_time.strftime('%H:%M')
            if group.room:
                variables['room_number'] = str(group.room.name)

        if not variables['amount'] and recipient_type == 'student':
            from apps.debts.models import Debt
            debt = Debt.objects.filter(
                student_id=recipient_id,
                status__in=['unpaid', 'partial'],
            ).first()
            if debt:
                variables['amount'] = f"{int(debt.amount):,}".replace(',', ' ')
                if not variables['due_date'] and debt.due_date:
                    variables['due_date'] = debt.due_date.strftime('%d.%m.%Y')

    logger.info("SMS variables: %s", variables)

    def replacer(match):
        return str(variables.get(match.group(1), ''))

    return re.sub(r'\{(\w+)\}', replacer, body)


class SmsSendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.notifications.tasks import send_sms_task

        recipients = request.data.get('recipients', [])
        template_id = request.data.get('template_id')
        message = request.data.get('message')
        phone = request.data.get('phone')
        company = getattr(request.user, 'company', None)

        # Simple mode: single phone + pre-resolved message, no recipients list
        if phone and message and not recipients:
            send_sms_task.delay(
                company_id=str(request.user.company_id),
                phone=phone,
                message=message,
            )
            return Response({'status': 'sent'})

        # Structured mode: backend resolves variables per recipient
        if template_id:
            try:
                template = SmsTemplate.objects.get(id=template_id)
                template_body = template.body
            except SmsTemplate.DoesNotExist:
                return Response({'error': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        elif message:
            template_body = message
        else:
            return Response(
                {'error': 'template_id or message required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not recipients:
            return Response({'error': 'recipients required'}, status=status.HTTP_400_BAD_REQUEST)

        for recipient in recipients:
            r_phone = recipient.get('phone', '')
            if not r_phone:
                continue
            extra_data = {
                'amount':   recipient.get('amount', ''),
                'due_date': recipient.get('due_date', ''),
            }
            resolved = resolve_variables(
                template_body,
                recipient.get('type', 'student'),
                recipient.get('id'),
                company,
                extra_data=extra_data,
            )
            send_sms_task.delay(
                company_id=str(request.user.company_id),
                phone=r_phone,
                message=resolved,
            )

        return Response({'status': 'sent', 'count': len(recipients)})


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'teacher':
            return Announcement.objects.none()
        return Announcement.objects.filter(
            is_active=True
        ).prefetch_related('reads').order_by('-created_at')

    def perform_create(self, serializer):
        if self.request.user.role != 'superadmin':
            raise PermissionDenied("Faqat superadmin xabar yoza oladi")
        serializer.save(created_by=self.request.user)

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        announcement = self.get_object()
        AnnouncementRead.objects.get_or_create(
            announcement=announcement,
            user=request.user
        )
        return Response({'status': 'read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        user = request.user
        if user.role in ['superadmin', 'teacher']:
            return Response({'unread': 0})
        total = Announcement.objects.filter(is_active=True).count()
        read = AnnouncementRead.objects.filter(
            user=user,
            announcement__is_active=True
        ).count()
        return Response({'unread': max(total - read, 0)})
