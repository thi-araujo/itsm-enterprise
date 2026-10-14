from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'apps.accounts'
    label = 'accounts'
    verbose_name = 'Contas e Perfis'

    def ready(self):
        # Importar aqui (e não no models.py) evita import circular.
        from . import signals  # noqa: F401
        # Avisos de configuração do LDAP no `manage.py check` (Fase 3.8).
        from . import checks   # noqa: F401
