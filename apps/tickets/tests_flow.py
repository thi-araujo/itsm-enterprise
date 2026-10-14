"""Testes do fluxo de atendimento — Fase 3.2.

Cobre finalizar o chamado (solução obrigatória) e escalonar para outro
membro da equipe (motivo obrigatório), incluindo as tentativas de burlar o
formulário por POST forjado.
"""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.testing import criar_solicitante, criar_tecnico
from apps.notifications.models import Notification
from apps.tickets.models import Comment, Escalation, Ticket


class FinalizarChamadoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_f')
        cls.tecnico = criar_tecnico('tec_f')

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Impressora travada', description='Não imprime',
            requester=self.paulo, assignee=self.tecnico, priority='medium')
        self.url = reverse('tickets:finish', args=[self.ticket.pk])
        self.client.force_login(self.tecnico)

    # ── Validação da solução ──────────────────────────────────────

    def test_sem_solucao_nao_finaliza(self):
        r = self.client.post(self.url, {'solution': ''}, follow=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        self.assertIsNone(self.ticket.resolved_at)
        self.assertContains(r, 'obrigatório')

    def test_solucao_curta_e_rejeitada(self):
        """"ok" não documenta nada — o form exige 10 caracteres."""
        r = self.client.post(self.url, {'solution': 'ok'}, follow=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        self.assertEqual(self.ticket.solution, '')
        self.assertContains(r, '10 caracteres')

    def test_get_nao_finaliza(self):
        """A view só aceita POST: um GET não pode mudar estado."""
        self.client.get(self.url)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')

    # ── Caminho feliz ─────────────────────────────────────────────

    def test_finalizar_grava_solucao_status_e_autor(self):
        self.client.post(self.url, {'solution': 'Troquei o cabo USB e o toner.'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'resolved')
        self.assertEqual(self.ticket.solution, 'Troquei o cabo USB e o toner.')
        self.assertEqual(self.ticket.resolved_by, self.tecnico)
        # resolved_at vem do save() do model, não da view.
        self.assertIsNotNone(self.ticket.resolved_at)

    def test_finalizar_registra_comentario_publico(self):
        """A solução entra na linha do tempo, visível ao solicitante."""
        self.client.post(self.url, {'solution': 'Reinstalei o driver da impressora.'})
        comentario = self.ticket.comments.get()
        self.assertFalse(comentario.is_internal)
        self.assertIn('Reinstalei o driver', comentario.content)

    def test_finalizar_notifica_o_solicitante_com_a_solucao(self):
        self.client.post(self.url, {'solution': 'Substituí a placa de rede.'})
        notif = Notification.objects.get(user=self.paulo, type='ticket_resolved')
        self.assertIn('Substituí a placa de rede.', notif.message)
        # A equipe não é notificada: a resolução interessa a quem abriu.
        self.assertFalse(Notification.objects.filter(
            user=self.tecnico, type='ticket_resolved').exists())

    def test_solucao_aparece_na_pagina_para_o_solicitante(self):
        self.client.post(self.url, {'solution': 'Formatei e reinstalei o Windows.'})
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertContains(r, 'Formatei e reinstalei o Windows.')

    def test_chamado_ja_resolvido_nao_finaliza_de_novo(self):
        self.ticket.status = 'resolved'
        self.ticket.save()
        r = self.client.post(self.url, {'solution': 'Tentando de novo agora.'},
                             follow=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.solution, '')
        self.assertContains(r, 'já está resolvido')

    def test_can_be_finished(self):
        for status, esperado in [('open', True), ('in_progress', True),
                                 ('waiting', True), ('resolved', False),
                                 ('closed', False)]:
            with self.subTest(status=status):
                self.assertEqual(Ticket(status=status).can_be_finished, esperado)

    # ── RBAC ──────────────────────────────────────────────────────

    def test_solicitante_nao_finaliza_nem_forjando_o_post(self):
        self.client.force_login(self.paulo)
        r = self.client.post(self.url, {'solution': 'Vou dizer que resolvi.'})
        self.ticket.refresh_from_db()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ticket.status, 'open')
        self.assertEqual(self.ticket.solution, '')

    def test_solicitante_nao_ve_o_botao_finalizar(self):
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertNotContains(r, reverse('tickets:finish', args=[self.ticket.pk]))


class EscalonarChamadoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo    = criar_solicitante('paulo_e')
        cls.tecnico1 = criar_tecnico('tec_e1')
        cls.tecnico2 = criar_tecnico('tec_e2')

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='VPN instável', description='Cai a cada 5 minutos',
            requester=self.paulo, assignee=self.tecnico1, priority='high')
        self.url = reverse('tickets:escalate', args=[self.ticket.pk])
        self.client.force_login(self.tecnico1)

    # ── Validação ─────────────────────────────────────────────────

    def test_sem_motivo_nao_escalona(self):
        r = self.client.post(self.url, {'to_user': self.tecnico2.pk, 'reason': ''},
                             follow=True)
        self.assertEqual(Escalation.objects.count(), 0)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.tecnico1)
        self.assertContains(r, 'obrigatório')

    def test_motivo_curto_e_rejeitado(self):
        self.client.post(self.url, {'to_user': self.tecnico2.pk, 'reason': 'sei la'})
        self.assertEqual(Escalation.objects.count(), 0)

    def test_sem_destino_nao_escalona(self):
        self.client.post(self.url, {'to_user': '', 'reason': 'Preciso de ajuda com o firewall.'})
        self.assertEqual(Escalation.objects.count(), 0)

    def test_nao_escalona_para_si_mesmo(self):
        """O próprio usuário sai do queryset do form, então o POST é inválido."""
        self.client.post(self.url, {'to_user': self.tecnico1.pk,
                                    'reason': 'Quero ficar com o chamado mesmo.'})
        self.assertEqual(Escalation.objects.count(), 0)

    def test_nao_escalona_para_solicitante(self):
        """Só quem atende pode receber um chamado escalonado."""
        self.client.post(self.url, {'to_user': self.paulo.pk,
                                    'reason': 'Passando para o usuário resolver.'})
        self.assertEqual(Escalation.objects.count(), 0)

    def test_chamado_encerrado_nao_escalona(self):
        """Repassar um chamado já resolvido reatribuiria o responsável sem
        ninguém esperar por isso."""
        for status in ('resolved', 'closed'):
            with self.subTest(status=status):
                self.ticket.status = status
                self.ticket.save()
                r = self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                                'reason': 'Reabrindo pelo caminho errado.'},
                                     follow=True)
                self.assertEqual(Escalation.objects.count(), 0)
                self.assertContains(r, 'não pode ser escalonado')

    def test_solicitante_nao_ve_o_botao_escalonar(self):
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertNotContains(r, reverse('tickets:escalate', args=[self.ticket.pk]))

    # ── Caminho feliz ─────────────────────────────────────────────

    def test_escalonar_grava_historico_e_troca_o_responsavel(self):
        self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                    'reason': 'Problema é de roteamento, fora do meu escopo.'})
        esc = Escalation.objects.get()
        self.assertEqual(esc.ticket, self.ticket)
        self.assertEqual(esc.from_user, self.tecnico1)
        self.assertEqual(esc.to_user, self.tecnico2)
        self.assertIn('roteamento', esc.reason)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.tecnico2)
        # 'open' passa a 'in_progress': escalonado é chamado em atendimento.
        self.assertEqual(self.ticket.status, 'in_progress')

    def test_escalonar_nao_rebaixa_status_ja_avancado(self):
        self.ticket.status = 'waiting'
        self.ticket.save()
        self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                    'reason': 'Aguardando peça, repasso o acompanhamento.'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'waiting')

    def test_escalonar_notifica_quem_recebeu(self):
        self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                    'reason': 'Caso precisa de acesso ao core switch.'})
        notif = Notification.objects.get(user=self.tecnico2, type='ticket_escalated')
        self.assertIn('core switch', notif.message)

    def test_dois_escalonamentos_ficam_no_historico(self):
        self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                    'reason': 'Primeiro repasse, falta acesso.'})
        self.client.force_login(self.tecnico2)
        self.client.post(self.url, {'to_user': self.tecnico1.pk,
                                    'reason': 'Devolvendo, consegui o acesso para você.'})
        self.assertEqual(self.ticket.escalations.count(), 2)

    # ── RBAC ──────────────────────────────────────────────────────

    def test_solicitante_nao_escalona_nem_forjando_o_post(self):
        self.client.force_login(self.paulo)
        r = self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                        'reason': 'Quero outro técnico neste caso.'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Escalation.objects.count(), 0)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.tecnico1)

    def test_solicitante_nao_ve_o_historico_de_escalonamento(self):
        """Filtrado no queryset, como as notas internas: esconder no template
        deixaria o motivo no código-fonte da página."""
        self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                    'reason': 'MOTIVO-INTERNO: usuário não colabora.'})
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertNotContains(r, 'MOTIVO-INTERNO')

    def test_tecnico_ve_o_historico(self):
        self.client.post(self.url, {'to_user': self.tecnico2.pk,
                                    'reason': 'MOTIVO-INTERNO: usuário não colabora.'})
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertContains(r, 'MOTIVO-INTERNO')


class ChamadosAntigosTests(TestCase):
    """Os chamados que já existiam têm `solution` vazia e `resolved_by` nulo —
    nenhuma tela pode quebrar por isso (mesma regra do `assignee` nulo)."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('tec_antigo')
        cls.antigo  = Ticket.objects.create(
            title='Chamado sem solução', description='d',
            requester=cls.tecnico, priority='low', status='resolved')

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_telas_renderizam_sem_solucao(self):
        for url in (reverse('dashboard:index'),
                    reverse('tickets:list'),
                    reverse('tickets:queue'),
                    reverse('tickets:detail', args=[self.antigo.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_cartao_de_solucao_nao_aparece_quando_vazia(self):
        r = self.client.get(reverse('tickets:detail', args=[self.antigo.pk]))
        self.assertEqual(self.antigo.solution, '')
        self.assertNotContains(r, 'id="solution-card"')
