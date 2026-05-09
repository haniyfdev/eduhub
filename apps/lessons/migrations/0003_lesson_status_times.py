from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0002_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='lesson',
                    name='started_at',
                    field=models.DateTimeField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name='lesson',
                    name='finished_at',
                    field=models.DateTimeField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name='lesson',
                    name='status',
                    field=models.CharField(
                        max_length=20,
                        choices=[('pending', 'Pending'), ('ongoing', 'Ongoing'), ('finished', 'Finished')],
                        default='pending',
                    ),
                ),
            ],
        ),
    ]