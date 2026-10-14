"""Perfis de acesso (RBAC) do ITSM Enterprise.

O `User` do Django não tem campo de papel, então ligamos um perfil a ele por
um OneToOneField — uma linha de perfil para cada usuário. O perfil é criado
automaticamente por signal (ver signals.py), inclusive quando o usuário nasce
pelo /admin/ ou pelo `createsuperuser`.
"""

from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_REQUESTER  = 'requester'
    ROLE_TECHNICIAN = 'technician'
    ROLE_MANAGER    = 'manager'
    ROLE_ADMIN      = 'admin'

    ROLE_CHOICES = [
        (ROLE_REQUESTER,  'Solicitante'),
        (ROLE_TECHNICIAN, 'Técnico'),
        (ROLE_MANAGER,    'Gerente'),
        (ROLE_ADMIN,      'Administrador'),
    ]

    # Papéis que enxergam todos os chamados, a fila de atendimento e o CMDB,
    # e que podem receber chamados atribuídos.
    STAFF_ROLES = (ROLE_TECHNICIAN, ROLE_MANAGER, ROLE_ADMIN)

    # Papéis que enxergam os relatórios gerenciais.
    MANAGEMENT_ROLES = (ROLE_MANAGER, ROLE_ADMIN)

    user = models.OneToOneField(User, on_delete=models.CASCADE,
                                related_name='profile', verbose_name="Usuário")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES,
                            default=ROLE_REQUESTER, verbose_name="Perfil")
    department = models.CharField(max_length=100, blank=True,
                                  verbose_name="Departamento")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil de Acesso"
        verbose_name_plural = "Perfis de Acesso"
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()}"

    # ──────────────────────────────────────────────────────────────
    # Permissões. Concentradas aqui para que as views e os templates
    # nunca comparem `role` na mão — assim a regra muda em um só lugar.
    # ──────────────────────────────────────────────────────────────

    @property
    def can_see_all_tickets(self):
        """Vê os chamados de todos. Solicitante vê apenas os próprios."""
        return self.role in self.STAFF_ROLES

    @property
    def can_see_queue(self):
        """Acessa a fila de atendimento e atribui chamados."""
        return self.role in self.STAFF_ROLES

    @property
    def can_see_cmdb(self):
        """Acessa o inventário de ativos."""
        return self.role in self.STAFF_ROLES

    @property
    def can_see_internal_notes(self):
        """Lê e escreve notas internas (invisíveis ao solicitante)."""
        return self.role in self.STAFF_ROLES

    @property
    def can_manage_tickets(self):
        """Altera status, prioridade e técnico responsável."""
        return self.role in self.STAFF_ROLES

    @property
    def can_attend(self):
        """Pode receber chamados — aparece no seletor de técnico."""
        return self.role in self.STAFF_ROLES

    @property
    def can_see_reports(self):
        """Acessa os relatórios gerenciais."""
        return self.role in self.MANAGEMENT_ROLES
