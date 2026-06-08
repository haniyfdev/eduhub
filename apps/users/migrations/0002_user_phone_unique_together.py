from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # Drop the global unique constraint on phone
        migrations.AlterField(
            model_name='user',
            name='phone',
            field=models.CharField(max_length=20),
        ),
        # Add per-company uniqueness: (phone, company) must be unique
        migrations.AlterUniqueTogether(
            name='user',
            unique_together={('phone', 'company')},
        ),
    ]
