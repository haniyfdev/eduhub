import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0007_group_end_time_group_start_time'),
        ('rooms', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='group',
            name='room',
        ),
        migrations.AddField(
            model_name='group',
            name='room',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='groups',
                to='rooms.room',
            ),
        ),
    ]
