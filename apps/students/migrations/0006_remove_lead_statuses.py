from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0005_alter_student_status'),
        ('leads', '0003_data_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('archived', 'Archived'),
                    ('frozen', 'Frozen'),
                ],
                default='active',
                max_length=20,
            ),
        ),
    ]
