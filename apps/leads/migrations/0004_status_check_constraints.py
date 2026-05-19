from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('leads', '0003_data_migration'),
        ('students', '0009_student_archive_reason'),
    ]

    operations = [
        # Fix existing invalid data first
        migrations.RunSQL(
            sql="""
                UPDATE students
                SET status = 'trial'
                WHERE status = 'pending';
            """,
            reverse_sql="",
        ),

        # Leads constraint
        migrations.RunSQL(
            sql="""
                ALTER TABLE leads
                ADD CONSTRAINT leads_status_check
                CHECK (status IN ('pending', 'trial', 'ignored'));
            """,
            reverse_sql="""
                ALTER TABLE leads
                DROP CONSTRAINT IF EXISTS leads_status_check;
            """,
        ),

        # Students constraint
        migrations.RunSQL(
            sql="""
                ALTER TABLE students
                ADD CONSTRAINT students_status_check
                CHECK (status IN ('trial', 'active', 'frozen', 'archived'));
            """,
            reverse_sql="""
                ALTER TABLE students
                DROP CONSTRAINT IF EXISTS students_status_check;
            """,
        ),
    ]
