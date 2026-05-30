from django.core.management.base import BaseCommand
from datetime import date, timedelta
from decimal import Decimal


class Command(BaseCommand):
    help = 'Promote trial students who have 2+ present attendances'

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
                self.stdout.write(f'Promoting {student.first_name} {student.last_name} (present={present_count})')

                # 1. Promote student
                student.status = 'active'
                student.save(update_fields=['status'])

                # 2. Delete linked lead
                if student.lead_id:
                    Lead.objects.filter(id=student.lead_id).delete()
                    Student.objects.filter(id=student.id).update(lead=None)
                    self.stdout.write(f'  -> Lead deleted')

                # 3. Create debt if not exists
                gs = GroupStudent.objects.filter(
                    student=student,
                    left_at__isnull=True,
                ).select_related('group__course').first()

                if gs and gs.group.course and gs.group.course.price > 0:
                    debt, created = Debt.objects.get_or_create(
                        student=student,
                        company=student.company,
                        defaults={
                            'amount': gs.group.course.price,
                            'discount_amount': Decimal('0'),
                            'due_date': date.today() + timedelta(days=15),
                            'status': 'unpaid',
                        },
                    )
                    self.stdout.write(f'  -> Debt {"created" if created else "already exists"}: {debt.amount}')

        self.stdout.write('Done!')
