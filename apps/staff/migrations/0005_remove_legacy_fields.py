from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0004_add_user_fk'),
        ('users', '0001_initial'),
    ]

    operations = [
        # Make user non-nullable
        migrations.AlterField(
            model_name='staff',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff_profile',
                to='users.user',
            ),
        ),
        # Remove legacy fields
        migrations.RemoveField(model_name='staff', name='first_name'),
        migrations.RemoveField(model_name='staff', name='last_name'),
        migrations.RemoveField(model_name='staff', name='phone'),
        migrations.RemoveField(model_name='staff', name='role'),
        migrations.RemoveField(model_name='staff', name='hired_at'),
        # Fix salary_amount to use default=0
        migrations.AlterField(
            model_name='staff',
            name='salary_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
    ]
