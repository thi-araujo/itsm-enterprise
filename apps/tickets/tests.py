"""Testes do app tickets.

Cobre o caso mais frágil do projeto — ticket sem técnico (`assignee` nulo),
que precisa renderizar em TODOS os templates conforme o CLAUDE.md — além da
política de upload e do SLA automático por prioridade.
"""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Attachment, Category, Ticket


class TicketSemTecnicoTests(TestCase):
    """Um ticket com assignee nulo não pode quebrar nenhuma tela."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = User.objects.create_user('tecnico', 'tecnico@exemplo.local',
                                               'x', is_staff=True)
        cls.categoria = Category.objects.create(name='Rede')
        cls.sem_tecnico = Ticket.objects.create(
            title='Impressora sem tinta', description='Trocar toner',
            requester=cls.tecnico, category=cls.categoria, priority='low',
        )
        cls.com_tecnico = Ticket.objects.create(
            title='VPN fora do ar', description='Ninguém conecta',
            requester=cls.tecnico, assignee=cls.tecnico, priority='high',
        )

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_assignee_nulo_de_fato(self):
        self.assertIsNone(self.sem_tecnico.assignee)

    def test_todas_as_telas_renderizam(self):
        """Nenhuma tela pode estourar com assignee nulo."""
        urls = [
            reverse('dashboard:index'),
            reverse('tickets:list'),
            reverse('tickets:queue'),
            reverse('tickets:create'),
            reverse('tickets:detail', args=[self.sem_tecnico.pk]),
            reverse('notifications:list'),
            reverse('cmdb:list'),
            reverse('reports:dashboard'),
            reverse('reports:technician'),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_detalhe_mostra_nao_atribuido(self):
        r = self.client.get(reverse('tickets:detail', args=[self.sem_tecnico.pk]))
        self.assertContains(r, 'Não atribuído')

    def test_lista_html_nao_quebra_na_coluna_do_tecnico(self):
        """O partial usa {% if t.assignee %}; sem isso renderizaria 'None'."""
        r = self.client.get(reverse('tickets:list'))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'None')

    def test_filtro_sem_tecnico(self):
        r = self.client.get(reverse('tickets:list'), {'assignee': 'unassigned'})
        self.assertContains(r, 'Impressora sem tinta')
        self.assertNotContains(r, 'VPN fora do ar')

    def test_contador_do_badge_da_sidebar(self):
        r = self.client.get(reverse('tickets:unassigned_count'))
        self.assertEqual(r.json(), {'count': 1})


class SlaTests(TestCase):
    """SLA por prioridade: Crítica 2h, Alta 8h, Média 24h, Baixa 72h."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('sla', 'sla@exemplo.local', 'x')

    def test_prazo_definido_por_prioridade(self):
        esperado = {'critical': 2, 'high': 8, 'medium': 24, 'low': 72}
        for prioridade, horas in esperado.items():
            with self.subTest(prioridade=prioridade):
                antes = timezone.now()
                t = Ticket.objects.create(title='t', description='d',
                                          requester=self.user, priority=prioridade)
                delta = t.sla_deadline - antes
                self.assertAlmostEqual(delta.total_seconds() / 3600, horas, delta=0.1)

    def test_sla_vencido(self):
        t = Ticket.objects.create(title='t', description='d',
                                  requester=self.user, priority='critical')
        t.sla_deadline = timezone.now() - timezone.timedelta(hours=1)
        t.save()
        self.assertTrue(t.is_sla_breached)

    def test_resolvido_nao_conta_como_vencido(self):
        t = Ticket.objects.create(title='t', description='d',
                                  requester=self.user, priority='critical')
        t.sla_deadline = timezone.now() - timezone.timedelta(hours=1)
        t.status = 'resolved'
        t.save()
        self.assertFalse(t.is_sla_breached)

    def test_resolved_at_preenchido_automaticamente(self):
        t = Ticket.objects.create(title='t', description='d',
                                  requester=self.user, priority='low')
        self.assertIsNone(t.resolved_at)
        t.status = 'resolved'
        t.save()
        self.assertIsNotNone(t.resolved_at)


