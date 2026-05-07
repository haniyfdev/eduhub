# EduHub — Critical Rules for AI Agent

Read this file before writing any code. These rules are non-negotiable. Violating any of them will require a full rewrite.

---

## Rule 1: Never Delete Records

**Forbidden**: `instance.delete()`, `Model.objects.filter(...).delete()`, HTTP `DELETE` method on any core model.

**Correct approach**:
```python
# In the view:
instance.status = 'archived'
instance.archived_at = timezone.now()
instance.save()
```

Every model that can be "removed" must have:
- `status = CharField(choices=['active', 'archived'], default='active')`
- `archived_at = DateTimeField(null=True, blank=True)`

Archive endpoint pattern:
```python
@action(detail=True, methods=['post'])
def archive(self, request, pk=None):
    instance = self.get_object()
    instance.status = 'archived'
    instance.archived_at = timezone.now()
    instance.save()
    return Response({'status': 'archived'})
```

HTTP `DELETE` on archivable models must return `405 Method Not Allowed`.

**Exceptions** (these CAN be deleted): `SmsTemplate`, `Award`

---

## Rule 2: Multi-Tenant Filtering Is Mandatory

Every ViewSet must filter by `company_id`. No exceptions.

```python
def get_queryset(self):
    user = self.request.user
    if user.role == 'superadmin':
        return Model.objects.all()
    return Model.objects.filter(company_id=user.company_id)
```

Also enforce at object level:
```python
def get_object(self):
    obj = super().get_object()
    if self.request.user.role != 'superadmin':
        if obj.company_id != self.request.user.company_id:
            raise PermissionDenied()
    return obj
```

A user must never see, edit, or reference any data outside their own company.

---

## Rule 3: Payments Are Immutable

`PATCH` and `DELETE` on `Payment` records are forbidden.

```python
class PaymentViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'head', 'options']  # no patch, no delete
```

To correct a mistake, create two new payments:
1. Reversal: `amount = -original_amount`
2. Correction: `amount = correct_amount`

Both are logged in `AuditLog`. The history is never broken.

---

## Rule 4: Boss Always Means Boss and Manager

Wherever a permission check says `boss`, it means both `boss` and `manager`.

**Wrong**:
```python
if request.user.role == 'boss':
```

**Correct**:
```python
if request.user.role in ['boss', 'manager']:
```

This applies to every permission class, every view condition, and every inline comment. Never check for `boss` alone.

---

## Rule 5: Audit Log Is Automatic — Never Manual

Audit logs are written by Django signals, not in views.

```python
# WRONG — do not do this in views:
AuditLog.objects.create(...)

# CORRECT — signals handle it automatically
# See BUSINESS_LOGIC.md section 10
```

The `description` field in `AuditLog` is `NOT NULL`. Enforce this at the API level: any `PATCH` or sensitive `POST` request must include a `description` (reason) field in the request body. Validate in the serializer.

---

## Rule 6: SMS Is Always Asynchronous

Never call the Eskiz API in a view or serializer.

**Wrong**:
```python
send_sms(phone, message)  # synchronous — blocks the request
```

**Correct**:
```python
send_sms_task.delay(company_id=..., phone=phone, message=message)
```

Every SMS attempt must be logged in the `Notification` model regardless of success or failure.

---

## Rule 7: All Money Fields Are DecimalField

```python
# WRONG:
amount = models.IntegerField()

# CORRECT:
amount = models.DecimalField(max_digits=15, decimal_places=2)
```

This applies to: `Payment.amount`, `Debt.amount`, `TeacherSalary.total_amount`, `Expense.amount`, `Course.price`, `Discount.value`, `Subscription.price_per_unit`, `Subscription.amount_billed`, and all other monetary fields.

---

## Rule 8: Group Name Is Auto-Generated

Never expose a `name` input field for groups in the API or UI.

The group display name is always: `f"{number}{gender_type}"` → `"1a"`, `"2b"`, `"3c"`

`number` is auto-incremented per company:
```python
def generate_group_number(company):
    last = Group.objects.filter(company=company).order_by('-number').first()
    return (last.number + 1) if last else 1
```

