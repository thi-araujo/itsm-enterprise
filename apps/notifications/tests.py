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
from apps.notifications.email import notify_ticket_created, notify_sla_breach
from apps.notifications.models import Notification
from apps.tickets.models import Ticket


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
