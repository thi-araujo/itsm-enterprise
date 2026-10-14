"""Testes de autenticação."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LoginTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('thiago', 'thiago@exemplo.local', 'senha-de-teste')

    def test_tela_de_login_abre(self):
        r = self.client.get(reverse('accounts:login'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ITSM Enterprise')

    def test_login_valido_vai_para_o_dashboard(self):
        r = self.client.post(reverse('accounts:login'),
                             {'username': 'thiago', 'password': 'senha-de-teste'})
        self.assertRedirects(r, reverse('dashboard:index'))

    def test_login_invalido_mostra_erro(self):
        r = self.client.post(reverse('accounts:login'),
                             {'username': 'thiago', 'password': 'errada'}, follow=True)
        self.assertContains(r, 'inválidos')

    def test_usuario_logado_nao_ve_a_tela_de_login(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('accounts:login'))
        self.assertRedirects(r, reverse('dashboard:index'))

    def test_logout_volta_para_o_login(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('accounts:logout'))
        self.assertRedirects(r, reverse('accounts:login'))
