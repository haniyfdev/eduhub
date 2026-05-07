# EduHub — API Endpoints

## Global Rules

- **Base URL**: `/api/v1/` for all versioned endpoints
- **Auth header**: `Authorization: Bearer {access_token}` required on all endpoints except `/api/auth/login/`
- **Pagination**: All list endpoints support `?page=1&page_size=20`
- **Filtering**: All list endpoints support relevant filters (see per-endpoint notes)
- **Archive instead of delete**: Use `POST /{id}/archive/` — never send `DELETE`

---

## Auth Endpoints (no version prefix)

```
POST   /api/auth/login/                Login — returns access + refresh tokens
POST   /api/auth/token/refresh/        Refresh access token
POST   /api/auth/logout/               Logout (blacklist refresh token)
```

**Login request body**:
```json
{ "phone": "+998901234567", "password": "secret" }
```

**Login response**:
```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": {
    "id": "uuid",
    "role": "admin",
    "company_id": "uuid",
    "first_name": "Ali",
    "last_name": "Karimov"
  }
}
```

---

## Companies

```
GET    /api/v1/companies/              List all companies (superadmin only)
POST   /api/v1/companies/              Create company (superadmin only)
GET    /api/v1/companies/{id}/         Detail
PATCH  /api/v1/companies/{id}/         Update (superadmin, boss)
POST   /api/v1/companies/{id}/archive/ Archive (superadmin only)
```

---

## Users

```
GET    /api/v1/users/                  List staff in company (boss, manager)
POST   /api/v1/users/                  Create staff user (boss, manager)
GET    /api/v1/users/{id}/             Detail
PATCH  /api/v1/users/{id}/             Update
POST   /api/v1/users/{id}/archive/     Archive
```

---

## Teachers

```
GET    /api/v1/teachers/                        List (filter: status)
POST   /api/v1/teachers/                        Create (boss, manager)
GET    /api/v1/teachers/{id}/                   Detail + annotated all_students count
PATCH  /api/v1/teachers/{id}/                   Update basic info
PATCH  /api/v1/teachers/{id}/salary/            Update salary config (boss, manager only)
GET    /api/v1/teachers/{id}/salary-history/    All monthly salary records
POST   /api/v1/teachers/{id}/archive/           Archive
```

---

## Students

```
GET    /api/v1/students/                  List
                                          filters: status, course_id, group_id,
                                                   referral_source
POST   /api/v1/students/                  Create (status defaults to 'pending')
GET    /api/v1/students/{id}/             Full profile
PATCH  /api/v1/students/{id}/             Update
POST   /api/v1/students/{id}/archive/     Archive (sets status='archived')
GET    /api/v1/students/{id}/payments/    Full payment history
GET    /api/v1/students/{id}/debt/        Current debt record
GET    /api/v1/students/{id}/attendance/  Attendance history (filter: date_range)
GET    /api/v1/students/{id}/grades/      Grade history (filter: date_range)
GET    /api/v1/students/{id}/groups/      Group history (via group_students)
GET    /api/v1/students/{id}/notes/       Notes about this student
POST   /api/v1/students/{id}/notes/       Add a note
```

---

## Groups

```
GET    /api/v1/groups/                        List (filter: status, course_id, teacher_id)
POST   /api/v1/groups/                        Create (gender_type required)
GET    /api/v1/groups/{id}/                   Detail + current student list
PATCH  /api/v1/groups/{id}/                   Update
POST   /api/v1/groups/{id}/add-student/       Assign student to this group
POST   /api/v1/groups/{id}/remove-student/    Remove student (sets left_at=now)
POST   /api/v1/groups/{id}/archive/           Archive group
```

**add-student request body**:
```json
{ "student_id": "uuid" }
```

---

## Courses

```
GET    /api/v1/courses/              List (filter: status)
POST   /api/v1/courses/              Create (boss, manager)
GET    /api/v1/courses/{id}/         Detail
PATCH  /api/v1/courses/{id}/         Update (boss, manager)
POST   /api/v1/courses/{id}/archive/ Archive
```

---

## Lessons

```
GET    /api/v1/lessons/                        List (filter: group_id, date, teacher_id)
POST   /api/v1/lessons/                        Create (teacher, boss, manager)
GET    /api/v1/lessons/{id}/                   Detail
PATCH  /api/v1/lessons/{id}/                   Update (teacher of this lesson)
GET    /api/v1/lessons/{id}/attendance/         Get attendance records
POST   /api/v1/lessons/{id}/attendance/         Submit attendance (bulk create)
GET    /api/v1/lessons/{id}/grades/             Get grades
POST   /api/v1/lessons/{id}/grades/             Submit grades (bulk create)
```

**Attendance bulk submit body**:
```json
[
  { "student_id": "uuid", "status": "present", "note": null },
  { "student_id": "uuid", "status": "absent",  "note": "sick" },
  { "student_id": "uuid", "status": "late",    "note": null }
]
```

---

## Payments

```
GET    /api/v1/payments/         List (filter: student_id, month, course_id, payment_type)
POST   /api/v1/payments/         Record a payment
GET    /api/v1/payments/{id}/    Detail
```