`gender_type` is required. Raise `ValidationError` if missing:
```python
def validate_gender_type(self, value):
    if not value:
        raise serializers.ValidationError("gender_type is required to create a group.")
    return value
```

---

## Rule 9: Teacher Salary Ignores Whether Students Paid

For `percent` and `per_student` salary types, the calculation is based on student **count** and **course price**, not on actual payment records.

```python
# WRONG — do not use payments table for teacher salary:
total_paid = Payment.objects.filter(group__teacher=teacher).aggregate(Sum('amount'))

# CORRECT — use student count × course price:
student_count = GroupStudent.objects.filter(
    group__teacher=teacher, left_at__isnull=True
).count()
```

The teacher's salary obligation is on the education center, not on whether students paid. Always.

---

## Rule 10: Expenses Auto-Mirror Salary Records

When `TeacherSalary` or `StaffSalary` is created, an `Expense` record must be created automatically via Django signal.

```python
@receiver(post_save, sender=TeacherSalary)
def mirror_teacher_salary(sender, instance, created, **kwargs):
    if created:
        Expense.objects.create(
            company=instance.company,
            category='teacher_salary',
            source='auto',
            amount=instance.total_amount,
            description=f"Teacher salary — {instance.month}",
            expense_date=instance.month,
            reference_id=instance.id,
        )
```

Never create this expense manually. Never allow duplicate mirrors.

---

## Rule 11: Billing Is Per-Company, Not Global

Monthly debt and salary calculation is triggered per company based on their own cycle:
- `started_at` = subscription start date
- Billing runs every 30 days from that date (not on the 1st of the month)

Celery checks daily and fires only for companies whose billing date matches today.

```python
days_since_start = (today - subscription.started_at).days
if days_since_start > 0 and days_since_start % 30 == 0:
    assign_monthly_debts.delay(company_id)
```

---

## Rule 12: Supabase — Disable RLS

Supabase's Row Level Security (RLS) must be **disabled** on all tables. Django handles all access control through the permission classes and `get_queryset()` filtering.

Connect to Supabase via `DATABASE_URL` environment variable only. Do not hardcode credentials.

---

## Role Permission Reference

```
superadmin   — everything, everywhere
boss         — own company + all branches (full control)
manager      — own branch only (same permissions as boss within branch)
admin        — students, groups, payments, awards (no salary, no config)
teacher      — only their own groups and lessons
parent       — reserved for future mobile app (no permissions yet)
```

Permission classes to use (defined in `utils/permissions.py`):

```python
IsSuperAdmin           # role == 'superadmin'
IsBossOrManager        # role in ['boss', 'manager']
IsBossManagerOrAdmin   # role in ['boss', 'manager', 'admin']
IsTeacher              # role == 'teacher'
IsSameCompany          # obj.company_id == request.user.company_id
IsTeacherOfGroup       # obj.teacher_id == request.user.teacher.id
```

---

## P&L Dashboard Rule

The P&L response must always include all 8 expense categories, even if their value is `0`:

```python
ALL_EXPENSE_CATEGORIES = [
    'rent', 'utility', 'tax', 'fine',
    'discount', 'teacher_salary', 'staff_salary', 'other'
]

# Always build the full breakdown dict:
breakdown = {cat: expense_map.get(cat, Decimal('0')) for cat in ALL_EXPENSE_CATEGORIES}
```

This is intentional — boss sees empty slots and knows which categories need manual input.

---

## UUID Primary Keys Everywhere

```python
import uuid

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
```

All models inherit from `BaseModel`. Never use `AutoField` or `BigAutoField`.

---

## Phone as Login Field

The `User` model uses `phone` as the login identifier, not `email`.

```python
class User(AbstractBaseUser, PermissionsMixin):
    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['first_name', 'last_name']
```

---

## API Versioning

All business endpoints use `/api/v1/` prefix.
Auth endpoints do not: `/api/auth/login/`, `/api/auth/token/refresh/`
Superadmin panel uses `/api/superadmin/` prefix (no version — internal only).
