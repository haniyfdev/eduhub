import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Check and set the Telegram bot webhook URL'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, help='Override BACKEND_URL for this run')
        parser.add_argument('--info', action='store_true', help='Only show current webhook info, do not set')
        parser.add_argument('--delete', action='store_true', help='Delete/clear the webhook')

    def handle(self, *args, **options):
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            self.stderr.write(self.style.ERROR('TELEGRAM_BOT_TOKEN is not set'))
            return

        api = f'https://api.telegram.org/bot{token}'

        # Always show current webhook status
        r = requests.get(f'{api}/getWebhookInfo', timeout=10)
        info = r.json().get('result', {})
        current_url = info.get('url', '')
        pending = info.get('pending_update_count', 0)
        last_err = info.get('last_error_message', '')

        self.stdout.write(f'Current webhook URL : {current_url or "(none)"}')
        self.stdout.write(f'Pending updates     : {pending}')
        if last_err:
            self.stdout.write(self.style.WARNING(f'Last error          : {last_err}'))

        if options['info']:
            return

        if options['delete']:
            r = requests.post(f'{api}/deleteWebhook', timeout=10)
            if r.json().get('result'):
                self.stdout.write(self.style.SUCCESS('Webhook deleted'))
            else:
                self.stderr.write(self.style.ERROR(f'Delete failed: {r.text}'))
            return

        backend_url = options.get('url') or getattr(settings, 'BACKEND_URL', '')
        if not backend_url:
            self.stderr.write(self.style.ERROR('BACKEND_URL is not set. Use --url https://your-render-url.onrender.com'))
            return

        webhook_url = f'{backend_url.rstrip("/")}/api/telegram/webhook/'
        r = requests.post(f'{api}/setWebhook', json={'url': webhook_url}, timeout=10)
        result = r.json()
        if result.get('result'):
            self.stdout.write(self.style.SUCCESS(f'Webhook set to: {webhook_url}'))
        else:
            self.stderr.write(self.style.ERROR(f'setWebhook failed: {result}'))
