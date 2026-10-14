"""Backend de autenticação pelo Active Directory (Fase 3.8).

Um "backend de autenticação" é uma classe que o Django consulta quando alguém
tenta entrar. O `settings.AUTHENTICATION_BACKENDS` é uma **lista**: o Django
chama um por um, na ordem, até algum devolver um usuário. Aqui a ordem é

    1. LdapBackend     (este arquivo)  — senha conferida no AD
    2. ModelBackend    (o do Django)   — senha conferida no banco local

Essa cadeia é o que garante que o controlador de domínio cair não tranque
ninguém fora: as contas locais (`admin`, as de teste) continuam entrando pelo
segundo backend.

O que acontece no primeiro login de alguém do AD
------------------------------------------------
O usuário não existe no banco do Django ainda. Ele é criado na hora, com nome,
e-mail e departamento vindos do diretório, e com o papel deduzido dos grupos de
que ele participa. Isso se chama provisionamento *just-in-time*: não há
importação em massa do AD, e quem nunca entrar no sistema nunca ocupa uma linha.
"""

import logging

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.utils import timezone

from .ldap_client import LdapIndisponivel, autenticar
from .models import UserProfile

logger = logging.getLogger(__name__)


class LdapBackend(ModelBackend):
    """Autentica no AD e espelha o usuário no banco do Django.

    Herda de `ModelBackend` só para reaproveitar `get_user()` e a checagem de
    permissões — o método `authenticate()`, que é o que importa, é todo
    reescrito aqui.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not settings.LDAP_ENABLED:
            # Desligado: sai na hora, sem abrir socket nem esperar timeout.
            return None

        # O formulário de login do Django manda `username`, mas outros
        # caminhos (ex.: o `authenticate()` chamado na mão) podem usar o nome
        # do campo configurado em USERNAME_FIELD.
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or not password:
            return None

        try:
            dados = autenticar(username, password)
        except LdapIndisponivel as erro:
            # Não é "senha errada": é o AD inacessível. Devolvendo None, o
            # Django segue para o ModelBackend e o login local ainda funciona.
            logger.warning('LDAP indisponível (%s): seguindo para a '
                           'autenticação local.', erro)
            return None

        if dados is None:
            return None

        user = self._sincronizar(dados)
        # Conta desativada no Django não entra, mesmo com a senha certa no AD.
        if not self.user_can_authenticate(user):
            logger.info('LDAP: %s autenticou no AD mas está inativo no ITSM.',
                        user.username)
            return None
        return user

    # ──────────────────────────────────────────────────────────────
    # Espelho no banco
    # ──────────────────────────────────────────────────────────────

    def _sincronizar(self, dados):
        """Cria ou atualiza o `User` e o `UserProfile` a partir do AD."""
        user, criado = self._obter_ou_criar(dados.username)

        if criado:
            # A senha do AD **não** é guardada aqui. Sem isto, uma cópia do
            # hash ficaria no db.sqlite3 e trocar a senha no domínio não
            # revogaria o acesso ao ITSM.
            user.set_unusable_password()
            logger.info('LDAP: criando usuário %s no primeiro login.',
                        user.username)

        user.first_name = dados.first_name or user.first_name
        user.last_name  = dados.last_name or user.last_name
        user.email      = dados.email or user.email
        user.save()

        self._sincronizar_perfil(user, dados, criado)
        return user

    def _obter_ou_criar(self, username):
        """Busca o usuário **sem diferenciar maiúsculas** e cria se faltar.

        O `sAMAccountName` do AD não diferencia caixa, mas o `username` do
        Django sim. Sem o `iexact`, o AD devolvendo `Thiago` criaria um segundo
        usuário ao lado do `thiago` que já existe — duas contas, dois conjuntos
        de chamados, mesma pessoa.
        """
        existente = User.objects.filter(username__iexact=username).first()
        if existente:
            return existente, False
        # O signal de accounts/signals.py cria o UserProfile junto.
        return User.objects.create(username=username), True

    def _sincronizar_perfil(self, user, dados, criado):
        # Pelo `user.profile`, e não por uma consulta nova: o signal que cria o
        # perfil já deixou a instância pendurada no `user`. Buscando outra
        # cópia do mesmo registro, as alterações iriam para o banco mas quem
        # lesse `user.profile` depois veria os valores antigos.
        try:
            perfil = user.profile
        except UserProfile.DoesNotExist:
            perfil = UserProfile.objects.create(user=user)

        papel = papel_para_grupos(dados.groups)

        if papel is not None:
            # Um grupo do AD casou: o diretório é a autoridade.
            perfil.role = papel
        elif criado:
            # Ninguém casou e o usuário é novo: entra com o menor privilégio.
            perfil.role = settings.LDAP_DEFAULT_ROLE

        # Usuário que já existia e não casa com nenhum grupo mantém o papel
        # que tem. Sem esta regra, o `thiago` (Administrador criado à mão)
        # seria rebaixado a Solicitante no primeiro login pelo AD.

        if dados.department:
            perfil.department = dados.department

        perfil.from_ldap      = True
        perfil.ldap_last_sync = timezone.now()
        perfil.save()
        return perfil


def papel_para_grupos(grupos):
    """Traduz os grupos do AD no papel do ITSM, ou None se nenhum casar.

    O `LDAP_GROUP_ROLE_MAP` é uma **lista ordenada**, não um dicionário: o
    primeiro grupo que casar vence, então o mapeamento deve começar pelo papel
    mais privilegiado. Quem está em "ITSM-Admins" e em "ITSM-Tecnicos" ao mesmo
    tempo precisa sair daqui como Administrador, e não depender da ordem em que
    o AD devolveu os grupos.

    A comparação ignora maiúsculas porque nome de grupo no AD não diferencia
    caixa, e ninguém deveria perder o acesso por ter digitado `ITSM-admins`.
    """
    presentes = {str(g).casefold() for g in grupos}
    for grupo, papel in settings.LDAP_GROUP_ROLE_MAP:
        if grupo.casefold() in presentes:
            return papel
    return None
