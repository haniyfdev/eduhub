# apps/salaries/management/commands/calculate_salaries.py
#
# Ishlatish:
#   python manage.py calculate_salaries            ← joriy oy
#   python manage.py calculate_salaries --month 2026-05  ← aniq oy
#
# Render Cron Job: har oyning 1-sida soat 01:00 da
#   python manage.py calculate_salaries
#   Schedule: 0 1 1 * *

from decimal import Decimal
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.teachers.models import Teacher
from apps.salaries.models import TeacherSalary


class Command(BaseCommand):
    help = "Har bir faol o'qituvchi uchun oylik maosh hisoblaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--month',
            type=str,
            default=None,
            help='Hisoblash oyi (YYYY-MM formatida, default: joriy oy)',
        )

    def handle(self, *args, **options):
        # ── Oy aniqlash ─────────────────────────────────────────────────────
        if options['month']:
            try:
                year, mon = options['month'].split('-')
                target = date(int(year), int(mon), 1)
            except Exception:
                self.stderr.write("Xato format. YYYY-MM ko'rinishida kiriting.")
                return
        else:
            today = date.today()
            target = date(today.year, today.month, 1)

        self.stdout.write(f"Hisoblash oyi: {target.strftime('%Y-%m')}")

        # ── Faol o'qituvchilar ───────────────────────────────────────────────
        teachers = Teacher.objects.filter(
            status='active'
        ).select_related('user', 'company')

        created_count = 0
        skipped_count = 0

        for teacher in teachers:
            # Allaqachon hisoblangan bo'lsa o'tkazib yuborish
            if TeacherSalary.objects.filter(teacher=teacher, month=target).exists():
                skipped_count += 1
                continue

            base_amount = self._calculate_base(teacher, target)

            TeacherSalary.objects.create(
                company=teacher.company,
                teacher=teacher,
                month=target,
                base_amount=base_amount,
                kpi_amount=Decimal('0'),
                total_amount=base_amount,
            )
            created_count += 1
            self.stdout.write(
                f"  ✓ {teacher.user.get_full_name()} — {base_amount:,.0f} so'm"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nYaratildi: {created_count} | O'tkazildi: {skipped_count}"
            )
        )

    def _calculate_base(self, teacher: Teacher, month: date) -> Decimal:
        salary_type = teacher.salary_type

        # ── Fixed ────────────────────────────────────────────────────────────
        if salary_type == 'fixed':
            return teacher.fixed_amount or Decimal('0')

        # ── Percent — o'sha oy tushgan to'lovlar summasi * foiz ─────────────
        if salary_type == 'percent':
            from apps.payments.models import Payment
            total_payments = Payment.objects.filter(
                group__teacher=teacher,
                paid_at__year=month.year,
                paid_at__month=month.month,
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            percent = teacher.salary_percent or Decimal('0')
            return (total_payments * percent / Decimal('100')).quantize(Decimal('1'))

        # ── Per student — faol o'quvchilar soni * belgilangan summa ─────────
        if salary_type == 'per_student':
            from apps.groups.models import GroupStudent
            student_count = GroupStudent.objects.filter(
                group__teacher=teacher,
                group__status='active',
                left_at__isnull=True,
            ).values('student').distinct().count()

            per_amt = teacher.per_student_amt or Decimal('0')
            return (Decimal(student_count) * per_amt).quantize(Decimal('1'))

        return Decimal('0')