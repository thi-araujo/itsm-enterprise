"""Decorators de autorização por papel (RBAC).

Use sempre depois de @login_required:

    @login_required
    @staff_required
    def minha_view(request): ...
"""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import UserProfile


def role_required(*roles):
    """Restringe a view aos papéis informados.

    Quem não tem o papel recebe uma mensagem e volta ao dashboard — e não um
    403 seco, que não explica nada a quem está usando o sistema.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            perfil = getattr(request.user, 'profile', None)
            if perfil is None or perfil.role not in roles:
                messages.error(request, 'Você não tem permissão para acessar esta área.')
                return redirect('dashboard:index')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def staff_required(view):
    """Atalho: técnico, gerente ou administrador."""
    return role_required(*UserProfile.STAFF_ROLES)(view)


def management_required(view):
    """Atalho: gerente ou administrador."""
    return role_required(*UserProfile.MANAGEMENT_ROLES)(view)
