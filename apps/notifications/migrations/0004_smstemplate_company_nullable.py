import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0001_initial'),
        ('notifications', '0003_smstemplate_update'),
    ]

    operations = [
        migrations.AlterField(
            model_name='smstemplate',
            name='company',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sms_templates',
                to='companies.company',
            ),
        ),
    ]
