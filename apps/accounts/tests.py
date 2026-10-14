"""Testes de autenticação e de controle de acesso por papel (RBAC)."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.testing import (criar_admin, criar_gerente,
                                   criar_solicitante, criar_tecnico)
from apps.tickets.models import Comment, Ticket


class LoginTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('thiago', 'thiago@exemplo.local', 'senha-de-teste')

    def test_tela_de_login_abre(self):
        r = self.client.get(reverse('accounts:login'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ITSM Enterprise')

    def test_login_valido_vai_para_o_dashboard(self):
        r = self.client.post(reverse('accounts:login'),
                             {'username': 'thiago', 'password': 'senha-de-teste'})
        self.assertRedirects(r, reverse('dashboard:index'))

    def test_login_invalido_mostra_erro(self):
        r = self.client.post(reverse('accounts:login'),
                             {'username': 'thiago', 'password': 'errada'}, follow=True)
        self.assertContains(r, 'inválidos')

    def test_usuario_logado_nao_ve_a_tela_de_login(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('accounts:login'))
        self.assertRedirects(r, reverse('dashboard:index'))

    def test_logout_volta_para_o_login(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('accounts:logout'))
        self.assertRedirects(r, reverse('accounts:login'))


# ══════════════════════════════════════════════════════════════════
# RBAC — Fase 3.1
# ══════════════════════════════════════════════════════════════════


class PerfilAutomaticoTests(TestCase):
    """O signal cria o perfil de todo usuário novo."""

    def test_usuario_comum_nasce_solicitante(self):
        u = User.objects.create_user('novo', 'novo@exemplo.local', 'x')
        self.assertEqual(u.profile.role, UserProfile.ROLE_REQUESTER)

    def test_superusuario_nasce_administrador(self):
        u = User.objects.create_superuser('chefe', 'chefe@exemplo.local', 'x')
        self.assertEqual(u.profile.role, UserProfile.ROLE_ADMIN)

    def test_um_perfil_por_usuario(self):
        u = User.objects.create_user('unico', 'unico@exemplo.local', 'x')
        u.first_name = 'Alterado'
        u.save()   # salvar de novo não pode duplicar o perfil
        self.assertEqual(UserProfile.objects.filter(user=u).count(), 1)

    def test_str_do_perfil(self):
        u = criar_tecnico('zelda')
        self.assertEqual(str(u.profile), 'zelda — Técnico')


class PermissoesDoPerfilTests(TestCase):
    """A tabela de permissões da Fase 3.1, papel por papel."""

    def test_tabela_de_permissoes(self):
        esperado = {
            # papel:      (todos, fila,  cmdb,  notas, relat, atende)
            'requester':  (False, False, False, False, False, False),
            'technician': (True,  True,  True,  True,  False, True),
            'manager':    (True,  True,  True,  True,  True,  True),
            'admin':      (True,  True,  True,  True,  True,  True),
        }
        for papel, flags in esperado.items():
            perfil = UserProfile(role=papel)
            with self.subTest(papel=papel):
                self.assertEqual(
                    (perfil.can_see_all_tickets, perfil.can_see_queue,
                     perfil.can_see_cmdb, perfil.can_see_internal_notes,
                     perfil.can_see_reports, perfil.can_attend),
                    flags)


class IsolamentoDoSolicitanteTests(TestCase):
    """Solicitante vê e acessa apenas os próprios chamados."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo')
        cls.leandro = criar_solicitante('leandro')
        cls.tecnico = criar_tecnico('tec')

        cls.do_paulo = Ticket.objects.create(
            title='Monitor do Paulo', description='d',
            requester=cls.paulo, priority='low')
        cls.do_leandro = Ticket.objects.create(
            title='Teclado do Leandro', description='d',
            requester=cls.leandro, priority='low')

        Comment.objects.create(
            ticket=cls.do_paulo, author=cls.tecnico, is_internal=True,
            content='SEGREDO-DA-EQUIPE: trocar o monitor sem avisar')
        Comment.objects.create(
            ticket=cls.do_paulo, author=cls.tecnico, is_internal=False,
            content='Peça solicitada ao fornecedor')

    def setUp(self):
        self.client.force_login(self.paulo)

    def test_lista_mostra_so_os_proprios(self):
        r = self.client.get(reverse('tickets:list'))
        self.assertContains(r, 'Monitor do Paulo')
        self.assertNotContains(r, 'Teclado do Leandro')

    def test_chamado_alheio_devolve_404(self):
        """404 e não 403: um 403 confirmaria que o chamado existe."""
        r = self.client.get(reverse('tickets:detail', args=[self.do_leandro.pk]))
        self.assertEqual(r.status_code, 404)

    def test_proprio_chamado_abre(self):
        r = self.client.get(reverse('tickets:detail', args=[self.do_paulo.pk]))
        self.assertEqual(r.status_code, 200)

    def test_nota_interna_nao_vai_no_html(self):
        """Filtrada no queryset: esconder no template deixaria o texto no
        código-fonte da página."""
        r = self.client.get(reverse('tickets:detail', args=[self.do_paulo.pk]))
        self.assertNotContains(r, 'SEGREDO-DA-EQUIPE')
        self.assertContains(r, 'Peça solicitada ao fornecedor')

    def test_tecnico_ve_a_nota_interna(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('tickets:detail', args=[self.do_paulo.pk]))
        self.assertContains(r, 'SEGREDO-DA-EQUIPE')

    def test_solicitante_nao_cria_nota_interna_nem_forjando_o_post(self):
        self.client.post(reverse('tickets:add_comment', args=[self.do_paulo.pk]),
                         {'content': 'tentativa', 'is_internal': 'on'})
        criado = Comment.objects.get(content='tentativa')
        self.assertFalse(criado.is_internal)

    def test_solicitante_nao_comenta_em_chamado_alheio(self):
        r = self.client.post(reverse('tickets:add_comment', args=[self.do_leandro.pk]),
                             {'content': 'intruso'})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Comment.objects.filter(content='intruso').exists())

    def test_solicitante_nao_altera_status(self):
        r = self.client.post(reverse('tickets:update_status', args=[self.do_paulo.pk]),
                             {'status': 'closed', 'priority': 'low'})
        self.do_paulo.refresh_from_db()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.do_paulo.status, 'open')

    def test_dashboard_conta_so_os_proprios(self):
        r = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r.context['stats']['total'], 1)


