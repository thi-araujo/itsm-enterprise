Reorganize os apps Django para dentro da pasta `apps/`, conforme a arquitetura do @CLAUDE.md, SEM perder dados.

Passos obrigatórios:
1. Commit de backup antes de começar.
2. Crie `apps/__init__.py`.
3. Mova accounts, tickets, cmdb, notifications, reports e dashboard para `apps/`.
4. Em cada `apps.py`: `name = 'apps.<app>'` e `label = '<app>'` (manter o label original preserva tabelas e migrações).
5. Atualize `INSTALLED_APPS` para usar `'apps.<app>.apps.<Classe>Config'`.
6. Atualize includes em `itsm_project/urls.py` (`include('apps.tickets.urls')`).
7. Corrija imports entre apps (ex.: `from apps.cmdb.models import Asset`).
8. Rode `python manage.py check` e `python manage.py makemigrations --check --dry-run` — o resultado esperado é "No changes detected".
9. Rode `python manage.py runserver` e confirme que dashboard, tickets, fila, CMDB, relatórios e notificações abrem.
10. Commit: "refactor: move apps para apps/".
