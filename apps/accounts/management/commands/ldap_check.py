"""Diagnóstico da integração com o Active Directory (Fase 3.8).

Configurar LDAP às cegas é tentativa e erro: a mensagem de erro do bind é a
mesma para senha errada, base de busca errada e certificado recusado. Este
comando separa as etapas e diz em qual delas parou.

    python manage.py ldap_check                    # DNS, porta e TLS
    python manage.py ldap_check --user thiago      # bind + grupos reais

O `--user` é o que resolve o problema do mapeamento de grupos: ele imprime os
grupos que a conta realmente tem no AD e qual papel o `LDAP_GROUP_ROLE_MAP`
atual daria a ela.

A senha é pedida interativamente, nunca por argumento: argumento de linha de
comando fica no histórico do PowerShell e na lista de processos.
"""

from getpass import getpass

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts import ldap_client
from apps.accounts.ldap_backend import papel_para_grupos
from apps.accounts.models import UserProfile


class Command(BaseCommand):
    help = 'Testa a conexão e a autenticação no Active Directory.'

    # Só em memória, durante a execução do comando: o --list reaproveita a
    # credencial digitada no teste de bind, em vez de pedir duas vezes.
    _senha = ''

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            help='Usuário do AD para testar o bind. A senha é pedida na hora.',
        )
        parser.add_argument(
            '--list', action='store_true',
            help='Lista as contas do diretório e o papel que cada uma '
                 'receberia. Exige --user para autenticar a consulta.',
        )

    def handle(self, *args, **opcoes):
        self._mostrar_configuracao()
        username = opcoes.get('user')

        if not self._testar_conexao():
            if username:
                # Sem conexão não há o que autenticar. Dizer isso evita a
                # leitura de que o problema é a conta ou a senha — o comando
                # nem chegou a pedi-la.
                self.stdout.write(self.style.WARNING(
                    f'\n  O teste de login de {username} não foi executado: '
                    'sem conexão com o\n  servidor não há onde autenticar. '
                    'A senha não foi pedida.'))
            return

        if not username:
            self.stdout.write(
                '\nPara testar o login e descobrir os grupos de uma conta:\n'
                '  python manage.py ldap_check --user <usuario>')
            return

        if not self._testar_autenticacao(username):
            return

        if opcoes.get('list'):
            self._listar(username)

    # ──────────────────────────────────────────────────────────────

    def _titulo(self, texto):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{texto}'))

    def _ok(self, texto):
        self.stdout.write(self.style.SUCCESS(f'  [ok]    {texto}'))

    def _erro(self, texto):
        self.stdout.write(self.style.ERROR(f'  [erro]  {texto}'))

    def _aviso(self, texto):
        self.stdout.write(self.style.WARNING(f'  [aviso] {texto}'))

    def _item(self, rotulo, valor):
        self.stdout.write(f'  {rotulo:.<28} {valor}')

    def _explicar_recusa(self, username, relatorio):
        """Diz por que o AD recusou, em vez de pedir que se leia o log.

        São três situações bem diferentes, e o LDAP devolve a mesma coisa nas
        duas primeiras. Sem separá-las, o conserto é adivinhação.
        """
        if relatorio.get('fora_da_base'):
            # O bind passou: a senha está certa. O que falhou foi a leitura.
            self._erro(f'a senha de {username} foi aceita, mas a conta não '
                       f'apareceu na busca.')
            self._item('Base consultada', settings.LDAP_SEARCH_BASE)
            self._item('Resposta da busca', relatorio.get('busca', '—'))
            if relatorio.get('busca_mensagem'):
                self._item('Detalhe', relatorio['busca_mensagem'])
            self.stdout.write(
                '\n  Duas causas possíveis, e a resposta acima distingue:\n'
                '    • a conta está fora de LDAP_SEARCH_BASE (outra OU ou\n'
                '      outro domínio) → ajuste ITSM_LDAP_SEARCH_BASE;\n'
                '    • a conta não tem permissão de ler o diretório → use uma\n'
                '      conta de serviço em ITSM_LDAP_BIND_DN /\n'
                '      ITSM_LDAP_BIND_PASSWORD (ver docs/AD_LDAP.md).\n'
                '\n  Se o administrador entra e o usuário comum não, é o '
                'segundo caso.')
            return

        motivo = relatorio.get('motivo')
        if not motivo:
            self._erro('credencial recusada; o servidor não explicou o '
                       'motivo.')
            return

        codigo = relatorio.get('codigo')
        self._erro(f'o AD recusou o bind de {username}: {motivo}'
                   + (f' (data {codigo})' if codigo else ''))
        if relatorio.get('acao'):
            self.stdout.write(f'\n  O que fazer: {relatorio["acao"]}')

    # ──────────────────────────────────────────────────────────────

    def _mostrar_configuracao(self):
        self._titulo('Configuração (itsm_project/settings.py)')
        self._item('LDAP_ENABLED', settings.LDAP_ENABLED)
        self._item('LDAP_SERVER', settings.LDAP_SERVER)
        self._item('LDAP_PORT', settings.LDAP_PORT)
        self._item('LDAP_USE_SSL', settings.LDAP_USE_SSL)
        self._item('LDAP_START_TLS', settings.LDAP_START_TLS)
        self._item('LDAP_TLS_VALIDATE', settings.LDAP_TLS_VALIDATE)
        self._item('LDAP_CA_CERT_FILE', settings.LDAP_CA_CERT_FILE or '(nenhum)')
        self._item('LDAP_DOMAIN', settings.LDAP_DOMAIN)
        self._item('LDAP_SEARCH_BASE', settings.LDAP_SEARCH_BASE)
        self._item('LDAP_TIMEOUT', f'{settings.LDAP_TIMEOUT}s')
        self._item('LDAP_NESTED_GROUPS', settings.LDAP_NESTED_GROUPS)
        # Nunca imprimir LDAP_BIND_PASSWORD, só se existe.
        self._item('LDAP_BIND_DN', settings.LDAP_BIND_DN or '(nenhum — usa o '
                                                            'próprio usuário)')
        if settings.LDAP_BIND_DN:
            self._item('LDAP_BIND_PASSWORD',
                       'definida' if settings.LDAP_BIND_PASSWORD else 'VAZIA')

        if not settings.LDAP_ENABLED:
            self._aviso('LDAP_ENABLED está False: o login pelo AD não vai '
                        'funcionar na tela, mas este comando testa de qualquer '
                        'forma.')
        if settings.LDAP_PORT == 389 and not settings.LDAP_START_TLS:
            self._aviso('Porta 389 sem TLS: a senha trafega em texto claro. '
                        'Prefira a 636.')
        if not settings.LDAP_TLS_VALIDATE and (settings.LDAP_USE_SSL
                                               or settings.LDAP_START_TLS):
            self._aviso('Validação de certificado desligada: a conexão é '
                        'cifrada, mas não há garantia de que o servidor é o DC.')

    def _testar_conexao(self):
        self._titulo(f'Conexão com {settings.LDAP_SERVER}:{settings.LDAP_PORT}')
        ok, resultado = ldap_client.testar_conexao()
        if not ok:
            self._erro(resultado)
            self._explicar_falha_de_conexao(resultado)
            return False

        self._ok('servidor respondeu')
        dominios = getattr(resultado, 'naming_contexts', None) or []
        for contexto in dominios:
            self._item('naming context', contexto)
        if dominios and settings.LDAP_SEARCH_BASE not in dominios:
            self._aviso(f'LDAP_SEARCH_BASE ({settings.LDAP_SEARCH_BASE}) não '
                        f'está na lista acima — a busca não vai achar ninguém.')
        return True

    def _explicar_falha_de_conexao(self, mensagem):
        texto = mensagem.lower()
        if 'unavailable' in texto or '10054' in texto or 'reset' in texto:
            # Dois sintomas, uma causa: o controlador de domínio não tem
            # certificado de servidor instalado. A porta 636 até aceita a
            # conexão TCP (por isso o Test-NetConnection diz "aberta"), mas
            # derruba o handshake; o StartTLS na 389 responde "unavailable".
            self.stdout.write(
                '\n  O controlador de domínio não está oferecendo TLS — ele '
                'não tem\n  certificado de servidor instalado. Isso não é '
                'problema de configuração\n  daqui: desligar '
                'ITSM_LDAP_TLS_VALIDATE não resolve, porque não há\n'
                '  certificado nenhum para validar.\n\n'
                '  Duas saídas:\n'
                '    1. (correta) emitir um certificado para o DC — normalmente '
                'instalando a\n'
                '       função AD CS (Enterprise CA) no domínio. O DC passa a '
                'atender\n       em LDAPS sozinho, sem mais nenhuma mudança '
                'aqui.\n'
                '    2. (provisória) usar a porta 389 sem TLS:\n'
                '         $env:ITSM_LDAP_PORT = "389"\n'
                '       Funciona, mas a senha de domínio trafega em TEXTO '
                'CLARO pela rede.\n'
                '       Aceitável para testar numa rede controlada; não para '
                'produção.')
        elif 'certificate' in texto or 'verify failed' in texto:
            self.stdout.write(
                '\n  O servidor apresentou um certificado que não foi aceito. '
                'Duas saídas:\n'
                '    1. (correta) exporte a CA do domínio e aponte em '
                'ITSM_LDAP_CA_CERT_FILE\n'
                '    2. (atalho)  $env:ITSM_LDAP_TLS_VALIDATE = "0" — cifra, '
                'mas não valida o servidor')
        elif 'getaddrinfo' in texto or 'name or service' in texto:
            self.stdout.write(
                f'\n  O nome {settings.LDAP_SERVER} não resolveu no DNS. '
                'Confira com:\n'
                f'    Resolve-DnsName {settings.LDAP_SERVER}')
        elif 'timed out' in texto or 'timeout' in texto or 'refused' in texto:
            self.stdout.write(
                f'\n  A porta {settings.LDAP_PORT} não respondeu. Confira com:\n'
                f'    Test-NetConnection {settings.LDAP_SERVER} '
                f'-Port {settings.LDAP_PORT}')

    def _testar_autenticacao(self, username):
        self._titulo(f'Autenticação de {username}')
        senha = getpass(f'  Senha de {username} no domínio (não é exibida): ')
        if not senha:
            self._erro('senha vazia — o AD trataria isso como bind anônimo.')
            return False
        # Guardada só em memória, para o --list não pedir a senha duas vezes.
        self._senha = senha

        relatorio = {}
        try:
            dados = ldap_client.autenticar(username, senha,
                                           relatorio=relatorio)
        except ldap_client.LdapIndisponivel as erro:
            self._erro(f'servidor indisponível: {erro}')
            return False

        if dados is None:
            self._explicar_recusa(username, relatorio)
            return False

        self._ok('bind aceito pelo AD')
        self._titulo('Dados lidos do diretório')
        self._item('sAMAccountName', dados.username)
        self._item('Nome', f'{dados.first_name} {dados.last_name}'.strip() or '(vazio)')
        self._item('E-mail', dados.email or '(vazio)')
        self._item('Departamento', dados.department or '(vazio)')
        self._item('DN', dados.dn or '(vazio)')

        if not dados.email:
            # Consequência concreta, não só um campo em branco: o ITSM manda
            # e-mail em abertura, comentário, resolução e vencimento de SLA.
            self._aviso('a conta não tem `mail` no AD — esta pessoa não vai '
                        'receber\n          as notificações por e-mail do '
                        'ITSM (as internas, no sino, funcionam).\n'
                        '          Preencha o campo E-mail nas propriedades '
                        'do usuário no AD.')
        if not dados.department:
            self._aviso('a conta não tem `department` no AD — o campo fica '
                        'vazio no perfil do ITSM.')

        self._titulo(f'Grupos ({len(dados.groups)})')
        if not dados.groups:
            self._aviso('nenhum grupo retornado. Se a sua estrutura usa grupos '
                        'aninhados, ligue ITSM_LDAP_NESTED_GROUPS.')
        for grupo in sorted(dados.groups):
            self._item('', grupo)

        self._titulo('Papel que este usuário receberia no ITSM')
        papel = papel_para_grupos(dados.groups)
        papeis = dict(UserProfile.ROLE_CHOICES)
        if papel:
            self._ok(f'{papeis.get(papel, papel)} — por casar com o '
                     f'LDAP_GROUP_ROLE_MAP')
        else:
            padrao = settings.LDAP_DEFAULT_ROLE
            self._aviso(f'{papeis.get(padrao, padrao)} (LDAP_DEFAULT_ROLE) — '
                        f'nenhum grupo acima está no LDAP_GROUP_ROLE_MAP.')
            self.stdout.write('\n  Copie da lista de grupos acima os nomes '
                              'certos para o LDAP_GROUP_ROLE_MAP em '
                              'itsm_project/settings.py.')

    # ──────────────────────────────────────────────────────────────

    def _listar(self, username):
        """Conferência em massa: o que o ITSM leria de cada conta do AD.

        Mostra os dados que o login gravaria e o papel resultante, usando as
        mesmas funções do backend — a listagem não tem uma segunda
        implementação que poderia divergir.
        """
        self._titulo('Contas do diretório')
        try:
            contas = ldap_client.listar_usuarios(username, self._senha)
        except ldap_client.LdapIndisponivel as erro:
            self._erro(f'servidor indisponível: {erro}')
            return

        if contas is None:
            self._erro('credencial recusada na consulta.')
            return
        if not contas:
            self._aviso('nenhuma conta de pessoa encontrada em '
                        f'{settings.LDAP_SEARCH_BASE}.')
            return

        papeis = dict(UserProfile.ROLE_CHOICES)
        padrao = settings.LDAP_DEFAULT_ROLE
        self.stdout.write(
            f'  {"CONTA":<22}{"NOME":<26}{"E-MAIL":<30}'
            f'{"DEPARTAMENTO":<18}PAPEL')
        self.stdout.write('  ' + '-' * 112)

        sem_email = sem_nome = 0
        for conta in contas:
            nome = f'{conta.first_name} {conta.last_name}'.strip()
            papel = papel_para_grupos(conta.groups)
            rotulo = papeis.get(papel or padrao, papel or padrao)
            if papel is None:
                # Marca quem entra pelo padrão, para a lista não dar a
                # impressão de que o AD decidiu o papel dessa pessoa.
                rotulo += ' (padrão)'
            if not conta.email:
                sem_email += 1
            if not nome:
                sem_nome += 1
            self.stdout.write(
                f'  {conta.username:<22}{nome or "—":<26}'
                f'{conta.email or "—":<30}{conta.department or "—":<18}{rotulo}')

        self.stdout.write(f'\n  {len(contas)} conta(s).')
        if sem_email:
            self._aviso(f'{sem_email} sem e-mail: não receberão as '
                        'notificações por e-mail do ITSM.')
        if sem_nome:
            self._aviso(f'{sem_nome} sem nome legível: aparecerão pelo login.')
        if not sem_email and not sem_nome:
            self._ok('todas as contas têm nome e e-mail preenchidos.')
