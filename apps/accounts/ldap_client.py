"""Conversa com o Active Directory via LDAP (Fase 3.8).

Este módulo é a **única** parte do projeto que sabe o que é LDAP. O backend de
autenticação (`ldap_backend.py`) só recebe daqui um objeto `UsuarioLdap` e
decide o que fazer com ele no banco do Django. Essa separação é o que torna a
fase testável: os testes trocam a função `autenticar` por uma falsa e
exercitam todas as regras de mapeamento sem precisar de um servidor de verdade.

Por que `ldap3` e não `django-auth-ldap`
----------------------------------------
O caminho mais comum no Django é `django-auth-ldap`, que depende de
`python-ldap` — uma extensão escrita em C. Nesta máquina ela não compila (não
há wheel para Windows/Python 3.14 e falta o Visual Studio Build Tools), então
usamos `ldap3`, que é Python puro e instala em qualquer lugar.

Sobre a credencial de serviço
-----------------------------
Por padrão **não é necessária**: fazemos o bind com o próprio usuário que está
entrando e, já autenticados como ele, lemos os atributos e os grupos dele — um
usuário de domínio comum tem permissão de leitura no diretório. Se o seu AD
restringir essa leitura, preencha `LDAP_BIND_DN` e `LDAP_BIND_PASSWORD` por
variável de ambiente (nunca no arquivo versionado).
"""

import logging
import ssl

from django.conf import settings

logger = logging.getLogger(__name__)


class LdapIndisponivel(Exception):
    """O servidor não respondeu: fora do ar, rede, DNS, TLS.

    Distinto de "senha errada": aqui não sabemos se a credencial é válida, e
    quem chama deve seguir para o próximo backend em vez de recusar o login.
    """


class UsuarioLdap:
    """O que o AD contou sobre o usuário.

    Não é um model — nada vai ao banco aqui; quem grava é o `ldap_backend`.
    """

    def __init__(self, username, first_name='', last_name='', email='',
                 department='', groups=None, dn=''):
        self.username   = username
        self.first_name = first_name
        self.last_name  = last_name
        self.email      = email
        self.department = department
        self.groups     = list(groups or [])
        self.dn         = dn

    def __repr__(self):
        return f'<UsuarioLdap {self.username} grupos={self.groups}>'


# Atributos que pedimos ao AD. Pedir só o necessário mantém a resposta pequena
# e deixa explícito, para quem lê, de onde vem cada campo do perfil.
ATRIBUTOS = ['sAMAccountName', 'givenName', 'sn', 'mail', 'department',
             'displayName', 'memberOf']

# OID do "matching rule in chain" do AD: faz o servidor seguir a cadeia de
# grupos aninhados (grupo dentro de grupo). Sem ele, `memberOf` traz apenas os
# grupos diretos — e alguém que é Técnico por estar num grupo que *pertence* ao
# grupo de técnicos ficaria de fora.
REGRA_GRUPOS_ANINHADOS = '1.2.840.113556.1.4.1941'


def _desescapar_rdn(valor):
    """Desfaz o escape de um valor de DN (RFC 4514).

    O AD devolve `Suporte\\, Nível 2` quando o nome do grupo tem vírgula, e
    `\\C3\\A9` para alguns acentos. Comparar isso com o nome escrito no
    `LDAP_GROUP_ROLE_MAP` só funciona depois de desfazer o escape.

    Os pares hexadecimais são juntados em `bytes` antes de decodificar, porque
    um caractere acentuado em UTF-8 ocupa dois pares — decodificar um por vez
    produziria lixo.
    """
    from string import hexdigits

    saida = bytearray()
    i = 0
    while i < len(valor):
        caractere = valor[i]
        if caractere == '\\' and i + 1 < len(valor):
            par = valor[i + 1:i + 3]
            if len(par) == 2 and all(d in hexdigits for d in par):
                saida.append(int(par, 16))
                i += 3
                continue
            saida.extend(valor[i + 1].encode('utf-8'))
            i += 2
            continue
        saida.extend(caractere.encode('utf-8'))
        i += 1
    return saida.decode('utf-8', errors='replace')


