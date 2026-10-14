"""Testes da trilha de auditoria — Fase 3.4.

A captura é automática: o Ticket guarda um retrato de como saiu do banco
(`from_db`) e o save() compara. Os testes conferem os dois lados — o que é
registrado e o que **não** deve ser.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import (criar_gerente, criar_solicitante,
                                   criar_tecnico)
from apps.tickets.models import AuditLog, Category, Ticket


class AuditoriaAutomaticaTests(TestCase):
    """Alterações de campo são capturadas pelo save(), sem a view pedir."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico  = criar_tecnico('tec_aud')
        cls.outro    = criar_tecnico('tec_aud2')
        cls.rede     = Category.objects.create(name='Rede')
        cls.hardware = Category.objects.create(name='Hardware')

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Chamado auditado', description='d',
            requester=self.tecnico, priority='low', category=self.rede)
        # Recarrega: o retrato é tirado no from_db, não na instância criada
        # na memória.
        self.ticket = Ticket.objects.get(pk=self.ticket.pk)

    def _updates(self):
        return self.ticket.audit_logs.filter(action=AuditLog.ACTION_UPDATED)

    def test_criacao_gera_entrada(self):
        log = self.ticket.audit_logs.get()
        self.assertEqual(log.action, AuditLog.ACTION_CREATED)
        self.assertEqual(log.summary, 'Abriu o chamado')

    def test_mudanca_de_status_registra_rotulos_legiveis(self):
        self.ticket.status = 'in_progress'
        self.ticket.save_as(self.tecnico)
        log = self._updates().get()
        self.assertEqual(log.field, 'Status')
        self.assertEqual(log.old_value, 'Aberto')
        self.assertEqual(log.new_value, 'Em Andamento')
        self.assertEqual(log.summary, 'Status: Aberto → Em Andamento')
        self.assertEqual(log.user, self.tecnico)

    def test_mudanca_de_prioridade(self):
        self.ticket.priority = 'critical'
        self.ticket.save_as(self.tecnico)
        log = self._updates().get()
        self.assertEqual((log.field, log.old_value, log.new_value),
                         ('Prioridade', 'Baixa', 'Crítica'))

    def test_mudanca_de_tecnico_guarda_o_nome_e_nao_o_id(self):
        """O log guarda texto: se o usuário for apagado, a entrada continua
        dizendo o que estava escrito na época."""
        self.ticket.assignee = self.outro
        self.ticket.save_as(self.tecnico)
        log = self._updates().get()
        self.assertEqual(log.field, 'Técnico Responsável')
        self.assertEqual(log.old_value, '')          # estava sem técnico
        self.assertEqual(log.new_value, 'tec_aud2')

    def test_nome_no_log_sobrevive_a_remocao_do_usuario(self):
        self.ticket.assignee = self.outro
        self.ticket.save_as(self.tecnico)
        self.outro.delete()
        log = self._updates().get()
        self.assertEqual(log.new_value, 'tec_aud2')
        self.assertEqual(log.author_display, 'tec_aud')

    def test_mudanca_de_categoria(self):
        self.ticket.category = self.hardware
        self.ticket.save_as(self.tecnico)
        log = self._updates().get()
        self.assertEqual((log.field, log.old_value, log.new_value),
                         ('Categoria', 'Rede', 'Hardware'))

    def test_dois_campos_geram_duas_entradas(self):
        self.ticket.status   = 'waiting'
        self.ticket.priority = 'high'
        self.ticket.save_as(self.tecnico)
        campos = set(self._updates().values_list('field', flat=True))
        self.assertEqual(campos, {'Status', 'Prioridade'})

    def test_salvar_sem_mudar_nada_nao_gera_entrada(self):
        self.ticket.save_as(self.tecnico)
        self.assertEqual(self._updates().count(), 0)

    def test_salvar_duas_vezes_nao_duplica(self):
        """O retrato é renovado depois de cada save()."""
        self.ticket.status = 'in_progress'
        self.ticket.save_as(self.tecnico)
        self.ticket.save_as(self.tecnico)
        self.assertEqual(self._updates().count(), 1)

    def test_acao_sem_autor_aparece_como_sistema(self):
        """É o caso do comando check_sla e do manage.py shell."""
        self.ticket.status = 'closed'
        self.ticket.save()          # sem save_as: ninguém informou o autor
        log = self._updates().get()
        self.assertIsNone(log.user)
        self.assertEqual(log.author_display, 'Sistema')

    def test_update_do_queryset_nao_e_auditado(self):
        """Limitação conhecida e documentada: update() vai direto ao SQL."""
        Ticket.objects.filter(pk=self.ticket.pk).update(status='closed')
        self.assertEqual(self._updates().count(), 0)

    def test_campos_fora_da_lista_nao_sao_auditados(self):
        self.ticket.description = 'descrição nova'
        self.ticket.save_as(self.tecnico)
        self.assertEqual(self._updates().count(), 0)

    def test_prazo_sla_formatado(self):
        self.ticket.sla_deadline = timezone.now() + timezone.timedelta(hours=5)
        self.ticket.save_as(self.tecnico)
        log = self._updates().get()
        self.assertEqual(log.field, 'Prazo SLA')
        # dd/mm/aaaa hh:mm — não o datetime cru.
        self.assertRegex(log.new_value, r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$')


class AuditoriaDasAcoesTests(TestCase):
    """Os eventos que não são mudança de campo, registrados pelas views."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo    = criar_solicitante('paulo_aud')
        cls.tecnico  = criar_tecnico('tec_acao')
        cls.tecnico2 = criar_tecnico('tec_acao2')
        cls.gerente  = criar_gerente('ger_aud')
        cls.acesso   = Category.objects.create(name='Acessos', requires_approval=True)

    def _acoes(self, ticket):
        return list(ticket.audit_logs.values_list('action', flat=True))

    def test_abrir_chamado_pela_tela_registra_o_autor(self):
        self.client.force_login(self.paulo)
        self.client.post(reverse('tickets:create'), {
            'title': 'Pela tela', 'description': 'd',
            'ticket_type': 'incident', 'priority': 'low'})
        ticket = Ticket.objects.get(title='Pela tela')
        log = ticket.audit_logs.get()
        self.assertEqual(log.action, AuditLog.ACTION_CREATED)
        self.assertEqual(log.user, self.paulo)

    def test_comentario_registra(self):
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.paulo, priority='low')
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:add_comment', args=[ticket.pk]),
                         {'content': 'comentando'})
        log = ticket.audit_logs.get(action=AuditLog.ACTION_COMMENTED)
        self.assertEqual(log.user, self.tecnico)
        self.assertEqual(log.description, '')

    def test_nota_interna_fica_marcada_no_log(self):
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.paulo, priority='low')
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:add_comment', args=[ticket.pk]),
                         {'content': 'segredo', 'is_internal': 'on'})
        log = ticket.audit_logs.get(action=AuditLog.ACTION_COMMENTED)
        self.assertEqual(log.description, 'nota interna')

    def test_anexo_registra_o_nome_do_arquivo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.tecnico, priority='low')
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:upload_attachment', args=[ticket.pk]),
                         {'file': SimpleUploadedFile('manual.pdf', b'%PDF-1.4')},
                         HTTP_HX_REQUEST='true')
        log = ticket.audit_logs.get(action=AuditLog.ACTION_ATTACHED)
        self.assertEqual(log.description, 'manual.pdf')

    def test_anexo_rejeitado_nao_registra(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.tecnico, priority='low')
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:upload_attachment', args=[ticket.pk]),
                         {'file': SimpleUploadedFile('virus.exe', b'MZ')},
                         HTTP_HX_REQUEST='true')
        self.assertFalse(ticket.audit_logs.filter(
            action=AuditLog.ACTION_ATTACHED).exists())

    def test_finalizar_registra_status_e_solucao(self):
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.paulo, priority='low')
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:finish', args=[ticket.pk]),
                         {'solution': 'Troquei o cabo de rede.'})
        campos = set(ticket.audit_logs.filter(action=AuditLog.ACTION_UPDATED)
                     .values_list('field', flat=True))
        self.assertEqual(campos, {'Status', 'Solução'})

    def test_escalonar_registra_o_evento_e_a_troca_de_responsavel(self):
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.paulo, priority='low',
                                       assignee=self.tecnico)
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:escalate', args=[ticket.pk]),
                         {'to_user': self.tecnico2.pk,
                          'reason': 'Fora do meu escopo técnico.'})
        evento = ticket.audit_logs.get(action=AuditLog.ACTION_ESCALATED)
        self.assertEqual(evento.description, 'para tec_acao2')
        campos = set(ticket.audit_logs.filter(action=AuditLog.ACTION_UPDATED)
                     .values_list('field', flat=True))
        self.assertEqual(campos, {'Status', 'Técnico Responsável'})

    def test_aprovar_registra_evento_status_e_inicio_do_sla(self):
        """A aprovação muda status e prazo: 3 entradas no total."""
        ticket = Ticket.objects.create(
            title='t', description='d', requester=self.paulo,
            category=self.acesso, priority='critical', status='pending_approval')
        self.client.force_login(self.gerente)
        self.client.post(reverse('tickets:approve', args=[ticket.pk]),
                         {'comment': 'Liberado pelo gestor.'})
        evento = ticket.audit_logs.get(action=AuditLog.ACTION_APPROVED)
        self.assertEqual(evento.description, 'Liberado pelo gestor.')
        campos = set(ticket.audit_logs.filter(action=AuditLog.ACTION_UPDATED)
                     .values_list('field', flat=True))
        self.assertEqual(campos, {'Status', 'Prazo SLA'})

    def test_rejeitar_registra(self):
        ticket = Ticket.objects.create(
            title='t', description='d', requester=self.paulo,
            category=self.acesso, priority='low', status='pending_approval')
        self.client.force_login(self.gerente)
        self.client.post(reverse('tickets:reject', args=[ticket.pk]),
                         {'comment': 'Falta aprovação do gestor direto.'})
        evento = ticket.audit_logs.get(action=AuditLog.ACTION_REJECTED)
        self.assertEqual(evento.user, self.gerente)

    def test_atribuir_pela_fila_registra_o_autor(self):
        ticket = Ticket.objects.create(title='t', description='d',
                                       requester=self.paulo, priority='low')
        self.client.force_login(self.tecnico)
        self.client.post(reverse('tickets:assign', args=[ticket.pk]),
                         {'assignee_id': self.tecnico2.pk})
        log = ticket.audit_logs.get(field='Técnico Responsável')
        self.assertEqual(log.new_value, 'tec_acao2')
        self.assertEqual(log.user, self.tecnico)


class AuditoriaEhInternaTests(TestCase):
    """A trilha é conversa interna: "Prioridade: Crítica → Baixa" não é
    informação para o solicitante."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_int')
        cls.tecnico = criar_tecnico('tec_int')

    def setUp(self):
        self.ticket = Ticket.objects.create(title='t', description='d',
                                            requester=self.paulo, priority='critical')
        self.ticket = Ticket.objects.get(pk=self.ticket.pk)
        self.ticket.priority = 'low'
        self.ticket.save_as(self.tecnico)
        self.url = reverse('tickets:detail', args=[self.ticket.pk])

    def test_tecnico_ve_a_trilha(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(self.url)
        self.assertContains(r, 'Histórico de alterações')
        self.assertContains(r, 'Prioridade: Crítica → Baixa')

    def test_solicitante_nao_ve_nem_no_codigo_fonte(self):
        """Filtrada no queryset, como as notas internas."""
        self.client.force_login(self.paulo)
        r = self.client.get(self.url)
        self.assertNotContains(r, 'Histórico de alterações')
        self.assertNotContains(r, 'Prioridade: Crítica')
        self.assertNotContains(r, 'id="audit-card"')

    def test_chamado_sem_trilha_nao_mostra_o_cartao(self):
        """Os chamados abertos antes desta fase não têm registro nenhum."""
        antigo = Ticket.objects.create(title='antigo', description='d',
                                       requester=self.paulo, priority='low')
        antigo.audit_logs.all().delete()
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('tickets:detail', args=[antigo.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'id="audit-card"')


class AuditLogSomenteLeituraTests(TestCase):
    """O /admin/ não permite criar, editar nem apagar registros."""

    def test_admin_e_somente_leitura(self):
        from django.contrib.admin.sites import site
        from apps.tickets.models import AuditLog as Modelo

        admin_class = site._registry[Modelo]
        self.assertFalse(admin_class.has_add_permission(None))
        self.assertFalse(admin_class.has_change_permission(None))
        self.assertFalse(admin_class.has_delete_permission(None))
