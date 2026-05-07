# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commands

```bash
# Activate virtualenv (Windows)
venv\Scripts\activate

# Dev server
python manage.py runserver

# Migrations
python manage.py makemigrations
python manage.py migrate

# Run all tests
venv\Scripts\python -m pytest tests/ -q

# Run a single test file
venv\Scripts\python -m pytest tests/test_payments.py -v

# Run a single test by name
venv\Scripts\python -m pytest tests/ -k "test_payment_discount" -v

# Force DB rebuild (schema changed)
venv\Scripts\python -m pytest tests/ --create-db -q

# Django shell
python manage.py shell
```

Settings module is `config.settings.local` (set in `pytest.ini` and `manage.py`).

---

## Architecture

### Project Layout

```
apps/           — one Django app per domain (companies, users, teachers, students,
                  groups, courses, lessons, payments, debts, discounts, expenses,
                  salaries, notifications, audit, awards, subscriptions, superadmin_panel)
config/         — settings (base/local/production), urls.py, api_router.py, celery.py
utils/          — shared code: permissions.py, mixins.py
tests/          — flat pytest suite, one file per domain
docs/           — MODELS.md (all 23 models), RULES.md (12 hard rules), ARCHITECTURE.md, etc.
```

### URL Structure

| Prefix | Purpose |
|---|---|
| `/api/auth/` | Login, refresh, logout |
| `/api/v1/` | All business endpoints (see `config/api_router.py`) |
| `/api/superadmin/` | Superadmin panel (no version, internal only) |

### Multi-Tenancy (Rule 2)

Every ViewSet filters by `company_id`. Use `CompanyFilterMixin` from `utils/mixins.py`:

```python
class MyViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = MyModel.objects.all()
```

`CompanyFilterMixin.get_queryset()` — returns `qs.filter(company_id=user.company_id)` unless `role == 'superadmin'`.  
`CompanyFilterMixin.get_object()` — raises `PermissionDenied` if `obj.company_id != user.company_id` (skips check when model has no direct `company_id` FK, e.g. `Lesson`, `Attendance`).

### Permission Classes (`utils/permissions.py`)

```python
IsSuperAdmin              # role == 'superadmin'
IsBossOrManager           # role in ['boss', 'manager']   ← Rule 4: never check boss alone
IsBossManagerOrAdmin      # role in ['boss', 'manager', 'admin']
IsTeacher                 # role == 'teacher'
IsSameCompany             # obj.company_id == user.company_id (object-level)
IsTeacherOfGroup          # obj.teacher_id == user.teacher.id (object-level)
IsSuperAdminOrBossOrManager
```

DRF `|` operator works on **classes**, not instances:

```python
# CORRECT
return [(IsSuperAdmin | IsBossOrManager)()]
# WRONG — raises TypeError
return [IsSuperAdmin() | IsBossOrManager()]
```

### Models

All models inherit `BaseModel` (`apps/base.py`) — UUID primary key via `uuid.uuid4`.

Archivable models have `status = CharField(choices=['active','archived'])` and `archived_at`. Use `ArchiveMixin` from `utils/mixins.py` for the POST `/{pk}/archive/` action. Never call `.delete()` on archivable models.

**Exceptions** (can be deleted normally): `SmsTemplate`, `Award`.

All monetary fields: `DecimalField(max_digits=15, decimal_places=2)` — never `IntegerField`.

### Payments (Rule 3)

`Payment` is immutable. `http_method_names = ['get', 'post', 'head', 'options']` — no PATCH/PUT/DELETE. Corrections via reversal + new payment.

### Salary → Expense Signal (Rule 10)

`apps/salaries/signals.py` — `post_save` on `TeacherSalary` and `StaffSalary` automatically creates a mirroring `Expense` record (`category='teacher_salary'`/`'staff_salary'`, `source='auto'`). Only on `created=True`. Never create these manually.

### Celery

`config/celery.py` — two periodic tasks:
- `assign_monthly_debts` — fires daily; creates debts per company based on billing cycle (every 30 days from `subscription.started_at`, Rule 11)
- `mark_overdue_debts` — fires daily; sets `Debt.status='overdue'` when past due date

`CELERY_TASK_ALWAYS_EAGER = True` in `local.py` — tasks run synchronously in tests/dev.

### Audit Logs (Rule 5)

Written by Django signals only — never `AuditLog.objects.create()` in views. `description` field is NOT NULL; sensitive PATCH/POST requests must include a `description` in the request body (validated in serializer).

### SMS (Rule 6)

Never call the Eskiz API directly. Always: `send_sms_task.delay(company_id=..., phone=..., message=...)`. Every attempt is logged in `Notification`.

### Group Names (Rule 8)

Group `name` is auto-generated as `f"{number}{gender_type}"` (e.g. `"1a"`). Never expose a `name` input in the API; `number` auto-increments per company.

### Teacher Salary Calculation (Rule 9)

`apps/salaries/logic.py` — for `percent` and `per_student` types, use active student count × course price. Never use the `Payment` table.

### P&L Dashboard

`GET /api/v1/profit-loss/?month=YYYY-MM` — response always includes all 8 expense categories in `expenses.breakdown` even if zero: `rent`, `utility`, `tax`, `fine`, `discount`, `teacher_salary`, `staff_salary`, `other`.

### Database

Supabase PostgreSQL via **session pooler** (IPv4). Direct connection URL is IPv6-only on the free tier — always use the pooler URL in `.env`.

`--reuse-db` in `pytest.ini` prevents the `test_postgres` teardown from blocking (Supabase pooler holds a connection). Use `--create-db` to force a full rebuild when schema changes.

---

## Key Rules Summary (read `docs/RULES.md` for full details)

| # | Rule |
|---|------|
| 1 | Never delete — archive instead (`status='archived'`, `archived_at`) |
| 2 | Every ViewSet filters by `company_id` |
| 3 | Payments are immutable (no PATCH/DELETE) |
| 4 | `boss` always means `['boss', 'manager']` |
| 5 | Audit logs via signals only |
| 6 | SMS always async via Celery |
| 7 | All money fields are `DecimalField(max_digits=15, decimal_places=2)` |
| 8 | Group name is auto-generated, never user-supplied |
| 9 | Teacher salary uses student count, not payment records |
| 10 | Salary records auto-mirror to Expense via `post_save` signal |
| 11 | Billing is per-company, every 30 days from subscription start |
| 12 | Supabase RLS must be disabled; all access control in Django |
