from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0003_alter_expense_description'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expense',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
    ]
