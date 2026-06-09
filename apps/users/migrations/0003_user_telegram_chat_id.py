from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_phone_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='telegram_chat_id',
            field=models.BigIntegerField(null=True, blank=True),
        ),
    ]
