import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.lessons.models import Lesson
from apps.attendance.models import Attendance
from apps.students.models import Student
from apps.groups.models import Group, GroupStudent
from .conftest import make_phone

ATTENDANCE_URL = "/api/v1/attendance/"


@pytest.mark.django_db
class TestAttendancePermissions:
    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(ATTENDANCE_URL)
        assert resp.status_code == 401

    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(ATTENDANCE_URL)
        assert resp.status_code == 200

    def test_teacher_can_list(self, teacher_client):
        resp = teacher_client.get(ATTENDANCE_URL)
        assert resp.status_code == 200

    def test_post_not_allowed(self, boss_client):
        resp = boss_client.post(ATTENDANCE_URL, {})
        assert resp.status_code == 405


@pytest.mark.django_db
class TestAttendanceList:
    def test_list_returns_attendance_for_company(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(group=group, teacher=teacher, topic="Lesson 1", date=date.today())
        att = Attendance.objects.create(lesson=lesson, student=student, status="present")

        resp = boss_client.get(ATTENDANCE_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(att.id) in ids

    def test_filter_by_student(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(group=group, teacher=teacher, topic="Lesson 1", date=date.today())
        att = Attendance.objects.create(lesson=lesson, student=student, status="absent")

        resp = boss_client.get(f"{ATTENDANCE_URL}?student={student.id}")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(att.id) in ids

    def test_cross_company_attendance_excluded(self, boss_client, company2, db):
        from apps.teachers.models import Teacher
        from apps.users.models import User
        from apps.courses.models import Course
        from apps.rooms.models import Room

        other_user = User.objects.create_user(
            phone=make_phone(), password="pass",
            first_name="Other", last_name="Teacher",
            role="teacher", status="active", company=company2,
        )
        other_teacher = Teacher.objects.create(
            user=other_user, company=company2,
            salary_type="fixed", fixed_amount=Decimal("1000000"),
            hired_at=date.today(), status="active",
        )
        other_course = Course.objects.create(
            company=company2, name="Other Course", price=Decimal("400000"),
            duration_months=3, duration_hours=Decimal("60"),
        )
        other_course.teachers.add(other_teacher)
        other_room = Room.objects.create(company=company2, name=1, gender_type="a", status="active")
        other_group = Group.objects.create(
            company=company2, course=other_course, teacher=other_teacher,
            room=other_room, number=1, gender_type="a", status="active",
        )
        other_student = Student.objects.create(
            company=company2, first_name="Other", last_name="Student",
            phone=make_phone(), status="active",
        )
        other_lesson = Lesson.objects.create(group=other_group, teacher=other_teacher, topic="Other", date=date.today())
        other_att = Attendance.objects.create(lesson=other_lesson, student=other_student, status="present")

        resp = boss_client.get(ATTENDANCE_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(other_att.id) not in ids


@pytest.mark.django_db
class TestAttendanceNotes:
    def test_notes_returns_only_non_empty(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(group=group, teacher=teacher, topic="Lesson", date=date.today())
        with_note = Attendance.objects.create(lesson=lesson, student=student, status="late", note="Came late")
        Attendance.objects.create(lesson=lesson, student=student, status="present", note="")

        resp = boss_client.get(f"{ATTENDANCE_URL}notes/")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data]
        assert str(with_note.id) in ids
        assert len(resp.data) == 1
        assert resp.data[0]["note"] == "Came late"
        assert resp.data[0]["group_name"] == group.display_name

    def test_notes_filter_by_date_range(self, boss_client, group, teacher, student, group_student):
        old_lesson = Lesson.objects.create(group=group, teacher=teacher, topic="Old", date=date.today() - timedelta(days=30))
        new_lesson = Lesson.objects.create(group=group, teacher=teacher, topic="New", date=date.today())
        old_att = Attendance.objects.create(lesson=old_lesson, student=student, status="absent", note="Old note")
        new_att = Attendance.objects.create(lesson=new_lesson, student=student, status="absent", note="New note")

        resp = boss_client.get(f"{ATTENDANCE_URL}notes/?from_date={date.today() - timedelta(days=1)}")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data]
        assert str(new_att.id) in ids
        assert str(old_att.id) not in ids

    def test_notes_filter_by_group(self, boss_client, group, teacher, student, group_student, company, course, room):
        lesson = Lesson.objects.create(group=group, teacher=teacher, topic="Lesson", date=date.today())
        att = Attendance.objects.create(lesson=lesson, student=student, status="late", note="In this group")

        other_group = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=2, gender_type="a", status="active",
        )
        other_lesson = Lesson.objects.create(group=other_group, teacher=teacher, topic="Other", date=date.today())
        other_att = Attendance.objects.create(lesson=other_lesson, student=student, status="late", note="Other group")

        resp = boss_client.get(f"{ATTENDANCE_URL}notes/?group={group.id}")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data]
        assert str(att.id) in ids
        assert str(other_att.id) not in ids


@pytest.mark.django_db
class TestAttendanceSummary:
    def test_summary_only_includes_students_with_absences(self, boss_client, group, teacher, group_student, student, company):
        no_absence_student = Student.objects.create(
            company=company, first_name="Perfect", last_name="Attendance",
            phone=make_phone(), status="active",
        )
        GroupStudent.objects.create(group=group, student=no_absence_student, joined_at=timezone.now())

        lesson1 = Lesson.objects.create(group=group, teacher=teacher, topic="L1", date=date.today())
        lesson2 = Lesson.objects.create(group=group, teacher=teacher, topic="L2", date=date.today() - timedelta(days=1))

        Attendance.objects.create(lesson=lesson1, student=student, status="absent")
        Attendance.objects.create(lesson=lesson2, student=student, status="present")
        Attendance.objects.create(lesson=lesson1, student=no_absence_student, status="present")
        Attendance.objects.create(lesson=lesson2, student=no_absence_student, status="present")

        resp = boss_client.get(f"{ATTENDANCE_URL}summary/")
        assert resp.status_code == 200
        student_ids = [row["student_id"] for row in resp.data]
        assert str(student.id) in student_ids
        assert str(no_absence_student.id) not in student_ids

    def test_summary_attendance_pct(self, boss_client, group, teacher, student, group_student):
        lesson1 = Lesson.objects.create(group=group, teacher=teacher, topic="L1", date=date.today())
        lesson2 = Lesson.objects.create(group=group, teacher=teacher, topic="L2", date=date.today() - timedelta(days=1))
        lesson3 = Lesson.objects.create(group=group, teacher=teacher, topic="L3", date=date.today() - timedelta(days=2))

        Attendance.objects.create(lesson=lesson1, student=student, status="present")
        Attendance.objects.create(lesson=lesson2, student=student, status="present")
        Attendance.objects.create(lesson=lesson3, student=student, status="absent")

        resp = boss_client.get(f"{ATTENDANCE_URL}summary/")
        assert resp.status_code == 200
        row = next(r for r in resp.data if r["student_id"] == str(student.id))
        assert row["total"] == 3
        assert row["present"] == 2
        assert row["absent"] == 1
        assert row["attendance_pct"] == 67
        assert row["group"] == group.display_name
        assert row["course"] == group.course.name

    def test_summary_search_filter(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(group=group, teacher=teacher, topic="L1", date=date.today())
        Attendance.objects.create(lesson=lesson, student=student, status="absent")

        resp = boss_client.get(f"{ATTENDANCE_URL}summary/?search={student.first_name}")
        assert resp.status_code == 200
        assert any(r["student_id"] == str(student.id) for r in resp.data)

        resp_none = boss_client.get(f"{ATTENDANCE_URL}summary/?search=NoSuchStudentXYZ")
        assert resp_none.status_code == 200
        assert all(r["student_id"] != str(student.id) for r in resp_none.data)
