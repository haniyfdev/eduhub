# EduHub — Database Models (23 Models)

## Global Rules for All Models

- **Primary key**: `UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
- **Money fields**: Always `DecimalField(max_digits=15, decimal_places=2)` — never `IntegerField`
- **Deletion**: Forbidden. Use `status='archived'` + `archived_at=timezone.now()`
- **Timestamps**: `created_at = DateTimeField(auto_now_add=True)`
- **Multi-tenant**: Every model includes `company_id` FK to `Company` (except `SuperadminLog`)

---

## Model 1: `Company`
**App**: `apps/companies/`
**Table**: `companies`
**Purpose**: Education centers and their branches.

```python
id           = UUIDField(PK)
name         = CharField(max_length=255, NOT NULL)
phone        = CharField(max_length=20, nullable)
address      = CharField(max_length=500, nullable)
branch_of    = ForeignKey('self', nullable, related_name='branches')
              # NULL = main/head center
              # set = this is a branch of that center
description  = TextField(nullable)
status       = CharField(choices=['active','archived'], default='active')
closed_at    = DateTimeField(nullable)
created_at   = DateTimeField(auto_now_add)
```

**Notes**:
- Boss manages the main center AND all its branches
- Manager manages only their assigned branch (`company_id` = branch)
- `branch_of` is a self-referential FK

---

## Model 2: `User`
**App**: `apps/users/`
**Table**: `users`
**Purpose**: All staff who log in to the CRM system.

```python
id            = UUIDField(PK)
company_id    = ForeignKey(Company)
first_name    = CharField(max_length=100, NOT NULL)
last_name     = CharField(max_length=100, NOT NULL)
phone         = CharField(max_length=20, UNIQUE, NOT NULL)  # login username
password      = CharField(max_length=255, NOT NULL)         # hashed
role          = CharField(choices=[
                  'superadmin',  # EduHub owner
                  'boss',        # Education center owner
                  'manager',     # Branch manager
                  'admin',       # Receptionist / staff
                  'teacher',     # Teacher
                  'parent'       # Reserved for future mobile app
                ], NOT NULL)
status        = CharField(choices=['active','archived'], default='active')
closed_at     = DateTimeField(nullable)
created_at    = DateTimeField(auto_now_add)
```

**Notes**:
- `phone` is the `USERNAME_FIELD` (used for login, not email)
- `superadmin` is created via Django management command
- `parent` role is reserved — no permissions implemented yet
- Use `AbstractBaseUser` for custom User model

---

## Model 3: `Teacher`
**App**: `apps/teachers/`
**Table**: `teachers`
**Purpose**: Teacher profile linked to a User account.

```python
id               = UUIDField(PK)
user_id          = OneToOneField(User)         # login via User
company_id       = ForeignKey(Company)
salary_type      = CharField(choices=[
                     'fixed',       # flat monthly amount
                     'percent',     # % of group revenue
                     'per_student'  # amount × student count
                   ], NOT NULL)
fixed_amount     = DecimalField(nullable)      # used when salary_type='fixed'
salary_percent   = DecimalField(nullable)      # used when salary_type='percent', e.g. 40.00 = 40%
per_student_amt  = DecimalField(nullable)      # used when salary_type='per_student'
kpi_bonus        = DecimalField(nullable)      # optional monthly bonus
status           = CharField(choices=['active','archived'], default='active')
hired_at         = DateField(NOT NULL)
archived_at      = DateTimeField(nullable)
created_at       = DateTimeField(auto_now_add)
```

**Salary type rules**:
- `fixed`: Teacher receives `fixed_amount` every month. No relation to students or payments.
- `percent`: Teacher receives `salary_percent`% of total course price × ALL students in their groups. **Whether students paid is completely irrelevant.** The obligation is on the student, not the teacher.
- `per_student`: Teacher receives `per_student_amt × active_student_count`. Again, payment status is irrelevant.

**Notes**:
- `first_name`, `last_name`, `phone` are read from the linked `User` record
- `all_students` count is **annotated at query time**, not stored
- Only `boss` or `manager` can edit salary fields

---

## Model 4: `Student`
**App**: `apps/students/`
**Table**: `students`
**Purpose**: Student profiles.

```python
id                = UUIDField(PK)
company_id        = ForeignKey(Company)
first_name        = CharField(max_length=100, NOT NULL)
last_name         = CharField(max_length=100, NOT NULL)
phone             = CharField(max_length=20, nullable)
second_phone      = CharField(max_length=20, nullable)   # parent or backup
course_id         = ForeignKey(Course, nullable)          # intended course (used when pending)
referral_source   = CharField(nullable, choices=[
                      'banner',
                      'friend',
                      'parent',
                      'social_media',
                      'other'
                    ])
