"""
Configurações do projeto ITSM Enterprise.
Recriado em 2026-10-01 — a pasta itsm_project/ havia sido perdida
(não existia em disco nem no histórico do git).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ATENÇÃO: chave de desenvolvimento. Troque antes de ir para produção
# e mova para uma variável de ambiente.
SECRET_KEY = 'django-insecure-chave-de-desenvolvimento-nao-use-em-producao'

DEBUG = True

# Permite acesso pela rede local (runserver 0.0.0.0:8000), conforme CLAUDE.md.
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'django_htmx',
    'rest_framework',
    'rest_framework.authtoken',

    'apps.accounts.apps.AccountsConfig',
    'apps.tickets.apps.TicketsConfig',
    'apps.cmdb.apps.CmdbConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.reports.apps.ReportsConfig',
    'apps.dashboard.apps.DashboardConfig',
    'apps.api.apps.ApiConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'itsm_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'itsm_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Em desenvolvimento o WhiteNoise serve direto de static/, sem exigir
# collectstatic (senão avisa "No directory at: staticfiles/").
if DEBUG:
    WHITENOISE_USE_FINDERS = True
    WHITENOISE_AUTOREFRESH = True

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.StaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Upload de anexos (ver CLAUDE.md). Fonte única da política: as views, os
# forms e os templates leem daqui — não duplique a lista em outro lugar.
ALLOWED_UPLOAD_EXTENSIONS = [
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.png', '.jpg', '.jpeg', '.txt', '.log', '.zip',
]
MAX_UPLOAD_SIZE_MB = 10

# Derivados de MAX_UPLOAD_SIZE_MB — alterar só a constante acima.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ──────────────────────────────────────────────────────────────────
# API REST (Fase 3.5) — ver docs/API.md
# ──────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    # Token: o que uma integração externa usa (POST /api/v1/token/).
    # Sessão: permite navegar a API no browser com o login normal.
    #
    # O token vem primeiro de propósito: o DRF monta o desafio de
    # autenticação a partir da primeira classe da lista, e só a de token
    # oferece um. Com a sessão à frente, uma requisição sem credencial
    # receberia 403 ("proibido") em vez de 401 ("não autenticado").
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Nada aberto ao anônimo: sem credencial, 401/403.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    # Uma integração com defeito não derruba o banco.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/min',
        'user': '1000/hour',
    },
}

# ──────────────────────────────────────────────────────────────────
# Automações de SLA (Fase 3.7) — usadas por apps/tickets/automation.py
# e pelo comando `manage.py check_sla`.
#
# As horas de cada prioridade (Crítica 2h · Alta 8h · Média 24h · Baixa 72h)
# ficam no model, em Ticket.sla_hours_for_priority.
# ──────────────────────────────────────────────────────────────────

# Percentual do prazo a partir do qual o chamado é considerado em risco e
# recebe o aviso prévio.
SLA_WARNING_PERCENT = 80

# Liga o escalonamento automático do chamado vencido para um gerente.
# Em False, o comando só avisa e não reatribui ninguém.
SLA_AUTO_ESCALATE = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ──────────────────────────────────────────────────────────────────
# Integração com AD/LDAP (Fase 3.8) — ver docs/AD_LDAP.md
#
# A ordem desta lista importa: o Django tenta um backend por vez, na ordem,
# até algum devolver um usuário. O LDAP vem primeiro; o ModelBackend (senha
# guardada no banco) fica atrás como rede de segurança, para o controlador
# de domínio cair sem trancar ninguém fora do sistema.
# ──────────────────────────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'apps.accounts.ldap_backend.LdapBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Desligado por padrão. Com False, o LdapBackend sai na primeira linha — sem
# socket, sem espera. Ligue depois de validar a configuração com
# `python manage.py ldap_check`.
LDAP_ENABLED = os.environ.get('ITSM_LDAP_ENABLED', '').lower() in ('1', 'true', 'sim')

LDAP_SERVER = os.environ.get('ITSM_LDAP_SERVER', 'dc01.exemplo.local')
LDAP_DOMAIN = os.environ.get('ITSM_LDAP_DOMAIN', 'exemplo.local')
LDAP_SEARCH_BASE = os.environ.get('ITSM_LDAP_SEARCH_BASE', 'DC=exemplo,DC=local')

# 636 = LDAPS (TLS desde o primeiro byte). 389 é LDAP puro, e num bind simples
# as credenciais vão **em texto claro** pela rede — legíveis em qualquer
# captura de pacotes. Use 389 apenas com LDAP_START_TLS = True.
LDAP_PORT = int(os.environ.get('ITSM_LDAP_PORT', '636'))
LDAP_USE_SSL = LDAP_PORT == 636
LDAP_START_TLS = os.environ.get('ITSM_LDAP_START_TLS', '').lower() in ('1', 'true', 'sim')

# Validar o certificado do DC é o padrão. Certificado de AD normalmente é
# emitido por uma CA interna, que o Windows conhece e o Python não: exporte-a
# e aponte o arquivo em LDAP_CA_CERT_FILE. Desligar a validação conecta de
# qualquer jeito, mas aceita qualquer servidor que se diga o DC.
LDAP_TLS_VALIDATE = os.environ.get('ITSM_LDAP_TLS_VALIDATE', '1') != '0'
LDAP_CA_CERT_FILE = os.environ.get('ITSM_LDAP_CA_CERT_FILE', '')

# Segundos. Baixo de propósito: este tempo é esperado na tela de login quando
# o DC não responde.
LDAP_TIMEOUT = int(os.environ.get('ITSM_LDAP_TIMEOUT', '5'))

# Conta de serviço — opcional. Em branco (o padrão), a leitura dos atributos
# é feita com a conexão do próprio usuário que está entrando, o que dispensa
# guardar qualquer credencial. Se o seu AD restringir essa leitura, preencha
# por **variável de ambiente**: senha de serviço não entra em arquivo
# versionado.
LDAP_BIND_DN = os.environ.get('ITSM_LDAP_BIND_DN', '')
LDAP_BIND_PASSWORD = os.environ.get('ITSM_LDAP_BIND_PASSWORD', '')

# `{username}` é substituído pelo que a pessoa digitou (já escapado).
# `sAMAccountName` é o nome de logon curto do AD — o mesmo que ela usa no
# Windows.
LDAP_USER_FILTER = '(&(objectClass=user)(sAMAccountName={username}))'

# Grupo do AD → papel do ITSM. Lista **ordenada**: o primeiro que casar vence,
# então o papel mais privilegiado vem primeiro.
#
# Nomes conferidos no domínio exemplo.local em 14/10/2026 com
# `manage.py ldap_check --user joao.silva`. Para ver os grupos de outra
# conta, rode o mesmo comando com ela.
LDAP_GROUP_ROLE_MAP = [
    ('GRP-Admins',     'admin'),
    ('Domain Admins',  'admin'),
    ('GRP-Managers',   'manager'),     # ainda não existe no AD — criar
    ('GRP-Technical',  'technician'),
]
# Os demais grupos do domínio (GRP-Geral, GRP-Arquivos, GRP-Documentos,
# GRP-Cofre) ficaram fora de propósito: não são papéis de atendimento, e
# qualquer grupo não listado aqui simplesmente não concede privilégio —
# a pessoa entra como LDAP_DEFAULT_ROLE.

# Papel de quem autentica no AD mas não está em nenhum grupo do mapa.
# Solicitante é o menor privilégio.
LDAP_DEFAULT_ROLE = 'requester'

# Seguir grupos aninhados (grupo que é membro de outro grupo). Custa uma
# consulta a mais por login; ligue se a sua estrutura de grupos usa
# aninhamento.
LDAP_NESTED_GROUPS = False

# Autenticação — nomes de URL definidos em accounts/urls.py e dashboard/urls.py.
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:index'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Log no console. Importante: as notificações rodam dentro de try/except nas
# views (uma falha de e-mail não deve impedir a criação do ticket), então sem
# log essas exceções desapareceriam silenciosamente.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simples': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simples',
        },
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {
        'apps': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

# E-mail: em desenvolvimento, as mensagens aparecem no console.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'itsm-enterprise@exemplo.local'
