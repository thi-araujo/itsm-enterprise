"""Testes das notificações.

O ponto crítico: uma falha de SMTP não pode interromper o fluxo do ticket,
mas também não pode desaparecer sem rastro (era `fail_silently=True` + print).
"""

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.testing import criar_solicitante, criar_tecnico
from apps.notifications.email import (notify_ticket_created, notify_sla_breach,
                                      notify_ticket_opened)
from apps.notifications.models import Notification
from apps.tickets.models import Category, Ticket


class BackendQueFalha(BaseEmailBackend):
    """Simula um servidor de SMTP fora do ar, sem depender da rede."""

    def send_messages(self, email_messages):
        raise OSError('SMTP simulado fora do ar')


class EnvioDeEmailTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('n')
        cls.ticket = Ticket.objects.create(title='t', description='d',
                                           requester=cls.tecnico, priority='low')

    def test_caminho_normal_envia_o_email(self):
        notify_ticket_created(self.ticket)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ITSM Enterprise', mail.outbox[0].subject)

    @override_settings(EMAIL_BACKEND=f'{__name__}.BackendQueFalha')
    def test_falha_de_smtp_e_registrada_e_nao_propaga(self):
        with self.assertLogs('apps.notifications.email', level='ERROR') as log:
            notify_ticket_created(self.ticket)   # não deve levantar exceção
        self.assertIn('Falha ao enviar e-mail', log.output[0])
        self.assertIn('OSError', log.output[0])

    @override_settings(EMAIL_BACKEND=f'{__name__}.BackendQueFalha')
    def test_notificacao_interna_sobrevive_a_falha_de_email(self):
        """O sino da sidebar não depende do servidor de e-mail."""
        with self.assertLogs('apps.notifications.email', level='ERROR'):
            notify_ticket_created(self.ticket)
        self.assertEqual(
            Notification.objects.filter(user=self.tecnico, type='ticket_created').count(), 1)

    @override_settings(EMAIL_BACKEND=f'{__name__}.BackendQueFalha')
    def test_criar_ticket_funciona_com_smtp_fora_do_ar(self):
        self.client.force_login(self.tecnico)
        with self.assertLogs('apps.notifications.email', level='ERROR'):
            r = self.client.post(reverse('tickets:create'), {
                'title': 'Com SMTP caido', 'description': 'd',
                'ticket_type': 'incident', 'priority': 'low',
            })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Ticket.objects.filter(title='Com SMTP caido').exists())

    def test_sem_destinatario_nao_tenta_enviar(self):
        User.objects.filter(pk=self.tecnico.pk).update(email='')
        notify_ticket_created(self.ticket)
        self.assertEqual(len(mail.outbox), 0)
        # mas a notificação interna continua existindo
        self.assertEqual(Notification.objects.count(), 1)


class ConfirmacaoDeAberturaTests(TestCase):
    """`notify_ticket_opened` — o recibo para quem abriu o chamado.

    Antes desta função o solicitante não recebia nada na abertura: o
    `notify_ticket_created` vai só para a equipe. Quem abria um chamado ficava
    sem o número e sem o prazo, e a primeira mensagem só chegava no primeiro
    comentário público ou na resolução.
    """

    @classmethod
    def setUpTestData(cls):
        cls.solicitante = criar_solicitante('ana')
        cls.categoria_com_aprovacao = Category.objects.create(
            name='Acesso', requires_approval=True)

    def _abrir(self, **extra):
        dados = dict(title='Impressora parada', description='d',
                     requester=self.solicitante, priority='medium')
        dados.update(extra)
        return Ticket.objects.create(**dados)

    def test_envia_para_quem_abriu_com_o_numero_e_o_prazo(self):
        ticket = self._abrir()
        notify_ticket_opened(ticket)

        self.assertEqual(len(mail.outbox), 1)
        enviado = mail.outbox[0]
        self.assertEqual(enviado.to, [self.solicitante.email])
        self.assertIn(f'#{ticket.pk:04d}', enviado.subject)
        self.assertIn(f'#{ticket.pk:04d}', enviado.body)
        self.assertIn('Prazo de atendimento', enviado.body)
        self.assertIn(ticket.sla_deadline.strftime('%d/%m/%Y'), enviado.body)

    def test_chamado_que_espera_aprovacao_nao_promete_prazo(self):
        """O SLA só começa na aprovação (Fase 3.3): anunciar um prazo aqui
        seria mentira, e mostrar "—" pareceria defeito."""
        ticket = self._abrir(category=self.categoria_com_aprovacao,
                             status='pending_approval')
        notify_ticket_opened(ticket)

        corpo = mail.outbox[0].body
        self.assertIn('aprovação do gestor', corpo)
        self.assertNotIn('Prazo de atendimento', corpo)

    def test_sem_email_no_cadastro_nao_tenta_enviar(self):
        """Conta do AD sem o atributo `mail` preenchido."""
        User.objects.filter(pk=self.solicitante.pk).update(email='')
        self.solicitante.refresh_from_db()
        notify_ticket_opened(self._abrir())
        self.assertEqual(len(mail.outbox), 0)

    def test_nao_gera_notificacao_do_sino(self):
        """A pessoa acabou de clicar em criar e está vendo o chamado."""
        notify_ticket_opened(self._abrir())
        self.assertEqual(Notification.objects.count(), 0)

    def test_a_tela_de_abrir_chamado_envia_a_confirmacao(self):
        """Protege o ponto de chamada: a função existir não basta."""
        self.client.force_login(self.solicitante)
        self.client.post(reverse('tickets:create'), {
            'title': 'Pela tela', 'description': 'd',
            'ticket_type': 'incident', 'priority': 'low',
        })
        ticket = Ticket.objects.get(title='Pela tela')
        destinos = [m.to for m in mail.outbox]
        self.assertIn([self.solicitante.email], destinos,
                      'quem abriu o chamado pela tela deve receber o recibo')
        self.assertTrue(
            any(f'#{ticket.pk:04d} registrado' in m.subject
                for m in mail.outbox))

    def test_a_api_envia_a_confirmacao(self):
        """O segundo ponto de criação — a tela e a API têm de concordar."""
        self.client.force_login(self.solicitante)
        resposta = self.client.post(
            '/api/v1/tickets/',
            {'title': 'Pela API', 'description': 'd',
             'ticket_type': 'incident', 'priority': 'low'},
            content_type='application/json')
        self.assertEqual(resposta.status_code, 201)
        self.assertIn([self.solicitante.email], [m.to for m in mail.outbox])


