"""Verificações do `manage.py check` para a configuração do LDAP (Fase 3.8).

O Django tem um sistema de checagem que roda a cada `manage.py check`,
`runserver` e `test`. Registrar os avisos aqui é melhor que confiar na
documentação: a configuração perigosa aparece no terminal de quem subir o
sistema, não só para quem leu o `docs/AD_LDAP.md`.

São avisos (`Warning`), não erros — não impedem o projeto de rodar.
"""

from django.conf import settings
from django.core.checks import Warning, register


@register('ldap')
def verificar_configuracao_ldap(app_configs, **kwargs):
    if not settings.LDAP_ENABLED:
        # Desligado: não há o que avisar.
        return []

    avisos = []
    cifrado = settings.LDAP_USE_SSL or settings.LDAP_START_TLS

    if not cifrado:
        avisos.append(Warning(
            'LDAP ligado sem TLS: a senha de domínio dos usuários trafega '
            'em texto claro pela rede.',
            hint=f'A conexão com {settings.LDAP_SERVER}:{settings.LDAP_PORT} '
                 'é LDAP puro. Use a porta 636 (LDAPS) ou ligue '
                 'ITSM_LDAP_START_TLS — ambos exigem um certificado de '
                 'servidor instalado no controlador de domínio.',
            id='ldap.W001',
        ))

    if cifrado and not settings.LDAP_TLS_VALIDATE:
        avisos.append(Warning(
            'LDAP com TLS mas sem validar o certificado do servidor: a '
            'conexão é cifrada, porém não há garantia de estar falando com '
            'o controlador de domínio.',
            hint='Exporte a CA do domínio e aponte o arquivo em '
                 'ITSM_LDAP_CA_CERT_FILE, e então religue '
                 'ITSM_LDAP_TLS_VALIDATE.',
            id='ldap.W002',
        ))

    if not settings.LDAP_SEARCH_BASE:
        avisos.append(Warning(
            'LDAP_SEARCH_BASE está vazio: a busca pelo usuário não vai '
            'encontrar ninguém, e todo login pelo AD vai falhar.',
            hint='Normalmente é o domínio em forma de DN, como '
                 'DC=exemplo,DC=local. O `manage.py ldap_check` lista os '
                 'valores que o servidor aceita.',
            id='ldap.W003',
        ))

    if settings.LDAP_BIND_DN and not settings.LDAP_BIND_PASSWORD:
        avisos.append(Warning(
            'LDAP_BIND_DN preenchido sem LDAP_BIND_PASSWORD: o bind da conta '
            'de serviço seria anônimo e a leitura dos grupos falharia.',
            hint='Defina ITSM_LDAP_BIND_PASSWORD, ou deixe ITSM_LDAP_BIND_DN '
                 'em branco para ler o diretório com a conexão do próprio '
                 'usuário.',
            id='ldap.W004',
        ))

    return avisos
