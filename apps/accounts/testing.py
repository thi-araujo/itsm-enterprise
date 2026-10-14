"""Utilitários para os testes criarem usuários já com o papel desejado.

O perfil nasce pelo signal com o papel padrão; aqui ajustamos para o papel
que o teste precisa, evitando repetir isso em cada arquivo de teste.
"""

from django.contrib.auth.models import User

from .models import UserProfile

SENHA_DE_TESTE = 'senha-de-teste'


def criar_usuario(username, role=UserProfile.ROLE_REQUESTER, **extra):
    user = User.objects.create_user(username, f'{username}@exemplo.local',
                                    SENHA_DE_TESTE, **extra)
    if user.profile.role != role:
        user.profile.role = role
        user.profile.save()
    return user


def criar_solicitante(username='solicitante', **extra):
    return criar_usuario(username, UserProfile.ROLE_REQUESTER, **extra)


def criar_tecnico(username='tecnico', **extra):
    return criar_usuario(username, UserProfile.ROLE_TECHNICIAN, **extra)


def criar_gerente(username='gerente', **extra):
    return criar_usuario(username, UserProfile.ROLE_MANAGER, **extra)


def criar_admin(username='administrador', **extra):
    return criar_usuario(username, UserProfile.ROLE_ADMIN, **extra)
