from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api'
    # Mantém o label curto, como nos outros apps (ver CLAUDE.md).
    label = 'api'
    verbose_name = 'API REST'
