from django.db import migrations


def backfill_status(apps, schema_editor):
    Company = apps.get_model('companies', 'Company')
    updated = Company.objects.filter(status__isnull=True).update(status='active')
    print(f'  backfill_company_status: set status=active on {updated} companies')


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0005_add_archived_at_to_company'),
    ]

    operations = [
        migrations.RunPython(backfill_status, migrations.RunPython.noop),
    ]
