from django.core.management.base import BaseCommand
from datetime import date, timedelta
from decimal import Decimal


class Command(BaseCommand):
    help = 'Promote trial students who have 2+ present/late attendances'

    def handle(self, *args, **kwargs):
        from apps.students.models import Student
        from apps.attendance.models import Attendance
        from apps.leads.models import Lead
        from apps.debts.models import Debt
        from apps.groups.models import GroupStudent

        trial_students = Student.objects.filter(status='trial')
        self.stdout.write(f'Found {trial_students.count()} trial students')

        for student in trial_students:
            present_count = Attendance.objects.filter(
                student=student,
                status__in=['present', 'late'],
            ).count()

            if present_count >= 2:
                self.stdout.write(
                    f'Promoting {student.first_name} {student.last_name} '
                    f'(present+late={present_count})'
                )

                Student.objects.filter(id=student.id).update(status='active')

                if student.lead_id:
                    Lead.objects.filter(id=student.lead_id).delete()
                    Student.objects.filter(id=student.id).update(lead=None)
                    self.stdout.write('  -> Lead deleted')

                gs = GroupStudent.objects.filter(
                    student=student,
                    left_at__isnull=True,
                ).select_related('group__course').first()

                if gs and gs.group.course and gs.group.course.price > 0:
                    current_month = date.today().replace(day=1)
                    course_price = Decimal(str(gs.group.course.price))

                    active_discount = None
                    try:
                        active_discount = student.discounts.filter(
                            start_month__lte=current_month,
                            end_month__gte=current_month,
                            course=gs.group.course,
                        ).first()
                    except Exception:
                        pass

                    if active_discount:
                        discount_amt = course_price * active_discount.percent / 100
                        final_amount = course_price - discount_amt
                    else:
                        discount_amt = Decimal('0')
                        final_amount = course_price

                    debt, created = Debt.objects.get_or_create(
                        student=student,
                        company=student.company,
                        defaults={
                            'amount': final_amount,
                            'discount_amount': discount_amt,
                            'due_date': date.today() + timedelta(days=15),
                            'status': 'unpaid',
                        },
                    )
                    self.stdout.write(
                        f'  -> Debt {"created" if created else "already exists"}: {debt.amount}'
                    )
                else:
                    self.stdout.write('  -> No active group/course found')

        self.stdout.write('Done!')