> `PATCH` and `DELETE` are **not allowed** on payments.
> To correct a mistake: create a reversal payment with negative amount, then create the correct payment.

---

## Debts

```
GET    /api/v1/debts/                    List (filter: status, due_date)
GET    /api/v1/debts/?status=overdue     Overdue debtors only
PATCH  /api/v1/debts/{id}/               Update debt status manually
POST   /api/v1/debts/{id}/send-sms/      Manually trigger debt reminder SMS
```

---

## Discounts

```
GET    /api/v1/discounts/              List (filter: status, course_id)
POST   /api/v1/discounts/              Create (boss, manager)
PATCH  /api/v1/discounts/{id}/         Update
POST   /api/v1/discounts/{id}/archive/ Archive
```

---

## SMS Templates

```
GET    /api/v1/sms-templates/          List
POST   /api/v1/sms-templates/          Create (boss, manager)
PATCH  /api/v1/sms-templates/{id}/     Update
DELETE /api/v1/sms-templates/{id}/     Delete (templates CAN be deleted)
```

---

## Awards

```
GET    /api/v1/awards/             List (filter: student_id)
POST   /api/v1/awards/             Create
PATCH  /api/v1/awards/{id}/        Update
DELETE /api/v1/awards/{id}/        Delete
```

---

## Expenses

```
GET    /api/v1/expenses/              List (filter: category, month, source)
POST   /api/v1/expenses/              Create manual expense (boss, manager)
GET    /api/v1/expenses/?source=manual   Manual entries only
GET    /api/v1/expenses/?source=auto     Auto-generated salary mirrors only
```

---

## Staff Salaries

```
GET    /api/v1/staff-salaries/             List (filter: month, user_id)
POST   /api/v1/staff-salaries/             Create (boss, manager)
GET    /api/v1/staff-salaries/{id}/        Detail
```

---

## Teacher Salaries

```
GET    /api/v1/teacher-salaries/                   List (filter: month, teacher_id)
GET    /api/v1/teacher-salaries/{id}/              Detail
POST   /api/v1/teacher-salaries/{id}/mark-paid/    Mark salary as paid
```

---

## Audit Logs

```
GET    /api/v1/audit-logs/    List (filter: model_name, user_id, action, date_range)
                              Access: boss, manager, superadmin
```

---

## Notifications

```
GET    /api/v1/notifications/    List sent messages (filter: status, type, date)
```

---

## Subscriptions

```
GET    /api/v1/subscriptions/           Own company subscription history
GET    /api/v1/subscriptions/current/   Active subscription detail
```

---

## Dashboard

```
GET    /api/v1/dashboard/summary/        Key metrics overview
GET    /api/v1/dashboard/revenue/        Monthly revenue chart data (?period=6)
GET    /api/v1/dashboard/debts-summary/  Debt breakdown by status
GET    /api/v1/dashboard/teacher-stats/  Per-teacher statistics
```

**Summary response**:
```json
{
  "total_students": 247,
  "active_students": 230,
  "pending_students": 10,
  "trial_students": 7,
  "total_groups": 18,
  "active_groups": 15,
  "monthly_revenue": 28500000,
  "total_debtors": 34,
  "total_debt_amount": 6800000,
  "teachers_count": 12
}
```

**Revenue response** (`?period=6`):
```json
{
  "labels": ["Dec", "Jan", "Feb", "Mar", "Apr", "May"],
  "data":   [18200000, 22400000, 24100000, 26800000, 27500000, 28500000]
}
```

---

## P&L Dashboard (Boss / Manager only)

```
GET    /api/v1/profit-loss/             P&L for a specific month or year
                                        (?month=2026-05 or ?year=2026)
GET    /api/v1/profit-loss/history/     Monthly P&L history
GET    /api/v1/profit-loss/teachers/    Per-teacher revenue vs salary report
```

**P&L response**:
```json
{
  "period": "2026-05",
  "income": {
    "total": 28500000,
    "breakdown": [
      { "course": "English", "amount": 15000000 },
      { "course": "Python",  "amount": 13500000 }
    ]
  },
  "expenses": {
    "total": 16400000,
    "breakdown": {
      "teacher_salary": 9500000,
      "staff_salary":   2200000,
      "rent":           1800000,
      "utility":         400000,
      "tax":             300000,
      "fine":                 0,
      "discount":        200000,
      "other":                0
    }
  },
  "profit": 12100000,
  "margin": "42.5%"
}
```

> All 8 expense categories always appear in the response, even if their value is `0`.

---

## Superadmin Panel (Superadmin only)

```
GET    /api/superadmin/companies/        All companies with subscription status
GET    /api/superadmin/revenue/          EduHub total revenue per month
GET    /api/superadmin/subscriptions/    All active and past subscriptions
GET    /api/superadmin/logs/             Superadmin action log
POST   /api/superadmin/logs/             Add manual log entry
```

> These endpoints are completely invisible to company users.
> Only `role=superadmin` can access them.
