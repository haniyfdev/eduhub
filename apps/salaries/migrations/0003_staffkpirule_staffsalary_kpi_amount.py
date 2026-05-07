import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0001_initial'),
        ('salaries', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffsalary',
            name='kpi_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.CreateModel(
            name='StaffKpiRule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('role', models.CharField(choices=[('admin', 'Admin'), ('manager', 'Manager'), ('any', 'Any')], max_length=20)),
                ('metric', models.CharField(choices=[('attendance_rate', 'Attendance Rate'), ('payment_collected', 'Payment Collected'), ('student_enrolled', 'Student Enrolled')], max_length=30)),
                ('threshold', models.DecimalField(decimal_places=2, max_digits=15)),
                ('bonus_amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('status', models.CharField(choices=[('active', 'Active'), ('archived', 'Archived')], default='active', max_length=20)),
                ('archived_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kpi_rules', to='companies.company')),
            ],
            options={
                'db_table': 'staff_kpi_rules',
            },
        ),
    ]
