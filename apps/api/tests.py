"""Testes da API REST — Fase 3.5.

O foco é provar duas coisas:

1. O RBAC das fases anteriores vale na API. Um JSON que devolvesse o que a
   tela esconde seria um vazamento — é o maior risco de expor uma API sobre
   um sistema que já tem regras de visibilidade.
2. As regras de negócio são as mesmas da tela, porque vêm de services.py.
   Os testes conferem até a **mensagem de erro**, que precisa ser idêntica.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.accounts.testing import (SENHA_DE_TESTE, criar_admin, criar_gerente,
                                   criar_solicitante, criar_tecnico)
from apps.tickets import services
from apps.tickets.models import (Approval, AuditLog, Category, Comment,
                                 Escalation, Ticket)

JSON = 'application/json'


class ApiTestCase(TestCase):
    """Base com atalhos para falar JSON com a API."""

    def get(self, url, **params):
        return self.client.get(url, params, HTTP_ACCEPT=JSON)

    def post(self, url, dados=None):
        return self.client.post(url, json.dumps(dados or {}),
                                content_type=JSON, HTTP_ACCEPT=JSON)

    def patch(self, url, dados):
        return self.client.patch(url, json.dumps(dados),
                                 content_type=JSON, HTTP_ACCEPT=JSON)


class AutenticacaoTests(ApiTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('tec_api')

    def test_anonimo_recebe_401(self):
        """401 (não autenticado), não 403 — por isso o TokenAuthentication
        vem primeiro no settings: só ele monta o desafio."""
        for url in ('/api/v1/tickets/', '/api/v1/eu/', '/api/v1/estatisticas/',
                    '/api/v1/categorias/', '/api/v1/ativos/'):
            with self.subTest(url=url):
                r = self.get(url)
                self.assertEqual(r.status_code, 401)
                self.assertEqual(r['WWW-Authenticate'], 'Token')

    def test_token_por_usuario_e_senha(self):
        r = self.client.post('/api/v1/token/',
                             {'username': 'tec_api', 'password': SENHA_DE_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertIn('token', r.json())

    def test_senha_errada_nao_devolve_token(self):
        r = self.client.post('/api/v1/token/',
                             {'username': 'tec_api', 'password': 'errada'})
        self.assertEqual(r.status_code, 400)

    def test_token_autentica(self):
        token = Token.objects.create(user=self.tecnico)
        r = self.client.get('/api/v1/eu/', HTTP_ACCEPT=JSON,
                            HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['username'], 'tec_api')

    def test_token_invalido_recebe_401(self):
        r = self.client.get('/api/v1/eu/', HTTP_ACCEPT=JSON,
                            HTTP_AUTHORIZATION='Token naoexiste')
        self.assertEqual(r.status_code, 401)

    def test_sessao_tambem_autentica(self):
        """Para navegar a API no browser com o login normal."""
        self.client.force_login(self.tecnico)
        self.assertEqual(self.get('/api/v1/eu/').status_code, 200)


class EuTests(ApiTestCase):
    """`/eu/` entrega o papel e as permissões, para o cliente não adivinhar."""

    def test_permissoes_por_papel(self):
        esperado = {
            'paulo_eu': (criar_solicitante, False, False, False),
            'tec_eu':   (criar_tecnico,     True,  True,  False),
            'ger_eu':   (criar_gerente,     True,  True,  True),
            'adm_eu':   (criar_admin,       True,  True,  True),
        }
        for username, (fabrica, cmdb, gerenciar, aprovar) in esperado.items():
            with self.subTest(username=username):
                user = fabrica(username)
                self.client.force_login(user)
                dados = self.get('/api/v1/eu/').json()
                self.assertEqual(dados['permissoes']['ver_cmdb'], cmdb)
                self.assertEqual(dados['permissoes']['gerenciar_chamados'], gerenciar)
                self.assertEqual(dados['permissoes']['aprovar'], aprovar)
                self.assertEqual(dados['papel'], user.profile.role)


class VisibilidadeTests(ApiTestCase):
    """O `visible_to` da Fase 3.1 valendo na API."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_vis')
        cls.leandro = criar_solicitante('leandro_vis')
        cls.tecnico = criar_tecnico('tec_vis')

        cls.do_paulo = Ticket.objects.create(
            title='Monitor do Paulo', description='d',
            requester=cls.paulo, priority='low')
        cls.do_leandro = Ticket.objects.create(
            title='Teclado do Leandro', description='d',
            requester=cls.leandro, priority='low')
        Comment.objects.create(ticket=cls.do_paulo, author=cls.tecnico,
                               is_internal=True, content='SEGREDO-DA-EQUIPE')
        Comment.objects.create(ticket=cls.do_paulo, author=cls.tecnico,
                               is_internal=False, content='Peça solicitada')

    def test_solicitante_lista_so_os_proprios(self):
        self.client.force_login(self.paulo)
        titulos = [t['title'] for t in self.get('/api/v1/tickets/').json()['results']]
        self.assertEqual(titulos, ['Monitor do Paulo'])

    def test_solicitante_recebe_404_em_chamado_alheio(self):
        """404 e não 403, como no HTML: um 403 confirmaria que existe."""
        self.client.force_login(self.paulo)
        r = self.get(f'/api/v1/tickets/{self.do_leandro.pk}/')
        self.assertEqual(r.status_code, 404)

    def test_equipe_ve_todos(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.get('/api/v1/tickets/').json()['count'], 2)

    def test_nota_interna_nao_vai_no_json_do_solicitante(self):
        self.client.force_login(self.paulo)
        r = self.get(f'/api/v1/tickets/{self.do_paulo.pk}/comentarios/')
        corpo = r.content.decode()
        self.assertNotIn('SEGREDO-DA-EQUIPE', corpo)
        self.assertIn('Peça solicitada', corpo)

    def test_tecnico_recebe_a_nota_interna(self):
        self.client.force_login(self.tecnico)
        r = self.get(f'/api/v1/tickets/{self.do_paulo.pk}/comentarios/')
        self.assertIn('SEGREDO-DA-EQUIPE', r.content.decode())

    def test_solicitante_nao_ve_auditoria_nem_escalonamentos(self):
        self.client.force_login(self.paulo)
        for sufixo in ('auditoria', 'escalonamentos'):
            with self.subTest(sufixo=sufixo):
                r = self.get(f'/api/v1/tickets/{self.do_paulo.pk}/{sufixo}/')
                self.assertEqual(r.status_code, 403)

    def test_solicitante_nao_lista_ativos(self):
        self.client.force_login(self.paulo)
        self.assertEqual(self.get('/api/v1/ativos/').status_code, 403)

    def test_solicitante_nao_lista_tecnicos(self):
        self.client.force_login(self.paulo)
        self.assertEqual(self.get('/api/v1/tecnicos/').status_code, 403)

    def test_estatisticas_respeitam_o_perfil(self):
        self.client.force_login(self.paulo)
        self.assertEqual(self.get('/api/v1/estatisticas/').json()['total'], 1)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.get('/api/v1/estatisticas/').json()['total'], 2)


