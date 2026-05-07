# EduHub — Business Logic

This file describes all non-trivial business rules that must be implemented exactly as specified. Read this carefully before writing any view, serializer, or task.

---

## 1. Payment Flow

**Triggered by**: `POST /api/v1/payments/`

```
Step 1 — Validate ownership
  Confirm student, group, and course all belong to the same company.
  Raise 400 if mismatch.

Step 2 — Apply discount (if discount_id provided)
  discount = Discount.objects.get(id=discount_id, company=company)

  if discount.type == 'percent':
      final_amount = requested_amount * (1 - discount.value / 100)
  elif discount.type == 'fixed':
      final_amount = requested_amount - discount.value

  final_amount must never be negative — raise 400 if it would be.

Step 3 — Create Payment record
  Payment.objects.create(
      student=student,
      group=group,
      course=course,
      discount=discount or None,
      amount=final_amount,        # FROZEN at this value forever
      payment_type=payment_type,
      paid_at=now(),
  )

Step 4 — Update Debt
  debt = Debt.objects.get(student=student)
  debt.amount -= final_amount

  if debt.amount <= 0:
      debt.status = 'paid'
      debt.amount = 0
  elif debt.amount < original_debt_amount:
      debt.status = 'partial'

  debt.save()

Step 5 — Send confirmation SMS (async)
  send_payment_confirmation_sms.delay(student.id, final_amount)
  # Never send SMS synchronously

Step 6 — Audit log
  Written automatically via Django signal — do not write manually
```

---

## 2. Payment Correction (Reversal)

Payments are immutable. To fix a mistake:

```
Step 1 — Create reversal payment
  Payment.objects.create(
      student=student,
      group=group,
      course=course,
      amount=-original_amount,    # negative
      payment_type=original_payment_type,
      note="Reversal: [reason]",
      paid_at=now(),
  )

Step 2 — Create correct payment
  Payment.objects.create(
      ...
      amount=correct_amount,
      note="Correction: [reason]",
      paid_at=now(),
  )

Step 3 — Debt is recalculated automatically via signal
Step 4 — Both entries appear in audit_logs with mandatory description
```

---

## 3. Monthly Debt Assignment

**Triggered by**: Celery task on each company's billing date

```python
def assign_monthly_debts(company):
    # Get all students currently in active groups
    active_enrollments = GroupStudent.objects.filter(
        group__company=company,
        group__status='active',
        left_at__isnull=True       # currently enrolled
    ).select_related('student', 'group__course')

    for enrollment in active_enrollments:
        course_price = enrollment.group.course.price

        # Check for applicable discount
        discount = Discount.objects.filter(
            company=company,
            status='active'
        ).filter(
            Q(course=enrollment.group.course) | Q(course__isnull=True)
        ).order_by('-course').first()   # course-specific takes priority

        if discount:
            if discount.type == 'percent':
                final_price = course_price * (1 - discount.value / 100)
            else:
                final_price = course_price - discount.value
        else:
            final_price = course_price

        # Update or create debt record
        debt, created = Debt.objects.get_or_create(
            student=enrollment.student,
            company=company,
            defaults={'amount': 0, 'status': 'unpaid'}
        )
        debt.amount += final_price
        debt.due_date = billing_date + timedelta(days=15)
        debt.status = 'unpaid'
        debt.save()
```

---

## 4. Overdue Detection

**Triggered by**: Celery task, daily at 09:00

```python
def check_overdue_debts():
    today = date.today()
    Debt.objects.filter(
        due_date__lt=today,
        status__in=['unpaid', 'partial']
    ).update(status='overdue')

    # Trigger SMS for newly overdue debts
    overdue_debts = Debt.objects.filter(status='overdue')
    for debt in overdue_debts:
        send_debt_sms.delay(debt.student_id)
```

---

## 5. Teacher Salary Calculation

**Triggered by**: Celery task on company's billing date

```python
def calculate_teacher_salary(teacher, month, company):

    if teacher.salary_type == 'fixed':
        base_amount = teacher.fixed_amount
        # No relation to students or payments

    elif teacher.salary_type == 'percent':
        # Count ALL active students in teacher's groups this month
        student_count = GroupStudent.objects.filter(
            group__teacher=teacher,
            group__status='active',
            left_at__isnull=True
        ).count()

        # Get monthly course price for these students
        # Use the course price — whether students actually paid is IRRELEVANT
        total_course_revenue_due = sum(
            gs.group.course.price
            for gs in GroupStudent.objects.filter(
                group__teacher=teacher,
                group__status='active',
                left_at__isnull=True
            ).select_related('group__course')
        )

        base_amount = total_course_revenue_due * (teacher.salary_percent / 100)

    elif teacher.salary_type == 'per_student':
        student_count = GroupStudent.objects.filter(
            group__teacher=teacher,
            group__status='active',
            left_at__isnull=True
        ).count()

        base_amount = student_count * teacher.per_student_amt
        # Whether students paid is IRRELEVANT — teacher always gets paid

    kpi_amount = teacher.kpi_bonus or 0
    total_amount = base_amount + kpi_amount

    salary = TeacherSalary.objects.create(
        teacher=teacher,
        company=company,
        month=month,
        base_amount=base_amount,
        kpi_amount=kpi_amount,
        total_amount=total_amount,
    )

    # Auto-mirror to expenses
    Expense.objects.create(
        company=company,
        category='teacher_salary',
        source='auto',
        amount=total_amount,
        description=f"Teacher salary: {teacher.user.get_full_name()} — {month.strftime('%B %Y')}",
        expense_date=month,
        reference_id=salary.id,
    )
```

