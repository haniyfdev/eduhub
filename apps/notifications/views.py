import logging
import re
import threading
import uuid

from rest_framework import status, viewsets, mixins

logger = logging.getLogger(__name__)
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.mixins import CompanyFilterMixin, get_active_company
from utils.permissions import IsBossOrManager
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
        if self.action == 'create':
            user = getattr(self.request, 'user', None)
            if user and getattr(user, 'role', None) == 'superadmin':
                return [IsAuthenticated()]
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        from django.db.models import Q
        user = self.request.user
        if user.role == 'superadmin':
            return SmsTemplate.objects.filter(
                company__isnull=True
            ).order_by('-created_at')
        company = get_active_company(self.request)
        company_names = SmsTemplate.objects.filter(
            company=company
        ).values_list('name', flat=True)
        return SmsTemplate.objects.filter(
            Q(company=company) | Q(company__isnull=True, is_default=True)
        ).exclude(
            Q(company__isnull=True) & Q(name__in=company_names)
        ).order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == 'superadmin':
            serializer.save(company=None, is_default=True)
        else:
            serializer.save(company=get_active_company(self.request), is_default=False)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if instance.company is None and user.role != 'superadmin':
            new_template = SmsTemplate.objects.create(
                company=get_active_company(request),
                name=instance.name,
                trigger=instance.trigger,
                type=request.data.get('type', instance.type),
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
        if instance.company and instance.company != get_active_company(request):
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
                student = Student.objects.select_related('company').get(id=recipient_id)
                variables['student_name'] = f"{student.first_name} {student.last_name}"
                variables['phone'] = student.phone or ''
                variables['course_name'] = ''
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
                group_student__student_id=recipient_id,
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


def _send_sms_background(items: list, company_id: str) -> None:
    """Sends each (phone, message) pair via send_sms_task synchronously
    in a background thread. One failure must not stop the rest."""
    from apps.notifications.tasks import send_sms_task

    for phone, text in items:
        try:
            send_sms_task(company_id=company_id, phone=phone, message=text)
        except Exception as e:
            logger.error(f"SMS_SEND_ERROR: phone={phone}, error={e}")


def _send_telegram_background(items: list) -> None:
    """Sends each (chat_id, message) pair via the Telegram bot.
    One failure must not stop the rest."""
    import asyncio
    from aiogram import Bot
    from django.conf import settings

    async def _send_all():
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        for chat_id, text in items:
            try:
                logger.error(f"TELEGRAM_ATTEMPTING: chat_id={chat_id}")
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                logger.error(f"TELEGRAM_SENT_OK: chat_id={chat_id}")
            except Exception as e:
                logger.error(f"TELEGRAM_SEND_ERROR: chat_id={chat_id}, error={e}")
        await bot.session.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_send_all())
    except Exception as e:
        logger.error(f"TELEGRAM_LOOP_ERROR: {e}")
    finally:
        loop.close()


class SmsSendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.error(
            "SEND_SMS: template_id=%s, message=%s, recipients=%s",
            request.data.get('template_id'),
            request.data.get('message'),
            request.data.get('recipients'),
        )

        recipients = request.data.get('recipients', [])
        template_id = request.data.get('template_id')
        # message may be explicitly null (JSON) — normalize to None so falsy checks below are safe
        message = request.data.get('message') or None
        phone = request.data.get('phone')
        company = getattr(request.user, 'company', None)

        # Simple mode: single phone + pre-resolved message, no recipients list
        if phone and message and not recipients:
            thread = threading.Thread(
                target=_send_sms_background,
                args=([(phone, message)], str(request.user.company_id)),
                daemon=True,
            )
            thread.start()
            return Response({'status': 'queued'})

        # Structured mode: backend resolves variables per recipient
        if template_id:
            try:
                uuid.UUID(str(template_id))
            except (ValueError, TypeError, AttributeError):
                return Response({'error': 'Invalid template_id'}, status=status.HTTP_400_BAD_REQUEST)
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

        from apps.students.models import Student

        company_name = company.name if company else ''
        items = []
        telegram_sent = 0
        skipped = 0
        for recipient in recipients:
            r_phone = recipient.get('phone', '')
            if not r_phone:
                continue
            r_type = recipient.get('type', 'student')
            r_id = recipient.get('id')
            if r_type in ('student', 'lead'):
                try:
                    uuid.UUID(str(r_id))
                except (ValueError, TypeError, AttributeError):
                    return Response({'error': 'Invalid recipient id'}, status=status.HTTP_400_BAD_REQUEST)
            extra_data = {
                'amount':   recipient.get('amount', ''),
                'due_date': recipient.get('due_date', ''),
            }
            resolved = resolve_variables(
                template_body,
                recipient.get('type', 'student'),
                r_id,
                company,
                extra_data=extra_data,
            )

            chat_ids = []
            if r_type == 'student':
                s = Student.objects.filter(id=r_id).only(
                    'phone', 'second_phone', 'telegram_chat_id', 'telegram_chat_id_second'
                ).first()
                logger.error(
                    f"STUDENT_LOOKUP: id={r_id}, "
                    f"chat_id={s.telegram_chat_id if s else 'NOT FOUND'}, "
                    f"chat_id_second={s.telegram_chat_id_second if s else 'NOT FOUND'}"
                )
                if s:
                    recipient_phone = r_phone.replace(' ', '')
                    if recipient_phone == s.phone:
                        chat_ids = [s.telegram_chat_id] if s.telegram_chat_id else []
                    elif recipient_phone == s.second_phone:
                        chat_ids = [s.telegram_chat_id_second] if s.telegram_chat_id_second else []
                    else:
                        chat_ids = []

            if chat_ids:
                text = f"📬 <b>{company_name}</b>\n\n{resolved}"
                for chat_id in chat_ids:
                    items.append((chat_id, text))
                telegram_sent += len(chat_ids)
            else:
                logger.warning(f"TELEGRAM_SKIP: recipient_id={r_id}, type={r_type}, no telegram_chat_id linked")
                skipped += 1

        thread = threading.Thread(
            target=_send_telegram_background,
            args=(items,),
            daemon=True,
        )
        thread.start()

        return Response({'status': 'queued', 'telegram_sent': telegram_sent, 'skipped': skipped})


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