class AberturaDeChamadoTests(ApiTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_abre')
        cls.gerente = criar_gerente('ger_abre')
        cls.normal  = Category.objects.create(name='Impressão')
        cls.acesso  = Category.objects.create(name='Acessos', requires_approval=True)

    def setUp(self):
        self.client.force_login(self.paulo)

    def test_solicitante_abre_chamado(self):
        r = self.post('/api/v1/tickets/', {
            'title': 'Impressora sem tinta', 'description': 'Trocar toner',
            'ticket_type': 'incident', 'priority': 'high',
            'category': self.normal.pk})
        self.assertEqual(r.status_code, 201)
        ticket = Ticket.objects.get(title='Impressora sem tinta')
        self.assertEqual(ticket.requester, self.paulo)
        self.assertEqual(ticket.status, 'open')
        self.assertIsNotNone(ticket.sla_deadline)

    def test_abertura_registra_na_auditoria_com_o_autor(self):
        self.post('/api/v1/tickets/', {
            'title': 'Com auditoria', 'description': 'd',
            'ticket_type': 'incident', 'priority': 'low'})
        ticket = Ticket.objects.get(title='Com auditoria')
        log = ticket.audit_logs.get(action=AuditLog.ACTION_CREATED)
        self.assertEqual(log.user, self.paulo)

    def test_categoria_com_aprovacao_nasce_pendente_e_sem_sla(self):
        """Mesma regra da Fase 3.3, valendo pela API."""
        r = self.post('/api/v1/tickets/', {
            'title': 'Acesso ao RH', 'description': 'd',
            'ticket_type': 'request', 'priority': 'critical',
            'category': self.acesso.pk})
        self.assertEqual(r.status_code, 201)
        ticket = Ticket.objects.get(title='Acesso ao RH')
        self.assertEqual(ticket.status, 'pending_approval')
        self.assertIsNone(ticket.sla_deadline)
        self.assertIsNone(ticket.sla_started_at)

    def test_titulo_curto_e_recusado(self):
        r = self.post('/api/v1/tickets/', {
            'title': 'oi', 'description': 'd',
            'ticket_type': 'incident', 'priority': 'low'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('title', r.json())

    def test_solicitante_nao_escolhe_status_nem_tecnico(self):
        """Os campos nem existem no serializer de abertura."""
        tecnico = criar_tecnico('tec_abre')
        self.post('/api/v1/tickets/', {
            'title': 'Tentando escolher', 'description': 'd',
            'ticket_type': 'incident', 'priority': 'low',
            'status': 'resolved', 'assignee': tecnico.pk})
        ticket = Ticket.objects.get(title='Tentando escolher')
        self.assertEqual(ticket.status, 'open')
        self.assertIsNone(ticket.assignee)


class AlteracaoDeChamadoTests(ApiTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_alt')
        cls.tecnico = criar_tecnico('tec_alt')

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Chamado', description='d', requester=self.paulo, priority='low')
        self.url = f'/api/v1/tickets/{self.ticket.pk}/'

    def test_solicitante_nao_altera_nem_o_proprio_chamado(self):
        self.client.force_login(self.paulo)
        r = self.patch(self.url, {'priority': 'critical'})
        self.assertEqual(r.status_code, 403)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.priority, 'low')

    def test_tecnico_altera(self):
        self.client.force_login(self.tecnico)
        r = self.patch(self.url, {'status': 'in_progress',
                                  'assignee_id': self.tecnico.pk})
        self.assertEqual(r.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'in_progress')
        self.assertEqual(self.ticket.assignee, self.tecnico)

    def test_alteracao_fica_na_auditoria_com_o_autor(self):
        self.client.force_login(self.tecnico)
        self.patch(self.url, {'priority': 'critical'})
        log = self.ticket.audit_logs.get(field='Prioridade')
        self.assertEqual(log.user, self.tecnico)
        self.assertEqual((log.old_value, log.new_value), ('Baixa', 'Crítica'))

    def test_status_do_workflow_e_recusado(self):
        """Mesma regra do formulário HTML: `pending_approval` e `rejected`
        são do workflow de aprovação, não de um PATCH."""
        self.client.force_login(self.tecnico)
        for status_proibido in ('pending_approval', 'rejected'):
            with self.subTest(status=status_proibido):
                r = self.patch(self.url, {'status': status_proibido})
                self.assertEqual(r.status_code, 400)
                self.ticket.refresh_from_db()
                self.assertEqual(self.ticket.status, 'open')

    def test_solicitante_nao_pode_ser_tecnico(self):
        self.client.force_login(self.tecnico)
        r = self.patch(self.url, {'assignee_id': self.paulo.pk})
        self.assertEqual(r.status_code, 400)

    def test_delete_nao_existe(self):
        """Chamado não se apaga: o histórico é o registro."""
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.delete(self.url).status_code, 405)


class AcoesDoAtendimentoTests(ApiTestCase):
    """As ações usam as mesmas funções de services.py que a tela."""

    @classmethod
    def setUpTestData(cls):
        cls.paulo    = criar_solicitante('paulo_ac')
        cls.tecnico  = criar_tecnico('tec_ac')
        cls.tecnico2 = criar_tecnico('tec_ac2')
        cls.gerente  = criar_gerente('ger_ac')

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Chamado', description='d', requester=self.paulo,
            assignee=self.tecnico, priority='medium')
        self.base = f'/api/v1/tickets/{self.ticket.pk}/'

    # ── Finalizar ─────────────────────────────────────────────────

    def test_finalizar(self):
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'finalizar/',
                      {'solution': 'Troquei o cabo de rede do switch.'})
        self.assertEqual(r.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'resolved')
        self.assertEqual(self.ticket.resolved_by, self.tecnico)
        self.assertIsNotNone(self.ticket.resolved_at)

    def test_solucao_curta_tem_a_mesma_mensagem_da_tela(self):
        """A prova de que a regra é compartilhada: a mensagem é a mesma
        constante usada pelo formulário HTML."""
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'finalizar/', {'solution': 'ok'})
        self.assertEqual(r.status_code, 400)
        self.assertIn(services.ERRO_SOLUCAO_CURTA, json.dumps(r.json(), ensure_ascii=False))

    def test_finalizar_duas_vezes_e_recusado(self):
        self.client.force_login(self.tecnico)
        self.post(self.base + 'finalizar/', {'solution': 'Resolvido na primeira.'})
        r = self.post(self.base + 'finalizar/', {'solution': 'Resolvido de novo.'})
        self.assertEqual(r.status_code, 400)

    def test_solicitante_nao_finaliza(self):
        self.client.force_login(self.paulo)
        r = self.post(self.base + 'finalizar/', {'solution': 'Vou dizer que resolvi.'})
        self.assertEqual(r.status_code, 403)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')

    # ── Escalonar ─────────────────────────────────────────────────

    def test_escalonar(self):
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'escalonar/',
                      {'to_user': self.tecnico2.pk,
                       'reason': 'Fora do meu escopo técnico.'})
        self.assertEqual(r.status_code, 201)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.tecnico2)
        esc = Escalation.objects.get()
        self.assertEqual(esc.from_user, self.tecnico)
        self.assertEqual(self.ticket.audit_logs.filter(
            action=AuditLog.ACTION_ESCALATED).count(), 1)

    def test_escalonar_para_si_mesmo_e_recusado(self):
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'escalonar/',
                      {'to_user': self.tecnico.pk, 'reason': 'Quero ficar com ele.'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Escalation.objects.count(), 0)

    def test_escalonar_para_solicitante_e_recusado(self):
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'escalonar/',
                      {'to_user': self.paulo.pk, 'reason': 'Passando para o usuário.'})
        self.assertEqual(r.status_code, 400)

    def test_motivo_curto_tem_a_mesma_mensagem_da_tela(self):
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'escalonar/',
                      {'to_user': self.tecnico2.pk, 'reason': 'nao'})
        self.assertEqual(r.status_code, 400)
        self.assertIn(services.ERRO_MOTIVO_CURTO, json.dumps(r.json(), ensure_ascii=False))

    # ── Comentar ──────────────────────────────────────────────────

    def test_solicitante_comenta(self):
        self.client.force_login(self.paulo)
        r = self.post(self.base + 'comentarios/', {'content': 'Ainda não funciona'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.ticket.comments.count(), 1)

    def test_solicitante_nao_cria_nota_interna_nem_pelo_json(self):
        """services.comentar_chamado força is_internal=False — a API não é
        um caminho alternativo para burlar a regra."""
        self.client.force_login(self.paulo)
        self.post(self.base + 'comentarios/',
                  {'content': 'tentativa', 'is_internal': True})
        self.assertFalse(Comment.objects.get(content='tentativa').is_internal)

    def test_tecnico_cria_nota_interna(self):
        self.client.force_login(self.tecnico)
        self.post(self.base + 'comentarios/',
                  {'content': 'interna', 'is_internal': True})
        self.assertTrue(Comment.objects.get(content='interna').is_internal)

    def test_comentario_vazio_e_recusado(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.post(self.base + 'comentarios/',
                                   {'content': '   '}).status_code, 400)


class AprovacaoPelaApiTests(ApiTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.paulo   = criar_solicitante('paulo_apr')
        cls.tecnico = criar_tecnico('tec_apr')
        cls.gerente = criar_gerente('ger_apr')
        cls.acesso  = Category.objects.create(name='Acessos2', requires_approval=True)

    def setUp(self):
        self.ticket = Ticket.objects.create(
            title='Acesso ao financeiro', description='d', requester=self.paulo,
            category=self.acesso, priority='critical', status='pending_approval')
        self.base = f'/api/v1/tickets/{self.ticket.pk}/'

    def test_gerente_aprova_e_o_sla_comeca(self):
        self.client.force_login(self.gerente)
        antes = timezone.now()
        r = self.post(self.base + 'aprovar/', {'comment': 'Liberado pelo gestor.'})
        self.assertEqual(r.status_code, 201)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        horas = (self.ticket.sla_deadline - antes).total_seconds() / 3600
        self.assertAlmostEqual(horas, 2, delta=0.1)

    def test_gerente_rejeita(self):
        self.client.force_login(self.gerente)
        r = self.post(self.base + 'rejeitar/',
                      {'comment': 'Falta aprovação do gestor direto.'})
        self.assertEqual(r.status_code, 201)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'rejected')

    def test_rejeitar_sem_motivo_e_recusado(self):
        self.client.force_login(self.gerente)
        r = self.post(self.base + 'rejeitar/', {'comment': ''})
        self.assertEqual(r.status_code, 400)
        self.assertIn(services.ERRO_REJEICAO_CURTA, json.dumps(r.json(), ensure_ascii=False))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'pending_approval')

    def test_tecnico_nao_aprova(self):
        self.client.force_login(self.tecnico)
        r = self.post(self.base + 'aprovar/', {'comment': ''})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Approval.objects.count(), 0)

    def test_solicitante_nao_aprova_o_proprio(self):
        self.client.force_login(self.paulo)
        self.assertEqual(self.post(self.base + 'aprovar/').status_code, 403)

    def test_aprovar_duas_vezes_e_recusado(self):
        self.client.force_login(self.gerente)
        self.post(self.base + 'aprovar/', {'comment': ''})
        r = self.post(self.base + 'aprovar/', {'comment': ''})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Approval.objects.count(), 1)

    def test_solicitante_ve_o_parecer(self):
        self.client.force_login(self.gerente)
        self.post(self.base + 'rejeitar/', {'comment': 'MOTIVO-VISIVEL ao usuário.'})
        self.client.force_login(self.paulo)
        r = self.get(self.base + 'aprovacoes/')
        self.assertIn('MOTIVO-VISIVEL', r.content.decode())


