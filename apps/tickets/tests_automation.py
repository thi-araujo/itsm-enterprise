"""Testes das automações de SLA — Fase 3.7.

Os limites vêm do settings, então os testes usam @override_settings — é a
prova de que não há número cravado no código.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import (criar_admin, criar_gerente,
                                   criar_solicitante, criar_tecnico)
from apps.notifications.models import Notification
from apps.tickets import automation
from apps.tickets.models import AuditLog, Category, Escalation, Ticket


def ticket_com_prazo(requester, horas_decorridas, horas_totais=10, **extra):
    """Cria um chamado com o relógio do SLA numa posição conhecida.

    Define `sla_started_at` e `sla_deadline` na mão para o teste não depender
    de esperar o tempo passar.
    """
    agora  = timezone.now()
    inicio = agora - timezone.timedelta(hours=horas_decorridas)
    extra.setdefault('title', 't')
    extra.setdefault('description', 'd')
    extra.setdefault('priority', 'medium')
    ticket = Ticket.objects.create(requester=requester, **extra)
    Ticket.objects.filter(pk=ticket.pk).update(
        sla_started_at=inicio,
        sla_deadline=inicio + timezone.timedelta(hours=horas_totais))
    return Ticket.objects.get(pk=ticket.pk)


class PercentualDoPrazoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_solicitante('sol_pct')

    def test_percentual_decorrido(self):
        for decorridas, esperado in [(0, 0), (5, 50), (8, 80), (10, 100), (20, 200)]:
            with self.subTest(horas=decorridas):
                t = ticket_com_prazo(self.user, decorridas, horas_totais=10)
                self.assertAlmostEqual(t.sla_elapsed_percent, esperado, delta=1)

    def test_sem_prazo_devolve_none(self):
        """Chamado aguardando aprovação não tem relógio contando."""
        categoria = Category.objects.create(name='Acessos', requires_approval=True)
        t = Ticket.objects.create(title='t', description='d', requester=self.user,
                                  category=categoria, priority='low',
                                  status='pending_approval')
        self.assertIsNone(t.sla_deadline)
        self.assertIsNone(t.sla_elapsed_percent)
        self.assertFalse(t.sla_at_risk)

    def test_encerrado_devolve_none(self):
        for status in ('resolved', 'closed', 'rejected'):
            with self.subTest(status=status):
                t = ticket_com_prazo(self.user, 9, status=status)
                self.assertIsNone(t.sla_elapsed_percent)
                self.assertFalse(t.sla_at_risk)

    @override_settings(SLA_WARNING_PERCENT=80)
    def test_em_risco_usa_o_limite_do_settings(self):
        self.assertFalse(ticket_com_prazo(self.user, 5).sla_at_risk)    # 50%
        self.assertTrue(ticket_com_prazo(self.user, 8.5).sla_at_risk)   # 85%

    @override_settings(SLA_WARNING_PERCENT=40)
    def test_limite_mais_agressivo(self):
        """Com o limite em 40%, 50% do prazo já é risco."""
        self.assertTrue(ticket_com_prazo(self.user, 5).sla_at_risk)

    def test_vencido_nao_e_em_risco(self):
        """Em risco é "vai vencer"; vencido é outro estado."""
        t = ticket_com_prazo(self.user, 12)
        self.assertTrue(t.is_sla_breached)
        self.assertFalse(t.sla_at_risk)

    def test_sla_iniciado_na_criacao(self):
        t = Ticket.objects.create(title='t', description='d',
                                  requester=self.user, priority='high')
        self.assertIsNotNone(t.sla_started_at)
        horas = (t.sla_deadline - t.sla_started_at).total_seconds() / 3600
        self.assertAlmostEqual(horas, 8, delta=0.01)

    def test_sla_iniciado_na_aprovacao(self):
        """O relógio começa na decisão do gerente, não na abertura."""
        categoria = Category.objects.create(name='Acessos2', requires_approval=True)
        gerente = criar_gerente('ger_inicio')
        t = Ticket.objects.create(title='t', description='d', requester=self.user,
                                  category=categoria, priority='critical',
                                  status='pending_approval')
        self.assertIsNone(t.sla_started_at)
        self.client.force_login(gerente)
        self.client.post(reverse('tickets:approve', args=[t.pk]), {'comment': ''})
        t.refresh_from_db()
        self.assertIsNotNone(t.sla_started_at)
        self.assertAlmostEqual(t.sla_elapsed_percent, 0, delta=1)


@override_settings(SLA_WARNING_PERCENT=80)
class AvisoPrevioTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_av')
        cls.tecnico = criar_tecnico('tec_av')

    def test_abaixo_do_limite_nao_avisa(self):
        ticket_com_prazo(self.paulo, 5, assignee=self.tecnico)
        self.assertEqual(automation.avisar_sla_proximo(), [])

    def test_acima_do_limite_avisa_o_responsavel(self):
        t = ticket_com_prazo(self.paulo, 8.5, assignee=self.tecnico)
        avisados = automation.avisar_sla_proximo()
        self.assertEqual([x.pk for x in avisados], [t.pk])
        notif = Notification.objects.get(user=self.tecnico, type='sla_warning')
        self.assertIn('SLA em risco', notif.title)
        t.refresh_from_db()
        self.assertTrue(t.sla_warning_notified)

    def test_sem_responsavel_avisa_a_equipe(self):
        """Chamado perto de vencer e sem dono é problema de todos."""
        ticket_com_prazo(self.paulo, 9)
        automation.avisar_sla_proximo()
        self.assertTrue(Notification.objects.filter(
            user=self.tecnico, type='sla_warning').exists())
        self.assertFalse(Notification.objects.filter(
            user=self.paulo, type='sla_warning').exists())

    def test_nao_avisa_duas_vezes(self):
        """O comando roda de 15 em 15 minutos."""
        ticket_com_prazo(self.paulo, 8.5, assignee=self.tecnico)
        automation.avisar_sla_proximo()
        self.assertEqual(automation.avisar_sla_proximo(), [])
        self.assertEqual(Notification.objects.filter(type='sla_warning').count(), 1)

    def test_vencido_nao_recebe_aviso_previo(self):
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        self.assertEqual(automation.avisar_sla_proximo(), [])

    def test_encerrado_nao_recebe_aviso(self):
        for status in ('resolved', 'closed', 'rejected'):
            with self.subTest(status=status):
                ticket_com_prazo(self.paulo, 9, assignee=self.tecnico, status=status)
        self.assertEqual(automation.avisar_sla_proximo(), [])

    def test_dry_run_nao_grava(self):
        t = ticket_com_prazo(self.paulo, 8.5, assignee=self.tecnico)
        avisados = automation.avisar_sla_proximo(dry_run=True)
        self.assertEqual(len(avisados), 1)
        t.refresh_from_db()
        self.assertFalse(t.sla_warning_notified)
        self.assertEqual(Notification.objects.filter(type='sla_warning').count(), 0)


@override_settings(SLA_AUTO_ESCALATE=True)
class EscalonamentoAutomaticoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_esc')
        cls.tecnico = criar_tecnico('tec_esc')
        cls.gerente = criar_gerente('ger_esc')

    def test_vencido_vai_para_o_gerente(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        resultado = automation.escalonar_sla_vencido()
        self.assertEqual(resultado, [(t, self.gerente)])
        t.refresh_from_db()
        self.assertEqual(t.assignee, self.gerente)
        self.assertIsNotNone(t.sla_escalated_at)

    def test_escalonamento_fica_no_historico_como_sistema(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        automation.escalonar_sla_vencido()
        esc = Escalation.objects.get(ticket=t)
        self.assertIsNone(esc.from_user)        # "Sistema" na tela
        self.assertEqual(esc.to_user, self.gerente)
        self.assertIn('Escalonamento automático', esc.reason)
        self.assertIn('SLA vencido', esc.reason)

    def test_trilha_de_auditoria_mostra_sistema(self):
        """É aqui que a auditoria da Fase 3.4 se paga."""
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        automation.escalonar_sla_vencido()
        evento = t.audit_logs.get(action=AuditLog.ACTION_ESCALATED)
        self.assertIsNone(evento.user)
        self.assertEqual(evento.author_display, 'Sistema')
        # A troca de responsável também entra, pelo save() do model.
        troca = t.audit_logs.get(field='Técnico Responsável')
        self.assertEqual(troca.author_display, 'Sistema')
        self.assertEqual(troca.new_value, 'ger_esc')

    def test_sem_responsavel_tambem_escalona(self):
        """Vencido e sem dono: o escalonamento dá um responsável a ele."""
        t = ticket_com_prazo(self.paulo, 12)
        automation.escalonar_sla_vencido()
        t.refresh_from_db()
        self.assertEqual(t.assignee, self.gerente)

    def test_ja_com_gerente_nao_troca_de_responsavel(self):
        """Repassar de gerente para gerente é ruído."""
        t = ticket_com_prazo(self.paulo, 12, assignee=self.gerente)
        resultado = automation.escalonar_sla_vencido()
        self.assertEqual(resultado, [(t, None)])
        t.refresh_from_db()
        self.assertEqual(t.assignee, self.gerente)
        self.assertIsNotNone(t.sla_escalated_at)   # marcado, para não repetir
        self.assertEqual(Escalation.objects.count(), 0)

    def test_nao_escalona_duas_vezes(self):
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        automation.escalonar_sla_vencido()
        self.assertEqual(automation.escalonar_sla_vencido(), [])
        self.assertEqual(Escalation.objects.count(), 1)

    def test_distribui_pelo_gerente_com_menos_carga(self):
        outro = criar_admin('adm_esc')
        # O gerente já tem 2 chamados ativos; o admin, nenhum.
        for i in range(2):
            Ticket.objects.create(title=f'carga{i}', description='d',
                                  requester=self.paulo, assignee=self.gerente,
                                  priority='low')
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        automation.escalonar_sla_vencido()
        t.refresh_from_db()
        self.assertEqual(t.assignee, outro)

    def test_chamado_encerrado_nao_conta_como_carga(self):
        outro = criar_admin('adm_esc2')
        # 3 chamados do 'outro', todos encerrados: carga real é zero.
        for status in ('resolved', 'closed', 'rejected'):
            Ticket.objects.create(title=f'fim{status}', description='d',
                                  requester=self.paulo, assignee=outro,
                                  priority='low', status=status)
        Ticket.objects.create(title='ativo', description='d', requester=self.paulo,
                              assignee=self.gerente, priority='low')
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        automation.escalonar_sla_vencido()
        t.refresh_from_db()
        self.assertEqual(t.assignee, outro)

    def test_prioridade_nao_e_alterada(self):
        """De propósito: a prioridade define o prazo, e mexer nela depois do
        vencimento apagaria a evidência do furo."""
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico, priority='low')
        automation.escalonar_sla_vencido()
        t.refresh_from_db()
        self.assertEqual(t.priority, 'low')

    def test_prazo_nao_e_alterado(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        prazo = t.sla_deadline
        automation.escalonar_sla_vencido()
        t.refresh_from_db()
        self.assertEqual(t.sla_deadline, prazo)
        self.assertTrue(t.is_sla_breached)

    def test_notifica_quem_recebeu(self):
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        automation.escalonar_sla_vencido()
        self.assertTrue(Notification.objects.filter(
            user=self.gerente, type='ticket_escalated').exists())

    def test_nao_vencido_nao_escalona(self):
        ticket_com_prazo(self.paulo, 9, assignee=self.tecnico)
        self.assertEqual(automation.escalonar_sla_vencido(), [])

    def test_encerrado_nao_escalona(self):
        for status in ('resolved', 'closed', 'rejected'):
            with self.subTest(status=status):
                ticket_com_prazo(self.paulo, 12, assignee=self.tecnico, status=status)
        self.assertEqual(automation.escalonar_sla_vencido(), [])

    def test_aguardando_aprovacao_nao_escalona(self):
        """Sem prazo definido, não há SLA para vencer."""
        categoria = Category.objects.create(name='Acessos3', requires_approval=True)
        Ticket.objects.create(title='t', description='d', requester=self.paulo,
                              category=categoria, priority='critical',
                              status='pending_approval')
        self.assertEqual(automation.escalonar_sla_vencido(), [])

    def test_dry_run_nao_grava(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        resultado = automation.escalonar_sla_vencido(dry_run=True)
        self.assertEqual(len(resultado), 1)
        t.refresh_from_db()
        self.assertEqual(t.assignee, self.tecnico)
        self.assertIsNone(t.sla_escalated_at)
        self.assertEqual(Escalation.objects.count(), 0)

    @override_settings(SLA_AUTO_ESCALATE=False)
    def test_desligado_no_settings_nao_faz_nada(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        self.assertEqual(automation.escalonar_sla_vencido(), [])
        t.refresh_from_db()
        self.assertEqual(t.assignee, self.tecnico)


class SemGerenteCadastradoTests(TestCase):
    """Sem ninguém para escalonar, o comando não pode estourar."""

    @override_settings(SLA_AUTO_ESCALATE=True)
    def test_sem_gerente_nao_quebra(self):
        paulo   = criar_solicitante('paulo_sg')
        tecnico = criar_tecnico('tec_sg')
        t = ticket_com_prazo(paulo, 12, assignee=tecnico)
        with self.assertLogs('apps.tickets.automation', level='WARNING') as log:
            resultado = automation.escalonar_sla_vencido()
        self.assertEqual(resultado, [(t, None)])
        self.assertIn('não há gerente', log.output[0])
        t.refresh_from_db()
        self.assertEqual(t.assignee, tecnico)
        self.assertEqual(Escalation.objects.count(), 0)


class ComandoCheckSlaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_cmd')
        cls.tecnico = criar_tecnico('tec_cmd')
        cls.gerente = criar_gerente('ger_cmd')

    def _rodar(self, *args):
        from io import StringIO
        from django.core.management import call_command
        saida = StringIO()
        call_command('check_sla', *args, stdout=saida)
        return saida.getvalue()

    @override_settings(SLA_WARNING_PERCENT=80, SLA_AUTO_ESCALATE=True)
    def test_comando_executa_as_tres_automacoes(self):
        ticket_com_prazo(self.paulo, 8.5, assignee=self.tecnico, title='EM RISCO')
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico, title='VENCIDO')
        saida = self._rodar()
        self.assertIn('EM RISCO', saida)
        self.assertIn('VENCIDO', saida)
        self.assertIn('1 aviso(s) de risco', saida)
        self.assertIn('1 escalonamento(s)', saida)

    def test_dry_run_avisa_e_nao_grava(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        saida = self._rodar('--dry-run')
        self.assertIn('SIMULAÇÃO', saida)
        self.assertIn('[simulação]', saida)
        t.refresh_from_db()
        self.assertIsNone(t.sla_escalated_at)
        self.assertEqual(Escalation.objects.count(), 0)

    def test_quiet_imprime_so_o_resumo(self):
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico, title='VENCIDO')
        saida = self._rodar('--quiet')
        self.assertNotIn('VENCIDO', saida)
        self.assertIn('escalonamento(s) automático(s)', saida)

    def test_sem_nada_a_fazer(self):
        ticket_com_prazo(self.paulo, 1, assignee=self.tecnico)
        saida = self._rodar()
        self.assertIn('0 aviso(s) de risco', saida)
        self.assertIn('0 escalonamento(s)', saida)

    @override_settings(SLA_AUTO_ESCALATE=False)
    def test_comando_avisa_que_o_escalonamento_esta_desligado(self):
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        self.assertIn('desligado', self._rodar())

    def test_rejeitado_e_ignorado(self):
        """O comando usava a lista ['resolved','closed'] cravada, de antes da
        Fase 3.3; agora usa Ticket.CLOSED_STATUSES, que inclui 'rejected'."""
        ticket_com_prazo(self.paulo, 12, assignee=self.tecnico,
                         title='REJEITADO', status='rejected')
        saida = self._rodar()
        self.assertNotIn('REJEITADO', saida)


class TelaDoChamadoTests(TestCase):
    """O percentual e o aviso de risco aparecem no painel de SLA."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_tela')
        cls.tecnico = criar_tecnico('tec_tela')

    @override_settings(SLA_WARNING_PERCENT=80)
    def test_percentual_e_aviso_na_tela(self):
        t = ticket_com_prazo(self.paulo, 8.5, assignee=self.tecnico)
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('tickets:detail', args=[t.pk]))
        self.assertContains(r, 'Prazo decorrido')
        self.assertContains(r, 'sla-warn')

    def test_sem_prazo_nao_mostra_percentual(self):
        categoria = Category.objects.create(name='Acessos4', requires_approval=True)
        t = Ticket.objects.create(title='t', description='d', requester=self.paulo,
                                  category=categoria, priority='low',
                                  status='pending_approval')
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('tickets:detail', args=[t.pk]))
        self.assertNotContains(r, 'Prazo decorrido')

    def test_data_do_escalonamento_automatico_aparece(self):
        t = ticket_com_prazo(self.paulo, 12, assignee=self.tecnico)
        criar_gerente('ger_tela')
        automation.escalonar_sla_vencido()
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('tickets:detail', args=[t.pk]))
        self.assertContains(r, 'Escalonado por SLA')
