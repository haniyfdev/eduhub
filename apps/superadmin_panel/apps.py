from django.apps import AppConfig


class SuperadminPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.superadmin_panel'

    def ready(self):
        import apps.superadmin_panel.signals  # noqa