---

## 6. Staff Salary Auto-Mirror

**Triggered by**: Django signal on `StaffSalary` save

```python
@receiver(post_save, sender=StaffSalary)
def mirror_staff_salary_to_expenses(sender, instance, created, **kwargs):
    if created:
        Expense.objects.create(
            company=instance.company,
            category='staff_salary',
            source='auto',
            amount=instance.amount,
            description=f"Staff salary: {instance.user.get_full_name()} — {instance.month.strftime('%B %Y')}",
            expense_date=instance.month,
            reference_id=instance.id,
            created_by=None,
        )
```

---

## 7. P&L Calculation

**Used by**: `GET /api/v1/profit-loss/`

```python
def get_profit_loss(company, month):
    # Income: sum of all payments this month
    income = Payment.objects.filter(
        company=company,
        paid_at__year=month.year,
        paid_at__month=month.month
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Expenses: all expense records this month
    all_categories = [
        'rent', 'utility', 'tax', 'fine',
        'discount', 'teacher_salary', 'staff_salary', 'other'
    ]

    expense_data = Expense.objects.filter(
        company=company,
        expense_date__year=month.year,
        expense_date__month=month.month
    ).values('category').annotate(total=Sum('amount'))

    expense_map = {row['category']: row['total'] for row in expense_data}

    # Always return all categories, even if 0
    breakdown = {cat: expense_map.get(cat, Decimal('0')) for cat in all_categories}
    total_expenses = sum(breakdown.values())

    profit = income - total_expenses
    margin = (profit / income * 100) if income > 0 else Decimal('0')

    return {
        'income': income,
        'breakdown': breakdown,
        'total_expenses': total_expenses,
        'profit': profit,
        'margin': f"{margin:.1f}%",
    }
```

---

## 8. Group Name Auto-Generation

```python
def generate_group_number(company):
    last = Group.objects.filter(company=company).order_by('-number').first()
    return (last.number + 1) if last else 1

# In GroupSerializer.create():
number = generate_group_number(company)
group = Group.objects.create(number=number, gender_type=validated_data['gender_type'], ...)

# Display name is computed, not stored:
@property
def display_name(self):
    return f"{self.number}{self.gender_type}"   # "1a", "2b", "3c"
```

---

## 9. Subscription Billing Cycle

```python
def get_next_billing_date(subscription):
    if subscription.interval == 'monthly':
        delta = 30
    elif subscription.interval == 'quarterly':
        delta = 90
    elif subscription.interval == 'yearly':
        delta = 365

    days_since_start = (date.today() - subscription.started_at).days
    cycles_completed = days_since_start // delta
    next_billing = subscription.started_at + timedelta(days=delta * (cycles_completed + 1))
    return next_billing

# Celery checks daily:
def check_subscription_billing():
    for subscription in Subscription.objects.filter(status='active'):
        if date.today() == get_next_billing_date(subscription):
            assign_monthly_debts.delay(subscription.company_id)
            calculate_subscription_fee.delay(subscription.id)
```

**Subscription fee calculation**:
```python
def calculate_subscription_fee(subscription):
    if subscription.billing_type == 'per_student':
        count = Student.objects.filter(
            company=subscription.company,
            status='active'
        ).count()
        subscription.students_count = count
        subscription.amount_billed = count * subscription.price_per_unit

    elif subscription.billing_type == 'flat':
        subscription.amount_billed = subscription.price_per_unit

    subscription.save()
```

---

## 10. Audit Log via Django Signals

```python
# apps/audit/signals.py

AUDITED_MODELS = [Student, Payment, Teacher, Group, Course, Discount, TeacherSalary, StaffSalary]

@receiver(pre_save)
def capture_old_data(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    try:
        instance._pre_save_old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._pre_save_old = None

@receiver(post_save)
def write_audit_log(sender, instance, created, **kwargs):
    if sender not in AUDITED_MODELS:
        return

    old = getattr(instance, '_pre_save_old', None)
    current_user = get_current_user()   # from thread-local middleware

    AuditLog.objects.create(
        company=getattr(instance, 'company', None),
        user=current_user,
        action='created' if created else 'updated',
        model_name=sender.__name__,
        object_id=instance.pk,
        old_data=model_to_dict(old) if old else None,
        new_data=model_to_dict(instance),
        description='',   # UI must prompt user — validated at API level
    )
```

> `description` must be required in the API request body for any mutating endpoint. Validate this in the serializer, not here.
