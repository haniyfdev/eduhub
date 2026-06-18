from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0006_backfill_company_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='companysettings',
            name='freeze_billing_type',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('per_lesson', 'Per Lesson'), ('per_day', 'Per Day')],
                default='manual',
                max_length=20,
            ),
        ),
    ]
