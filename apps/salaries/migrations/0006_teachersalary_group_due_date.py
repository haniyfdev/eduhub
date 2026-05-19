import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0007_group_end_time_group_start_time'),
        ('salaries', '0005_teachersalary_payment_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='teachersalary',
            name='group',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='teacher_salaries',
                to='groups.group',
            ),
        ),
        migrations.AddField(
            model_name='teachersalary',
            name='due_date',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='teachersalary',
            unique_together={('teacher', 'group', 'month')},
        ),
    ]
