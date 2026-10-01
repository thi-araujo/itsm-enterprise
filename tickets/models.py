from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from cmdb.models import Asset


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrição")
    icon = models.CharField(max_length=50, default="bi-tag", verbose_name="Ícone Bootstrap")
    color = models.CharField(max_length=20, default="primary", verbose_name="Cor")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ['name']

    def __str__(self):
        return self.name


class Ticket(models.Model):
    PRIORITY_CHOICES = [
        ('low',      'Baixa'),
        ('medium',   'Média'),
        ('high',     'Alta'),
        ('critical', 'Crítica'),
    ]
    STATUS_CHOICES = [
        ('open',        'Aberto'),
        ('in_progress', 'Em Andamento'),
        ('waiting',     'Aguardando'),
        ('resolved',    'Resolvido'),
        ('closed',      'Fechado'),
    ]
    TYPE_CHOICES = [
        ('incident',       'Incidente'),
        ('request',        'Requisição'),
        ('change',         'Mudança'),
        ('problem',        'Problema'),
    ]

    # Identificação
    title       = models.CharField(max_length=200, verbose_name="Título")
    description = models.TextField(verbose_name="Descrição")
    ticket_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='incident', verbose_name="Tipo")

    # Classificação
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='tickets', verbose_name="Categoria")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', verbose_name="Prioridade")
    status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name="Status")

    # Pessoas
    requester = models.ForeignKey(User, on_delete=models.CASCADE,
                                   related_name='requested_tickets', verbose_name="Solicitante")
    assignee  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='assigned_tickets', verbose_name="Técnico Responsável")

    # SLA
    sla_deadline = models.DateTimeField(null=True, blank=True, verbose_name="Prazo SLA")

    # Datas
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at  = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Resolvido em")
    closed_at   = models.DateTimeField(null=True, blank=True, verbose_name="Fechado em")
    sla_breach_notified = models.BooleanField(default=False, verbose_name="SLA notificado")
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='tickets', verbose_name="Ativo vinculado")

    class Meta:
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.pk} — {self.title}"

    @property
    def priority_color(self):
        colors = {
            'low':      'success',
            'medium':   'warning',
            'high':     'danger',
            'critical': 'dark',
        }
        return colors.get(self.priority, 'secondary')

    @property
    def status_color(self):
        colors = {
            'open':        'primary',
            'in_progress': 'info',
            'waiting':     'warning',
            'resolved':    'success',
            'closed':      'secondary',
        }
        return colors.get(self.status, 'secondary')

    @property
    def is_sla_breached(self):
        if self.sla_deadline and self.status not in ('resolved', 'closed'):
            return timezone.now() > self.sla_deadline
        return False

    @property
    def sla_remaining_hours(self):
        if self.sla_deadline and self.status not in ('resolved', 'closed'):
            delta = self.sla_deadline - timezone.now()
            return max(0, int(delta.total_seconds() // 3600))
        return None

    def save(self, *args, **kwargs):
        # Define SLA automaticamente ao criar
        if not self.pk and not self.sla_deadline:
            sla_hours = {'critical': 2, 'high': 8, 'medium': 24, 'low': 72}
            hours = sla_hours.get(self.priority, 24)
            self.sla_deadline = timezone.now() + timezone.timedelta(hours=hours)
        # Registra data de resolução
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        if self.status == 'closed' and not self.closed_at:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)


class Comment(models.Model):
    ticket  = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    author  = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(verbose_name="Comentário")
    is_internal = models.BooleanField(default=False, verbose_name="Nota Interna")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comentário de {self.author} em #{self.ticket.pk}"


class Attachment(models.Model):
    ticket      = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    file        = models.FileField(upload_to='attachments/%Y/%m/')
    filename    = models.CharField(max_length=255)
    file_size   = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.filename

    @property
    def file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size // 1024} KB"
        return f"{self.file_size // (1024*1024)} MB"

    @property
    def icon(self):
        ext = self.filename.rsplit('.', 1)[-1].lower() if '.' in self.filename else ''
        icons = {
            'pdf': 'bi-file-pdf text-danger',
            'doc': 'bi-file-word text-primary', 'docx': 'bi-file-word text-primary',
            'xls': 'bi-file-excel text-success', 'xlsx': 'bi-file-excel text-success',
            'png': 'bi-file-image text-info', 'jpg': 'bi-file-image text-info',
            'jpeg': 'bi-file-image text-info',
            'zip': 'bi-file-zip text-warning', 'rar': 'bi-file-zip text-warning',
            'txt': 'bi-file-text text-secondary', 'log': 'bi-file-text text-secondary',
        }
        return icons.get(ext, 'bi-file-earmark text-muted')
