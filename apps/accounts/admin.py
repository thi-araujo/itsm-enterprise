from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    """Perfil editável na mesma tela do usuário."""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Perfil de Acesso'
    fields = ['role', 'department']


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ['username', 'email', 'first_name', 'last_name',
                    'perfil_de_acesso', 'is_active']

    @admin.display(description='Perfil')
    def perfil_de_acesso(self, obj):
        perfil = getattr(obj, 'profile', None)
        return perfil.get_role_display() if perfil else '—'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ['user', 'role', 'department', 'updated_at']
    list_filter   = ['role']
    search_fields = ['user__username', 'user__email', 'department']


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
