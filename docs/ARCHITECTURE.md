# EduHub — Architecture & Tech Stack

## What is EduHub?

EduHub is a **B2B SaaS CRM+ERP web application** for education centers (o'quv markazlar) in Uzbekistan. It is a **web-only** application (no mobile app in this phase).

### Core Principles

- **Multi-tenant**: One server hosts many education centers. Every piece of data belongs to a company and is strictly isolated.
- **Nothing is ever deleted**: Records are archived (`status='archived'`), never removed from the database.
- **Immutable financials**: Payment records are frozen. Corrections are made via reversal entries.
- **Async everything**: SMS and heavy tasks always go through Celery. Never block the request cycle.

---

## Tech Stack

### Backend
| Package | Purpose |
|---|---|
| Python (latest) | Primary language |
| Django (latest) | Web framework — ORM, signals, admin |
| Django REST Framework (latest) | RESTful API |
| djangorestframework-simplejwt (latest) | JWT authentication |
| django-filter (latest) | API filtering |
| django-cors-headers (latest) | CORS for Next.js frontend |
| django-celery-beat (latest) | Periodic task scheduling |
| django-redis (latest) | Django cache backend |
| python-decouple (latest) | `.env` environment variables |
| Pillow (latest) | Image handling (awards) |
| gunicorn (latest) | Production WSGI server |
| requests (latest) | HTTP calls (Eskiz SMS API) |
| psycopg2-binary (latest) | PostgreSQL connector |
| celery (latest) | Async task queue |
| redis (latest) | Cache + Celery broker |

### `requirements.txt`
```
Django
djangorestframework
djangorestframework-simplejwt
django-filter
django-cors-headers
django-celery-beat
django-redis
python-decouple
Pillow
gunicorn
requests
psycopg2-binary
celery
redis
```

---

## Deployment

| Service | Provider |
|---|---|
| Backend | Render (Python/Django Web Service) |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js (separate repository) |
| Cache & Broker | Redis (Render Redis or Upstash) |
| SMS | Eskiz.uz API |

### Environment Variables (`.env`)
```
SECRET_KEY=
DEBUG=False
DATABASE_URL=postgresql://...   # from Supabase
REDIS_URL=redis://...
ESKIZ_EMAIL=
ESKIZ_PASSWORD=
ALLOWED_HOSTS=your-app.onrender.com
CORS_ALLOWED_ORIGINS=https://your-nextjs-app.com
```

### Supabase Note
> Disable **Row Level Security (RLS)** on all tables in Supabase.
> Django handles all access control. Connect only via `DATABASE_URL`.

---

## Project Structure

```
eduhub/
├── config/
│   ├── settings/
│   │   ├── base.py           # Shared settings
│   │   ├── local.py          # Development overrides
│   │   └── production.py     # Production overrides
│   ├── urls.py               # Root URL router
│   ├── celery.py             # Celery + Beat configuration
│   └── wsgi.py
│
├── apps/
│   ├── companies/            # Model: Company
│   ├── users/                # Model: User (custom auth)
│   ├── teachers/             # Model: Teacher
│   ├── students/             # Model: Student
│   ├── groups/               # Model: Group, GroupStudent
│   ├── courses/              # Model: Course
│   ├── lessons/              # Model: Lesson
│   ├── attendance/           # Model: Attendance
│   ├── grades/               # Model: Grade
│   ├── payments/             # Model: Payment
│   ├── debts/                # Model: Debt
│   ├── salaries/             # Model: TeacherSalary, StaffSalary, TeacherWorkLog
│   ├── notifications/        # Model: Notification, SmsTemplate
│   ├── audit/                # Model: AuditLog
│   ├── subscriptions/        # Model: Subscription
│   ├── notes/                # Model: StudentNote
│   ├── discounts/            # Model: Discount
│   ├── awards/               # Model: Award
│   ├── expenses/             # Model: Expense
│   └── superadmin_panel/     # Model: SuperadminLog + superadmin endpoints
│
├── utils/
│   ├── permissions.py        # All custom permission classes
│   ├── sms.py                # Eskiz.uz API wrapper
│   ├── pagination.py         # Default pagination config
│   └── mixins.py             # Shared ViewSet mixins
│
├── manage.py
└── requirements.txt
```

---

## API Base URL

All versioned endpoints use the prefix `/api/v1/`.

> **Why versioning?** If a breaking `/api/v2/` is released in the future, existing clients continue working on `/api/v1/` without changes.

Auth endpoints are unversioned: `/api/auth/login/`, `/api/auth/token/refresh/`

---

## Multi-Tenant Rule

This is the single most important architectural rule.

**Every ViewSet must filter by `company_id`:**

```python
def get_queryset(self):
    user = self.request.user
    if user.role == 'superadmin':
        return Model.objects.all()
    return Model.objects.filter(company_id=user.company_id)
```

A user must never be able to see or modify data from another company. This filter must be present in **every** ViewSet without exception.
