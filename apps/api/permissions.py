"""Permissões da API, espelhando os decorators do RBAC (Fase 3.1).

Os decorators de `apps/accounts/permissions.py` redirecionam para o dashboard
com uma mensagem — comportamento certo para uma tela, errado para uma API,
que precisa devolver **403** com um corpo JSON. Mesma regra, outro
transporte: as duas leem as propriedades do `UserProfile`.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class _PerfilPermission(BasePermission):
    """Base: autentica e consulta uma propriedade do UserProfile."""

    propriedade = None
    message = 'Você não tem permissão para esta operação.'

    def has_permission(self, request, view):
        perfil = getattr(request.user, 'profile', None)
        if perfil is None:
            return False
        return bool(getattr(perfil, self.propriedade, False))


class IsStaff(_PerfilPermission):
    """Técnico, gerente ou administrador."""

    propriedade = 'can_manage_tickets'
    message = 'Apenas a equipe de atendimento pode executar esta operação.'


class IsManagement(_PerfilPermission):
    """Gerente ou administrador."""

    propriedade = 'can_approve'
    message = 'Apenas gerentes e administradores podem executar esta operação.'


class ReadOnlyOrStaff(BasePermission):
    """Leitura para qualquer autenticado; escrita só para a equipe.

    Usada nos chamados: o solicitante abre (POST na coleção, tratado à parte)
    e consulta os próprios, mas não altera status, técnico nem prioridade.
    """

    message = 'Apenas a equipe de atendimento pode alterar chamados.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        perfil = getattr(request.user, 'profile', None)
        return perfil is not None and perfil.can_manage_tickets
