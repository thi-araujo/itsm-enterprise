"""Testes do CMDB — inclui ativo sem responsável (`owner` nulo), o mesmo
padrão de FK nula que o CLAUDE.md exige tratar em todos os templates."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.testing import criar_tecnico
from apps.cmdb.models import Asset, AssetType
from apps.tickets.models import Ticket


class AtivoSemResponsavelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_tecnico('c')
        cls.tipo = AssetType.objects.create(name='Notebook')
        cls.sem_dono = Asset.objects.create(name='NB-SEM-DONO', asset_tag='PAT-001',
                                            asset_type=cls.tipo)
        cls.com_dono = Asset.objects.create(name='NB-DO-THIAGO', asset_tag='PAT-002',
                                            asset_type=cls.tipo, owner=cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def test_owner_nulo_de_fato(self):
        self.assertIsNone(self.sem_dono.owner)

    def test_lista_e_detalhe_renderizam_sem_dono(self):
        for url in (reverse('cmdb:list'),
                    reverse('cmdb:detail', args=[self.sem_dono.pk])):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, 'None')

    def test_detalhe_com_dono_mostra_o_nome(self):
        r = self.client.get(reverse('cmdb:detail', args=[self.com_dono.pk]))
        self.assertContains(r, self.user.username)

    def test_str_do_ativo(self):
        self.assertEqual(str(self.sem_dono), 'PAT-001 — NB-SEM-DONO')


class AtivoVinculadoAoTicketTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = criar_tecnico('c2')
        cls.ativo = Asset.objects.create(name='SRV-01', asset_tag='PAT-010')
        cls.ticket = Ticket.objects.create(title='Servidor lento', description='d',
                                           requester=cls.user, priority='high',
                                           asset=cls.ativo)

    def test_ticket_aponta_para_o_ativo(self):
        self.assertEqual(self.ticket.asset, self.ativo)
        self.assertIn(self.ticket, self.ativo.tickets.all())

    def test_apagar_o_ativo_nao_apaga_o_ticket(self):
        """asset usa on_delete=SET_NULL — o chamado tem de sobreviver."""
        self.ativo.delete()
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.asset)
