"""Testes do workflow de aprovação — Fase 3.3.

Cobre o gatilho por categoria, o SLA que só começa a contar depois da
aprovação, a decisão do gerente e as tentativas de burlar o fluxo por POST
forjado.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import (criar_admin, criar_gerente,
                                   criar_solicitante, criar_tecnico)
from apps.notifications.models import Notification
from apps.tickets.models import Approval, Category, Ticket


class GatilhoPorCategoriaTests(TestCase):
    """A categoria decide se o chamado nasce aguardando aprovação."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo    = criar_solicitante('paulo_ap')
        cls.gerente  = criar_gerente('ger_ap')
        cls.com_aprovacao = Category.objects.create(
            name='Acesso e Permissões', requires_approval=True)
        cls.sem_aprovacao = Category.objects.create(
            name='Impressão', requires_approval=False)

    def setUp(self):
        self.client.force_login(self.paulo)

    def _abrir(self, categoria, priority='critical', title='Chamado'):
        dados = {'title': title, 'description': 'd',
                 'ticket_type': 'request', 'priority': priority}
        if categoria is not None:
            dados['category'] = categoria.pk
        self.client.post(reverse('tickets:create'), dados)
        return Ticket.objects.get(title=title)

    def test_categoria_normal_nasce_aberto_com_sla(self):
        t = self._abrir(self.sem_aprovacao, title='Impressora sem tinta')
        self.assertEqual(t.status, 'open')
        self.assertIsNotNone(t.sla_deadline)

    def test_categoria_com_aprovacao_nasce_pendente_e_sem_sla(self):
        """O ponto central da fase: o relógio do SLA não pode começar antes
        da aprovação, senão um crítico (2h) parado no fim de semana já nasce
        vencido e ninguém podia atendê-lo."""
        t = self._abrir(self.com_aprovacao, title='Acesso ao sistema de RH')
        self.assertEqual(t.status, 'pending_approval')
        self.assertIsNone(t.sla_deadline)
        self.assertFalse(t.is_sla_breached)
        self.assertIsNone(t.sla_remaining_hours)
        self.assertTrue(t.is_awaiting_approval)

    def test_chamado_sem_categoria_nasce_aberto(self):
        t = self._abrir(None, title='Sem categoria nenhuma')
        self.assertEqual(t.status, 'open')
        self.assertIsNotNone(t.sla_deadline)

    def test_pendente_nao_aparece_na_fila_dos_tecnicos(self):
        t = self._abrir(self.com_aprovacao, title='Acesso ao financeiro')
        tecnico = criar_tecnico('tec_fila_ap')
        self.client.force_login(tecnico)
        r = self.client.get(reverse('tickets:queue'))
        self.assertNotContains(r, 'Acesso ao financeiro')
        self.assertEqual(t.status, 'pending_approval')

    def test_pendente_nao_conta_no_badge_de_sem_tecnico(self):
        """O badge da fila conta chamados atendíveis; pendente não é um."""
        self._abrir(self.com_aprovacao, title='Acesso ao CRM')
        tecnico = criar_tecnico('tec_badge_ap')
        self.client.force_login(tecnico)
        self.assertEqual(self.client.get(reverse('tickets:unassigned_count')).json(),
                         {'count': 0})

    def test_aviso_na_criacao_menciona_a_aprovacao(self):
        dados = {'title': 'Acesso ao SAP', 'description': 'd',
                 'ticket_type': 'request', 'priority': 'low',
                 'category': self.com_aprovacao.pk}
        r = self.client.post(reverse('tickets:create'), dados, follow=True)
        self.assertContains(r, 'enviado para aprovação')

    def test_notificacao_vai_para_quem_aprova_e_nao_para_a_equipe(self):
        tecnico = criar_tecnico('tec_notif_ap')
        self._abrir(self.com_aprovacao, title='Acesso ao Jira')
        self.assertTrue(Notification.objects.filter(
            user=self.gerente, type='approval_requested').exists())
        # O técnico não é avisado: enquanto não houver aprovação não há nada
        # que ele possa fazer com o chamado.
        self.assertFalse(Notification.objects.filter(user=tecnico).exists())

    def test_tela_de_criacao_avisa_quais_categorias_exigem_aprovacao(self):
        r = self.client.get(reverse('tickets:create'))
        self.assertContains(r, 'Exige aprovação')
        self.assertContains(r, 'Acesso e Permissões')


class DecisaoDeAprovacaoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_dec')
        cls.gerente = criar_gerente('ger_dec')
        cls.tecnico = criar_tecnico('tec_dec')
        cls.categoria = Category.objects.create(name='Acessos', requires_approval=True)

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Acesso ao sistema financeiro', description='d',
            requester=self.paulo, category=self.categoria,
            priority='critical', status='pending_approval')
        self.aprovar  = reverse('tickets:approve', args=[self.ticket.pk])
        self.rejeitar = reverse('tickets:reject', args=[self.ticket.pk])
        self.client.force_login(self.gerente)

    # ── Aprovar ───────────────────────────────────────────────────

    def test_aprovar_libera_para_a_fila(self):
        self.client.post(self.aprovar, {'comment': ''})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        self.assertEqual(self.ticket.approvals.count(), 1)
        self.assertTrue(self.ticket.last_approval.is_approved)
        self.assertEqual(self.ticket.last_approval.decided_by, self.gerente)

    def test_sla_comeca_a_contar_na_aprovacao(self):
        """O prazo é contado a partir de agora, não da abertura."""
        self.assertIsNone(self.ticket.sla_deadline)
        antes = timezone.now()
        self.client.post(self.aprovar, {'comment': ''})
        self.ticket.refresh_from_db()
        # Prioridade crítica: 2h a partir da decisão (CLAUDE.md).
        horas = (self.ticket.sla_deadline - antes).total_seconds() / 3600
        self.assertAlmostEqual(horas, 2, delta=0.1)
        self.assertFalse(self.ticket.is_sla_breached)

    def test_aprovar_sem_parecer_e_permitido(self):
        """Ao aprovar, o parecer é opcional — ao rejeitar, não."""
        self.client.post(self.aprovar, {'comment': ''})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        self.assertEqual(self.ticket.last_approval.comment, '')

    def test_parecer_entra_na_linha_do_tempo(self):
        self.client.post(self.aprovar, {'comment': 'Aprovado conforme política de acesso.'})
        comentario = self.ticket.comments.get()
        self.assertFalse(comentario.is_internal)
        self.assertIn('política de acesso', comentario.content)

    def test_aprovar_notifica_o_solicitante(self):
        self.client.post(self.aprovar, {'comment': 'Liberado pelo gestor da área.'})
        notif = Notification.objects.get(user=self.paulo, type='approval_decided')
        self.assertIn('aprovado', notif.title)
        self.assertIn('gestor da área', notif.message)

    # ── Rejeitar ──────────────────────────────────────────────────

    def test_rejeitar_sem_motivo_e_recusado(self):
        r = self.client.post(self.rejeitar, {'comment': ''}, follow=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'pending_approval')
        self.assertEqual(Approval.objects.count(), 0)
        self.assertContains(r, 'obrigatório')

    def test_rejeitar_com_motivo_curto_e_recusado(self):
        r = self.client.post(self.rejeitar, {'comment': 'nao'}, follow=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'pending_approval')
        self.assertContains(r, '10 caracteres')

    def test_rejeitar_encerra_o_chamado(self):
        self.client.post(self.rejeitar,
                         {'comment': 'Pedido sem aprovação do gestor da área.'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'rejected')
        self.assertFalse(self.ticket.last_approval.is_approved)
        # Rejeitado não conta SLA nem volta a ser atendível.
        self.assertIsNone(self.ticket.sla_deadline)
        self.assertFalse(self.ticket.is_sla_breached)
        self.assertFalse(self.ticket.can_be_finished)
        self.assertFalse(self.ticket.can_be_escalated)

    def test_solicitante_ve_o_motivo_da_rejeicao(self):
        """Ao contrário do motivo de escalonamento, este é para o solicitante."""
        self.client.post(self.rejeitar,
                         {'comment': 'MOTIVO-VISIVEL: falta aprovação do gestor.'})
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertContains(r, 'MOTIVO-VISIVEL')
        self.assertContains(r, 'Chamado rejeitado')

    # ── Guardas ───────────────────────────────────────────────────

    def test_nao_decide_duas_vezes(self):
        self.client.post(self.aprovar, {'comment': ''})
        r = self.client.post(self.rejeitar, {'comment': 'Mudei de ideia agora.'},
                             follow=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        self.assertEqual(Approval.objects.count(), 1)
        self.assertContains(r, 'não está aguardando aprovação')

    def test_chamado_que_nao_precisa_de_aprovacao_nao_e_aprovavel(self):
        normal = Ticket.objects.create(title='Normal', description='d',
                                       requester=self.paulo, priority='low')
        r = self.client.post(reverse('tickets:approve', args=[normal.pk]),
                             {'comment': ''}, follow=True)
        normal.refresh_from_db()
        self.assertEqual(normal.status, 'open')
        self.assertEqual(Approval.objects.count(), 0)
        self.assertContains(r, 'não está aguardando aprovação')

    def test_get_nao_decide(self):
        self.client.get(self.aprovar)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'pending_approval')
        self.assertEqual(Approval.objects.count(), 0)

    def test_painel_de_gestao_escondido_enquanto_aguarda(self):
        """Não há o que gerenciar: o chamado nem foi autorizado ainda."""
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertNotContains(r, reverse('tickets:update_status', args=[self.ticket.pk]))
        self.assertNotContains(r, reverse('tickets:finish', args=[self.ticket.pk]))


class PermissaoDeAprovacaoTests(TestCase):
    """Só gerente e admin decidem (UserProfile.can_approve)."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_perm')
        cls.tecnico = criar_tecnico('tec_perm')
        cls.gerente = criar_gerente('ger_perm')
        cls.admin   = criar_admin('adm_perm')
        cls.categoria = Category.objects.create(name='Acessos2', requires_approval=True)

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Acesso ao AD', description='d', requester=self.paulo,
            category=self.categoria, priority='medium', status='pending_approval')

    def test_can_approve_por_papel(self):
        esperado = {'requester': False, 'technician': False,
                    'manager': True, 'admin': True}
        for user in (self.paulo, self.tecnico, self.gerente, self.admin):
            with self.subTest(papel=user.profile.role):
                self.assertEqual(user.profile.can_approve,
                                 esperado[user.profile.role])

    def test_tecnico_nao_aprova_nem_forjando_o_post(self):
        self.client.force_login(self.tecnico)
        r = self.client.post(reverse('tickets:approve', args=[self.ticket.pk]),
                             {'comment': ''})
        self.ticket.refresh_from_db()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ticket.status, 'pending_approval')
        self.assertEqual(Approval.objects.count(), 0)

    def test_solicitante_nao_aprova_o_proprio_chamado(self):
        self.client.force_login(self.paulo)
        self.client.post(reverse('tickets:approve', args=[self.ticket.pk]),
                         {'comment': ''})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'pending_approval')

    def test_fila_de_aprovacao_so_para_quem_aprova(self):
        for user, liberado in [(self.paulo, False), (self.tecnico, False),
                               (self.gerente, True), (self.admin, True)]:
            with self.subTest(papel=user.profile.role):
                self.client.force_login(user)
                r = self.client.get(reverse('tickets:approvals'))
                self.assertEqual(r.status_code, 200 if liberado else 302)

    def test_contador_do_badge_so_para_quem_aprova(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(
            reverse('tickets:pending_approval_count')).json(), {'count': 1})
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(
            reverse('tickets:pending_approval_count')).status_code, 302)

    def test_menu_aprovacoes_so_para_quem_aprova(self):
        url = reverse('tickets:approvals')
        for user, visivel in [(self.paulo, False), (self.tecnico, False),
                              (self.gerente, True), (self.admin, True)]:
            with self.subTest(papel=user.profile.role):
                self.client.force_login(user)
                html = self.client.get(reverse('dashboard:index')).content.decode()
                self.assertEqual(url in html, visivel)

    def test_fila_de_aprovacao_lista_os_pendentes(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse('tickets:approvals'))
        self.assertContains(r, 'Acesso ao AD')
        self.assertEqual(r.context['total'], 1)

    def test_solicitante_ve_o_proprio_chamado_pendente_sem_os_botoes(self):
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertContains(r, 'Aguardando aprovação do gerente')
        self.assertNotContains(r, reverse('tickets:approve', args=[self.ticket.pk]))
        self.assertNotContains(r, reverse('tickets:reject', args=[self.ticket.pk]))


class StatusDoWorkflowTests(TestCase):
    """Os status do workflow não ficam no <select> do painel de gestão."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('tec_sel')
        cls.ticket  = Ticket.objects.create(title='t', description='d',
                                            requester=cls.tecnico, priority='low')

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_select_de_status_nao_oferece_os_do_workflow(self):
        from apps.tickets.forms import TicketUpdateForm
        valores = [v for v, _ in TicketUpdateForm().fields['status'].choices]
        self.assertNotIn('pending_approval', valores)
        self.assertNotIn('rejected', valores)
        self.assertIn('open', valores)
        self.assertIn('resolved', valores)

    def test_post_forjado_com_status_do_workflow_e_recusado(self):
        """O Django valida contra as choices do campo, então não precisa de
        validação extra na view."""
        for status in ('pending_approval', 'rejected'):
            with self.subTest(status=status):
                self.client.post(
                    reverse('tickets:update_status', args=[self.ticket.pk]),
                    {'status': status, 'priority': 'low'})
                self.ticket.refresh_from_db()
                self.assertEqual(self.ticket.status, 'open')


class ChamadosExistentesTests(TestCase):
    """As categorias sem a flag e os chamados já abertos não mudam de
    comportamento (o banco tem 13 chamados anteriores à fase)."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico   = criar_tecnico('tec_leg')
        cls.categoria = Category.objects.create(name='Rede', requires_approval=False)
        cls.ticket    = Ticket.objects.create(
            title='Chamado anterior', description='d', requester=cls.tecnico,
            category=cls.categoria, priority='high', status='in_progress')

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_categoria_sem_flag_nao_muda_nada(self):
        self.assertFalse(self.categoria.requires_approval)
        self.assertIsNotNone(self.ticket.sla_deadline)
        self.assertTrue(self.ticket.can_be_finished)

    def test_telas_renderizam(self):
        for url in (reverse('dashboard:index'), reverse('tickets:list'),
                    reverse('tickets:queue'),
                    reverse('tickets:detail', args=[self.ticket.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_sem_aprovacao_nao_mostra_cartao_de_decisao(self):
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertNotContains(r, 'id="approval-card"')
        self.assertNotContains(r, 'id="approval-banner"')