status            = CharField(choices=[
                      'pending',   # registered, waiting for group
                      'active',    # in a group, studying
                      'trial',     # attending trial class
                      'archived'   # left or finished
                    ], default='pending')
created_at        = DateTimeField(auto_now_add)
archived_at       = DateTimeField(nullable)
```

**Status flow**:
```
pending → student walks in, admin registers them, course_id set
trial   → attending a trial class before committing
active  → assigned to a group via GroupStudent
archived → left or finished studying
```

**Notes**:
- `balance` field does not exist — debt is tracked via the `Debt` model
- `course_id` helps admin filter pending students by intended course
- Admin workflow: student walks in → registered as `pending` → assigned to group → becomes `active`

---

## Model 5: `Group`
**App**: `apps/groups/`
**Table**: `groups`
**Purpose**: A course group with a teacher and students.

```python
id            = UUIDField(PK)
company_id    = ForeignKey(Company)
course_id     = ForeignKey(Course)
teacher_id    = ForeignKey(Teacher)
number        = PositiveIntegerField(NOT NULL)    # auto-incremented per company
gender_type   = CharField(choices=[
                  'a',  # male students
                  'b',  # female students
                  'c'   # mixed
                ], NOT NULL)
room          = CharField(nullable)
status        = CharField(choices=['active','archived'], default='active')
created_at    = DateTimeField(auto_now_add)
archived_at   = DateTimeField(nullable)
```

**Group display name**: `f"{number}{gender_type}"` → `"1a"`, `"2b"`, `"3c"`

**Notes**:
- `gender_type` is **required** — raise `ValidationError` if missing
- `number` is auto-incremented within each company (not globally)
- Group name is never typed by user — always auto-generated
- Groups are never deleted, only archived

---

## Model 6: `GroupStudent`
**App**: `apps/groups/`
**Table**: `group_students`
**Purpose**: Records which student is in which group, with full history.

```python
id          = UUIDField(PK)
student_id  = ForeignKey(Student)
group_id    = ForeignKey(Group)
joined_at   = DateTimeField(NOT NULL)
left_at     = DateTimeField(nullable)   # NULL = currently active in this group
```

**Notes**:
- `joined_at` and `left_at` belong to this **relationship**, not to the student or group
- `left_at = NULL` means the student is currently in this group
- When a student moves groups: set `left_at = now()` on old record, create new record
- A student can be in multiple groups simultaneously (different courses)
- This is the **source of truth** for student group history

---

## Model 7: `Course`
**App**: `apps/courses/`
**Table**: `courses`
**Purpose**: Course catalog — what subjects does this center teach?

```python
id               = UUIDField(PK)
company_id       = ForeignKey(Company)
teacher_id       = ForeignKey(Teacher, nullable)   # lead/main teacher
name             = CharField(max_length=255, NOT NULL)
description      = TextField(nullable)
price            = DecimalField(NOT NULL)           # monthly fee
duration_months  = IntegerField(NOT NULL)
duration_hours   = IntegerField(NOT NULL)           # total course hours
status           = CharField(choices=['active','archived'], default='active')
created_at       = DateTimeField(auto_now_add)
closed_at        = DateTimeField(nullable)
```

**Notes**:
- `price` is the base price; discounts are applied at payment time
- Price changes do NOT affect historical payments (payments store frozen amount)
- Only `boss` or `manager` can change `price`

---

## Model 8: `Lesson`
**App**: `apps/lessons/`
**Table**: `lessons`
**Purpose**: Individual class sessions taught by a teacher.

```python
id          = UUIDField(PK)
group_id    = ForeignKey(Group)
teacher_id  = ForeignKey(Teacher)   # stored for direct responsibility
topic       = CharField(max_length=255, NOT NULL)
date        = DateField(NOT NULL)
note        = TextField(nullable)
created_at  = DateTimeField(auto_now_add)
```

**Notes**:
- `start_time` and `duration_min` are **not included** (not needed)
- Only the teacher can create/edit lessons for their own groups
- `attendance` and `grades` are both linked to `lesson_id`
- Auto-creates a `TeacherWorkLog` entry when saved

---

## Model 9: `Attendance`
**App**: `apps/attendance/`
**Table**: `attendance`
**Purpose**: Per-student attendance record for each lesson.

```python
id          = UUIDField(PK)
lesson_id   = ForeignKey(Lesson)
student_id  = ForeignKey(Student)
status      = CharField(choices=['present','absent','late'], NOT NULL)
note        = TextField(nullable)
```

**Notes**:
- "Who marked attendance" → use `lesson.teacher_id` (no redundant FK)
- `note` is important — teacher explains absences, tardiness, etc.
- Submitted in bulk: teacher sends attendance for all students at once

---

## Model 10: `Grade`
**App**: `apps/grades/`
**Table**: `grades`
**Purpose**: Per-student grade for each lesson.

```python
id          = UUIDField(PK)
lesson_id   = ForeignKey(Lesson)
student_id  = ForeignKey(Student)
score       = DecimalField(max_digits=5, decimal_places=2, NOT NULL)   # 0–100
note        = TextField(nullable)
created_at  = DateTimeField(auto_now_add)
```

**Notes**:
- `type` field is **not included** (one lesson can have multiple grade types — too abstract)
- "Who graded" → use `lesson.teacher_id` (no redundant FK)
- Multiple grades per student per lesson are allowed

---

## Model 11: `Payment`
**App**: `apps/payments/`
**Table**: `payments`
**Purpose**: Immutable financial log of every payment made.

```python
id            = UUIDField(PK)
company_id    = ForeignKey(Company)
student_id    = ForeignKey(Student)
group_id      = ForeignKey(Group)
course_id     = ForeignKey(Course)
discount_id   = ForeignKey(Discount, nullable)
amount        = DecimalField(NOT NULL)      # FROZEN — final amount after discount
payment_type  = CharField(choices=['cash','card','transfer'], NOT NULL)
note          = TextField(nullable)
paid_at       = DateTimeField(NOT NULL)
```

**IMMUTABILITY RULE**:
- `PATCH` and `DELETE` are **forbidden** on payments
- To correct a mistake:
  1. Create reversal: new `Payment` with `amount = -original_amount`
  2. Create correct: new `Payment` with right amount
  3. Both entries auto-logged via `AuditLog` with mandatory description
- This is standard financial record-keeping practice

---

## Model 12: `Debt`
**App**: `apps/debts/`
**Table**: `debts`
**Purpose**: Real-time debt status per student (mutable — updated as payments come in).

```python
id          = UUIDField(PK)
company_id  = ForeignKey(Company)
student_id  = OneToOneField(Student)
amount      = DecimalField(NOT NULL)    # current outstanding debt
due_date    = DateField(NOT NULL)       # payment deadline
status      = CharField(choices=['unpaid','partial','paid','overdue'])
updated_at  = DateTimeField(auto_now)
```

**Status logic**:
- `unpaid` → debt created, nothing paid yet
- `partial` → some payment made, balance remains
- `paid` → fully settled
- `overdue` → `due_date` has passed and status is still `unpaid` or `partial` → triggers SMS

**Notes**:
- `PATCH` is allowed on `Debt` (it is a real-time status record, not a financial log)
- Updated automatically after every payment is recorded
- Celery task runs daily to detect and mark overdue debts

---

## Model 13: `TeacherSalary`
**App**: `apps/salaries/`
**Table**: `teacher_salaries`
**Purpose**: Monthly salary record per teacher.

```python
id            = UUIDField(PK)
company_id    = ForeignKey(Company)
teacher_id    = ForeignKey(Teacher)
month         = DateField(NOT NULL)          # always first day: 2026-01-01
base_amount   = DecimalField(NOT NULL)
kpi_amount    = DecimalField(default=0)
total_amount  = DecimalField(NOT NULL)       # base + kpi
paid_at       = DateTimeField(nullable)
note          = TextField(nullable)
created_at    = DateTimeField(auto_now_add)
```

**Notes**:
- One record per teacher per month
- Calculated automatically by Celery on each company's billing date
- After creation → auto-creates mirror in `Expense` (`category='teacher_salary'`, `source='auto'`)
- `boss`/`manager` can manually add `kpi_amount`

---

## Model 14: `TeacherWorkLog`
**App**: `apps/salaries/`
**Table**: `teacher_work_logs`
**Purpose**: Per-lesson work log used for salary calculation.

```python
id              = UUIDField(PK)
company_id      = ForeignKey(Company)
teacher_id      = ForeignKey(Teacher)
lesson_id       = ForeignKey(Lesson)
hours           = DecimalField(nullable)     # NULL if center uses percent/per_student
students_count  = IntegerField(NOT NULL)
logged_at       = DateTimeField(auto_now_add)
```

**Notes**:
- `hours` is nullable — only relevant when `salary_type='fixed'` (hourly variant)
- `students_count` is always recorded (used for `per_student` salary type)
- Auto-created via Django signal when a `Lesson` is saved

---

## Model 15: `Notification`
**App**: `apps/notifications/`
**Table**: `notifications`
**Purpose**: Log of every SMS or call attempt.

```python
id               = UUIDField(PK)
company_id       = ForeignKey(Company)
recipient_phone  = CharField(max_length=20, NOT NULL)
message          = TextField(NOT NULL)
type             = CharField(choices=['sms','call'], NOT NULL)
status           = CharField(choices=['pending','sent','failed'], default='pending')
sent_at          = DateTimeField(nullable)
created_at       = DateTimeField(auto_now_add)
```

**Notes**:
- Push notifications are **not included** (web-only app; mobile is future phase)
- All SMS are sent asynchronously via Celery — never in a view
- Every attempt is logged here regardless of success or failure

---

## Model 16: `AuditLog`
**App**: `apps/audit/`
**Table**: `audit_logs`
**Purpose**: Complete change history — who changed what, when, and why.

```python
id           = UUIDField(PK)
company_id   = ForeignKey(Company, nullable)   # NULL for superadmin actions
user_id      = ForeignKey(User)
action       = CharField(choices=['created','updated','deleted'], NOT NULL)
model_name   = CharField(max_length=100, NOT NULL)   # e.g. "Student", "Payment"
object_id    = UUIDField(NOT NULL)                   # PK of the changed record
old_data     = JSONField(nullable)                   # snapshot before change
new_data     = JSONField(nullable)                   # snapshot after change
description  = CharField(max_length=500, NOT NULL)   # user must explain — never nullable
created_at   = DateTimeField(auto_now_add)
```

**Notes**:
- Written automatically via **Django signals** (`pre_save` / `post_save`) — never written manually in views
- `description` is `NOT NULL` — the UI must require a reason field before saving any edit
- `model_name` = Django model class name (e.g. `"Student"`, `"Payment"`)
- `object_id` = UUID of the changed record

---

## Model 17: `Subscription`
**App**: `apps/subscriptions/`
**Table**: `subscriptions`
**Purpose**: EduHub billing subscription per education center.

```python
id               = UUIDField(PK)
company_id       = ForeignKey(Company)
plan             = CharField(choices=['basic','pro','enterprise'])
billing_type     = CharField(choices=['per_student','flat'])
price_per_unit   = DecimalField(NOT NULL)
                   # basic: 1000 UZS per student per month
                   # pro: 1,000,000 UZS flat per quarter
