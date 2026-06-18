# Bug Report — 59 Pre-Existing Test Failures (commit `58d9189`)

This report documents the **genuine application-code bugs** uncovered while fixing the 59
pre-existing test failures during the "Complete test suite coverage" task. All fixes live in
commit `58d9189` ("Complete test suite coverage: fix 59 pre-existing failures, add 127 new
tests").

**Note on scope:** the 59 failing tests had two different root causes:

1. **Genuine app-code bugs** (13 of them, cataloged below) — the application logic was
   wrong, and the test was correctly written against the intended behavior.
2. **Test-side bugs** — the test itself used stale field names, wrong fixtures, or wrong
   assumptions about the API contract (e.g. `tests/conftest.py` fixtures referencing
   `Discount.type`/`Discount.value` instead of `Discount.percent`/`Discount.months`,
   `Debt.objects.filter(student=...)` instead of `group_student__student=...`,
   `tests/test_companies.py` expecting 403 where 200 was always correct, `"type"` vs
   `"trigger"` payload keys in `tests/test_notifications.py`, etc.). These required only
   test-file edits (in `tests/conftest.py`, `tests/test_companies.py`,
   `tests/test_courses.py`, `tests/test_teachers.py`, `tests/test_students.py`,
   `tests/test_telegram_bot.py`, `tests/test_debts.py`, `tests/test_groups.py`,
   `tests/test_notifications.py`, `tests/test_payments.py`, `tests/test_company_settings.py`)
   and are not app-code bugs, so they are not itemized as numbered bugs below.

Only category 1 — actual defects in `apps/` source files — is itemized below, grouped by app
as requested.

---

## apps/payments/

### BUG #1
**File:** `apps/payments/serializers.py` (`PaymentCreateSerializer`)
**Test that caught it:** `tests/test_payments.py::TestPaymentCreationBusinessLogic::test_payment_with_percent_discount`, `test_payment_with_fixed_discount`
**Problem:** When a payment was created with a `discount_id`, the serializer computed the
discounted amount using `discount.type` and `discount.value` — fields that don't exist on
the `Discount` model (it actually has `percent` and `months`). Any payment that applied a
discount would crash with an `AttributeError`.
**Fix:** Changed the calculation to use the real field:
`final_amount = requested_amount * (1 - Decimal(discount.percent) / Decimal('100'))`.

### BUG #2
**File:** `apps/payments/serializers.py` (`PaymentCreateSerializer`)
**Test that caught it:** `tests/test_payments.py::TestPaymentCreationBusinessLogic::test_negative_discount_rejected`
**Problem:** Nothing stopped a discount percentage greater than 100% from producing a
negative `final_amount`, which would have created a payment for a negative sum.
**Fix:** Added a validation check — if `final_amount < 0`, raise
`ValidationError({'requested_amount': "Chegirma to'lov summasidan katta"})`.

---

## apps/salaries/

### BUG #3
**File:** `apps/salaries/logic.py` (`calculate_teacher_salary`)
**Test that caught it:** `tests/test_company_settings.py::TestTeacherContractBreakPolicy::test_full_policy_pays_complete_salary`, `test_prorate_policy_pays_partial_salary`, `test_none_policy_pays_zero_salary`, `test_active_teacher_always_gets_full_salary`
**Problem:** The function returned `[]` (no salary at all) for any teacher with
`status in ('frozen', 'archived')`. This meant archived teachers never got a final salary,
regardless of the company's `teacher_contract_break_policy` ('full' / 'prorate' / 'none').
**Fix:** Split the two statuses apart. `'frozen'` teachers still return `[]`, but
`'archived'` teachers (with `salary_type == 'fixed'`) now get a dedicated calculation branch
that reads `CompanySettings.teacher_contract_break_policy` and computes:
- `'full'` → full `fixed_amount`
- `'prorate'`/other → `fixed_amount * (days_worked / 30)` based on `archived_at`
- `'none'` → `0`

then creates/updates the final `TeacherSalary` record via `update_or_create` and reconciles it.

### BUG #4
**File:** `apps/salaries/logic.py` (`calculate_teacher_salary`)
**Test that caught it:** `tests/test_salaries.py` — multiple tests across `TestPercentSalaryDebts`, `TestPerStudentSalaryDebts`, `TestMultipleGroups`, `TestArchivedStudentDebt`, and `TestDebtMonthFilter::test_current_month_debt_included` / `test_only_current_month_debt_counted_when_both_exist`
**Problem:** For `percent` and `per_student` teachers, the group debt sum used to compute
salary was filtered by `Debt.due_date` falling in `month + 1` (the month *after* the billing
month), instead of the billing month itself. Since debts are created with `due_date` in the
billing month (per CLAUDE.md Rule 9), this off-by-one meant the query almost always matched
zero debts, so `base_amount` (and therefore the whole salary) computed as `0` instead of the
correct percentage/coefficient of the group's debt total.
**Fix:** Removed the `next_month = month + relativedelta(months=1)` computation and filter
`Debt.objects.filter(group_student__group=group, company=teacher.company, due_date__year=month.year, due_date__month=month.month)` directly on the billing `month`.

---

## apps/superadmin_panel/

### BUG #5
**File:** `apps/superadmin_panel/serializers.py` (`CompanyCardSerializer`)
**Test that caught it:** `tests/test_superadmin.py::TestSuperadminCompanies::test_company_has_subscription_and_user_count`
**Problem:** The superadmin "companies" list endpoint did not expose whether a company's
subscription was current (`active_subscription`) or how many users belonged to it
(`user_count`) — both fields were simply missing from the serialized response.
**Fix:** Added two `SerializerMethodField`s (and registered them in `Meta.fields`):
- `get_active_subscription` — looks at the company's most recent
  `subscription_debts` entry and returns `debt.status != 'overdue'` (or `True` if no debt
  record exists yet).
- `get_user_count` — returns `User.objects.filter(company=obj).count()`.

---

## apps/groups/

### BUG #6
**File:** `apps/groups/views.py` (group "add student" action)
**Test that caught it:** `tests/test_groups.py::TestGroupStudentActions::test_add_student_transitions_pending_to_active`
**Problem:** When a student with `status == 'pending'` was added to a group, their status
was left as `'pending'` — the student was never promoted to `'active'`, even though they now
had an active enrollment (`GroupStudent` with `status='trial'`).
**Fix:** Before creating the `GroupStudent` record, added a check that flips the student to
`'active'` if their current status is `'pending'`:
```python
if student.status == 'pending':
    student.status = 'active'
    student.save(update_fields=['status'])
```

---

## apps/notifications/

### BUG #7
**File:** `apps/notifications/views.py` (`SmsTemplateViewSet.get_permissions`)
**Test that caught it:** `tests/test_notifications.py::TestSmsTemplateCRUD::test_admin_blocked_from_create`, `test_teacher_blocked_from_create`
**Problem:** Creating an SMS template had no role restriction beyond being authenticated —
`admin` and `teacher` users (who should be blocked) could successfully create SMS templates.
**Fix:** Added `from utils.permissions import IsBossOrManager` and, in
`get_permissions()`, return `[IsBossOrManager()]` specifically for the `create` action
(before falling back to `[IsAuthenticated()]` for everything else).

---

## apps/expenses/

### BUG #8
**File:** `apps/expenses/pl_views.py` (`ProfitLossView` / `_parse_date_range`)
**Test that caught it:** `tests/test_expenses.py::TestProfitLoss::test_pl_requires_month_or_year_param`, `test_pl_by_month_returns_all_8_categories`, `test_pl_by_year_works`
**Problem:** `_parse_date_range` had no support for the `?month=YYYY-MM` or `?year=YYYY`
query parameters used by the P&L dashboard, and `ProfitLossView.get` would silently return
`200` (defaulting to the current month) even when neither parameter was supplied, instead of
the documented `400` error.
**Fix:** `_parse_date_range` now parses `?month=YYYY-MM` (via `relativedelta` to compute the
month's `from_date`/`to_date`) and `?year=YYYY` (full calendar year), falling back to
existing `from_date`/`to_date` handling. `ProfitLossView.get` now returns
`400 {'error': "'month' or 'year' parameter required"}` if neither is provided.

### BUG #9
**File:** `apps/expenses/pl_views.py` (`ProfitLossView` / `_salary_totals`)
**Test that caught it:** `tests/test_expenses.py::TestProfitLoss::test_pl_by_month_returns_all_8_categories`, `test_pl_response_structure`, `test_pl_profit_calculation`
**Problem:** The `expenses.breakdown` field was built as an ad-hoc list (one combined
`'maoshlar'` entry for salaries plus per-category rows), so it did not always contain all 8
required categories (`rent, utility, tax, fine, discount, teacher_salary, staff_salary,
other`) as mandated by the P&L rule in CLAUDE.md. Additionally, the top-level response used
`net_profit` / `net_profit_percent` instead of the expected `profit` / `margin` keys.
**Fix:** `_salary_totals` now returns a `(teacher_paid, staff_paid)` tuple instead of one
combined `Decimal`. `breakdown` is now a fixed dict with exactly the 8 required keys
(`teacher_salary`/`staff_salary` populated from `_salary_totals`, the rest from `cats[...]`),
and `total_expense = sum(breakdown.values())`. Response keys `net_profit` → `profit` and
`net_profit_percent` → `margin` (kept `expense_percent`).

### BUG #10
**File:** `apps/expenses/views.py` (`ExpenseViewSet`)
**Test that caught it:** `tests/test_expenses.py::TestExpenseCRUD::test_cross_company_blocked`
**Problem:** `ExpenseViewSet` only included Create/Update/List mixins, so `GET
/api/v1/expenses/{id}/` was not supported (returned `405 Method Not Allowed`) instead of the
expected `403`/`404` for a cross-company record.
**Fix:** Added `mixins.RetrieveModelMixin` to the view set's base classes so detail-by-id GET
requests are handled (and correctly enforce the company-scoping permission/queryset checks).

---

## apps/debts/

### BUG #11
**File:** `apps/debts/tasks.py` (`assign_monthly_debts`)
**Test that caught it:** `tests/test_company_settings.py::TestBillingTypeVariants::test_monthly_billing_charges_full_price`, `test_per_lesson_billing_charges_by_attendance`, `test_upfront_billing_charges_full_course_on_new_enrollment`, `test_upfront_billing_skips_existing_enrollment`
**Problem:** The monthly debt-assignment task completely ignored
`CompanySettings.billing_type`. Every enrollment was always charged the flat
`course.price` for the month, regardless of whether the company was configured for
`'monthly'`, `'per_lesson'` (charge per attended lesson), or `'upfront'` (charge the full
course total on enrollment, only within the enrollment window) billing.
**Fix:** Added `CompanySettings.objects.get_or_create(company=company)` and branched on
`billing_type`:
- `'upfront'` — skip enrollments older than the current month; otherwise charge
  `course_price * duration_months`.
- `'per_lesson'` — count `Attendance` records with `status='present'` for the billing month
  and charge `(course_price / 20) * attended_count`.
- otherwise (`'monthly'`/default) — charge the flat `course_price` as before.

Discount calculations now apply to this computed `base_price` instead of always the raw
`course_price`.

---

## apps/companies/

### BUG #12
**File:** `apps/companies/dashboard_views.py` (`DashboardSummaryView`)
**Test that caught it:** `tests/test_dashboard.py::TestDashboardSummary::test_summary_reflects_data`
**Problem:** The `total_students` field in the dashboard summary was computed from
`active_students.count()` — i.e. it only counted students with `status='active'`, so
pending/trial/archived students were excluded from the "total" figure (making
`total_students` equal to `active_students`, which is wrong).
**Fix:** Changed `'total_students'` to `students.count()` (the full, unfiltered queryset),
so it reflects every student in the company regardless of status.

### BUG #13
**File:** `apps/companies/dashboard_views.py` (`DashboardTeacherStatsView`)
**Test that caught it:** `tests/test_dashboard.py::TestDashboardTeacherStats::test_returns_list`, `test_teacher_entry_fields`
**Problem:** The per-teacher `monthly_revenue` figure was computed via
`Payment.objects.filter(company=company, group__teacher=teacher, ...)`. `Payment` has no
direct `group` foreign key, so this lookup path doesn't exist — the query raised a
`FieldError`, causing the whole endpoint to fail.
**Fix:** Changed the filter to the correct relation path:
`Payment.objects.filter(company=company, group_student__group__teacher=teacher, ...)`
(via `Payment.group_student.group.teacher`).

---

## Summary Table

| # | App | Bug type | Fixed in |
|---|-----|----------|----------|
| 1 | apps/payments/ | Serializer referenced non-existent model fields (`discount.type`/`discount.value`) causing `AttributeError` | `apps/payments/serializers.py` |
| 2 | apps/payments/ | Missing validation — discount could push payment amount negative | `apps/payments/serializers.py` |
| 3 | apps/salaries/ | Archived teachers always got `[]` salary, ignoring `teacher_contract_break_policy` | `apps/salaries/logic.py` |
| 4 | apps/salaries/ | Off-by-one month filter on group debt sum for percent/per_student salaries | `apps/salaries/logic.py` |
| 5 | apps/superadmin_panel/ | Missing `active_subscription`/`user_count` fields on company card serializer | `apps/superadmin_panel/serializers.py` |
| 6 | apps/groups/ | Pending student not promoted to `active` when added to a group | `apps/groups/views.py` |
| 7 | apps/notifications/ | SMS template creation had no role restriction (admin/teacher could create) | `apps/notifications/views.py` |
| 8 | apps/expenses/ | P&L view missing `?month=`/`?year=` query param support and required-param validation | `apps/expenses/pl_views.py` |
| 9 | apps/expenses/ | P&L `expenses.breakdown` not a fixed 8-category dict; `net_profit`/`net_profit_percent` renamed to `profit`/`margin` | `apps/expenses/pl_views.py` |
| 10 | apps/expenses/ | `ExpenseViewSet` missing `RetrieveModelMixin` (no GET detail endpoint) | `apps/expenses/views.py` |
| 11 | apps/debts/ | `assign_monthly_debts` ignored `CompanySettings.billing_type` (monthly/per_lesson/upfront) | `apps/debts/tasks.py` |
| 12 | apps/companies/ | Dashboard `total_students` only counted active students | `apps/companies/dashboard_views.py` |
| 13 | apps/companies/ | Dashboard `monthly_revenue` used invalid `group__teacher` FK path, raising `FieldError` | `apps/companies/dashboard_views.py` |
