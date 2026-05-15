import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0003_data_migration'),
        ('students', '0006_remove_lead_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('trial', 'Trial'),
                    ('archived', 'Archived'),
                    ('frozen', 'Frozen'),
                ],
                default='active',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='student',
            name='lead',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='student',
                to='leads.lead',
            ),
        ),
    ]