interval         = CharField(choices=['monthly','quarterly','yearly'])
students_count   = IntegerField(nullable)     # basic only — updated on billing date
amount_billed    = DecimalField(nullable)     # final calculated amount
started_at       = DateField(NOT NULL)
expires_at       = DateField(NOT NULL)
status           = CharField(choices=['active','expired','cancelled'])
```

**Billing cycle rule**:
- Billing runs **30 days after `started_at`**, then every 30/90/365 days
- NOT on the 1st of every month — each company has its own cycle
- Celery checks daily: `if today == next_billing_date → bill this company`
- `next_billing_date = started_at + (30 * cycle_count)` days

**Plan change**:
- Old subscription → `status='cancelled'`
- New subscription → new record with `status='active'`

---

## Model 18: `SmsTemplate`
**App**: `apps/notifications/`
**Table**: `sms_templates`
**Purpose**: Reusable SMS templates with placeholders.

```python
id          = UUIDField(PK)
company_id  = ForeignKey(Company)
name        = CharField(max_length=255, NOT NULL)
body        = TextField(NOT NULL)
             # Supported placeholders:
             # {student_name}, {amount}, {due_date},
             # {group_name}, {course_name}
type        = CharField(choices=['debt','welcome','reminder','custom'])
created_at  = DateTimeField(auto_now_add)
```

**Notes**:
- `boss`/`manager` can edit templates through the UI — no coding needed
- Placeholders are replaced at send time in the backend

---

## Model 19: `StudentNote`
**App**: `apps/notes/`
**Table**: `student_notes`
**Purpose**: Internal staff notes about a student.

```python
id          = UUIDField(PK)
student_id  = ForeignKey(Student)
author_id   = ForeignKey(User)
note        = TextField(NOT NULL)
created_at  = DateTimeField(auto_now_add)
```

**Notes**:
- Students never see these notes
- Multiple notes per student allowed
- Used for admin/teacher communication about a student

---

## Model 20: `Discount`
**App**: `apps/discounts/`
**Table**: `discounts`
**Purpose**: Discount rules defined per company (optionally per course).

```python
id          = UUIDField(PK)
company_id  = ForeignKey(Company)
course_id   = ForeignKey(Course, nullable)   # NULL = applies to all courses
name        = CharField(max_length=255, NOT NULL)
type        = CharField(choices=['percent','fixed'])
value       = DecimalField(NOT NULL)
             # percent: 10.00 = 10%
             # fixed: 50000 = 50,000 UZS deducted
