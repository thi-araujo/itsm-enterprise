"""Criação automática do perfil de acesso.

Um signal é uma função que o Django chama sozinho quando algo acontece no
banco. Aqui, sempre que um `User` é salvo, garantimos que ele tenha um
`UserProfile` — inclusive quando o usuário é criado pelo /admin/, pelo
`createsuperuser` ou pelo `seed_data.py`.
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def criar_perfil_do_usuario(sender, instance, created, **kwargs):
    if created:
        # Superusuário nasce Administrador; os demais nascem Solicitante,
        # que é o papel de menor privilégio.
        papel = (UserProfile.ROLE_ADMIN if instance.is_superuser
                 else UserProfile.ROLE_REQUESTER)
        UserProfile.objects.create(user=instance, role=papel)
    elif not UserProfile.objects.filter(user=instance).exists():
        # Rede de segurança: usuário antigo que ficou sem perfil.
        UserProfile.objects.create(user=instance)