class VerificacoesDeEmailTests(TestCase):
    """`manage.py check` reclamando de configuração de e-mail.

    O `_send_email` registra a falha de SMTP e segue — decisão certa, porque
    criar um chamado não pode depender do servidor de e-mail. O efeito
    colateral é que o sintoma de configuração errada é o **silêncio**. Estes
    avisos trazem o problema para o terminal de quem sobe o sistema.
    """

    SMTP = 'django.core.mail.backends.smtp.EmailBackend'

    def _ids(self):
        from apps.notifications.checks import verificar_configuracao_de_email
        return [a.id for a in verificar_configuracao_de_email(None)]

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_modo_console_avisa_que_nada_sai_da_maquina(self):
        """É o padrão, não um defeito — mas é a causa de "abri o chamado e
        não recebi o e-mail"."""
        self.assertEqual(self._ids(), ['email.W001'])

    def test_backend_de_teste_nao_gera_aviso(self):
        """A suíte roda com `locmem`: avisar sobre SMTP aqui seria ruído em
        todo `manage.py test`."""
        self.assertEqual(self._ids(), [])

    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.gmail.com',
                       EMAIL_HOST_USER='itsm@gmail.com',
                       EMAIL_HOST_PASSWORD='x', EMAIL_TIMEOUT=10,
                       DEFAULT_FROM_EMAIL='itsm@gmail.com',
                       EMAIL_USE_TLS=True, EMAIL_USE_SSL=False)
    def test_configuracao_completa_passa_sem_aviso(self):
        self.assertEqual(self._ids(), [])

    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.gmail.com',
                       EMAIL_HOST_USER='itsm@gmail.com',
                       EMAIL_HOST_PASSWORD='x', EMAIL_TIMEOUT=10,
                       DEFAULT_FROM_EMAIL='itsm@gmail.com',
                       EMAIL_USE_TLS=True, EMAIL_USE_SSL=True)
    def test_tls_e_ssl_juntos_e_erro(self):
        """O Django levanta exceção no envio, que o `_send_email` engole: o
        chamado é criado e o e-mail nunca sai. Melhor barrar no check."""
        self.assertIn('email.E001', self._ids())

    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.gmail.com',
                       EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='',
                       EMAIL_TIMEOUT=10, DEFAULT_FROM_EMAIL='a@b.com')
    def test_smtp_sem_credencial_avisa(self):
        self.assertIn('email.W002', self._ids())

    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.office365.com',
                       EMAIL_HOST_USER='itsm@araujo.corp',
                       EMAIL_HOST_PASSWORD='x', EMAIL_TIMEOUT=10,
                       DEFAULT_FROM_EMAIL='naoresponda@outromundo.com')
    def test_remetente_de_outro_dominio_avisa(self):
        """Causa clássica de "o código está certo e o e-mail não chega"."""
        self.assertIn('email.W003', self._ids())

    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.gmail.com',
                       EMAIL_HOST_USER='itsm@gmail.com',
                       EMAIL_HOST_PASSWORD='x', EMAIL_TIMEOUT=None,
                       DEFAULT_FROM_EMAIL='itsm@gmail.com')
    def test_sem_timeout_avisa(self):
        """O envio é síncrono: sem timeout, a tela de quem abre o chamado
        fica pendurada esperando o SMTP."""
        self.assertIn('email.W004', self._ids())


class SlaBreachTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('s')
        cls.ticket = Ticket.objects.create(title='t', description='d',
                                           requester=cls.tecnico, priority='critical')

    def test_nao_notifica_duas_vezes(self):
        notify_sla_breach(self.ticket)
        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.sla_breach_notified)

        antes = Notification.objects.count()
        notify_sla_breach(self.ticket)
        self.assertEqual(Notification.objects.count(), antes)


class TelaDeNotificacoesTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_solicitante('v')
        for i in range(3):
            Notification.objects.create(user=cls.user, type='ticket_created',
                                        title=f'n{i}', message='m')

    def setUp(self):
        self.client.force_login(self.user)

    def test_contador_de_nao_lidas(self):
        self.assertEqual(self.client.get(reverse('notifications:unread_count')).json(),
                         {'count': 3})

    def test_marcar_todas_como_lidas(self):
        self.client.post(reverse('notifications:mark_all_read'))
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)