condition   = TextField(nullable)            # human-readable explanation
status      = CharField(choices=['active','archived'], default='active')
created_at  = DateTimeField(auto_now_add)
```

**Notes**:
- Each company manages its own discounts independently — no cross-company leakage
- `discount_id` is stored in `Payment` for historical reference
- `boss`/`admin` applies discount when recording a payment

---

## Model 21: `Award`
**App**: `apps/awards/`
**Table**: `awards`
**Purpose**: Certificates and achievements issued to students.

```python
id          = UUIDField(PK)
company_id  = ForeignKey(Company)
title       = CharField(max_length=255, NOT NULL)
description = TextField(nullable)
image_url   = CharField(max_length=500, nullable)
issued_to   = ForeignKey(Student)
issued_at   = DateField(NOT NULL)
created_at  = DateTimeField(auto_now_add)
```

---

## Model 22: `StaffSalary`
**App**: `apps/salaries/`
**Table**: `staff_salaries`
**Purpose**: Monthly salary records for non-teacher staff (admins, receptionists, assistants, managers).

```python
id          = UUIDField(PK)
company_id  = ForeignKey(Company)
user_id     = ForeignKey(User)
month       = DateField(NOT NULL)       # first day of month: 2026-01-01
amount      = DecimalField(NOT NULL)
paid_at     = DateTimeField(nullable)
note        = TextField(nullable)
created_at  = DateTimeField(auto_now_add)
```

**Notes**:
- After creation → auto-creates mirror in `Expense` (`category='staff_salary'`, `source='auto'`)
- Entered manually by `boss`/`manager` each month
- Covers all non-teacher staff

---

## Model 23: `Expense`
**App**: `apps/expenses/`
**Table**: `expenses`
**Purpose**: All company expenses — automatic (salary mirrors) and manual (rent, utilities, etc.). This is the foundation of the P&L dashboard.

```python
id            = UUIDField(PK)
company_id    = ForeignKey(Company)
category      = CharField(choices=[
                  'rent',
                  'utility',
                  'tax',
                  'fine',
                  'discount',
                  'teacher_salary',
                  'staff_salary',
                  'other'
                ], NOT NULL)
