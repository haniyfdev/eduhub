from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_announcement_models'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='smstemplate',
            name='type',
        ),
        migrations.AddField(
            model_name='smstemplate',
            name='trigger',
            field=models.CharField(
                choices=[
                    ('debt_reminder', 'Qarzdorlik eslatmasi'),
                    ('payment_confirmed', "To'lov tasdiqi"),
                    ('lesson_reminder', 'Dars eslatmasi'),
                    ('course_started', 'Kurs boshlanishi'),
                    ('overdue_debt', "Muddati o'tgan qarz"),
                    ('custom', 'Boshqa'),
                ],
                default='custom',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='smstemplate',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='smstemplate',
            name='is_default',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='smstemplate',
            name='name',
            field=models.CharField(max_length=100),
        ),
    ]
