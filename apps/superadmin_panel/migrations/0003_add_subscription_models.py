import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin_panel', '0002_initial'),
        ('companies', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, max_digits=15)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='plan_updates',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'subscription_plan'},
        ),
        migrations.CreateModel(
            name='CompanySubscriptionDebt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('partial', 'Partial'), ('paid', 'Paid'), ('overdue', 'Overdue')],
                    default='pending',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subscription_debts',
                    to='companies.company',
                )),
            ],
            options={'db_table': 'company_subscription_debts', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='CompanySubscriptionPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=15)),
                ('paid_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subscription_payments',
                    to='companies.company',
                )),
                ('debt', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payments',
                    to='superadmin_panel.companysubscriptiondebt',
                )),
                ('recorded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='recorded_subscription_payments',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'company_subscription_payments', 'ordering': ['-paid_at']},
        ),
    ]