class ListagemTests(ApiTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico  = criar_tecnico('tec_lis')
        cls.tecnico2 = criar_tecnico('tec_lis2')
        for i in range(30):
            Ticket.objects.create(
                title=f'Chamado {i:02d}', description='d',
                requester=cls.tecnico, priority='low',
                status='open' if i % 2 else 'in_progress',
                assignee=cls.tecnico if i < 5 else None)

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_paginacao(self):
        dados = self.get('/api/v1/tickets/').json()
        self.assertEqual(dados['count'], 30)
        self.assertEqual(len(dados['results']), 25)
        self.assertIsNotNone(dados['next'])

    def test_filtro_por_status(self):
        dados = self.get('/api/v1/tickets/', status='open').json()
        self.assertEqual(dados['count'], 15)

    def test_filtro_sem_tecnico(self):
        dados = self.get('/api/v1/tickets/', assignee='unassigned').json()
        self.assertEqual(dados['count'], 25)

    def test_filtro_atribuidos_a_mim(self):
        dados = self.get('/api/v1/tickets/', assignee='me').json()
        self.assertEqual(dados['count'], 5)

    def test_busca(self):
        dados = self.get('/api/v1/tickets/', search='Chamado 07').json()
        self.assertEqual(dados['count'], 1)

    def test_ordenacao(self):
        dados = self.get('/api/v1/tickets/', ordering='created_at').json()
        self.assertEqual(dados['results'][0]['title'], 'Chamado 00')

    def test_campos_calculados_na_listagem(self):
        item = self.get('/api/v1/tickets/').json()['results'][0]
        for campo in ('status_nome', 'priority_nome', 'sla_vencido',
                      'sla_percentual', 'requester'):
            self.assertIn(campo, item)


class EstatisticasTests(ApiTestCase):
    """O endpoint que a Fase 3.6 vai consumir."""

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('tec_est')
        agora = timezone.now()
        for status in ('open', 'open', 'in_progress', 'resolved'):
            Ticket.objects.create(title=f't {status}', description='d',
                                  requester=cls.tecnico, priority='high',
                                  status=status)
        # Um vencido, para o contador de SLA.
        vencido = Ticket.objects.create(title='vencido', description='d',
                                        requester=cls.tecnico, priority='critical')
        Ticket.objects.filter(pk=vencido.pk).update(
            sla_deadline=agora - timezone.timedelta(hours=1))

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_estrutura(self):
        dados = self.get('/api/v1/estatisticas/').json()
        for chave in ('total', 'por_status', 'por_prioridade', 'em_aberto',
                      'sem_tecnico', 'sla_vencido', 'aguardando_aprovacao',
                      'por_categoria', 'por_tecnico'):
            self.assertIn(chave, dados)

    def test_numeros(self):
        dados = self.get('/api/v1/estatisticas/').json()
        self.assertEqual(dados['total'], 5)
        self.assertEqual(dados['por_status']['open'], 3)   # 2 + o vencido
        self.assertEqual(dados['em_aberto'], 4)            # exclui o resolvido
        self.assertEqual(dados['sla_vencido'], 1)

    def test_recorte_por_periodo(self):
        dados = self.get('/api/v1/estatisticas/', days=30).json()
        self.assertEqual(dados['total'], 5)

    def test_days_invalido_recebe_400(self):
        self.assertEqual(self.get('/api/v1/estatisticas/', days='abc').status_code, 400)


class CategoriasEAtivosTests(ApiTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tecnico = criar_tecnico('tec_cat')
        Category.objects.create(name='Rede')
        Category.objects.create(name='Acessos3', requires_approval=True)

    def setUp(self):
        self.client.force_login(self.tecnico)

    def test_categorias_informam_se_exigem_aprovacao(self):
        dados = self.get('/api/v1/categorias/').json()
        por_nome = {c['name']: c['requires_approval'] for c in dados}
        self.assertFalse(por_nome['Rede'])
        self.assertTrue(por_nome['Acessos3'])

    def test_categoria_e_somente_leitura(self):
        r = self.post('/api/v1/categorias/', {'name': 'Nova'})
        self.assertEqual(r.status_code, 405)

    def test_tecnicos_lista_quem_atende(self):
        criar_solicitante('sol_cat')
        usernames = [u['username'] for u in self.get('/api/v1/tecnicos/').json()]
        self.assertIn('tec_cat', usernames)
        self.assertNotIn('sol_cat', usernames)
