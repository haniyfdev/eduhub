from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0002_add_birth_date_and_decimal_hours'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='phone',
            field=models.CharField(max_length=20),
        ),
    ]
