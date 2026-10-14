"""Testes das agregações e do dashboard avançado — Fase 3.6.

Os números aqui são conferidos na mão de propósito: um erro de agregação não
quebra nada, só mostra o valor errado — é o tipo de bug que passa anos sem
ser notado.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import (criar_gerente, criar_solicitante,
                                   criar_tecnico)
from apps.tickets import stats
from apps.tickets.models import Category, Ticket


def resolvido(ticket, horas_depois, dentro_do_prazo=True):
    """Marca o chamado como resolvido `horas_depois` da abertura.

    Usa `update()` para escrever as datas sem passar pelo save() — que
    sobrescreveria `resolved_at` com o `now()`.
    """
    criado = ticket.created_at
    Ticket.objects.filter(pk=ticket.pk).update(
        status='resolved',
        resolved_at=criado + timezone.timedelta(hours=horas_depois),
        sla_deadline=criado + timezone.timedelta(
            hours=horas_depois + (1 if dentro_do_prazo else -1)),
    )
    return Ticket.objects.get(pk=ticket.pk)


class VolumeDiarioTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_tecnico('tec_vol')
        hoje = timezone.now()
        # 2 hoje, 1 anteontem, nada ontem.
        for deslocamento, quantidade in [(0, 2), (2, 1)]:
            for i in range(quantidade):
                t = Ticket.objects.create(title=f't{deslocamento}{i}', description='d',
                                          requester=cls.user, priority='low')
                Ticket.objects.filter(pk=t.pk).update(
                    created_at=hoje - timezone.timedelta(days=deslocamento))

    def test_uma_consulta_so(self):
        """A versão anterior fazia um count() por dia — até 30 consultas para
        montar um gráfico. Este teste falha se o laço voltar."""
        with self.assertNumQueries(1):
            stats.volume_diario(Ticket.objects.all(), dias=30)

    def test_serie_tem_um_ponto_por_dia(self):
        serie = stats.volume_diario(Ticket.objects.all(), dias=7)
        self.assertEqual(len(serie), 7)

    def test_dia_sem_chamado_vem_com_zero(self):
        """O banco não devolve linha para dia vazio; sem preencher, o gráfico
        ficaria com buracos."""
        serie = stats.volume_diario(Ticket.objects.all(), dias=3)
        totais = [ponto['total'] for ponto in serie]
        self.assertEqual(totais, [1, 0, 2])   # anteontem, ontem, hoje

    def test_ordem_cronologica(self):
        serie = stats.volume_diario(Ticket.objects.all(), dias=5)
        hoje = timezone.localdate().strftime('%d/%m')
        self.assertEqual(serie[-1]['dia'], hoje)

    def test_limite_de_dias(self):
        self.assertEqual(len(stats.volume_diario(Ticket.objects.all(), dias=999)),
                         stats.MAX_DIAS_NO_GRAFICO)
        self.assertEqual(len(stats.volume_diario(Ticket.objects.all(), dias=0)), 1)

    def test_respeita_o_queryset_recebido(self):
        """As funções recebem queryset, não o model — é assim que o RBAC se
        aplica antes da agregação."""
        outro = criar_solicitante('sol_vol')
        Ticket.objects.create(title='do outro', description='d',
                              requester=outro, priority='low')
        serie = stats.volume_diario(Ticket.objects.filter(requester=outro), dias=1)
        self.assertEqual(serie[0]['total'], 1)


class CumprimentoDeSlaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_tecnico('tec_sla')

    def _criar(self, titulo, **extra):
        return Ticket.objects.create(title=titulo, description='d',
                                     requester=self.user, priority='low', **extra)

    def test_sem_resolvidos_devolve_none(self):
        self._criar('aberto')
        resultado = stats.cumprimento_de_sla(Ticket.objects.all())
        self.assertIsNone(resultado['percentual'])
        self.assertEqual(resultado['avaliados'], 0)

    def test_conta_conferida_na_mao(self):
        """3 no prazo e 1 atrasado = 75%."""
        for i in range(3):
            resolvido(self._criar(f'ok{i}'), 2, dentro_do_prazo=True)
        resolvido(self._criar('atrasado'), 2, dentro_do_prazo=False)

        resultado = stats.cumprimento_de_sla(Ticket.objects.all())
        self.assertEqual(resultado['avaliados'], 4)
        self.assertEqual(resultado['no_prazo'], 3)
        self.assertEqual(resultado['atrasados'], 1)
        self.assertEqual(resultado['percentual'], 75.0)

    def test_chamado_sem_prazo_nao_entra_na_conta(self):
        """Sem SLA definido não se pode julgar cumprido nem furado."""
        t = self._criar('sem prazo')
        Ticket.objects.filter(pk=t.pk).update(
            status='resolved', resolved_at=timezone.now(), sla_deadline=None)
        self.assertEqual(stats.cumprimento_de_sla(Ticket.objects.all())['avaliados'], 0)

    def test_aberto_nao_entra_na_conta(self):
        resolvido(self._criar('fechado'), 1)
        self._criar('ainda aberto')
        self.assertEqual(stats.cumprimento_de_sla(Ticket.objects.all())['avaliados'], 1)

    def test_rejeitado_nao_conta_como_resolvido(self):
        """CLOSED_STATUSES inclui 'rejected', mas rejeitado não foi resolvido
        — por isso stats usa a sua própria lista."""
        t = self._criar('rejeitado')
        Ticket.objects.filter(pk=t.pk).update(
            status='rejected', resolved_at=timezone.now())
        self.assertEqual(stats.cumprimento_de_sla(Ticket.objects.all())['avaliados'], 0)
        self.assertEqual(stats.estatisticas_de(Ticket.objects.all())['resolvidos'], 0)


class TempoMedioTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_tecnico('tec_tmp')

    def test_sem_resolvidos_devolve_none(self):
        """None e não zero: zero seria lido como "resolvemos na hora"."""
        Ticket.objects.create(title='aberto', description='d',
                              requester=self.user, priority='low')
        self.assertIsNone(
            stats.tempo_medio_de_resolucao_horas(Ticket.objects.all()))

    def test_media_de_duas_resolucoes(self):
        """2h e 6h = média de 4h."""
        for horas in (2, 6):
            t = Ticket.objects.create(title=f't{horas}', description='d',
                                      requester=self.user, priority='low')
            resolvido(t, horas)
        media = stats.tempo_medio_de_resolucao_horas(Ticket.objects.all())
        self.assertAlmostEqual(media, 4, delta=0.1)


class EstatisticasDeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('tec_est2')
        cls.rede    = Category.objects.create(name='Rede')
        cls.acesso  = Category.objects.create(name='Acessos', requires_approval=True)

        for i, status in enumerate(('open', 'open', 'in_progress')):
            Ticket.objects.create(title=f't{i} {status}', description='d',
                                  requester=cls.tecnico, priority='high',
                                  status=status,
                                  category=cls.rede, assignee=cls.tecnico)
        Ticket.objects.create(title='sem tecnico', description='d',
                              requester=cls.tecnico, priority='critical')
        Ticket.objects.create(title='pendente', description='d',
                              requester=cls.tecnico, category=cls.acesso,
                              priority='low', status='pending_approval')
        vencido = Ticket.objects.create(title='vencido', description='d',
                                        requester=cls.tecnico, priority='critical')
        Ticket.objects.filter(pk=vencido.pk).update(
            sla_deadline=timezone.now() - timezone.timedelta(hours=1))

    def test_contadores(self):
        dados = stats.estatisticas_de(Ticket.objects.all())
        self.assertEqual(dados['total'], 6)
        self.assertEqual(dados['em_aberto'], 6)       # nenhum encerrado
        self.assertEqual(dados['sem_tecnico'], 3)     # os 3 sem assignee
        self.assertEqual(dados['sla_vencido'], 1)
        self.assertEqual(dados['aguardando_aprovacao'], 1)

    def test_distribuicoes(self):
        dados = stats.estatisticas_de(Ticket.objects.all())
        # 2 do laço + "sem tecnico" + "vencido"
        self.assertEqual(dados['por_status']['open'], 4)
        self.assertEqual(dados['por_status']['in_progress'], 1)
        self.assertEqual(dados['por_prioridade']['high'], 3)
        self.assertEqual(dados['por_tipo']['incident'], 6)

    def test_chaves_limpas_nas_listas(self):
        """A API é contrato público: `nome`/`total`, não o `category__name`
        cru do ORM."""
        dados = stats.estatisticas_de(Ticket.objects.all())
        categoria = dados['por_categoria'][0]
        self.assertEqual(set(categoria), {'nome', 'total'})
        tecnico = dados['por_tecnico'][0]
        self.assertEqual(set(tecnico), {'username', 'nome', 'total'})
        self.assertEqual(tecnico['username'], 'tec_est2')

    def test_recorte_por_periodo(self):
        antigo = Ticket.objects.create(title='antigo', description='d',
                                       requester=self.tecnico, priority='low')
        Ticket.objects.filter(pk=antigo.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=60))
        self.assertEqual(stats.estatisticas_de(Ticket.objects.all())['total'], 7)
        self.assertEqual(stats.estatisticas_de(Ticket.objects.all(), dias=30)['total'], 6)
        self.assertEqual(stats.estatisticas_de(Ticket.objects.all(), dias=30)['periodo_dias'], 30)


class DashboardTests(TestCase):
    """A primeira carga é renderizada pelo servidor — a página tem de mostrar
    números corretos mesmo sem JavaScript (que é o caso do test client)."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_dash')
        cls.tecnico = criar_tecnico('tec_dash')
        cls.gerente = criar_gerente('ger_dash')
        for i in range(4):
            Ticket.objects.create(title=f'da equipe {i}', description='d',
                                  requester=cls.tecnico, priority='low')
        Ticket.objects.create(title='do Paulo', description='d',
                              requester=cls.paulo, priority='low')

    def test_numeros_renderizados_pelo_servidor(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r.context['stats']['total'], 5)
        # O número aparece no HTML, não só no contexto.
        self.assertContains(r, 'data-stat="total"')

    def test_solicitante_ve_so_os_proprios_numeros(self):
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('dashboard:index'))
        self.assertEqual(r.context['stats']['total'], 1)

    def test_solicitante_nao_ve_os_kpis_de_gestao(self):
        self.client.force_login(self.paulo)
        r = self.client.get(reverse('dashboard:index'))
        self.assertNotContains(r, 'id="dash-kpis"')
        self.assertNotContains(r, 'SLA cumprido')
        self.assertNotContains(r, 'Sem técnico')

    def test_equipe_ve_os_kpis_de_gestao(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse('dashboard:index'))
        self.assertContains(r, 'id="dash-kpis"')
        self.assertContains(r, 'SLA cumprido')
        self.assertContains(r, 'Tempo médio de resolução')

    def test_url_da_api_vai_num_data_attribute(self):
        """É o que permite o JS viver em static/js/dashboard.js, fora do
        template (fecha a pendência do JS inline)."""
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('dashboard:index'))
        self.assertContains(r, 'data-stats-url="/api/v1/estatisticas/"')
        self.assertContains(r, 'js/dashboard.js')

    def test_flag_de_perfil_vai_para_o_js(self):
        for user, esperado in [(self.paulo, '0'), (self.tecnico, '1')]:
            with self.subTest(papel=user.profile.role):
                self.client.force_login(user)
                r = self.client.get(reverse('dashboard:index'))
                self.assertContains(r, f'data-pode-gerenciar="{esperado}"')

    def test_canvas_dos_tres_graficos(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('dashboard:index'))
        for canvas in ('grafico-status', 'grafico-prioridade', 'grafico-volume'):
            with self.subTest(canvas=canvas):
                self.assertContains(r, f'id="{canvas}"')

    def test_seletor_de_periodo(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(reverse('dashboard:index'))
        self.assertContains(r, 'id="dash-periodo"')


class EndpointDeEstatisticasTests(TestCase):
    """O endpoint que o dashboard consome (Fase 3.5 + 3.6)."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_end')
        cls.tecnico = criar_tecnico('tec_end')
        Ticket.objects.create(title='do Paulo', description='d',
                              requester=cls.paulo, priority='low')
        Ticket.objects.create(title='da equipe', description='d',
                              requester=cls.tecnico, priority='low')

    def test_campos_novos_da_fase(self):
        self.client.force_login(self.tecnico)
        dados = self.client.get('/api/v1/estatisticas/',
                                HTTP_ACCEPT='application/json').json()
        for chave in ('volume_diario', 'por_tipo', 'sla_cumprimento',
                      'tempo_medio_resolucao_horas', 'sla_em_risco',
                      'resolvidos', 'periodo_dias'):
            with self.subTest(chave=chave):
                self.assertIn(chave, dados)

    def test_solicitante_nao_recebe_numeros_de_gestao(self):
        self.client.force_login(self.paulo)
        dados = self.client.get('/api/v1/estatisticas/',
                                HTTP_ACCEPT='application/json').json()
        self.assertEqual(dados['total'], 1)
        for chave in ('por_tecnico', 'sla_cumprimento', 'sem_tecnico'):
            with self.subTest(chave=chave):
                self.assertNotIn(chave, dados)

    def test_dias_invalido_recebe_400(self):
        self.client.force_login(self.tecnico)
        for valor in ('abc', '0', '-5'):
            with self.subTest(valor=valor):
                r = self.client.get('/api/v1/estatisticas/', {'days': valor},
                                    HTTP_ACCEPT='application/json')
                self.assertEqual(r.status_code, 400)

    def test_volume_diario_acompanha_o_periodo(self):
        self.client.force_login(self.tecnico)
        dados = self.client.get('/api/v1/estatisticas/', {'days': 7},
                                HTTP_ACCEPT='application/json').json()
        self.assertEqual(len(dados['volume_diario']), 7)
        self.assertEqual(dados['periodo_dias'], 7)


class RelatorioUsaAsMesmasContasTests(TestCase):
    """O relatório passou a usar stats.py — os valores têm de bater."""

    @classmethod
    def setUpTestData(cls):
        cls.gerente = criar_gerente('ger_rel')
        for i in range(3):
            Ticket.objects.create(title=f't{i}', description='d',
                                  requester=cls.gerente, priority='low',
                                  assignee=cls.gerente)
        resolvido(Ticket.objects.first(), 2)

    def test_relatorio_abre_e_os_numeros_batem(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(r.status_code, 200)
        dados = stats.estatisticas_de(Ticket.objects.all())
        self.assertEqual(r.context['total'], dados['total'])
        self.assertEqual(r.context['resolved'], dados['resolvidos'])

    def test_grafico_diario_sem_n_mais_1(self):
        """O relatório era o dono do laço de 30 consultas."""
        self.client.force_login(self.gerente)
        with self.assertNumQueries(1):
            stats.volume_diario(Ticket.objects.all(), dias=30)

    def test_days_invalido_nao_quebra_o_relatorio(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse('reports:dashboard'), {'days': 'abc'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['days'], 30)
