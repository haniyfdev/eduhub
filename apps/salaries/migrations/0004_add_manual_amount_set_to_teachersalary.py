from django.db import migrations


class Migration(migrations.Migration):
    """manual_amount_set is now a computed property on the model — no DB column needed."""

    dependencies = [
        ('salaries', '0003_auto'),
    ]

    operations = []
