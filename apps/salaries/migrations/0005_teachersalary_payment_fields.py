from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('salaries', '0004_merge_20260503_1827'),
    ]

    operations = [
        migrations.AddField(
            model_name='teachersalary',
            name='calculated_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='teachersalary',
            name='paid_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='teachersalary',
            name='carry_over',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='teachersalary',
            name='status',
            field=models.CharField(
                choices=[('unpaid', 'Unpaid'), ('partial', 'Partial'), ('paid', 'Paid')],
                default='unpaid',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='teachersalary',
            name='is_paid',
            field=models.BooleanField(default=False),
        ),
        # Back-fill calculated_amount from existing total_amount
        migrations.RunSQL(
            sql='UPDATE teacher_salaries SET calculated_amount = total_amount WHERE calculated_amount = 0',
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Mark existing paid records
        migrations.RunSQL(
            sql="UPDATE teacher_salaries SET is_paid = TRUE, status = 'paid', paid_amount = calculated_amount WHERE paid_at IS NOT NULL",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
