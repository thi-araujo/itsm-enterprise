Faça um diagnóstico completo do projeto ITSM Enterprise SEM alterar nenhum arquivo:

1. Liste a estrutura de pastas (ignore venv, __pycache__, media).
2. Leia `itsm_project/settings.py` e `itsm_project/urls.py`.
3. Leia os `models.py` de todos os apps e compare com o descrito em @docs/STATUS.md.
4. Rode `python manage.py check` e `python manage.py showmigrations`.
5. Procure ocorrências de "raven" (sem diferenciar maiúsculas) em todo o projeto e conte por arquivo.
6. Aponte templates que quebram quando `ticket.assignee` é nulo.

Entregue um relatório em português: o que está ok, o que está divergente e uma lista priorizada de correções. Aguarde minha aprovação antes de corrigir.
