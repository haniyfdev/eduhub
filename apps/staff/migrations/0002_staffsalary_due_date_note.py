from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffsalary',
            name='due_date',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='staffsalary',
            name='note',
            field=models.TextField(null=True, blank=True),
        ),
    ]
