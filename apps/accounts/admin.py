from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    """Perfil editável na mesma tela do usuário."""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Perfil de Acesso'
    fields = ['role', 'department', 'from_ldap', 'ldap_last_sync']
    # Quem grava estes dois é o backend do AD (Fase 3.8); editar à mão aqui
    # só criaria uma informação que o próximo login sobrescreve.
    readonly_fields = ['from_ldap', 'ldap_last_sync']


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ['username', 'email', 'first_name', 'last_name',
                    'perfil_de_acesso', 'origem_da_conta', 'is_active']

    @admin.display(description='Perfil')
    def perfil_de_acesso(self, obj):
        perfil = getattr(obj, 'profile', None)
        return perfil.get_role_display() if perfil else '—'

    @admin.display(description='Origem', boolean=False)
    def origem_da_conta(self, obj):
        """Conta do AD ou local — a senha de quem vem do AD é trocada no
        domínio, e tentar redefini-la aqui não teria efeito."""
        perfil = getattr(obj, 'profile', None)
        if perfil is None:
            return '—'
        return 'Active Directory' if perfil.from_ldap else 'Local'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ['user', 'role', 'department', 'from_ldap',
                     'ldap_last_sync', 'updated_at']
    list_filter   = ['role', 'from_ldap']
    search_fields = ['user__username', 'user__email', 'department']


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
