"""Testes do dashboard — foco no contador de SLA, que passou de contagem em
memória para consulta no banco e precisa dar exatamente o mesmo resultado."""

from pathlib import Path

from django.conf import settings
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


class IdentidadeVisualTests(TestCase):
    """Garante que as classes da identidade visual existam no CSS *e* nos
    templates.

    Motivo: um rename feito pela metade deixou o CSS chamando `.card-itsm`
    enquanto os templates escreviam `itsm-card`. Nada estourava — o navegador
    simplesmente ignora uma classe sem regra — e as telas ficavam sem estilo.
    Este teste falha se os dois lados voltarem a divergir.
    """

    # Classes de componente do projeto (as do Bootstrap ficam de fora).
    CLASSES = [
        'itsm-card', 'itsm-table',
        'stat-card', 'stat-value', 'stat-label', 'stat-icon',
        'priority-badge', 'status-badge', 'ticket-id', 'sla-breached',
        'btn-itsm', 'toast-msg',
    ]

    # Classes montadas no template a partir do valor do campo
    # (ex.: class="priority-badge badge-{{ t.priority }}"), por isso só
    # podem ser conferidas no CSS.
    CLASSES_DINAMICAS = [
        'badge-low', 'badge-medium', 'badge-high', 'badge-critical',
        'status-open', 'status-in_progress', 'status-waiting',
        'status-resolved', 'status-closed',
    ]

    @classmethod
    def setUpTestData(cls):
        cls.css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'itsm.css').read_text(encoding='utf-8')
        cls.templates = '\n'.join(
            caminho.read_text(encoding='utf-8')
            for caminho in (Path(settings.BASE_DIR) / 'templates').rglob('*.html')
        )

    def test_toda_classe_do_css_tem_regra_e_uso(self):
        for classe in self.CLASSES:
            with self.subTest(classe=classe):
                self.assertIn('.%s' % classe, self.css,
                              '%s é usada nos templates mas não tem regra no itsm.css' % classe)
                self.assertIn(classe, self.templates,
                              '%s tem regra no itsm.css mas nenhum template usa' % classe)

    def test_classes_dinamicas_tem_regra(self):
        for classe in self.CLASSES_DINAMICAS:
            with self.subTest(classe=classe):
                self.assertIn('.%s' % classe, self.css)

    def test_badge_de_status_usa_a_cor_do_status(self):
        """Antes todo status saía azul, com a cor fixa no `style=` inline."""
        user = criar_admin('visual')
        aberto = Ticket.objects.create(title='Aberto', description='d',
                                       requester=user, priority='low')
        resolvido = Ticket.objects.create(title='Resolvido', description='d',
                                          requester=user, priority='low',
                                          status='resolved')
        self.client.force_login(user)
        html = self.client.get(reverse('tickets:list')).content.decode()
        self.assertIn('status-badge status-open', html)
        self.assertIn('status-badge status-resolved', html)
        self.assertEqual(aberto.status, 'open')
        self.assertEqual(resolvido.status, 'resolved')
