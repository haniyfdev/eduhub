from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.mixins import get_active_company


class SmsVariablesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.students.models import Student
        from apps.groups.models import GroupStudent
        from apps.debts.models import Debt

        student_ids = request.data.get('student_ids', [])
        company = get_active_company(request)

        students = Student.objects.filter(
            id__in=student_ids,
            company=company,
        ).select_related('course', 'company')

        result = {}
        for student in students:
            gs = GroupStudent.objects.filter(
                student=student,
                left_at__isnull=True,
            ).select_related(
                'group__teacher__user',
                'group__course',
                'group__room',
            ).first()

            teacher_name = ''
            room_number = ''
            lesson_time = ''
            group_name = ''
            course_name = student.course.name if student.course else ''

            if gs:
                group = gs.group
                group_name = f"{group.number}{(group.gender_type or '').upper()}"
                if group.room:
                    room_number = str(group.room.name)
                if group.start_time:
                    lesson_time = group.start_time.strftime('%H:%M')
                if group.teacher and group.teacher.user:
                    u = group.teacher.user
                    teacher_name = f"{u.first_name} {u.last_name}".strip()
                if group.course:
                    course_name = group.course.name

            amount = ''
            balance = ''
            due_date = ''
            try:
                from django.db.models import Sum
                from apps.payments.models import Payment
                total_paid = Payment.objects.filter(
                    student=student,
                    company=company,
                ).aggregate(total=Sum('amount'))['total'] or 0
                amount = str(int(total_paid))

                debt = Debt.objects.filter(
                    student=student,
                    company=company,
                    status__in=('unpaid', 'partial', 'overdue'),
                ).first()
                if debt:
                    balance = str(int(debt.amount))
                    due_date = debt.due_date.strftime('%d.%m.%Y') if debt.due_date else ''
            except Exception:
                pass

            result[str(student.id)] = {
                'student_name': f"{student.first_name} {student.last_name}",
                'phone': student.phone or '',
                'course_name': course_name,
                'group_name': group_name,
                'teacher_name': teacher_name,
                'room_number': room_number,
                'lesson_time': lesson_time,
                'company_name': student.company.name,
                'amount': amount,
                'balance': balance,
                'due_date': due_date,
            }

        lead_ids = request.data.get('lead_ids', [])
        if lead_ids:
            from apps.leads.models import Lead
            leads = Lead.objects.filter(
                id__in=lead_ids,
                company=company,
            ).select_related('course', 'company')
            for lead in leads:
                group_name = ''
                teacher_name = ''
                room_number = ''
                lesson_time = ''
                course_name = lead.course.name if lead.course else ''

                # trial lead → linked student → group
                try:
                    student = lead.student  # OneToOneField reverse
                    gs = GroupStudent.objects.filter(
                        student=student,
                        left_at__isnull=True,
                    ).select_related(
                        'group__teacher__user',
                        'group__course',
                        'group__room',
                    ).first()
                    if gs:
                        group = gs.group
                        group_name = f"{group.number}{(group.gender_type or '').upper()}"
                        if group.room:
                            room_number = str(group.room.name)
                        if group.start_time:
                            lesson_time = group.start_time.strftime('%H:%M')
                        if group.teacher and group.teacher.user:
                            u = group.teacher.user
                            teacher_name = f"{u.first_name} {u.last_name}".strip()
                        if group.course:
                            course_name = group.course.name
                except Exception:
                    pass

                result[str(lead.id)] = {
                    'student_name': f"{lead.first_name} {lead.last_name}",
                    'phone': lead.phone or '',
                    'course_name': course_name,
                    'group_name': group_name,
                    'teacher_name': teacher_name,
                    'room_number': room_number,
                    'lesson_time': lesson_time,
                    'company_name': lead.company.name,
                    'amount': '',
                    'balance': '',
                    'due_date': '',
                }

        return Response(result)
