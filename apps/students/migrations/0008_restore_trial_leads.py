from django.db import migrations


def restore_trial_leads(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    Lead = apps.get_model('leads', 'Lead')

    for student in Student.objects.filter(status='trial', lead__isnull=True):
        lead = Lead.objects.create(
            company=student.company,
            first_name=student.first_name,
            last_name=student.last_name,
            phone=student.phone,
            second_phone=student.second_phone,
            course=student.course,
            birth_date=student.birth_date,
            referral_source=student.referral_source,
            status='trial',
        )
        student.lead = lead
        student.save(update_fields=['lead'])


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0007_student_lead_fk'),
    ]

    operations = [
        migrations.RunPython(restore_trial_leads, migrations.RunPython.noop),
    ]
