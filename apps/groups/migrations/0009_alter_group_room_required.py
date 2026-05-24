import django.db.models.deletion
from django.db import migrations, models

_AFFECTED = "SELECT id FROM groups WHERE room_id IS NULL"

_CLEANUP_SQL = f"""
DELETE FROM attendance
WHERE lesson_id IN (SELECT id FROM lessons WHERE group_id IN ({_AFFECTED}));

DELETE FROM grades
WHERE lesson_id IN (SELECT id FROM lessons WHERE group_id IN ({_AFFECTED}));

DELETE FROM teacher_work_logs
WHERE lesson_id IN (SELECT id FROM lessons WHERE group_id IN ({_AFFECTED}));

DELETE FROM lessons
WHERE group_id IN ({_AFFECTED});

DELETE FROM payments
WHERE group_id IN ({_AFFECTED});

UPDATE teacher_salaries SET group_id = NULL
WHERE group_id IN ({_AFFECTED});

DELETE FROM group_students
WHERE group_id IN ({_AFFECTED});

DELETE FROM groups WHERE room_id IS NULL;
"""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('groups', '0008_alter_group_room'),
        ('rooms', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=_CLEANUP_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='group',
            name='room',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='groups',
                to='rooms.room',
            ),
        ),
    ]
