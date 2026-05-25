import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discounts', '0001_initial'),
        ('courses', '0001_initial'),
        ('students', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Drop all old fields
        migrations.RemoveField(model_name='discount', name='name'),
        migrations.RemoveField(model_name='discount', name='type'),
        migrations.RemoveField(model_name='discount', name='value'),
        migrations.RemoveField(model_name='discount', name='condition'),
        migrations.RemoveField(model_name='discount', name='status'),
        migrations.RemoveField(model_name='discount', name='course'),
        # Add new fields
        migrations.AddField(
            model_name='discount',
            name='student',
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='discounts',
                to='students.student',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='discount',
            name='course',
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='discounts',
                to='courses.course',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='discount',
            name='percent',
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='discount',
            name='months',
            field=models.PositiveIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='discount',
            name='start_month',
            field=models.DateField(default='2026-01-01'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='discount',
            name='end_month',
            field=models.DateField(default='2026-01-01'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='discount',
            name='created_by',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_discounts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='discount',
            name='note',
            field=models.TextField(blank=True, null=True),
        ),
    ]
