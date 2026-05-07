import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.users.models import User
from apps.teachers.models import Teacher
from apps.students.models import Student
from apps.courses.models import Course
from apps.groups.models import Group, GroupStudent
from apps.discounts.models import Discount
from apps.debts.models import Debt
from apps.payments.models import Payment
from apps.expenses.models import Expense


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_phone():
    return f"+998{uuid.uuid4().int % 10**9:09d}"


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

@pytest.fixture
def company(db):
    return Company.objects.create(name="Test Academy", phone="+998901234567")


@pytest.fixture
def company2(db):
    return Company.objects.create(name="Other Academy", phone="+998901234568")


# ---------------------------------------------------------------------------
# Users — one per role
# ---------------------------------------------------------------------------

@pytest.fixture
def superadmin(db):
    return User.objects.create_user(
        phone=make_phone(), password="pass1234",
        first_name="Super", last_name="Admin",
        role="superadmin", status="active",
    )


@pytest.fixture
def boss(db, company):
    return User.objects.create_user(
        phone=make_phone(), password="pass1234",
        first_name="Boss", last_name="User",
        role="boss", status="active", company=company,
    )


@pytest.fixture
def manager(db, company):
    return User.objects.create_user(
        phone=make_phone(), password="pass1234",
        first_name="Manager", last_name="User",
        role="manager", status="active", company=company,
    )


@pytest.fixture
def admin_user(db, company):
    return User.objects.create_user(
        phone=make_phone(), password="pass1234",
        first_name="Admin", last_name="User",
        role="admin", status="active", company=company,
    )


@pytest.fixture
def teacher_user(db, company):
    return User.objects.create_user(
        phone=make_phone(), password="pass1234",
        first_name="Teacher", last_name="User",
        role="teacher", status="active", company=company,
    )


@pytest.fixture
def teacher(db, company, teacher_user):
    return Teacher.objects.create(
        user=teacher_user,
        company=company,
        salary_type="fixed",
        fixed_amount=Decimal("2000000"),
        hired_at=date.today(),
        status="active",
    )


@pytest.fixture
def parent_user(db, company):
    return User.objects.create_user(
        phone=make_phone(), password="pass1234",
        first_name="Parent", last_name="User",
        role="parent", status="active", company=company,
    )


# ---------------------------------------------------------------------------
# Course, Group, Student
# ---------------------------------------------------------------------------

@pytest.fixture
def course(db, company, teacher):
    return Course.objects.create(
        company=company,
        teacher=teacher,
        name="Python Course",
        price=Decimal("500000"),
        duration_months=3,
        duration_hours=60,
        status="active",
    )


@pytest.fixture
def group(db, company, course, teacher):
    return Group.objects.create(
        company=company,
        course=course,
        teacher=teacher,
        number=1,
        gender_type="a",
        status="active",
    )


@pytest.fixture
def student(db, company):
    return Student.objects.create(
        company=company,
        first_name="Student",
        last_name="One",
        phone=make_phone(),
        status="active",
    )


@pytest.fixture
def pending_student(db, company):
    return Student.objects.create(
        company=company,
        first_name="Pending",
        last_name="Student",
        phone=make_phone(),
        status="pending",
    )


@pytest.fixture
def group_student(db, group, student):
    return GroupStudent.objects.create(
        group=group, student=student, joined_at=timezone.now()
    )


@pytest.fixture
def discount(db, company, course):
    return Discount.objects.create(
        company=company,
        course=course,
        name="10% off",
        type="percent",
        value=Decimal("10"),
        status="active",
    )


@pytest.fixture
def debt(db, company, student):
    return Debt.objects.create(
        company=company,
        student=student,
        amount=Decimal("500000"),
        due_date=date.today() + timedelta(days=30),
        status="unpaid",
    )


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def superadmin_client(superadmin):
    return auth_client(superadmin)


@pytest.fixture
def boss_client(boss):
    return auth_client(boss)


@pytest.fixture
def manager_client(manager):
    return auth_client(manager)


@pytest.fixture
def admin_client(admin_user):
    return auth_client(admin_user)


@pytest.fixture
def teacher_client(teacher_user):
    return auth_client(teacher_user)


@pytest.fixture
def parent_client(parent_user):
    return auth_client(parent_user)
