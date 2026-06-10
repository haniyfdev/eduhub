import logging

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.mixins import get_active_company
from utils.permissions import IsBossOrManager
from utils.telegram_notify import send_telegram_sync
from .models import Notification
from .telegram_templates import TEMPLATES

logger = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):
        return ''


def render_template(template_key: str, lang: str, variables: dict) -> str:
    templates = TEMPLATES.get(template_key)
    if not templates:
        raise ValueError('invalid_template')
    lang = lang if lang in templates else 'uz'
    return templates[lang].format_map(_SafeDict(variables))


def _student_variables(student, company) -> dict:
    from apps.debts.models import Debt
    from apps.groups.models import GroupStudent

    variables = {
        'full_name': f"{student.first_name} {student.last_name}",
        'company_name': company.name if company else '',
    }

    gs = GroupStudent.objects.filter(
        student=student, left_at__isnull=True
    ).select_related('group__course').first()

    if gs and gs.group:
        variables['course_name'] = gs.group.course.name if gs.group.course else ''
        debt = Debt.objects.filter(group_student=gs, status__in=['unpaid', 'partial']).first()
        if debt:
            variables['amount'] = f"{int(debt.amount):,}".replace(',', ' ')
            if debt.due_date:
                variables['due_date'] = debt.due_date.strftime('%d.%m.%Y')

    return variables


def _send_to_student(student, template_key: str, lang: str, variables: dict, company) -> bool:
    """Renders the template, sends via Telegram, and logs to Notification. Returns sent status."""
    if not student.telegram_chat_id:
        return False

    base_vars = _student_variables(student, company)
    base_vars.update(variables or {})
    text = render_template(template_key, lang, base_vars)

    sent = send_telegram_sync(student.telegram_chat_id, text)
    Notification.objects.create(
        company=company,
        recipient_phone=student.phone,
        message=text,
        type='telegram',
        status='sent' if sent else 'failed',
        sent_at=timezone.now() if sent else None,
    )
    return sent


class SendToStudentView(APIView):
    """POST /api/v1/notifications/send-to-student/"""
    permission_classes = [IsBossOrManager]

    def post(self, request):
        from apps.students.models import Student

        student_id = request.data.get('student_id')
        template_key = request.data.get('template_key')
        lang = request.data.get('lang', 'uz')
        variables = request.data.get('variables', {})

        if not student_id or not template_key:
            return Response(
                {'error': 'student_id and template_key are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_active_company(request)
        try:
            student = Student.objects.get(id=student_id, company=company)
        except (Student.DoesNotExist, ValidationError):
            return Response({'error': 'student_not_found'}, status=status.HTTP_404_NOT_FOUND)

        if not student.telegram_chat_id:
            return Response({'error': 'telegram_not_linked'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sent = _send_to_student(student, template_key, lang, variables, company)
        except ValueError:
            return Response({'error': 'invalid_template'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'sent': sent})


class SendToGroupView(APIView):
    """POST /api/v1/notifications/send-to-group/"""
    permission_classes = [IsBossOrManager]

    def post(self, request):
        from apps.groups.models import Group, GroupStudent

        group_id = request.data.get('group_id')
        template_key = request.data.get('template_key')
        lang = request.data.get('lang', 'uz')
        variables = request.data.get('variables', {})

        if not group_id or not template_key:
            return Response(
                {'error': 'group_id and template_key are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_active_company(request)
        try:
            group = Group.objects.get(id=group_id, company=company)
        except (Group.DoesNotExist, ValidationError):
            return Response({'error': 'group_not_found'}, status=status.HTTP_404_NOT_FOUND)

        memberships = GroupStudent.objects.filter(
            group=group, left_at__isnull=True
        ).select_related('student')

        sent_count = 0
        skipped_count = 0
        for gs in memberships:
            try:
                sent = _send_to_student(gs.student, template_key, lang, variables, company)
            except ValueError:
                return Response({'error': 'invalid_template'}, status=status.HTTP_400_BAD_REQUEST)
            if sent:
                sent_count += 1
            else:
                skipped_count += 1

        return Response({'sent': sent_count, 'skipped': skipped_count})


class SendToAllView(APIView):
    """POST /api/v1/notifications/send-to-all/"""
    permission_classes = [IsBossOrManager]

    def post(self, request):
        from apps.students.models import Student

        template_key = request.data.get('template_key')
        lang = request.data.get('lang', 'uz')
        variables = request.data.get('variables', {})

        if not template_key:
            return Response({'error': 'template_key is required'}, status=status.HTTP_400_BAD_REQUEST)

        company = get_active_company(request)
        students = Student.objects.filter(company=company, status='active')

        sent_count = 0
        skipped_count = 0
        for student in students:
            try:
                sent = _send_to_student(student, template_key, lang, variables, company)
            except ValueError:
                return Response({'error': 'invalid_template'}, status=status.HTTP_400_BAD_REQUEST)
            if sent:
                sent_count += 1
            else:
                skipped_count += 1

        return Response({'sent': sent_count, 'skipped': skipped_count})


class SendCustomView(APIView):
    """POST /api/v1/notifications/send-custom/"""
    permission_classes = [IsBossOrManager]

    def post(self, request):
        from apps.students.models import Student
        from apps.groups.models import Group, GroupStudent

        target = request.data.get('target')
        target_id = request.data.get('target_id')
        title = request.data.get('title', '')
        body = request.data.get('body', '')
        lang = request.data.get('lang', 'uz')

        if target not in ('student', 'group', 'all'):
            return Response({'error': 'invalid_target'}, status=status.HTTP_400_BAD_REQUEST)

        company = get_active_company(request)
        variables = {'title': title, 'body': body}

        if target == 'student':
            try:
                student = Student.objects.get(id=target_id, company=company)
            except (Student.DoesNotExist, ValidationError):
                return Response({'error': 'student_not_found'}, status=status.HTTP_404_NOT_FOUND)
            if not student.telegram_chat_id:
                return Response({'error': 'telegram_not_linked'}, status=status.HTTP_400_BAD_REQUEST)
            sent = _send_to_student(student, 'custom_message', lang, variables, company)
            return Response({'sent': sent})

        if target == 'group':
            try:
                group = Group.objects.get(id=target_id, company=company)
            except (Group.DoesNotExist, ValidationError):
                return Response({'error': 'group_not_found'}, status=status.HTTP_404_NOT_FOUND)
            students = [
                gs.student for gs in GroupStudent.objects.filter(
                    group=group, left_at__isnull=True
                ).select_related('student')
            ]
        else:
            students = Student.objects.filter(company=company, status='active')

        sent_count = 0
        skipped_count = 0
        for student in students:
            if _send_to_student(student, 'custom_message', lang, variables, company):
                sent_count += 1
            else:
                skipped_count += 1

        return Response({'sent': sent_count, 'skipped': skipped_count})