def _nome_do_grupo(dn):
    """Extrai o nome do grupo do DN completo.

    De `CN=ITSM-Tecnicos,OU=Grupos,DC=exemplo,DC=local` sai `ITSM-Tecnicos`.
    Usa o parser do próprio `ldap3` em vez de `split(',')` porque um nome de
    grupo pode conter vírgula escapada, e o split cortaria o nome no meio.
    """
    from ldap3.utils.dn import parse_dn
    try:
        return _desescapar_rdn(parse_dn(str(dn))[0][1])
    except Exception:
        logger.warning('LDAP: não consegui ler o nome do grupo em %r', dn)
        return str(dn)


def _primeiro(entrada, atributo):
    """Lê um atributo do resultado do ldap3, que devolve lista ou escalar."""
    valor = entrada.get(atributo)
    if isinstance(valor, (list, tuple)):
        valor = valor[0] if valor else ''
    if valor is None:
        return ''
    return str(valor).strip()


def _escapar(valor):
    """Escapa o que o usuário digitou antes de montar o filtro LDAP.

    Sem isto, um username como `*` casaria com qualquer conta e um `)`
    quebraria o filtro — é a mesma classe de problema que SQL injection,
    aplicada a LDAP.
    """
    from ldap3.utils.conv import escape_filter_chars
    return escape_filter_chars(valor)


def _servidor(com_info=False):
    """Monta o objeto `Server` do ldap3 a partir do settings.

    `com_info` pede ao servidor o RootDSE e o esquema — informação útil no
    diagnóstico, e peso morto numa autenticação, que acontece a cada login.
    """
    from ldap3 import ALL, NONE, Server, Tls

    tls = None
    if settings.LDAP_USE_SSL or settings.LDAP_START_TLS:
        # CERT_REQUIRED valida o certificado do controlador de domínio; é o
        # padrão de propósito. Certificado de AD costuma ser emitido por uma
        # CA interna: aponte-a em LDAP_CA_CERT_FILE. Desligar a validação faz
        # a conexão funcionar, mas aceita qualquer servidor que se diga o DC.
        tls = Tls(
            validate=ssl.CERT_REQUIRED if settings.LDAP_TLS_VALIDATE else ssl.CERT_NONE,
            ca_certs_file=settings.LDAP_CA_CERT_FILE or None,
        )

    return Server(
        settings.LDAP_SERVER,
        port=settings.LDAP_PORT,
        use_ssl=settings.LDAP_USE_SSL,
        tls=tls,
        get_info=ALL if com_info else NONE,
        connect_timeout=settings.LDAP_TIMEOUT,
    )


def _conectar(usuario_bind, senha_bind):
    """Abre a conexão e faz o bind.

    Devolve a `Connection`, ou None se a credencial foi recusada. Levanta
    `LdapIndisponivel` se o servidor não respondeu.
    """
    from ldap3 import Connection
    from ldap3.core.exceptions import LDAPException

    try:
        conexao = Connection(
            _servidor(),
            user=usuario_bind,
            password=senha_bind,
            # Sem isto o ldap3 levanta exceção em vez de devolver False, e
            # "senha errada" viraria um erro 500 na tela de login.
            raise_exceptions=False,
            receive_timeout=settings.LDAP_TIMEOUT,
        )
        if settings.LDAP_START_TLS and not settings.LDAP_USE_SSL:
            conexao.open()
            conexao.start_tls()
        if not conexao.bind():
            # Credencial recusada — o resultado traz o motivo do AD (senha
            # errada, conta expirada, conta desabilitada...).
            logger.info('LDAP: bind recusado para %s (%s)',
                        usuario_bind, conexao.result.get('description'))
            return None
        return conexao
    except LDAPException as erro:
        raise LdapIndisponivel(str(erro)) from erro
    except OSError as erro:
        # Socket, DNS, TLS: alguns desses o ldap3 deixa passar direto.
        raise LdapIndisponivel(str(erro)) from erro


def _fechar(conexao):
    if conexao is None:
        return
    try:
        conexao.unbind()
    except Exception:
        pass


def _montar_upn(username):
    """Transforma `thiago` em `thiago@exemplo.local`.

    O AD aceita bind simples com o UPN, que é o que a pessoa digita no Windows.
    Se ela já digitou `thiago@exemplo.local` ou a forma com barra invertida,
    deixamos como está — ela sabe o que está fazendo.
    """
    if '@' in username or '\\' in username:
        return username
    dominio = settings.LDAP_DOMAIN
    return f'{username}@{dominio}' if dominio else username


