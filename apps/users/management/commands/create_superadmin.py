from django.core.management.base import BaseCommand
from apps.users.models import User


class Command(BaseCommand):
    help = 'Create a superadmin user, or update an existing one with --force'

    def add_arguments(self, parser):
        parser.add_argument('--phone', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--first_name', required=True)
        parser.add_argument('--last_name', required=True)
        parser.add_argument('--force', action='store_true',
                            help='Update phone and password if superadmin already exists')

    def handle(self, *args, **options):
        existing = User.objects.filter(role='superadmin').first()

        if existing:
            if not options['force']:
                self.stdout.write('Superadmin already exists. Use --force to update.')
                return
            existing.phone = options['phone']
            existing.first_name = options['first_name']
            existing.last_name = options['last_name']
            existing.set_password(options['password'])
            existing.save()
            self.stdout.write(self.style.SUCCESS(
                f"Superadmin updated: {existing.first_name} {existing.last_name} ({existing.phone})"
            ))
        else:
            User.objects.create_superuser(
                phone=options['phone'],
                password=options['password'],
                first_name=options['first_name'],
                last_name=options['last_name'],
            )
            self.stdout.write(self.style.SUCCESS(
                f"Superadmin created: {options['first_name']} {options['last_name']} ({options['phone']})"
            ))
