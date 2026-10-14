"""Testes dos relatórios — o cálculo de SLA cumprido virou consulta com F()."""

from django.contrib.auth.models import User
from django.db.models import F
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.tickets.models import Ticket


class SlaCumpridoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = User.objects.create_user('r', 'r@exemplo.local', 'x', is_staff=True)
        agora = timezone.now()

        def criar(titulo, resolvido_em, prazo):
            t = Ticket.objects.create(title=titulo, description='d',
                                      requester=cls.tecnico, assignee=cls.tecnico,
                                      priority='low', status='resolved')
            Ticket.objects.filter(pk=t.pk).update(resolved_at=resolvido_em,
                                                  sla_deadline=prazo)

        # dentro do prazo (2) e fora do prazo (1)
        criar('ok 1', agora - timezone.timedelta(hours=3), agora - timezone.timedelta(hours=1))
        criar('ok 2', agora - timezone.timedelta(hours=2), agora + timezone.timedelta(hours=1))
        criar('estourou', agora, agora - timezone.timedelta(hours=4))

    def test_consulta_com_F_bate_com_o_calculo_em_memoria(self):
        qs = Ticket.objects.filter(status__in=['resolved', 'closed'],
                                   resolved_at__isnull=False,
                                   sla_deadline__isnull=False)
        em_memoria = sum(1 for t in qs if t.resolved_at <= t.sla_deadline)
        na_consulta = qs.filter(resolved_at__lte=F('sla_deadline')).count()
        self.assertEqual(em_memoria, na_consulta)
        self.assertEqual(na_consulta, 2)

    def test_percentual_no_relatorio_geral(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('reports:dashboard'), {'days': 365})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['sla_pct'], 66.7)   # 2 de 3

    def test_relatorio_por_tecnico(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('reports:technician'), {'days': 365})
        self.assertEqual(r.status_code, 200)
        linha = next(d for d in r.context['data'] if d['tech'] == self.tecnico)
        self.assertEqual(linha['sla_ok'], 2)
        self.assertEqual(linha['sla_pct'], 66.7)

    def test_relatorio_sem_dados_nao_divide_por_zero(self):
        Ticket.objects.all().delete()
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['sla_pct'], 0)
