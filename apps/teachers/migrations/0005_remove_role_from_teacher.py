from django.db import migrations


class Migration(migrations.Migration):
    """
    role field was added and immediately removed before any production deploy.
    This no-op migration keeps the chain clean from 0004.
    """

    dependencies = [
        ('teachers', '0004_add_birth_date_and_decimal_hours'),
    ]

    operations = []
