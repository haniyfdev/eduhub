import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('companies', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Staff',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=20)),
                ('role', models.CharField(choices=[
                    ('admin', 'Admin'), ('manager', 'Menejer'), ('accountant', 'Buxgalter'),
                    ('security', 'Qorovul'), ('cleaner', 'Farrosh'), ('supply', 'Zavxoz'), ('other', 'Boshqa'),
                ], max_length=20)),
                ('contract_type', models.CharField(choices=[
                    ('monthly', 'Oylik belgilangan'), ('contract', 'Shartnomaviy'),
                ], default='monthly', max_length=20)),
                ('salary_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('contract_months', models.IntegerField(blank=True, null=True)),
                ('contract_start', models.DateField(blank=True, null=True)),
                ('contract_end', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[
                    ('active', 'Faol'), ('archived', 'Arxivlangan'),
                ], default='active', max_length=20)),
                ('hired_at', models.DateField(auto_now_add=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='staff_members',
                    to='companies.company',
                )),
            ],
            options={'db_table': 'staff'},
        ),
        migrations.CreateModel(
            name='StaffSalary',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('month', models.DateField()),
                ('calculated_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('paid_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('carry_over', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('status', models.CharField(choices=[
                    ('unpaid', 'Unpaid'), ('partial', 'Partial'), ('paid', 'Paid'),
                ], default='unpaid', max_length=10)),
                ('is_paid', models.BooleanField(default=False)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('staff', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='salaries',
                    to='staff.staff',
                )),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='staff_member_salaries',
                    to='companies.company',
                )),
            ],
            options={'db_table': 'staff_member_salaries'},
        ),
        migrations.AlterUniqueTogether(
            name='staffsalary',
            unique_together={('staff', 'month')},
        ),
    ]
