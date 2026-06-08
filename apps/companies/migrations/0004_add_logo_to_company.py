from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0003_auto'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='logo',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
