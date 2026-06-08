from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin_panel', '0004_seed_subscription_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='companysubscriptionpayment',
            name='payment_method',
            field=models.CharField(
                choices=[('cash', 'Cash'), ('card', 'Card'), ('transfer', 'Transfer')],
                default='cash',
                max_length=20,
            ),
        ),
    ]
