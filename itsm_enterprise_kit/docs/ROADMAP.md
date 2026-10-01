# 🗺️ ROADMAP — ITSM Enterprise com Django 6.0 + HTMX + Bootstrap 5

## 📌 FASE 0 — Fundamentos Python + Django (2~3 semanas)
Antes de construir o ITSM, esses conceitos precisam estar no sangue.

**Python básico obrigatório**
- Variáveis, tipos, listas, dicionários
- Funções, classes, herança
- pip, ambientes virtuais (venv)

**Django essencial**
- `models.py` → banco de dados
- `views.py` → lógica
- `urls.py` → rotas
- `templates/` → HTML dinâmico
- Django Admin
- Django ORM (queries)

🎯 **Mini projeto da fase:** cadastro simples de ativos de TI (CRUD completo)

## 📌 FASE 1 — Estrutura Base do ITSM (3~4 semanas)
O coração do sistema.

**Módulos**
- ✅ Autenticação e perfis de usuário (técnico, solicitante, gerente)
- ✅ Criação e listagem de Tickets/Chamados
- ✅ Categorias e prioridades (Baixa, Média, Alta, Crítica)
- ✅ Status do chamado (Aberto → Em andamento → Resolvido → Fechado)
- ✅ Dashboard básico

**Stack em uso:** Django + SQLite · Bootstrap 5 para o layout · HTMX para atualizar partes da página sem reload

🎯 **Entrega da fase:** sistema abrindo chamado e mudando status em tempo real via HTMX

## 📌 FASE 2 — Funcionalidades Corporativas (4~5 semanas)
Aqui o ITSM começa a parecer com o ServiceNow.
- 📋 SLA — prazo de atendimento por prioridade com alerta de vencimento
- 👥 Fila de atendimento — atribuição automática ou manual por técnico
- 💬 Comentários internos e públicos no chamado
- 📎 Anexos — upload de arquivos no chamado
- 📧 Notificações por e-mail (Django + SMTP)
- 🏷️ CMDB básico — catálogo de ativos vinculados ao chamado
- 📊 Relatórios simples — chamados por período, técnico, categoria

## 📌 FASE 3 — Nível Especialista (ongoing)
Funcionalidades avançadas que diferenciam um ITSM profissional.
- 🔐 RBAC — controle de acesso por papel (Role-Based Access Control)
- 🔄 Workflows — fluxos de aprovação (ex.: chamados de acesso precisam de aprovação do gerente)
- 📡 API REST (Django REST Framework) — integração com outros sistemas
- 🔍 Auditoria — log de todas as ações no chamado
- 📈 Dashboard avançado com gráficos (Chart.js ou Plotly)
- 🤖 Automações — escalonamento automático por SLA vencido
- 🔗 Integração com AD/LDAP — autenticação corporativa

## 🧱 Arquitetura do Projeto
```
itsm_project/
├── manage.py
├── itsm_project/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/       # Usuários, perfis, autenticação
│   ├── tickets/        # Chamados, categorias, status, SLA
│   ├── cmdb/           # Ativos de TI
│   ├── notifications/  # E-mails e alertas
│   └── reports/        # Relatórios e dashboard
├── templates/
├── static/
│   ├── css/
│   └── js/
└── requirements.txt
```

## 🛠️ Stack Completa
| Camada | Tecnologia |
|---|---|
| Backend | Django 6.0 |
| Banco | SQLite (dev) → PostgreSQL (produção) |
| Frontend | Bootstrap 5 + HTMX |
| Gráficos | Chart.js |
| E-mail | Django SMTP / SendGrid |
| API | Django REST Framework |
| Autenticação | Django Auth + django-allauth |
