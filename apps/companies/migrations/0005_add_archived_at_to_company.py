from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0004_add_logo_to_company'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
