from django.db import migrations


def seed_subscription_plan(apps, schema_editor):
    SubscriptionPlan = apps.get_model('superadmin_panel', 'SubscriptionPlan')
    if not SubscriptionPlan.objects.exists():
        SubscriptionPlan.objects.create(price=0)


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin_panel', '0003_add_subscription_models'),
    ]

    operations = [
        migrations.RunPython(seed_subscription_plan, migrations.RunPython.noop),
    ]
