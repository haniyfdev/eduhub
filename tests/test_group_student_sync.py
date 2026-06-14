from datetime import timedelta

import pytest
from django.utils import timezone

from apps.groups.models import Group, GroupStudent
from apps.students.models import Student

STUDENTS_URL = "/api/v1/students/"


@pytest.mark.django_db
class TestGroupStudentArchiveSync:
    def test_archive_student_sets_all_active_memberships_to_left(self, student, group_student):
        student.status = 'archived'
        student.save()

        group_student.refresh_from_db()
        assert group_student.status == 'left'

    def test_archive_student_sets_left_at_to_now(self, student, group_student):
        before = timezone.now()
        student.status = 'archived'
        student.save()
        after = timezone.now()

        group_student.refresh_from_db()
        assert group_student.left_at is not None
        assert before <= group_student.left_at <= after

    def test_archive_student_with_multiple_groups_closes_all(
        self, student, group_student, group, course, teacher, room, company,
    ):
        group2 = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=2, gender_type="a", status="active",
        )
        gs2 = GroupStudent.objects.create(group=group2, student=student, joined_at=timezone.now())

        student.status = 'archived'
        student.save()

        group_student.refresh_from_db()
        gs2.refresh_from_db()
        assert group_student.status == 'left'
        assert gs2.status == 'left'
        assert group_student.left_at is not None
        assert gs2.left_at is not None

    def test_already_left_membership_not_double_updated(self, student, group_student):
        past = timezone.now() - timedelta(days=10)
        group_student.status = 'left'
        group_student.left_at = past
        group_student.save()

        student.status = 'archived'
        student.save()

        group_student.refresh_from_db()
        assert group_student.left_at == past

    def test_unarchive_student_does_not_reopen_memberships(self, student, group_student):
        student.status = 'archived'
        student.save()
        group_student.refresh_from_db()
        assert group_student.status == 'left'

        student.status = 'active'
        student.save()

        group_student.refresh_from_db()
        assert group_student.status == 'left'
        assert group_student.left_at is not None

    def test_archived_student_not_counted_in_active_students(self, student, group_student, company):
        assert Student.objects.filter(company=company, status='active').count() == 1

        student.status = 'archived'
        student.save()

        assert Student.objects.filter(company=company, status='active').count() == 0

    def test_direct_status_patch_also_triggers_sync(self, boss_client, student, group_student):
        resp = boss_client.patch(f"{STUDENTS_URL}{student.id}/", {"status": "archived"})

        assert resp.status_code == 200

        group_student.refresh_from_db()
        assert group_student.status == 'left'
        assert group_student.left_at is not None
