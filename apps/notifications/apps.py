from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "apps.notifications"
    label = "notifications"

    def ready(self):
        # Avisos de configuração de e-mail no `manage.py check`.
        from . import checks  # noqa: F401