source        = CharField(choices=['auto','manual'], NOT NULL)
               # auto = created by system (salary mirrors)
               # manual = entered by boss/manager
amount        = DecimalField(NOT NULL)
description   = CharField(max_length=500, NOT NULL)
expense_date  = DateField(NOT NULL)
reference_id  = UUIDField(nullable)
               # teacher_salary.id or staff_salary.id when source='auto'
created_by    = ForeignKey(User, nullable)   # only for source='manual'
created_at    = DateTimeField(auto_now_add)
```

**Auto-mirror logic**:
```
TeacherSalary saved →
  Expense.objects.create(
    category='teacher_salary',
    source='auto',
    amount=teacher_salary.total_amount,
    reference_id=teacher_salary.id,
    description=f"Teacher salary: {teacher.user.get_full_name()} — {month}"
  )

StaffSalary saved →
  Expense.objects.create(
    category='staff_salary',
    source='auto',
    amount=staff_salary.amount,
    reference_id=staff_salary.id,
    description=f"Staff salary: {user.get_full_name()} — {month}"
  )
```

**P&L rule**: All 8 expense categories must always appear in the dashboard response, even when their value is `0`. This lets `boss` see empty slots and fill them in manually.

---

---

## Model 24: `CompanySettings`
**App**: `apps/companies/`
**Table**: `company_settings`
**Purpose**: Per-company configuration for billing, attendance, and salary policies.

```python
id                           = UUIDField(PK)
company                      = OneToOneField(Company, related_name='settings')
billing_type                 = CharField(choices=[
                                 'monthly',    # full course price monthly (default)
                                 'per_lesson', # (course.price / 20) × lessons_attended
                                 'upfront',    # course.price × duration_months, charged once at enrollment
                               ], default='monthly')