class UploadDeAnexoTests(TestCase):
    """Política de upload: fonte única em settings, e rejeição sempre avisada."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('up', 'up@exemplo.local', 'x', is_staff=True)
        cls.ticket = Ticket.objects.create(title='t', description='d',
                                           requester=cls.user, priority='low')

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse('tickets:upload_attachment', args=[self.ticket.pk])

    def test_arquivo_valido_e_salvo(self):
        r = self.client.post(self.url,
                             {'file': SimpleUploadedFile('ok.pdf', b'%PDF-1.4')},
                             HTTP_HX_REQUEST='true')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.ticket.attachments.count(), 1)

    def test_extensao_proibida_e_rejeitada_com_aviso(self):
        r = self.client.post(self.url,
                             {'file': SimpleUploadedFile('virus.exe', b'MZ')},
                             HTTP_HX_REQUEST='true')
        self.assertEqual(self.ticket.attachments.count(), 0)
        self.assertContains(r, 'Tipo não permitido')
        self.assertContains(r, '.exe')

    def test_rejeicao_htmx_nao_substitui_a_lista_de_anexos(self):
        """O form usa hx-swap=beforeend; sem HX-Retarget o redirect injetaria
        a página inteira dentro de #attachments-list."""
        r = self.client.post(self.url,
                             {'file': SimpleUploadedFile('virus.exe', b'MZ')},
                             HTTP_HX_REQUEST='true')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['HX-Retarget'], '#attach-error')
        self.assertEqual(r['HX-Reswap'], 'innerHTML')
        self.assertNotContains(r, '<html')

    @override_settings(MAX_UPLOAD_SIZE_MB=1)
    def test_limite_de_tamanho_vem_do_settings(self):
        """Com o limite reduzido via settings, um arquivo de 2 MB é rejeitado.
        Prova que a view não tem o valor hardcoded."""
        grande = SimpleUploadedFile('grande.pdf', b'x' * (2 * 1024 * 1024))
        r = self.client.post(self.url, {'file': grande}, HTTP_HX_REQUEST='true')
        self.assertEqual(self.ticket.attachments.count(), 0)
        self.assertContains(r, 'Arquivo muito grande')
        self.assertContains(r, '1 MB')

    @override_settings(ALLOWED_UPLOAD_EXTENSIONS=['.pdf'])
    def test_lista_de_extensoes_vem_do_settings(self):
        r = self.client.post(self.url,
                             {'file': SimpleUploadedFile('planilha.xlsx', b'PK')},
                             HTTP_HX_REQUEST='true')
        self.assertEqual(self.ticket.attachments.count(), 0)
        self.assertContains(r, 'Tipo não permitido')

    def test_anexo_rejeitado_na_criacao_avisa_o_usuario(self):
        """Antes o arquivo era descartado em silêncio e o ticket era criado."""
        r = self.client.post(reverse('tickets:create'), {
            'title': 'Com anexo ruim', 'description': 'd',
            'ticket_type': 'incident', 'priority': 'low',
            'attachment': SimpleUploadedFile('script.sh', b'#!/bin/sh'),
        }, follow=True)
        novo = Ticket.objects.get(title='Com anexo ruim')
        self.assertEqual(novo.attachments.count(), 0)
        self.assertContains(r, 'anexo NÃO foi salvo')

    def test_tamanho_formatado_do_anexo(self):
        att = Attachment.objects.create(ticket=self.ticket, uploaded_by=self.user,
                                        filename='a.pdf', file_size=2048)
        self.assertEqual(att.file_size_display, '2 KB')


class PoliticaNosTemplatesTests(TestCase):
    """Os templates leem a política do settings, sem duplicar a lista."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tpl', 'tpl@exemplo.local', 'x')
        cls.ticket = Ticket.objects.create(title='t', description='d',
                                           requester=cls.user, priority='low')

    def setUp(self):
        self.client.force_login(self.user)

    @override_settings(MAX_UPLOAD_SIZE_MB=7)
    def test_limite_aparece_nas_duas_telas(self):
        for url in (reverse('tickets:create'),
                    reverse('tickets:detail', args=[self.ticket.pk])):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'máx. 7MB')

    @override_settings(ALLOWED_UPLOAD_EXTENSIONS=['.pdf', '.zip'])
    def test_accept_do_input_vem_do_settings(self):
        r = self.client.get(reverse('tickets:detail', args=[self.ticket.pk]))
        self.assertContains(r, 'accept=".pdf,.zip"')


class NotificacaoNaoDerrubaOFluxoTests(TestCase):
    """Uma falha ao notificar não pode impedir a criação do ticket, mas tem
    de aparecer no log (antes era `except Exception: pass`)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('nt', 'nt@exemplo.local', 'x', is_staff=True)

    def setUp(self):
        self.client.force_login(self.user)

    def test_falha_ao_notificar_e_registrada_e_ticket_sobrevive(self):
        import apps.notifications.email as mail

        original = mail.notify_ticket_created

        def explode(ticket):
            raise RuntimeError('falha simulada')

        mail.notify_ticket_created = explode
        try:
            with self.assertLogs('apps.tickets.views', level='ERROR') as log:
                r = self.client.post(reverse('tickets:create'), {
                    'title': 'Sobrevive', 'description': 'd',
                    'ticket_type': 'incident', 'priority': 'low',
                })
        finally:
            mail.notify_ticket_created = original

        self.assertEqual(r.status_code, 302)
        self.assertTrue(Ticket.objects.filter(title='Sobrevive').exists())
        self.assertIn('Falha ao notificar', log.output[0])
        self.assertIn('RuntimeError', log.output[0])


class AcessoRestritoTests(TestCase):
    """Toda view exige login (CLAUDE.md, convenções Django)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('a', 'a@exemplo.local', 'x')
        cls.ticket = Ticket.objects.create(title='t', description='d',
                                           requester=cls.user, priority='low')

    def test_anonimo_e_redirecionado_para_o_login(self):
        urls = [
            reverse('dashboard:index'),
            reverse('tickets:list'),
            reverse('tickets:queue'),
            reverse('tickets:create'),
            reverse('tickets:detail', args=[self.ticket.pk]),
            reverse('cmdb:list'),
            reverse('reports:dashboard'),
            reverse('notifications:list'),
        ]
        for url in urls:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertIn('/accounts/login/', r['Location'])
