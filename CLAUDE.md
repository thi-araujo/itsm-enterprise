# ITSM Enterprise — Instruções para o Claude Code

Este arquivo é lido automaticamente pelo Claude Code a cada sessão.
Mantenha-o curto e atualizado. Detalhes longos ficam em `docs/`.

## Sobre o projeto
- **Nome oficial:** ITSM Enterprise (Help Desk corporativo inspirado no ServiceNow)
- **Autor:** Thiago — Analista de Infraestrutura, desenvolvedor Python iniciante
- **Stack:** Python 3.13 · Django 6.0 · Django REST Framework · SQLite (dev) → PostgreSQL (prod) · Bootstrap 5 · HTMX · Chart.js
- **Sistema operacional de desenvolvimento:** Windows 11 + PowerShell + PyCharm
- **Roadmap completo:** ver @docs/ROADMAP.md
- **Status de cada fase:** ver @docs/STATUS.md
- **Automações de SLA e agendamento:** ver @docs/AUTOMACAO_SLA.md
- **API REST:** ver @docs/API.md
- **Integração AD/LDAP:** ver @docs/AD_LDAP.md
- **E-mail (quem recebe o quê, SMTP):** ver @docs/EMAIL.md

## Regras obrigatórias
1. O nome do sistema é **ITSM Enterprise**. A palavra "RAVEN" (e variações `raven`, `Raven`) NÃO deve existir em nenhum arquivo, classe CSS, variável, template, e-mail ou comentário.
2. Todo texto voltado ao usuário (labels, mensagens, e-mails) e todos os comentários de código em **português brasileiro**.
3. Nomes de variáveis, funções, classes e campos de model em **inglês** (padrão Django).
4. Antes de alterar models, leia o model atual. Após alterar: `python manage.py makemigrations` → `python manage.py migrate` → `python manage.py check`.
5. Nunca apague `db.sqlite3`, pastas `migrations/` ou `media/` sem pedir confirmação.
6. Nunca edite migrações já aplicadas; crie novas.
7. Antes de tarefas grandes, apresente um plano e aguarde aprovação.
8. Ao terminar cada tarefa, informe: arquivos criados, arquivos alterados, comandos que o Thiago precisa rodar e como testar no navegador.
9. Explique as mudanças de forma didática — o autor está aprendendo Django.

## Comandos do projeto (PowerShell)
```powershell
.\venv\Scripts\Activate.ps1                 # ativar ambiente virtual
pip install -r requirements.txt             # instalar dependências
python manage.py check                      # validar o projeto
python manage.py makemigrations             # gerar migrações
python manage.py migrate                    # aplicar migrações
python manage.py runserver 0.0.0.0:8000     # rodar acessível na rede local
python manage.py check_sla                  # automações de SLA (aviso, vencimento, escalonamento)
python manage.py check_sla --dry-run        # mostra o que faria, sem gravar
python manage.py ldap_check                 # diagnóstico da conexão com o AD
python manage.py ldap_check --user joao.silva   # testa o login e lista os grupos
python manage.py sendtestemail voce@exemplo.com  # confere o envio de e-mail
python manage.py createsuperuser            # criar admin
```

## Arquitetura alvo
```
itsm_enterprise/
├── manage.py
├── CLAUDE.md
├── requirements.txt
├── itsm_project/          # settings.py, urls.py, wsgi.py
├── apps/
│   ├── accounts/          # usuários, perfis, autenticação, RBAC
│   ├── tickets/           # chamados, categorias, status, SLA, comentários, anexos
│   ├── cmdb/              # ativos de TI
│   ├── notifications/     # notificações internas e e-mails
│   ├── reports/           # relatórios
│   ├── dashboard/         # painel principal
│   └── api/               # API REST (serializers, viewsets) — prefixo /api/v1/
├── templates/             # base.html + uma pasta por app + partials/
├── static/                # css/, js/, img/
└── media/                 # uploads (anexos)
```

## Convenções Django
- Toda view exige `@login_required` (ou mixin equivalente).
- Views HTMX: checar `request.htmx` e devolver um template de `templates/partials/`.
- Feedback ao usuário via `django.contrib.messages`.
- Cada app tem `urls.py` com `app_name` definido; usar sempre `{% url 'app:nome' %}`.
- Ao mover apps para `apps/`, o `AppConfig` deve ter `name = 'apps.<app>'` e **manter `label = '<app>'`** para não quebrar migrações, tabelas e ForeignKeys existentes.
- Regra de negócio que muda o estado de um chamado (finalizar, escalonar, aprovar,
  comentar) vive em `apps/tickets/services.py`, **nunca** na view nem no serializer:
  a tela HTML e a API REST chamam a mesma função. As funções levantam
  `ValidationError`; cada camada traduz (a view para `messages`, a API para HTTP 400).
- Autenticação: `AUTHENTICATION_BACKENDS` tem o LDAP na frente e o
  `ModelBackend` atrás, nessa ordem — o controlador de domínio cair não pode
  trancar ninguém fora. Senha de conta do AD **nunca** é gravada no Django.
- Credencial de serviço e qualquer segredo: só por variável de ambiente
  (`ITSM_*`), nunca em arquivo versionado.
- Upload permitido: .pdf .doc .docx .xls .xlsx .png .jpg .jpeg .txt .log .zip — máx. 10 MB.
- SLA por prioridade: Crítica 2h · Alta 8h · Média 24h · Baixa 72h.
- Ticket sem técnico (`assignee` nulo) deve funcionar em TODOS os templates: use `{% if ticket.assignee %}` em vez de encadear `|default` sobre atributos de objeto nulo.

## Identidade visual
- Tema escuro, fonte Sora (texto) e JetBrains Mono (IDs/números).
- Variáveis CSS com prefixo `--itsm-` e classes com prefixo `itsm-` (ex.: `itsm-card`, `btn-itsm`).

## Lições já aprendidas neste projeto
- Templates com `{% block %}` sem `{% endblock %}` quebram a página inteira — conferir o fechamento.
- Formulário com anexo precisa de `enctype="multipart/form-data"` e `request.FILES` na view.
- Todo app incluído em `itsm_project/urls.py` precisa ter `urls.py` próprio, mesmo vazio.
