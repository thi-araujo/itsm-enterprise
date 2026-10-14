"""Cria o perfil dos usuários que já existiam antes do RBAC.

Sem esta migração, os usuários atuais ficariam sem `UserProfile` e qualquer
página quebraria com RelatedObjectDoesNotExist. O mapeamento usa as flags que
até agora faziam o papel de "papel":

    is_superuser  -> Administrador
    is_staff      -> Técnico
    (demais)      -> Solicitante
"""

from django.db import migrations


def criar_perfis(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('accounts', 'UserProfile')

    for user in User.objects.all():
        if UserProfile.objects.filter(user=user).exists():
            continue
        if user.is_superuser:
            papel = 'admin'
        elif user.is_staff:
            papel = 'technician'
        else:
            papel = 'requester'
        UserProfile.objects.create(user=user, role=papel)


def remover_perfis(apps, schema_editor):
    """Reversão: desfaz o que esta migração criou."""
    UserProfile = apps.get_model('accounts', 'UserProfile')
    UserProfile.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_perfis, remover_perfis),
    ]
