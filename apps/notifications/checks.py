"""Verificações do `manage.py check` para a configuração de e-mail.

Mesma ideia das verificações de LDAP (`apps/accounts/checks.py`): configuração
de e-mail errada só aparece quando alguém abre um chamado e o aviso não chega —
e aí a causa está num log, não na tela. Aqui ela aparece no terminal de quem
sobe o sistema.

Um erro de SMTP não interrompe o chamado (ver `_send_email`), o que é a decisão
certa — mas também significa que o silêncio é o sintoma. Por isso estes avisos.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register

CONSOLE = 'django.core.mail.backends.console.EmailBackend'
SMTP = 'django.core.mail.backends.smtp.EmailBackend'


def _dominio(endereco):
    return endereco.rsplit('@', 1)[-1].lower() if '@' in endereco else ''


@register('email')
def verificar_configuracao_de_email(app_configs, **kwargs):
    avisos = []

    if settings.EMAIL_BACKEND == CONSOLE:
        # Não é um defeito: é o padrão de desenvolvimento. Mas vale dizer em
        # voz alta, porque "abri o chamado e não recebi o e-mail" é
        # exatamente o que acontece aqui, e a causa não é óbvia.
        avisos.append(Warning(
            'E-mail em modo console: nenhuma mensagem sai da máquina.',
            hint='As mensagens são impressas no terminal do runserver. '
                 'Para enviar de verdade, defina ITSM_EMAIL_HOST no .env '
                 '(ver docs/EMAIL.md).',
            id='email.W001',
        ))
        return avisos

    if settings.EMAIL_BACKEND != SMTP:
        # `locmem` (a suíte de testes), `dummy` ou um backend próprio. Checar
        # host, usuário e senha aí não faz sentido: não há SMTP nenhum. Sem
        # esta saída, todo `manage.py test` imprimiria avisos falsos.
        return avisos

    if getattr(settings, 'EMAIL_USE_TLS', False) and \
       getattr(settings, 'EMAIL_USE_SSL', False):
        # O Django levanta exceção no envio, que o `_send_email` registra e
        # engole — o chamado é criado e o e-mail nunca sai. Melhor barrar aqui.
        avisos.append(Error(
            'EMAIL_USE_TLS e EMAIL_USE_SSL ligados ao mesmo tempo: são '
            'mutuamente exclusivos.',
            hint='Use ITSM_EMAIL_USE_TLS=1 na porta 587 (STARTTLS) ou '
                 'ITSM_EMAIL_USE_SSL=1 na porta 465.',
            id='email.E001',
        ))

    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        avisos.append(Warning(
            'SMTP configurado sem usuário ou sem senha.',
            hint='Defina ITSM_EMAIL_USER e ITSM_EMAIL_PASSWORD. Microsoft 365 '
                 'e Gmail exigem autenticação; sem ela a mensagem é recusada.',
            id='email.W002',
        ))

    remetente = _dominio(settings.DEFAULT_FROM_EMAIL)
    conta = _dominio(settings.EMAIL_HOST_USER)
    if remetente and conta and remetente != conta:
        # Causa clássica de "o código está certo e o e-mail não chega": o
        # provedor recusa remetente que não seja a caixa autenticada.
        avisos.append(Warning(
            f'O remetente ({settings.DEFAULT_FROM_EMAIL}) é de um domínio '
            f'diferente da conta do SMTP ({settings.EMAIL_HOST_USER}).',
            hint='Microsoft 365 e Gmail recusam esse envio, a não ser que a '
                 'conta tenha permissão de "enviar como" esse endereço. '
                 'Deixe ITSM_EMAIL_FROM vazio para usar a própria conta.',
            id='email.W003',
        ))

    if not getattr(settings, 'EMAIL_TIMEOUT', None):
        avisos.append(Warning(
            'SMTP sem timeout: um servidor que não responde pendura a '
            'requisição de quem está abrindo o chamado.',
            hint='Defina ITSM_EMAIL_TIMEOUT (o padrão do projeto é 10s).',
            id='email.W004',
        ))

    return avisos