def _buscar_usuario(conexao, username):
    """Procura a conta pelo `sAMAccountName`.

    Devolve `(atributos, dn)` ou `(None, '')`.
    """
    from ldap3 import SUBTREE

    filtro = settings.LDAP_USER_FILTER.format(username=_escapar(username))
    conexao.search(
        search_base=settings.LDAP_SEARCH_BASE,
        search_filter=filtro,
        search_scope=SUBTREE,
        attributes=ATRIBUTOS,
    )
    if not conexao.entries:
        return None, ''
    entrada = conexao.entries[0]
    return entrada.entry_attributes_as_dict, str(entrada.entry_dn)


def _grupos_aninhados(conexao, dn_do_usuario):
    """Todos os grupos do usuário, inclusive por aninhamento.

    Pergunta ao AD "quais grupos têm este usuário na cadeia de membros?" usando
    o matching rule in chain. É uma consulta a mais, por isso fica atrás do
    `LDAP_NESTED_GROUPS`.
    """
    from ldap3 import SUBTREE

    filtro = (f'(&(objectClass=group)'
              f'(member:{REGRA_GRUPOS_ANINHADOS}:={_escapar(dn_do_usuario)}))')
    conexao.search(
        search_base=settings.LDAP_SEARCH_BASE,
        search_filter=filtro,
        search_scope=SUBTREE,
        attributes=['cn'],
    )
    return [str(entrada.cn) for entrada in conexao.entries]


def autenticar(username, password):
    """Valida a credencial no AD e devolve um `UsuarioLdap`, ou None.

    None = credencial recusada ou conta não encontrada na base de busca.
    `LdapIndisponivel` = não foi possível falar com o servidor.
    """
    if not username or not password:
        # Bind com senha vazia é um **bind anônimo**, que o AD aceita — e a
        # autenticação "passaria" com a senha em branco. Barrado aqui.
        return None

    conexao = _conectar(_montar_upn(username), password)
    if conexao is None:
        return None

    conexao_servico = None
    try:
        # A leitura dos dados usa a conexão do próprio usuário, a não ser que
        # uma conta de serviço tenha sido configurada.
        leitura = conexao
        if settings.LDAP_BIND_DN:
            conexao_servico = _conectar(settings.LDAP_BIND_DN,
                                        settings.LDAP_BIND_PASSWORD)
            if conexao_servico is None:
                # A senha do usuário estava certa (o bind acima passou); quem
                # está errada é a credencial de serviço. Avisar alto: isto é
                # erro de configuração, não de quem está tentando entrar.
                logger.error('LDAP: credencial de serviço (LDAP_BIND_DN) '
                             'recusada pelo servidor.')
                raise LdapIndisponivel('credencial de serviço recusada')
            leitura = conexao_servico

        entrada, dn = _buscar_usuario(leitura, username)
        if entrada is None:
            # Bind passou mas não achamos a conta: base de busca errada, ou o
            # usuário está fora dela. Não é "senha errada" — por isso o aviso.
            logger.warning('LDAP: %s autenticou mas não foi encontrado em %s',
                           username, settings.LDAP_SEARCH_BASE)
            return None

        grupos = [_nome_do_grupo(g) for g in (entrada.get('memberOf') or [])]
        if settings.LDAP_NESTED_GROUPS and dn:
            grupos = _grupos_aninhados(leitura, dn)

        return UsuarioLdap(
            username=_primeiro(entrada, 'sAMAccountName') or username,
            first_name=_primeiro(entrada, 'givenName'),
            last_name=_primeiro(entrada, 'sn'),
            email=_primeiro(entrada, 'mail'),
            department=_primeiro(entrada, 'department'),
            groups=grupos,
            dn=dn,
        )
    finally:
        _fechar(conexao)
        _fechar(conexao_servico)


def testar_conexao():
    """Abre a conexão sem autenticar ninguém, para o `manage.py ldap_check`.

    Devolve `(True, informação_do_servidor)` ou `(False, mensagem_de_erro)`.
    """
    from ldap3 import Connection
    from ldap3.core.exceptions import LDAPException

    try:
        conexao = Connection(_servidor(com_info=True),
                             receive_timeout=settings.LDAP_TIMEOUT)
        conexao.open()
        if settings.LDAP_START_TLS and not settings.LDAP_USE_SSL:
            conexao.start_tls()
        info = conexao.server.info
        conexao.unbind()
        return True, info
    except (LDAPException, OSError) as erro:
        return False, str(erro)
