from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0008_restore_trial_leads'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='archive_reason',
            field=models.CharField(
                blank=True,
                choices=[('graduated', 'Kursni bitirdi'), ('dropped_out', 'Tashlab ketdi')],
                max_length=20,
                null=True,
            ),
        ),
        migrations.RunSQL(
            "UPDATE students SET archive_reason = 'graduated' WHERE status = 'archived' AND archive_reason IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
