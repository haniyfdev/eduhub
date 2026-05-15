from django.db import migrations


def migrate_leads_data(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    Lead = apps.get_model('leads', 'Lead')
    for student in Student.objects.filter(status__in=['pending', 'trial', 'ignored']):
        Lead.objects.create(
            company_id=student.company_id,
            first_name=student.first_name,
            last_name=student.last_name,
            phone=student.phone,
            second_phone=student.second_phone,
            course_id=student.course_id,
            birth_date=student.birth_date,
            referral_source=student.referral_source,
            status=student.status,
            created_at=student.created_at,
            archived_at=student.archived_at,
        )
    Student.objects.filter(status__in=['pending', 'trial', 'ignored']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0002_real_table'),
    ]

    operations = [
        migrations.RunPython(migrate_leads_data, migrations.RunPython.noop),
    ]
