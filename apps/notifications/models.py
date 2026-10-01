from django.db import models
from django.contrib.auth.models import User


class Notification(models.Model):
    TYPE_CHOICES = [
        ('ticket_created',  'Ticket Criado'),
        ('ticket_assigned', 'Ticket Atribuído'),
        ('ticket_updated',  'Ticket Atualizado'),
        ('ticket_resolved', 'Ticket Resolvido'),
        ('comment_added',   'Comentário Adicionado'),
        ('sla_warning',     'Aviso de SLA'),
        ('sla_breach',      'SLA Vencido'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type       = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    ticket_id  = models.IntegerField(null=True, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'

    def __str__(self):
        return f"[{self.type}] {self.title} → {self.user.username}"

    @property
    def type_icon(self):
        icons = {
            'ticket_created':  'bi-plus-circle text-primary',
            'ticket_assigned': 'bi-person-check text-info',
            'ticket_updated':  'bi-pencil text-warning',
            'ticket_resolved': 'bi-check-circle text-success',
            'comment_added':   'bi-chat-left-text text-secondary',
            'sla_warning':     'bi-alarm text-warning',
            'sla_breach':      'bi-exclamation-octagon text-danger',
        }
        return icons.get(self.type, 'bi-bell')