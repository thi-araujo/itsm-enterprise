"""Testes do dashboard — foco no contador de SLA, que passou de contagem em
memória para consulta no banco e precisa dar exatamente o mesmo resultado."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import criar_admin
from apps.tickets.models import Ticket


class SlaRiskTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_admin('d')
        agora = timezone.now()
        vencido = agora - timezone.timedelta(hours=1)
        futuro  = agora + timezone.timedelta(hours=5)

        # 3 vencidos e abertos -> devem contar
        for i, status in enumerate(['open', 'in_progress', 'waiting']):
            t = Ticket.objects.create(title=f'vencido {i}', description='d',
                                      requester=cls.user, priority='low', status=status)
            Ticket.objects.filter(pk=t.pk).update(sla_deadline=vencido)

        # vencidos mas já encerrados -> NÃO devem contar
        for status in ['resolved', 'closed']:
            t = Ticket.objects.create(title=f'encerrado {status}', description='d',
                                      requester=cls.user, priority='low', status=status)
            Ticket.objects.filter(pk=t.pk).update(sla_deadline=vencido)

        # dentro do prazo -> NÃO conta
        t = Ticket.objects.create(title='no prazo', description='d',
                                  requester=cls.user, priority='low')
        Ticket.objects.filter(pk=t.pk).update(sla_deadline=futuro)

        # sem prazo definido -> NÃO conta
        t = Ticket.objects.create(title='sem prazo', description='d',
                                  requester=cls.user, priority='low')
        Ticket.objects.filter(pk=t.pk).update(sla_deadline=None)

    def test_consulta_bate_com_o_calculo_em_memoria(self):
        """A consulta substituiu `sum(1 for t in tickets if t.is_sla_breached)`."""
        tickets = Ticket.objects.all()
        em_memoria = sum(1 for t in tickets if t.is_sla_breached)
        na_consulta = (tickets.filter(sla_deadline__lt=timezone.now())
                              .exclude(status__in=['resolved', 'closed']).count())
        self.assertEqual(em_memoria, na_consulta)
        self.assertEqual(na_consulta, 3)

    def test_dashboard_exibe_o_numero_correto(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['stats']['sla_risk'], 3)
        self.assertEqual(r.context['stats']['total'], 7)
