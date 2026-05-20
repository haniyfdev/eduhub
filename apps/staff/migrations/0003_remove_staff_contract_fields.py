from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0002_staffsalary_due_date_note'),
    ]

    operations = [
        migrations.RemoveField(model_name='staff', name='contract_type'),
        migrations.RemoveField(model_name='staff', name='contract_months'),
        migrations.RemoveField(model_name='staff', name='contract_start'),
        migrations.RemoveField(model_name='staff', name='contract_end'),
    ]
