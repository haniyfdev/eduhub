from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='schedule',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
