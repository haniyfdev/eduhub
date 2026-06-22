from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR


def compute_billing_breakdown(gs, debt=None, billing_type_override=None):
    """Attendance/day breakdown + prorated calculated_amount for a GroupStudent.

    Shared by DebtViewSet.last_month_attendance (the existing Sobiq debt
    confirmation flow) and the refund-candidate detection endpoint, so both
    use identical proration math.

    billing_type_override lets a caller force a specific billing type
    instead of the inferred one — used by the refund flow when the stored
    archive_billing_type snapshot is known to be stale (see
    apps.refunds.services.get_refund_candidate_info).
    """
    from apps.attendance.models import Attendance
    from apps.lessons.models import Lesson

    if gs.left_at is None:
        # Active/frozen/reactivated student still in group — use today as end_date.
        # Prefer the billing_type stored on the debt itself (set at freeze time);
        # fall back to the live company setting so new debts still work.
        from apps.companies.models import CompanySettings
        from django.utils import timezone as tz
        end_date = tz.now().date()
        company_settings, _ = CompanySettings.objects.get_or_create(company=gs.group.company)
        billing_type = billing_type_override or (debt.billing_type if debt else None) or company_settings.freeze_billing_type
    else:
        end_date     = gs.left_at.date()
        billing_type = billing_type_override or (debt.billing_type if debt else None) or gs.archive_billing_type or 'manual'

    joined_at       = gs.joined_at.date()
    month_start     = end_date.replace(day=1)
    effective_start = max(joined_at, month_start)

    course_price = Decimal(str(gs.group.course.price)) if gs.group.course else Decimal('0')

    lessons = Lesson.objects.filter(
        group=gs.group,
        date__gte=month_start,
        date__lte=end_date,
    ).order_by('date')

    attendance_data = []
    for lesson in lessons:
        att = Attendance.objects.filter(lesson=lesson, student=gs.student).first()
        attendance_data.append({
            'lesson_id': str(lesson.id),
            'date':      lesson.date.strftime('%d/%m/%Y'),
            'status':    att.status if att else 'absent',
        })

    calculated_amount = None
    raw_amount        = None
    per_unit          = None
    units_count       = None
    total_units       = None
    unit_label        = None

    if billing_type == 'per_day':
        days_in_month = 30
        days_in_group = (end_date - effective_start).days + 1
        per_unit          = (course_price / days_in_month).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        units_count       = days_in_group
        total_units       = days_in_month
        raw_amount        = per_unit * days_in_group
        calculated_amount = (raw_amount / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000
        unit_label        = 'day'

    elif billing_type == 'per_lesson':
        from dateutil.relativedelta import relativedelta
        import datetime

        # Map Uzbek day abbreviations → Python weekday numbers (Mon=0 … Sun=6)
        DAY_MAP = {
            'du': 0, 'dushanba': 0,
            'se': 1, 'seshanba': 1,
            'ch': 2, 'cho': 2, 'chorshanba': 2,
            'pa': 3, 'payshanba': 3,
            'ju': 4, 'juma': 4,
            'sh': 5, 'sha': 5, 'shanba': 5,
            'ya': 6, 'yakshanba': 6,
        }

        # Parse group schedule: "Du,Se,Ch 16:00" → {0, 1, 2}
        lesson_weekdays: set[int] = set()
        schedule_str = gs.group.schedule or ''
        days_part = schedule_str.split(' ')[0]  # "Du,Se,Ch"
        for abbr in days_part.split(','):
            key = abbr.strip().lower()
            if key in DAY_MAP:
                lesson_weekdays.add(DAY_MAP[key])

        # One full billing cycle: joined_at → joined_at + 1 month
        cycle_start = joined_at
        cycle_end   = cycle_start + relativedelta(months=1)

        # Count lesson days in [cycle_start, cycle_end)
        total_lessons_in_cycle = 0
        if lesson_weekdays:
            d = cycle_start
            while d < cycle_end:
                if d.weekday() in lesson_weekdays:
                    total_lessons_in_cycle += 1
                d += datetime.timedelta(days=1)

        if total_lessons_in_cycle == 0:
            total_lessons_in_cycle = 12  # fallback

        attended = sum(1 for a in attendance_data if a['status'] in ['present', 'late'])

        per_unit          = (course_price / total_lessons_in_cycle).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        units_count       = attended
        total_units       = total_lessons_in_cycle
        raw_amount        = per_unit * attended
        calculated_amount = (raw_amount / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000
        unit_label        = 'lesson'

    return {
        'lessons':           attendance_data,
        'period_start':      effective_start.strftime('%d/%m/%Y'),
        'left_at':           end_date.strftime('%d/%m/%Y'),
        'month_start':       month_start,
        'end_date':          end_date,
        'course_price':      float(course_price),
        'course_name':       gs.group.course.name if gs.group.course else '—',
        'group_name':        gs.group.display_name,
        'student_name':      f"{gs.student.first_name} {gs.student.last_name}",
        'billing_type':      billing_type,
        'raw_amount':        float(raw_amount) if raw_amount is not None else None,
        'calculated_amount': float(calculated_amount) if calculated_amount is not None else None,
        'per_unit':          float(per_unit) if per_unit is not None else None,
        'units_count':       units_count,
        'total_units':       total_units,
        'unit_label':        unit_label,
    }
