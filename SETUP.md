# RAVEN ITSM — Guia de Setup

## Pré-requisitos
- Python 3.11+
- pip

---

## 1. Criar e ativar ambiente virtual

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

## 2. Instalar dependências

```bash
pip install -r requirements.txt
```

## 3. Aplicar migrações (cria o banco SQLite)

```bash
python manage.py makemigrations
python manage.py migrate
```

## 4. Carregar dados de exemplo

```bash
python manage.py shell < seed_data.py
```

## 5. Rodar o servidor

```bash
python manage.py runserver
```

Acesse: **http://127.0.0.1:8000**

---

## Credenciais de acesso

| Usuário  | Senha      | Perfil         |
|----------|------------|----------------|
| admin    | admin      | Superusuário   |
| thiago   | thiago123  | Técnico        |

---

## Estrutura do projeto

```
itsm_enterprise/
├── manage.py
├── requirements.txt
├── seed_data.py          ← dados de exemplo
├── db.sqlite3            ← criado após migrate
├── itsm_project/
│   ├── settings.py
│   └── urls.py
├── apps/
│   ├── accounts/         ← login/logout
│   ├── tickets/          ← chamados (core)
│   └── dashboard/        ← painel principal
└── templates/
    ├── base.html
    ├── accounts/
    ├── tickets/
    ├── dashboard/
    └── partials/         ← fragmentos HTMX
```

---

## Próximos passos (Fase 2)

- [ ] SLA com alerta por e-mail
- [ ] Upload de anexos
- [ ] Relatórios em PDF
- [ ] API REST (Django REST Framework)
- [ ] Autenticação LDAP/AD
