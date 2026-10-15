"""Testes da integração com AD/LDAP (Fase 3.8).

Nenhum teste aqui toca a rede. Há duas estratégias, de propósito:

1. A maioria substitui `ldap_backend.autenticar` por uma função falsa. O que
   está sendo testado é a **regra**: que papel sai de quais grupos, o que
   acontece no segundo login, o que acontece quando o AD cai.

2. `ClienteLdapComServidorFalsoTests` usa o modo `MOCK_SYNC` do próprio
   `ldap3`, que simula um diretório em memória. Esse exercita a biblioteca de
   verdade — o filtro de busca, a leitura dos atributos, o parser de DN — e
   pegaria um erro que um mock escrito por mim nunca pegaria.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .ldap_backend import LdapBackend, papel_para_grupos
from .ldap_client import LdapIndisponivel, UsuarioLdap, autenticar
from .models import UserProfile
from .testing import SENHA_DE_TESTE, criar_admin, criar_usuario

# Mapa usado nos testes: fixo aqui para que mexer no settings do projeto não
# quebre a suíte, e para deixar a ordem de precedência explícita.
MAPA = [
    ('ITSM-Admins',   UserProfile.ROLE_ADMIN),
    ('ITSM-Gerentes', UserProfile.ROLE_MANAGER),
    ('ITSM-Tecnicos', UserProfile.ROLE_TECHNICIAN),
]

ldap_ligado = override_settings(
    LDAP_ENABLED=True,
    LDAP_GROUP_ROLE_MAP=MAPA,
    LDAP_DEFAULT_ROLE=UserProfile.ROLE_REQUESTER,
)


def usuario_ldap(username='joao', grupos=(), **extra):
    """Monta o objeto que o AD devolveria, com valores razoáveis."""
    dados = {
        'first_name': 'João',
        'last_name':  'Silva',
        'email':      f'{username}@exemplo.local',
        'department': 'Infraestrutura',
        'dn':         f'CN={username},OU=Usuarios,DC=exemplo,DC=local',
    }
    dados.update(extra)
    return UsuarioLdap(username=username, groups=list(grupos), **dados)


def responder(dados):
    """Patch de `autenticar` que devolve sempre o mesmo resultado."""
    return mock.patch('apps.accounts.ldap_backend.autenticar',
                      return_value=dados)


@ldap_ligado
class MapeamentoDeGruposTests(TestCase):
    """`papel_para_grupos` — a tradução de grupo do AD para papel do ITSM."""

    def test_grupo_de_admin_vira_administrador(self):
        self.assertEqual(papel_para_grupos(['ITSM-Admins']),
                         UserProfile.ROLE_ADMIN)

    def test_grupo_de_gerente_vira_gerente(self):
        self.assertEqual(papel_para_grupos(['ITSM-Gerentes']),
                         UserProfile.ROLE_MANAGER)

    def test_grupo_de_tecnico_vira_tecnico(self):
        self.assertEqual(papel_para_grupos(['ITSM-Tecnicos']),
                         UserProfile.ROLE_TECHNICIAN)

    def test_grupo_desconhecido_nao_casa(self):
        self.assertIsNone(papel_para_grupos(['Contabilidade', 'Todos']))

    def test_sem_grupo_nenhum_nao_casa(self):
        self.assertIsNone(papel_para_grupos([]))

    def test_vence_o_papel_mais_privilegiado_do_mapa(self):
        """Quem está em vários grupos recebe o primeiro do mapa, não o
        primeiro que o AD devolveu — senão o papel mudaria de login para
        login conforme a ordem do diretório."""
        grupos = ['ITSM-Tecnicos', 'ITSM-Admins', 'ITSM-Gerentes']
        self.assertEqual(papel_para_grupos(grupos), UserProfile.ROLE_ADMIN)
        self.assertEqual(papel_para_grupos(list(reversed(grupos))),
                         UserProfile.ROLE_ADMIN)

    def test_comparacao_ignora_maiusculas(self):
        """Nome de grupo no AD não diferencia caixa; ninguém deve perder
        acesso porque o settings diz `ITSM-Tecnicos` e o AD devolveu
        `itsm-tecnicos`."""
        self.assertEqual(papel_para_grupos(['itsm-TECNICOS']),
                         UserProfile.ROLE_TECHNICIAN)


@ldap_ligado
class PrimeiroLoginTests(TestCase):
    """O usuário do AD que ainda não existe no banco do Django."""

    def test_cria_o_usuario_com_os_dados_do_diretorio(self):
        with responder(usuario_ldap('joao', ['ITSM-Tecnicos'])):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='qualquer')

        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'joao')
        self.assertEqual(user.first_name, 'João')
        self.assertEqual(user.last_name, 'Silva')
        self.assertEqual(user.email, 'joao@exemplo.local')
        self.assertEqual(user.profile.department, 'Infraestrutura')
        self.assertEqual(user.profile.role, UserProfile.ROLE_TECHNICIAN)

    def test_marca_a_conta_como_vinda_do_ad(self):
        with responder(usuario_ldap('joao')):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='qualquer')
        self.assertTrue(user.profile.from_ldap)
        self.assertIsNotNone(user.profile.ldap_last_sync)

    def test_a_senha_do_ad_nao_fica_guardada_no_django(self):
        """Sem isto, uma cópia do hash ficaria no banco e trocar a senha no
        domínio não revogaria o acesso ao ITSM."""
        with responder(usuario_ldap('joao')):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='senha-do-dominio')

        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.check_password('senha-do-dominio'))

    def test_sem_grupo_conhecido_entra_como_solicitante(self):
        with responder(usuario_ldap('joao', ['Contabilidade'])):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='qualquer')
        self.assertEqual(user.profile.role, UserProfile.ROLE_REQUESTER)

    @override_settings(LDAP_DEFAULT_ROLE=UserProfile.ROLE_TECHNICIAN)
    def test_o_papel_padrao_e_configuravel(self):
        with responder(usuario_ldap('joao', [])):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='qualquer')
        self.assertEqual(user.profile.role, UserProfile.ROLE_TECHNICIAN)

    def test_o_perfil_nasce_junto_com_o_usuario(self):
        with responder(usuario_ldap('joao')):
            LdapBackend().authenticate(None, username='joao', password='x')
        self.assertEqual(UserProfile.objects.filter(user__username='joao')
                         .count(), 1)


@ldap_ligado
class LoginSeguinteTests(TestCase):
    """O usuário do AD que já está no banco."""

    def test_atualiza_os_dados_sem_duplicar_o_usuario(self):
        with responder(usuario_ldap('joao', ['ITSM-Tecnicos'])):
            LdapBackend().authenticate(None, username='joao', password='x')

        promovido = usuario_ldap('joao', ['ITSM-Gerentes'],
                                 last_name='Silva Neto',
                                 department='Governança')
        with responder(promovido):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='x')

        self.assertEqual(User.objects.filter(username='joao').count(), 1)
        self.assertEqual(user.last_name, 'Silva Neto')
        self.assertEqual(user.profile.department, 'Governança')
        self.assertEqual(user.profile.role, UserProfile.ROLE_MANAGER)

    def test_username_com_outra_caixa_nao_cria_segundo_usuario(self):
        """O `sAMAccountName` do AD não diferencia maiúsculas, o `username` do
        Django sim. Sem busca `iexact`, o AD devolvendo `Thiago` criaria uma
        conta ao lado do `thiago` que já existe — duas contas, dois conjuntos
        de chamados, mesma pessoa."""
        criar_usuario('thiago', UserProfile.ROLE_ADMIN)

        with responder(usuario_ldap('Thiago', ['ITSM-Admins'])):
            user = LdapBackend().authenticate(None, username='Thiago',
                                              password='x')

        self.assertEqual(User.objects.filter(username__iexact='thiago')
                         .count(), 1)
        self.assertEqual(user.username, 'thiago')

    def test_usuario_local_nao_e_rebaixado_por_falta_de_grupo(self):
        """O `admin` criado à mão não pode virar Solicitante só porque
        autenticou pelo AD sem estar em nenhum grupo do mapa."""
        criar_admin('chefe')

        with responder(usuario_ldap('chefe', ['Contabilidade'])):
            user = LdapBackend().authenticate(None, username='chefe',
                                              password='x')

        self.assertEqual(user.profile.role, UserProfile.ROLE_ADMIN)

    def test_usuario_local_mantem_a_senha_local(self):
        """Quem já existia continua conseguindo entrar pelo backend local — a
        senha dele não é apagada por ter autenticado uma vez no AD."""
        criar_usuario('chefe', UserProfile.ROLE_ADMIN)

        with responder(usuario_ldap('chefe')):
            LdapBackend().authenticate(None, username='chefe', password='x')

        user = User.objects.get(username='chefe')
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password(SENHA_DE_TESTE))

    def test_campo_vazio_no_ad_nao_apaga_o_dado_que_ja_existe(self):
        criar_usuario('chefe', first_name='Nome', last_name='Antigo')

        with responder(usuario_ldap('chefe', first_name='', last_name='',
                                    email='', department='')):
            user = LdapBackend().authenticate(None, username='chefe',
                                              password='x')

        self.assertEqual(user.first_name, 'Nome')
        self.assertEqual(user.last_name, 'Antigo')


@ldap_ligado
class RecusaTests(TestCase):
    """Quando o backend do AD tem de dizer "não" ou sair do caminho."""

    def test_credencial_recusada_nao_autentica(self):
        with responder(None):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='errada')
        self.assertIsNone(user)
        self.assertFalse(User.objects.filter(username='joao').exists())

    def test_servidor_fora_do_ar_nao_autentica_nem_quebra(self):
        with mock.patch('apps.accounts.ldap_backend.autenticar',
                        side_effect=LdapIndisponivel('timeout')):
            user = LdapBackend().authenticate(None, username='joao',
                                              password='x')
        self.assertIsNone(user)

    def test_conta_inativa_no_itsm_nao_entra_mesmo_com_senha_certa(self):
        criar_usuario('demitido', is_active=False)

        with responder(usuario_ldap('demitido', ['ITSM-Admins'])):
            user = LdapBackend().authenticate(None, username='demitido',
                                              password='x')
        self.assertIsNone(user)

    def test_senha_em_branco_nao_chega_ao_servidor(self):
        """Bind com senha vazia é bind anônimo, que o AD aceita — e a
        autenticação "passaria" com a senha em branco."""
        with mock.patch('apps.accounts.ldap_backend.autenticar') as falsa:
            self.assertIsNone(LdapBackend().authenticate(None, username='joao',
                                                         password=''))
            self.assertIsNone(LdapBackend().authenticate(None, username='joao',
                                                         password=None))
        falsa.assert_not_called()

    def test_senha_em_branco_tambem_e_barrada_no_cliente(self):
        """A mesma guarda no `ldap_client`, para quem chamar direto."""
        with mock.patch('apps.accounts.ldap_client._conectar') as conectar:
            self.assertIsNone(autenticar('joao', ''))
            self.assertIsNone(autenticar('', 'senha'))
        conectar.assert_not_called()


class LdapDesligadoTests(TestCase):
    """Com `LDAP_ENABLED = False` — que é o padrão do projeto."""

    @override_settings(LDAP_ENABLED=False)
    def test_o_backend_sai_sem_abrir_conexao(self):
        with mock.patch('apps.accounts.ldap_backend.autenticar') as falsa:
            user = LdapBackend().authenticate(None, username='joao',
                                              password='x')
        self.assertIsNone(user)
        # Importa que nem tente: senão cada login esperaria o timeout do AD.
        falsa.assert_not_called()

    @override_settings(LDAP_ENABLED=False)
    def test_o_login_local_continua_funcionando(self):
        criar_usuario('local')
        user = authenticate(username='local', password=SENHA_DE_TESTE)
        self.assertIsNotNone(user)


@ldap_ligado
class CadeiaDeBackendsTests(TestCase):
    """`AUTHENTICATION_BACKENDS` — o AD na frente, o banco local atrás.

    Esta é a razão de a fase não ser um ponto único de falha: o DC cair não
    pode trancar ninguém fora do sistema.
    """

    def test_ad_fora_do_ar_e_o_login_local_ainda_funciona(self):
        criar_usuario('local')
        with mock.patch('apps.accounts.ldap_backend.autenticar',
                        side_effect=LdapIndisponivel('sem rota para o host')):
            user = authenticate(username='local', password=SENHA_DE_TESTE)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'local')

    def test_conta_que_nao_existe_no_ad_entra_pela_senha_local(self):
        criar_usuario('local')
        with responder(None):
            user = authenticate(username='local', password=SENHA_DE_TESTE)
        self.assertIsNotNone(user)

    def test_senha_errada_nos_dois_lugares_nao_autentica(self):
        criar_usuario('local')
        with responder(None):
            self.assertIsNone(authenticate(username='local',
                                           password='nao-e-essa'))

    def test_o_ad_e_consultado_antes_do_banco_local(self):
        """Se o AD aceita, é o papel do AD que vale — mesmo que exista uma
        senha local para o mesmo username."""
        criar_usuario('local', UserProfile.ROLE_REQUESTER)
        with responder(usuario_ldap('local', ['ITSM-Gerentes'])):
            user = authenticate(username='local', password=SENHA_DE_TESTE)
        self.assertEqual(user.profile.role, UserProfile.ROLE_MANAGER)


@ldap_ligado
class TelaDeLoginTests(TestCase):
    """O caminho completo: o formulário de `/accounts/login/`."""

    def test_usuario_do_ad_entra_pela_tela_e_cai_no_dashboard(self):
        with responder(usuario_ldap('joao', ['ITSM-Tecnicos'])):
            resposta = self.client.post(reverse('accounts:login'),
                                        {'username': 'joao',
                                         'password': 'senha-do-dominio'},
                                        follow=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['user'].username, 'joao')
        self.assertTrue(resposta.context['user'].is_authenticated)

    def test_credencial_recusada_mostra_o_aviso_da_tela(self):
        with responder(None):
            resposta = self.client.post(reverse('accounts:login'),
                                        {'username': 'joao',
                                         'password': 'errada'})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context['user'].is_authenticated)

    @override_settings(LDAP_DOMAIN='exemplo.local')
    def test_a_tela_avisa_que_a_senha_e_a_do_dominio(self):
        """Sem o aviso, a pessoa tentaria uma senha local que o sistema nem
        guarda — a senha de quem vem do AD fica no domínio."""
        resposta = self.client.get(reverse('accounts:login'))
        self.assertContains(resposta, 'senha de rede')
        self.assertContains(resposta, 'exemplo.local')


class AvisoDeDominioDesligadoTests(TestCase):
    @override_settings(LDAP_ENABLED=False)
    def test_sem_ldap_a_tela_nao_fala_de_dominio(self):
        resposta = self.client.get(reverse('accounts:login'))
        self.assertNotContains(resposta, 'senha de rede')


class VerificacoesDoCheckTests(TestCase):
    """`manage.py check` reclamando de configuração perigosa de LDAP.

    Os avisos existem porque documentação não aparece no terminal de quem
    sobe o sistema; o `check` aparece.
    """

    def _ids(self):
        from .checks import verificar_configuracao_ldap
        return [aviso.id for aviso in verificar_configuracao_ldap(None)]

    @override_settings(LDAP_ENABLED=False, LDAP_USE_SSL=False,
                       LDAP_SEARCH_BASE='')
    def test_ldap_desligado_nao_gera_aviso(self):
        self.assertEqual(self._ids(), [])

    @override_settings(LDAP_ENABLED=True, LDAP_USE_SSL=False,
                       LDAP_START_TLS=False)
    def test_avisa_quando_a_senha_trafega_em_texto_claro(self):
        self.assertIn('ldap.W001', self._ids())

    @override_settings(LDAP_ENABLED=True, LDAP_USE_SSL=True,
                       LDAP_TLS_VALIDATE=False)
    def test_avisa_quando_o_certificado_nao_e_validado(self):
        ids = self._ids()
        self.assertIn('ldap.W002', ids)
        # Com TLS, o aviso de texto claro não deve aparecer.
        self.assertNotIn('ldap.W001', ids)

    @override_settings(LDAP_ENABLED=True, LDAP_USE_SSL=True,
                       LDAP_TLS_VALIDATE=True, LDAP_SEARCH_BASE='')
    def test_avisa_quando_a_base_de_busca_esta_vazia(self):
        self.assertIn('ldap.W003', self._ids())

    @override_settings(LDAP_ENABLED=True, LDAP_USE_SSL=True,
                       LDAP_TLS_VALIDATE=True,
                       LDAP_BIND_DN='CN=svc,DC=exemplo,DC=local',
                       LDAP_BIND_PASSWORD='')
    def test_avisa_conta_de_servico_sem_senha(self):
        self.assertIn('ldap.W004', self._ids())

    @override_settings(LDAP_ENABLED=True, LDAP_USE_SSL=True,
                       LDAP_TLS_VALIDATE=True,
                       LDAP_SEARCH_BASE='DC=exemplo,DC=local',
                       LDAP_BIND_DN='', LDAP_BIND_PASSWORD='')
    def test_configuracao_segura_nao_gera_aviso(self):
        self.assertEqual(self._ids(), [])


# ──────────────────────────────────────────────────────────────────────
# Servidor LDAP falso, de dentro do próprio ldap3
# ──────────────────────────────────────────────────────────────────────

BASE = 'DC=exemplo,DC=local'
DN_JOAO = f'CN=Joao Silva,OU=Usuarios,{BASE}'


def _conexao_falsa():
    """Uma `Connection` do ldap3 ligada a um diretório em memória.

    `MOCK_SYNC` é uma estratégia do próprio ldap3: ela responde às buscas sem
    socket nenhum, aplicando o filtro LDAP de verdade.
    """
    from ldap3 import Connection, MOCK_SYNC, Server

    conexao = Connection(Server('srv-falso'), client_strategy=MOCK_SYNC)
    conexao.strategy.add_entry(DN_JOAO, {
        'objectClass':    ['top', 'person', 'user'],
        'sAMAccountName': 'joao',
        'givenName':      'João',
        'sn':             'Silva',
        'mail':           'joao@exemplo.local',
        'department':     'Infraestrutura',
        'memberOf': [
            f'CN=ITSM-Tecnicos,OU=Grupos,{BASE}',
            f'CN=Suporte\\, Nível 2,OU=Grupos,{BASE}',
        ],
    })
    # Conta sem `givenName`/`sn`, como as criadas à mão no AD: o nome existe
    # só no CN do DN.
    conexao.strategy.add_entry(f'CN=Maria Clara dos Santos,OU=Usuarios,{BASE}', {
        'objectClass':    ['top', 'person', 'user'],
        'sAMAccountName': 'maria.santos',
        'memberOf':       [f'CN=ITSM-Gerentes,OU=Grupos,{BASE}'],
    })
    # Conta com `displayName` mas sem `givenName`/`sn`.
    conexao.strategy.add_entry(f'CN=jpaulo,OU=Usuarios,{BASE}', {
        'objectClass':    ['top', 'person', 'user'],
        'sAMAccountName': 'joao.paulo',
        'displayName':    'João Paulo Souza',
    })
    # Conta cujo `sAMAccountName` **não** é o prefixo do UPN. No AD os dois
    # são campos independentes, e foi o que apareceu no domínio deste projeto:
    # a pessoa digita `lara`, o bind é validado contra o UPN e passa, e uma
    # busca só por `sAMAccountName=lara` não acharia nada.
    conexao.strategy.add_entry(f'CN=Lara Souza,OU=Usuarios,{BASE}', {
        'objectClass':       ['top', 'person', 'user'],
        'sAMAccountName':    'lara.souza',
        'userPrincipalName': 'lara@exemplo.local',
        'givenName':         'Lara',
        'sn':                'Souza',
    })
    # Conta de computador: no AD ela também tem `objectClass=user` e
    # apareceria na listagem se o filtro não a excluísse.
    conexao.strategy.add_entry(f'CN=PC-EXEMPLO-01,OU=Computadores,{BASE}', {
        'objectClass':    ['top', 'person', 'user', 'computer'],
        'sAMAccountName': 'PC-EXEMPLO-01$',
    })
    conexao.bind()
    return conexao


@override_settings(LDAP_ENABLED=True, LDAP_SEARCH_BASE=BASE,
                   LDAP_GROUP_ROLE_MAP=MAPA, LDAP_NESTED_GROUPS=False,
                   LDAP_BIND_DN='')
class ClienteLdapComServidorFalsoTests(TestCase):
    """Exercita o `ldap_client` contra o diretório em memória do ldap3.

    O bind é substituído (é ele que falaria com a rede); da busca para frente
    tudo é o ldap3 de verdade.
    """

    def setUp(self):
        self.conexao = _conexao_falsa()
        patch = mock.patch('apps.accounts.ldap_client._conectar',
                           return_value=self.conexao)
        patch.start()
        self.addCleanup(patch.stop)
        # O `autenticar` fecha a conexão no fim; o mock de `_conectar` devolve
        # sempre a mesma, então recriamos quando um teste precisa de duas.

    def test_le_os_atributos_da_conta(self):
        dados = autenticar('joao', 'senha')

        self.assertIsNotNone(dados)
        self.assertEqual(dados.username, 'joao')
        self.assertEqual(dados.first_name, 'João')
        self.assertEqual(dados.last_name, 'Silva')
        self.assertEqual(dados.email, 'joao@exemplo.local')
        self.assertEqual(dados.department, 'Infraestrutura')
        self.assertEqual(dados.dn, DN_JOAO)

    def test_extrai_o_nome_dos_grupos_do_dn(self):
        dados = autenticar('joao', 'senha')
        self.assertIn('ITSM-Tecnicos', dados.groups)

    def test_nome_de_grupo_com_virgula_escapada_nao_e_cortado(self):
        """`split(',')` devolveria `CN=Suporte\\` — é por isso que o parser de
        DN do ldap3 é usado no lugar."""
        dados = autenticar('joao', 'senha')
        self.assertIn('Suporte, Nível 2', dados.groups)

    def test_nome_vem_do_display_name_quando_falta_given_name(self):
        """Conta de AD montada à mão costuma não ter `givenName`/`sn`. Sem a
        queda para trás, o ITSM mostraria `joao.paulo` em todas as telas."""
        dados = autenticar('joao.paulo', 'senha')
        self.assertEqual(dados.first_name, 'João')
        self.assertEqual(dados.last_name, 'Paulo Souza')

    def test_nome_vem_do_cn_quando_nem_display_name_existe(self):
        dados = autenticar('maria.santos', 'senha')
        self.assertEqual(dados.first_name, 'Maria')
        self.assertEqual(dados.last_name, 'Clara dos Santos')

    def test_given_name_preenchido_tem_precedencia(self):
        """Quem tem os campos certos no AD não passa pela queda para trás —
        senão o CN (`Joao Silva`, sem acento) venceria o `givenName`."""
        dados = autenticar('joao', 'senha')
        self.assertEqual(dados.first_name, 'João')
        self.assertEqual(dados.last_name, 'Silva')

    @override_settings(LDAP_DOMAIN='exemplo.local')
    def test_conta_e_achada_pelo_upn_quando_o_nome_curto_difere(self):
        """A pessoa digita `lara`, mas o `sAMAccountName` é `lara.souza`.

        O bind simples do AD é validado contra o `userPrincipalName`, então
        essa conta autentica. Procurar só por `sAMAccountName=lara` devolvia
        busca bem-sucedida e nenhuma entrada — a senha era aceita e o login
        falhava em seguida, sem o usuário nunca chegar a ser criado no ITSM.
        """
        dados = autenticar('lara', 'senha')

        self.assertIsNotNone(dados, 'a conta deveria ser achada pelo UPN')
        # O username gravado no Django é o `sAMAccountName` real, não o que
        # foi digitado: é o identificador estável da conta no domínio.
        self.assertEqual(dados.username, 'lara.souza')
        self.assertEqual(dados.first_name, 'Lara')

    @override_settings(LDAP_DOMAIN='exemplo.local')
    def test_digitar_o_upn_completo_tambem_acha(self):
        """`lara@exemplo.local` é uma das formas válidas no Windows."""
        dados = autenticar('lara@exemplo.local', 'senha')
        self.assertIsNotNone(dados)
        self.assertEqual(dados.username, 'lara.souza')

    @override_settings(LDAP_DOMAIN='exemplo.local')
    def test_o_nome_curto_continua_achando_quem_bate_pelos_dois(self):
        """A conta normal, em que `sAMAccountName` é o prefixo do UPN, não
        pode ter deixado de ser encontrada pela mudança do filtro."""
        dados = autenticar('joao', 'senha')
        self.assertIsNotNone(dados)
        self.assertEqual(dados.username, 'joao')

    def test_conta_fora_da_base_de_busca_nao_e_encontrada(self):
        """Bind aceito e busca vazia não é "senha errada" — é configuração
        errada. De qualquer forma o login não passa."""
        self.assertIsNone(autenticar('ninguem', 'senha'))

    def test_username_com_curinga_nao_casa_com_qualquer_conta(self):
        """Sem escapar o que a pessoa digitou, `*` viraria um filtro curinga e
        casaria com a primeira conta do diretório — a mesma classe de problema
        que SQL injection."""
        self.assertIsNone(autenticar('*', 'senha'))

    def test_parenteses_no_username_nao_quebram_o_filtro(self):
        self.assertIsNone(autenticar('jo)ao', 'senha'))


@override_settings(LDAP_ENABLED=True, LDAP_SEARCH_BASE=BASE,
                   LDAP_GROUP_ROLE_MAP=MAPA, LDAP_NESTED_GROUPS=False,
                   LDAP_BIND_DN='')
class ListagemDeUsuariosTests(TestCase):
    """`listar_usuarios` — a conferência em massa do `ldap_check --list`."""

    def setUp(self):
        patch = mock.patch('apps.accounts.ldap_client._conectar',
                           return_value=_conexao_falsa())
        patch.start()
        self.addCleanup(patch.stop)

    def test_lista_as_contas_ordenadas_por_login(self):
        from .ldap_client import listar_usuarios
        contas = listar_usuarios('joao', 'senha')
        self.assertEqual([c.username for c in contas],
                         ['joao', 'joao.paulo', 'lara.souza', 'maria.santos'])

    def test_conta_de_computador_fica_fora_da_lista(self):
        """No AD a máquina também tem `objectClass=user`; sem o filtro, a
        listagem viria com os PCs do domínio no meio das pessoas."""
        from .ldap_client import listar_usuarios
        contas = [c.username for c in listar_usuarios('joao', 'senha')]
        self.assertNotIn('PC-EXEMPLO-01$', contas)

    def test_a_listagem_le_os_mesmos_dados_que_o_login_gravaria(self):
        """Usa o mesmo `_montar_usuario` do `autenticar`; uma segunda
        implementação divergiria na primeira mudança."""
        from .ldap_client import listar_usuarios
        contas = {c.username: c for c in listar_usuarios('joao', 'senha')}

        self.assertEqual(contas['joao'].email, 'joao@exemplo.local')
        self.assertIn('ITSM-Tecnicos', contas['joao'].groups)
        # A queda para trás do nome vale na listagem também.
        self.assertEqual(contas['maria.santos'].first_name, 'Maria')
        self.assertEqual(contas['joao.paulo'].last_name, 'Paulo Souza')

    def test_sem_credencial_nao_consulta(self):
        from .ldap_client import listar_usuarios
        self.assertEqual(listar_usuarios('joao', ''), [])

    def test_credencial_recusada_devolve_none_e_nao_lista_vazia(self):
        """None e `[]` significam coisas diferentes: "não entrei" contra
        "entrei e o diretório está vazio"."""
        from .ldap_client import listar_usuarios
        with mock.patch('apps.accounts.ldap_client._conectar',
                        return_value=None):
            self.assertIsNone(listar_usuarios('joao', 'senha'))


class MapaDeGruposDoProjetoTests(TestCase):
    """O `LDAP_GROUP_ROLE_MAP` que está no settings — não um mapa de teste.

    Num domínio real, a maioria dos grupos existe para conceder acesso a
    compartilhamentos, impressoras e aplicações, e é distribuída por GPO
    automaticamente. Mapear um desses para um papel do ITSM daria privilégio
    de atendimento a quem só precisava de uma pasta — escalonamento de
    privilégio sem ninguém ter decidido isso.

    Por isso o mapa é mínimo e cada acréscimo exige revisão: só entra aqui
    grupo criado **exatamente** para definir papel no ITSM.
    """

    def test_o_mapa_nao_cresceu_sem_revisao(self):
        """Este teste falha de propósito quando alguém acrescenta um grupo.

        Não é para impedir o acréscimo: é para que ele passe por aqui, onde
        está escrito o critério.
        """
        self.assertEqual([grupo for grupo, _ in settings.LDAP_GROUP_ROLE_MAP],
                         ['Domain Admins'])

    def test_grupo_de_compartilhamento_nao_concede_papel(self):
        for grupo in ['GRP-Arquivos', 'GRP-Financeiro', 'Impressoras-Andar2',
                      'Todos-os-Usuarios', 'VPN-Usuarios']:
            with self.subTest(grupo=grupo):
                self.assertIsNone(papel_para_grupos([grupo]))

    def test_conta_sem_grupo_mapeado_entra_como_solicitante(self):
        self.assertIsNone(papel_para_grupos(['GRP-Arquivos', 'VPN-Usuarios']))
        self.assertEqual(settings.LDAP_DEFAULT_ROLE,
                         UserProfile.ROLE_REQUESTER)

    def test_domain_admins_concede_administrador(self):
        self.assertEqual(papel_para_grupos(['Domain Admins']),
                         UserProfile.ROLE_ADMIN)


@override_settings(LDAP_ENABLED=True,
                   LDAP_GROUP_ROLE_MAP=[('Domain Admins', 'admin')],
                   LDAP_DEFAULT_ROLE=UserProfile.ROLE_REQUESTER)
class DomainUsersAbreChamadoTests(TestCase):
    """Quem está em `Domain Users` entra como Solicitante e abre chamado.

    `Domain Users` é o grupo primário de **toda** conta do domínio: o AD a
    coloca lá na criação e não dá para tirar. Então "todo usuário do domínio"
    e "quem está em Domain Users" são o mesmo conjunto de pessoas.

    Isto já é o comportamento do `LDAP_DEFAULT_ROLE`, e estes testes existem
    para que continue sendo — inclusive os dois últimos, que mostram por que o
    grupo **não** deve ser acrescentado ao `LDAP_GROUP_ROLE_MAP`.
    """

    def test_conta_so_em_domain_users_entra_como_solicitante(self):
        with responder(usuario_ldap('maria', ['Domain Users'])):
            user = LdapBackend().authenticate(None, username='maria',
                                              password='qualquer')

        self.assertIsNotNone(user, 'a conta do domínio deve conseguir entrar')
        self.assertEqual(user.profile.role, UserProfile.ROLE_REQUESTER)
        self.assertTrue(user.is_active)

    def test_o_solicitante_do_ad_pode_abrir_chamado(self):
        """O papel só serve se a pessoa chegar à tela de abrir chamado."""
        with responder(usuario_ldap('maria', ['Domain Users'])):
            user = LdapBackend().authenticate(None, username='maria',
                                              password='qualquer')

        self.client.force_login(user, backend='apps.accounts.ldap_backend.'
                                              'LdapBackend')
        resposta = self.client.get(reverse('tickets:create'))
        self.assertEqual(resposta.status_code, 200)

    def test_domain_users_com_domain_admins_sai_administrador(self):
        """Estar nos dois não pode rebaixar o administrador do domínio."""
        with responder(usuario_ldap('thiago', ['Domain Users',
                                               'Domain Admins'])):
            user = LdapBackend().authenticate(None, username='thiago',
                                              password='qualquer')
        self.assertEqual(user.profile.role, UserProfile.ROLE_ADMIN)

    def test_conta_sem_memberof_entra_como_solicitante(self):
        """A forma **real** da conta comum: sem nenhum grupo em `memberOf`.

        O AD guarda o grupo primário em `primaryGroupID` e **não** o lista em
        `memberOf`. Quem está só em `Domain Users` chega aqui, portanto, sem
        grupo nenhum — e é por isso que pôr o grupo no `LDAP_GROUP_ROLE_MAP`
        não teria efeito: ele nunca apareceria para casar.

        Este teste monta a entrada como o `ldap3` a devolveria, com o atributo
        ausente, para garantir que a leitura não quebra nem inventa grupo.
        """
        from .ldap_client import _montar_usuario

        entrada = {'sAMAccountName': ['maria'], 'givenName': ['Maria'],
                   'sn': ['Souza'], 'mail': [], 'department': [],
                   'displayName': []}          # sem a chave 'memberOf'
        dados = _montar_usuario(
            entrada, 'CN=Maria Souza,OU=Usuarios,DC=exemplo,DC=local', 'maria')
        self.assertEqual(dados.groups, [])

        with responder(dados):
            user = LdapBackend().authenticate(None, username='maria',
                                              password='qualquer')
        self.assertIsNotNone(user)
        self.assertEqual(user.profile.role, UserProfile.ROLE_REQUESTER)
        self.assertEqual(user.first_name, 'Maria')

    def test_domain_users_no_mapa_rebaixaria_o_tecnico_promovido_a_mao(self):
        """A armadilha: por isso o grupo fica fora do `LDAP_GROUP_ROLE_MAP`.

        Vale quando o grupo **chega** na lista — com `LDAP_NESTED_GROUPS`
        ligado, ou se alguém o tiver adicionado como membro secundário. Aí
        toda conta passa a casar, e casar sobrescreve o papel: o Técnico
        promovido à mão em /admin/ voltaria a Solicitante no login seguinte, e
        o ajuste manual deixaria de ser durável.

        Fora do mapa (como está), ninguém casa, o papel atual é mantido, e a
        conta nova cai no `LDAP_DEFAULT_ROLE` — que já é Solicitante.
        """
        criar_usuario('tecnico.ad', UserProfile.ROLE_TECHNICIAN)

        # Como está hoje: o papel dado à mão sobrevive ao login pelo AD.
        with responder(usuario_ldap('tecnico.ad', ['Domain Users'])):
            user = LdapBackend().authenticate(None, username='tecnico.ad',
                                              password='qualquer')
        self.assertEqual(user.profile.role, UserProfile.ROLE_TECHNICIAN)

        # E se alguém acrescentasse o grupo ao mapa:
        with override_settings(LDAP_GROUP_ROLE_MAP=[
                ('Domain Admins', 'admin'),
                ('Domain Users',  'requester')]):
            with responder(usuario_ldap('tecnico.ad', ['Domain Users'])):
                user = LdapBackend().authenticate(None, username='tecnico.ad',
                                                 password='qualquer')
        self.assertEqual(user.profile.role, UserProfile.ROLE_REQUESTER,
                         'se isto falhar, o rebaixamento deixou de acontecer '
                         'e o aviso no settings pode ser revisto')


class NomeCurtoTests(TestCase):
    """`_nome_curto` — tirar o domínio do que a pessoa digitou.

    As três formas abaixo funcionam no logon do Windows, então todas chegam à
    tela de login do ITSM. O `sAMAccountName` é só a parte curta.
    """

    def test_as_tres_formas_de_digitar(self):
        from .ldap_client import _nome_curto
        for digitado in ['lara', 'lara@araujo.corp', 'ARAUJO\\lara']:
            with self.subTest(digitado=digitado):
                self.assertEqual(_nome_curto(digitado), 'lara')

    def test_ponto_no_nome_e_preservado(self):
        from .ldap_client import _nome_curto
        self.assertEqual(_nome_curto('lara.souza@araujo.corp'), 'lara.souza')


class MotivoDaRecusaTests(TestCase):
    """`_motivo_da_recusa` — traduzir o `data NNN` do AD.

    O AD recusa todo bind com o mesmo código LDAP (`invalidCredentials`), de
    propósito: contar a diferença ajudaria quem está tentando adivinhar contas.
    O motivo real vem no texto de diagnóstico, e sem decodificá-lo "senha
    errada" e "precisa trocar a senha no primeiro logon" são a mesma coisa na
    tela — sendo que a segunda é o estado padrão de toda conta nova no AD.
    """

    def _mensagem(self, data):
        return {'description': 'invalidCredentials',
                'message': ('80090308: LdapErr: DSID-0C09044E, comment: '
                            f'AcceptSecurityContext error, data {data}, v4f7c')}

    def test_senha_incorreta(self):
        from .ldap_client import _motivo_da_recusa
        motivo, _, codigo = _motivo_da_recusa(self._mensagem('52e'))
        self.assertEqual(codigo, '52e')
        self.assertIn('senha incorreta', motivo)

    def test_precisa_trocar_a_senha(self):
        """O caso que mais engana: a conta está certa e nunca entra."""
        from .ldap_client import _motivo_da_recusa
        motivo, acao, codigo = _motivo_da_recusa(self._mensagem('773'))
        self.assertEqual(codigo, '773')
        self.assertIn('trocar a senha', motivo)
        self.assertIn('recém-criada', acao)

    def test_conta_desabilitada(self):
        from .ldap_client import _motivo_da_recusa
        motivo, _, codigo = _motivo_da_recusa(self._mensagem('533'))
        self.assertEqual(codigo, '533')
        self.assertIn('desabilitada', motivo)

    def test_maiuscula_no_codigo_nao_muda_nada(self):
        from .ldap_client import _motivo_da_recusa
        self.assertEqual(_motivo_da_recusa(self._mensagem('52E'))[2], '52e')

    def test_codigo_desconhecido_ainda_informa_o_numero(self):
        from .ldap_client import _motivo_da_recusa
        motivo, _, codigo = _motivo_da_recusa(self._mensagem('999'))
        self.assertEqual(codigo, '999')
        self.assertIn('999', motivo)

    def test_servidor_que_nao_e_ad_cai_na_descricao_padrao(self):
        """Perder o detalhe é aceitável; deixar de responder não é."""
        from .ldap_client import _motivo_da_recusa
        motivo, acao, codigo = _motivo_da_recusa(
            {'description': 'invalidCredentials', 'message': ''})
        self.assertEqual((motivo, acao, codigo),
                         ('invalidCredentials', '', ''))

    def test_resultado_vazio_nao_quebra(self):
        from .ldap_client import _motivo_da_recusa
        self.assertEqual(_motivo_da_recusa(None)[0], 'motivo não informado')
        self.assertEqual(_motivo_da_recusa({})[0], 'motivo não informado')


class DivisaoDoNomeTests(TestCase):
    """`_dividir_nome` — o Django tem dois campos, o AD costuma ter um."""

    def test_nome_e_sobrenome(self):
        from .ldap_client import _dividir_nome
        self.assertEqual(_dividir_nome('Thiago Araujo'), ('Thiago', 'Araujo'))

    def test_nome_composto_mantem_o_sobrenome_inteiro(self):
        from .ldap_client import _dividir_nome
        self.assertEqual(_dividir_nome('Maria Clara dos Santos'),
                         ('Maria', 'Clara dos Santos'))

    def test_nome_de_uma_palavra_nao_inventa_sobrenome(self):
        from .ldap_client import _dividir_nome
        self.assertEqual(_dividir_nome('Thiago'), ('Thiago', ''))

    def test_vazio_nao_quebra(self):
        from .ldap_client import _dividir_nome
        self.assertEqual(_dividir_nome(''), ('', ''))
        self.assertEqual(_dividir_nome('   '), ('', ''))


class MontagemDoUpnTests(TestCase):
    """Como o que a pessoa digita vira o usuário do bind."""

    @override_settings(LDAP_DOMAIN='exemplo.local')
    def test_nome_curto_recebe_o_dominio(self):
        from .ldap_client import _montar_upn
        self.assertEqual(_montar_upn('thiago'), 'thiago@exemplo.local')

    @override_settings(LDAP_DOMAIN='exemplo.local')
    def test_quem_ja_digitou_o_dominio_e_respeitado(self):
        from .ldap_client import _montar_upn
        self.assertEqual(_montar_upn('thiago@outro.corp'), 'thiago@outro.corp')
        self.assertEqual(_montar_upn('ARAUJO\\thiago'), 'ARAUJO\\thiago')

    @override_settings(LDAP_DOMAIN='')
    def test_sem_dominio_configurado_vai_o_nome_cru(self):
        from .ldap_client import _montar_upn
        self.assertEqual(_montar_upn('thiago'), 'thiago')