class AreasRestritasTests(TestCase):
    """Fila e CMDB exigem equipe; relatórios exigem gerente ou admin."""

    @classmethod
    def setUpTestData(cls):
        cls.solicitante = criar_solicitante('sol')
        cls.tecnico     = criar_tecnico('tec2')
        cls.gerente     = criar_gerente('ger')

    def _assert_bloqueado(self, url):
        r = self.client.get(url, follow=True)
        self.assertRedirects(r, reverse('dashboard:index'))
        self.assertContains(r, 'não tem permissão')

    def test_solicitante_bloqueado_na_fila_cmdb_e_relatorios(self):
        self.client.force_login(self.solicitante)
        for url in (reverse('tickets:queue'), reverse('cmdb:list'),
                    reverse('reports:dashboard'), reverse('reports:technician')):
            with self.subTest(url=url):
                self._assert_bloqueado(url)

    def test_solicitante_bloqueado_no_contador_da_fila(self):
        self.client.force_login(self.solicitante)
        self.assertEqual(self.client.get(reverse('tickets:unassigned_count')).status_code, 302)

    def test_tecnico_entra_na_fila_e_no_cmdb(self):
        self.client.force_login(self.tecnico)
        for url in (reverse('tickets:queue'), reverse('cmdb:list')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_tecnico_bloqueado_nos_relatorios(self):
        self.client.force_login(self.tecnico)
        self._assert_bloqueado(reverse('reports:dashboard'))

    def test_gerente_entra_em_tudo(self):
        self.client.force_login(self.gerente)
        for url in (reverse('tickets:queue'), reverse('cmdb:list'),
                    reverse('reports:dashboard')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class SidebarPorPerfilTests(TestCase):
    """A sidebar esconde o que o perfil não acessa."""

    @classmethod
    def setUpTestData(cls):
        cls.solicitante = criar_solicitante('sol2')
        cls.tecnico     = criar_tecnico('tec3')
        cls.admin       = criar_admin('adm')

    def _html_do_dashboard(self, user):
        self.client.force_login(user)
        return self.client.get(reverse('dashboard:index')).content.decode()

    def test_solicitante_nao_ve_os_menus_restritos(self):
        html = self._html_do_dashboard(self.solicitante)
        # Checa os LINKS, não as palavras: títulos de seção também citariam
        # "Relatórios" sem que o link exista.
        self.assertNotIn(reverse('tickets:queue'), html)
        self.assertNotIn(reverse('cmdb:list'), html)
        self.assertNotIn(reverse('reports:dashboard'), html)
        self.assertIn('Meus Chamados', html)
        self.assertIn('Solicitante', html)

    def test_tecnico_ve_fila_e_cmdb_mas_nao_relatorios(self):
        html = self._html_do_dashboard(self.tecnico)
        self.assertIn(reverse('tickets:queue'), html)
        self.assertIn(reverse('cmdb:list'), html)
        self.assertNotIn(reverse('reports:dashboard'), html)

    def test_admin_ve_tudo(self):
        html = self._html_do_dashboard(self.admin)
        for url in (reverse('tickets:queue'), reverse('cmdb:list'),
                    reverse('reports:dashboard')):
            with self.subTest(url=url):
                self.assertIn(url, html)


class SeletorDeTecnicoTests(TestCase):
    """O seletor de técnico vem do perfil, não da flag is_staff."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico     = criar_tecnico('tec4')
        cls.gerente     = criar_gerente('ger2')
        cls.solicitante = criar_solicitante('sol3')
        # is_staff=True mas papel de solicitante: NÃO deve atender chamados.
        cls.staff_sem_papel = criar_solicitante('staff_sem_papel', is_staff=True)

    def test_fila_lista_apenas_quem_atende(self):
        self.client.force_login(self.tecnico)
        tecnicos = self.client.get(reverse('tickets:queue')).context['technicians']
        self.assertIn(self.tecnico, tecnicos)
        self.assertIn(self.gerente, tecnicos)
        self.assertNotIn(self.solicitante, tecnicos)
        self.assertNotIn(self.staff_sem_papel, tecnicos)