absent_policy                = CharField(choices=[
                                 'ignore',    # no financial effect (default)
                                 'deduct',    # subtract lesson_price from student debt on absence
                                 'penalty',   # add 5% of lesson_price to student debt on absence
                               ], default='ignore')
teacher_contract_break_policy = CharField(choices=[
                                 'full',      # pay full salary even if teacher archived this month (default)
                                 'prorate',   # pay days_worked / 30 × salary
                                 'none',      # no salary if teacher archived this month
                               ], default='full')
created_at                   = DateTimeField(auto_now_add)
updated_at                   = DateTimeField(auto_now)
```

**Notes**:
- Created on demand via `GET/PATCH /api/v1/company-settings/my/` (auto-created with defaults if missing)
- `billing_type` is consumed by `assign_monthly_debts` Celery task
- `absent_policy` is consumed by the `Attendance` post_save signal (`apps/attendance/signals.py`)
- `teacher_contract_break_policy` is consumed by `calculate_teacher_salary` in `apps/salaries/logic.py`
- Only `boss` and `manager` can access; superadmin uses the detail endpoint by ID

---

## Model 25: `StaffKpiRule`
**App**: `apps/salaries/`
**Table**: `staff_kpi_rules`
**Purpose**: KPI bonus rules for non-teacher staff. Defines metrics, thresholds, and bonus amounts per company.

```python
id           = UUIDField(PK)
company_id   = ForeignKey(Company)
name         = CharField(max_length=255, NOT NULL)
role         = CharField(choices=['admin', 'manager', 'any'], NOT NULL)
metric       = CharField(choices=[
                 'attendance_rate',    # student attendance % tracked by this staff
                 'payment_collected',  # total payment amount collected
                 'student_enrolled',   # number of new students enrolled
               ], NOT NULL)
threshold    = DecimalField(NOT NULL)   # min value to earn the bonus
bonus_amount = DecimalField(NOT NULL)   # flat bonus paid when threshold is met
status       = CharField(choices=['active','archived'], default='active')
archived_at  = DateTimeField(nullable)
created_at   = DateTimeField(auto_now_add)
```

**Notes**:
- Only `boss`/`manager` can create, update, or archive rules
- Archived rules are hidden from list view but preserved (Rule 1 — never delete)
- `StaffSalary.kpi_amount` stores the earned KPI bonus for a given month
- `GET/POST /api/v1/staff-kpi-rules/`, `PATCH /api/v1/staff-kpi-rules/{id}/`

---

## Model Relationships Summary

```
Company ── CompanySettings
  ├── User ──────────────────── Teacher
  │                                ├── TeacherSalary ──► Expense (auto)
  │                                └── TeacherWorkLog
  ├── Course ──────── Group ──── Lesson
  │                     │           ├── Attendance ──► [absent_policy signal]
  │                     │           └── Grade
  ├── Student ── GroupStudent ──┘
  │     ├── Payment ──── Discount
  │     ├── Debt
  │     ├── StudentNote
  │     └── Award
  ├── StaffSalary ─────────────► Expense (auto)
  ├── StaffKpiRule
  ├── Expense (manual: rent, utility, tax...)
  ├── Notification ── SmsTemplate
  ├── AuditLog
  └── Subscription
```
