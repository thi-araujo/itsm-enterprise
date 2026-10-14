from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.cmdb.models import Asset


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrição")
    icon = models.CharField(max_length=50, default="bi-tag", verbose_name="Ícone Bootstrap")
    color = models.CharField(max_length=20, default="primary", verbose_name="Cor")
    # Workflow de aprovação (Fase 3.3). Fica na categoria, e não no tipo do
    # chamado, para a política ser um checkbox no /admin/ em vez de um deploy.
    requires_approval = models.BooleanField(
        default=False, verbose_name="Exige aprovação do gerente",
        help_text="Chamados desta categoria nascem aguardando aprovação.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ['name']

    def __str__(self):
        return self.name


class TicketQuerySet(models.QuerySet):
    """Consultas de Ticket que dependem do perfil de acesso (RBAC)."""

    def visible_to(self, user):
        """Restringe aos chamados que o usuário pode ver.

        Técnico, gerente e administrador veem todos. Solicitante vê apenas os
        que ele mesmo abriu. Centralizar isso aqui — e não espalhar `if` pelas
        views — garante que nenhuma tela esqueça o filtro.
        """
        perfil = getattr(user, 'profile', None)
        if perfil is not None and perfil.can_see_all_tickets:
            return self
        return self.filter(requester=user)


class Ticket(models.Model):
    PRIORITY_CHOICES = [
        ('low',      'Baixa'),
        ('medium',   'Média'),
        ('high',     'Alta'),
        ('critical', 'Crítica'),
    ]
    STATUS_CHOICES = [
        ('pending_approval', 'Aguardando Aprovação'),
        ('open',             'Aberto'),
        ('in_progress',      'Em Andamento'),
        ('waiting',          'Aguardando'),
        ('resolved',         'Resolvido'),
        ('closed',           'Fechado'),
        ('rejected',         'Rejeitado'),
    ]

    # Status controlados pelo workflow de aprovação, e não escolhidos à mão:
    # ficam fora do <select> do painel "Atualizar Ticket" (ver TicketUpdateForm).
    WORKFLOW_STATUSES = ('pending_approval', 'rejected')

    # Status em que o chamado não está mais em atendimento.
    CLOSED_STATUSES = ('resolved', 'closed', 'rejected')

    # Campos acompanhados pela auditoria (Fase 3.4), com o rótulo que aparece
    # na linha do tempo. Qualquer save() que mude um deles gera uma entrada.
    AUDITED_FIELDS = {
        'status':       'Status',
        'priority':     'Prioridade',
        'assignee':     'Técnico Responsável',
        'category':     'Categoria',
        'sla_deadline': 'Prazo SLA',
        'title':        'Título',
        'solution':     'Solução',
    }
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
    # Quando o relógio começou (Fase 3.7). Sem este campo não dá para dizer
    # "já passou 80% do prazo": calcular `sla_deadline - 24h` erraria se a
    # prioridade tivesse sido alterada depois da abertura.
    sla_started_at = models.DateTimeField(null=True, blank=True,
                                          verbose_name="SLA iniciado em")
    # Controle de idempotência das automações: o comando roda de 15 em 15
    # minutos e não pode reavisar nem reescalonar o mesmo chamado.
    sla_warning_notified = models.BooleanField(default=False,
                                               verbose_name="Aviso de SLA enviado")
    # DateTimeField e não BooleanField: serve de marca e de registro de quando.
    sla_escalated_at = models.DateTimeField(null=True, blank=True,
                                            verbose_name="Escalonado por SLA em")

    # Atendimento (Fase 3.2)
    solution    = models.TextField(blank=True, verbose_name="Solução")
    # Quem finalizou. Não dá para usar `assignee`: o responsável pode mudar
    # depois da resolução e a trilha de quem resolveu se perderia.
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='resolved_tickets', verbose_name="Resolvido por")

    # Datas
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at  = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Resolvido em")
    closed_at   = models.DateTimeField(null=True, blank=True, verbose_name="Fechado em")
    sla_breach_notified = models.BooleanField(default=False, verbose_name="SLA notificado")
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='tickets', verbose_name="Ativo vinculado")

    objects = TicketQuerySet.as_manager()

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
            'pending_approval': 'warning',
            'open':             'primary',
            'in_progress':      'info',
            'waiting':          'warning',
            'resolved':         'success',
            'closed':           'secondary',
            'rejected':         'danger',
        }
        return colors.get(self.status, 'secondary')

    # ──────────────────────────────────────────────────────────────
    # Estado do chamado. As views e os templates perguntam por estas
    # propriedades e nunca repetem a lista de status.
    # ──────────────────────────────────────────────────────────────

    @property
    def is_in_attendance(self):
        """Está em atendimento: já foi liberado e ainda não terminou.

        Aguardando aprovação não conta — o chamado ainda não foi autorizado,
        então não há o que finalizar nem a quem repassar.
        """
        return (self.status not in self.CLOSED_STATUSES
                and self.status != 'pending_approval')

    @property
    def can_be_finished(self):
        """Só faz sentido finalizar um chamado que ainda está em atendimento."""
        return self.is_in_attendance

    @property
    def can_be_escalated(self):
        """Idem para escalonar: repassar um chamado encerrado não faz sentido
        e reatribuiria o responsável sem ninguém esperar por isso."""
        return self.is_in_attendance

    @property
    def is_awaiting_approval(self):
        """Aguardando a decisão do gerente (Fase 3.3)."""
        return self.status == 'pending_approval'

    @property
    def last_approval(self):
        """A última decisão de aprovação, ou None se nunca houve uma."""
        return self.approvals.first()   # ordering = ['-created_at']

    @property
    def is_sla_breached(self):
        if self.sla_deadline and self.status not in self.CLOSED_STATUSES:
            return timezone.now() > self.sla_deadline
        return False

    @property
    def sla_remaining_hours(self):
        if self.sla_deadline and self.status not in self.CLOSED_STATUSES:
            delta = self.sla_deadline - timezone.now()
            return max(0, int(delta.total_seconds() // 3600))
        return None

    @property
    def sla_elapsed_percent(self):
        """Quanto do prazo já passou, em porcentagem (Fase 3.7).

        Devolve None quando não há prazo contando — chamado aguardando
        aprovação, resolvido, fechado ou rejeitado. Passa de 100 quando o
        prazo já estourou.
        """
        if not self.sla_deadline or self.status in self.CLOSED_STATUSES:
            return None
        inicio = self.sla_started_at or self.created_at
        if not inicio:
            return None
        total = (self.sla_deadline - inicio).total_seconds()
        if total <= 0:
            return 100
        decorrido = (timezone.now() - inicio).total_seconds()
        return max(0, int(decorrido / total * 100))

    @property
    def sla_at_risk(self):
        """Passou do limite de aviso do settings e ainda não venceu."""
        percentual = self.sla_elapsed_percent
        if percentual is None:
            return False
        return percentual >= settings.SLA_WARNING_PERCENT and not self.is_sla_breached

    def start_sla(self):
        """Inicia a contagem do SLA a partir de agora.

        Usado na aprovação: um chamado que esperou o gerente não pode nascer
        com o prazo contando desde a abertura, senão um crítico (SLA de 2h)
        que ficou o fim de semana parado já estaria vencido antes de alguém
        poder atendê-lo.
        """
        agora = timezone.now()
        self.sla_started_at = agora
        self.sla_deadline = agora + timezone.timedelta(
            hours=self.sla_hours_for_priority())

    def sla_hours_for_priority(self):
        """Horas de SLA da prioridade atual (CLAUDE.md: 2 · 8 · 24 · 72)."""
        return {'critical': 2, 'high': 8, 'medium': 24, 'low': 72}.get(self.priority, 24)

    # ──────────────────────────────────────────────────────────────
    # Auditoria (Fase 3.4)
    #
    # O chamado guarda um retrato de como estava quando saiu do banco
    # (`from_db`) e, a cada save(), compara o estado atual com esse retrato.
    # Assim toda alteração fica registrada — pela view, pelo /admin/, pelo
    # shell ou pelo comando check_sla —, sem depender de alguém lembrar de
    # chamar o log em cada lugar.
    #
    # Limitação conhecida: `QuerySet.update()` vai direto ao SQL e não passa
    # pelo save(), então não é auditado. Hoje o projeto só usa update() em
    # `sla_breach_notified`, que não está em AUDITED_FIELDS.
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._audit_snapshot = instance._audit_state()
        return instance

    def _audit_state(self):
        """Valores brutos dos campos auditados, para comparar sem consultas.

        Para as chaves estrangeiras guarda o id (`assignee_id`), e não o
        objeto: ler `self.assignee` dispararia uma consulta a cada chamado
        carregado, inclusive nas listagens, onde nada vai ser salvo.
        """
        estado = {}
        for campo in self.AUDITED_FIELDS:
            try:
                atributo = self._meta.get_field(campo).attname   # 'assignee_id'
            except Exception:
                atributo = campo
            estado[campo] = getattr(self, atributo, None)
        return estado

    def _audit_display(self, campo, valor_bruto):
        """Converte o valor bruto no texto que vai para o log.

        O log guarda o texto já formatado ("Crítica", "Técnico Um") e não o
        código nem o id. Num registro de auditoria é isso que se quer: se o
        usuário for renomeado ou apagado, a entrada continua dizendo o que
        estava escrito na época — um FK vivo reescreveria o passado.
        """
        if valor_bruto in (None, ''):
            return ''
        if campo in ('status', 'priority'):
            opcoes = dict(self.STATUS_CHOICES if campo == 'status' else self.PRIORITY_CHOICES)
            return opcoes.get(valor_bruto, str(valor_bruto))
        if campo == 'assignee':
            user = User.objects.filter(pk=valor_bruto).first()
            return (user.get_full_name() or user.username) if user else ''
        if campo == 'category':
            categoria = Category.objects.filter(pk=valor_bruto).first()
            return categoria.name if categoria else ''
        if campo == 'sla_deadline':
            return timezone.localtime(valor_bruto).strftime('%d/%m/%Y %H:%M')
        # Título e solução: texto livre, truncado para caber na coluna.
        texto = str(valor_bruto)
        return texto[:250] + '…' if len(texto) > 250 else texto

    def save_as(self, user, *args, **kwargs):
        """Salva registrando quem fez a alteração.

        O save() não tem acesso ao request, então a view informa o autor. Sem
        isso o log fica com o usuário nulo e a tela mostra "Sistema" — o que
        é correto para o comando check_sla, mas não para uma ação de tela.
        """
        self._audit_user = user
        return self.save(*args, **kwargs)

    def _registrar_auditoria(self, criado):
        from_user = getattr(self, '_audit_user', None)

        if criado:
            AuditLog.objects.create(ticket=self, user=from_user,
                                    action=AuditLog.ACTION_CREATED)
        else:
            anterior = getattr(self, '_audit_snapshot', None)
            if anterior is None:
                # Instância montada na memória (sem vir do banco): não há com
                # o que comparar, então não há o que registrar.
                return
            atual = self._audit_state()
            for campo, rotulo in self.AUDITED_FIELDS.items():
                if anterior.get(campo) == atual.get(campo):
                    continue
                AuditLog.objects.create(
                    ticket=self, user=from_user, action=AuditLog.ACTION_UPDATED,
                    field=rotulo,
                    old_value=self._audit_display(campo, anterior.get(campo)),
                    new_value=self._audit_display(campo, atual.get(campo)),
                )

        # Novo ponto de partida: um segundo save() na mesma requisição não
        # pode registrar de novo a mesma alteração.
        self._audit_snapshot = self._audit_state()

    def save(self, *args, **kwargs):
        criado = self.pk is None

        # SLA automático ao criar — exceto aguardando aprovação, onde o
        # relógio só começa quando o gerente liberar (ver start_sla).
        if not self.pk and not self.sla_deadline and not self.is_awaiting_approval:
            agora = timezone.now()
            self.sla_started_at = agora
            self.sla_deadline = agora + timezone.timedelta(
                hours=self.sla_hours_for_priority())
        # Registra data de resolução
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        if self.status == 'closed' and not self.closed_at:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)
        self._registrar_auditoria(criado)


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


class Escalation(models.Model):
    """Histórico de escalonamentos de um chamado (Fase 3.2).

    É um model próprio, e não um comentário de texto, porque o histórico
    precisa ser consultável — `ticket.escalations.count()`, "quantos chamados
    foram escalonados para este técnico" — e será a base do escalonamento
    automático por SLA vencido (Fase 3.7). Texto solto num Comment não
    responde a essas perguntas.
    """

    ticket    = models.ForeignKey(Ticket, on_delete=models.CASCADE,
                                  related_name='escalations', verbose_name="Ticket")
    # from_user e to_user são SET_NULL: se o técnico sair da empresa e o
    # usuário for apagado, o registro de auditoria tem de sobreviver.
    from_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='escalations_sent', verbose_name="Escalonado por")
    to_user   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='escalations_received', verbose_name="Escalonado para")
    reason    = models.TextField(verbose_name="Motivo")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data")

    class Meta:
        verbose_name = "Escalonamento"
        verbose_name_plural = "Escalonamentos"
        ordering = ['-created_at']

    def __str__(self):
        destino = self.to_user.username if self.to_user else "—"
        return f"#{self.ticket_id} escalonado para {destino}"


class AuditLog(models.Model):
    """Trilha cronológica de tudo o que aconteceu no chamado (Fase 3.4).

    Não substitui a Escalation nem a Approval: aqueles guardam dados
    estruturados que o sistema consulta (o motivo, a decisão, o parecer).
    Este é o registro em ordem de tempo — eles geram entradas aqui.

    As alterações de campo chegam automaticamente pelo save() do Ticket; os
    eventos que não são mudança de valor (comentário, anexo, escalonamento,
    aprovação) são registrados pelas views com `AuditLog.registrar`.
    """

    ACTION_CREATED   = 'created'
    ACTION_UPDATED   = 'updated'
    ACTION_COMMENTED = 'commented'
    ACTION_ATTACHED  = 'attached'
    ACTION_ESCALATED = 'escalated'
    ACTION_APPROVED  = 'approved'
    ACTION_REJECTED  = 'rejected'

    ACTION_CHOICES = [
        (ACTION_CREATED,   'Abriu o chamado'),
        (ACTION_UPDATED,   'Alterou um campo'),
        (ACTION_COMMENTED, 'Comentou'),
        (ACTION_ATTACHED,  'Anexou arquivo'),
        (ACTION_ESCALATED, 'Escalonou'),
        (ACTION_APPROVED,  'Aprovou'),
        (ACTION_REJECTED,  'Rejeitou'),
    ]

    # Ícone de cada ação na linha do tempo.
    ACTION_ICONS = {
        ACTION_CREATED:   'bi-plus-circle',
        ACTION_UPDATED:   'bi-pencil',
        ACTION_COMMENTED: 'bi-chat-left-text',
        ACTION_ATTACHED:  'bi-paperclip',
        ACTION_ESCALATED: 'bi-arrow-up-right-circle',
        ACTION_APPROVED:  'bi-patch-check',
        ACTION_REJECTED:  'bi-x-octagon',
    }

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE,
                               related_name='audit_logs', verbose_name="Ticket")
    # Nulo = ação do sistema (o comando check_sla, por exemplo) ou usuário
    # apagado depois. SET_NULL para a trilha sobreviver ao desligamento.
    user   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='audit_logs', verbose_name="Autor")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES,
                              verbose_name="Ação")
    # Preenchidos só em 'updated'. Guardam o texto já formatado — ver
    # Ticket._audit_display.
    field      = models.CharField(max_length=60, blank=True, verbose_name="Campo")
    old_value  = models.CharField(max_length=255, blank=True, verbose_name="Valor anterior")
    new_value  = models.CharField(max_length=255, blank=True, verbose_name="Valor novo")
    # Texto livre dos eventos que não são mudança de campo.
    description = models.CharField(max_length=255, blank=True, verbose_name="Descrição")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data")

    class Meta:
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['ticket', '-created_at'])]

    def __str__(self):
        return f"#{self.ticket_id} — {self.get_action_display()}"

    @classmethod
    def registrar(cls, ticket, user, action, description=''):
        """Atalho para os eventos que não são alteração de campo."""
        return cls.objects.create(ticket=ticket, user=user, action=action,
                                  description=description)

    @property
    def author_display(self):
        """Nome de quem agiu, ou "Sistema" quando não houve usuário."""
        if not self.user:
            return 'Sistema'
        return self.user.get_full_name() or self.user.username

    @property
    def icon(self):
        return self.ACTION_ICONS.get(self.action, 'bi-circle')

    @property
    def summary(self):
        """Uma frase pronta para a linha do tempo."""
        if self.action == self.ACTION_UPDATED:
            de  = self.old_value or '—'
            para = self.new_value or '—'
            return f"{self.field}: {de} → {para}"
        if self.description:
            return f"{self.get_action_display()} — {self.description}"
        return self.get_action_display()


class Approval(models.Model):
    """Decisão de aprovação de um chamado (Fase 3.3).

    É FK e não OneToOne, como a Escalation, para o histórico aguentar um
    futuro "solicitar nova aprovação" depois de uma rejeição.

    Diferença importante em relação ao escalonamento: o motivo registrado
    aqui **o solicitante vê**. Ele precisa saber por que o pedido foi negado.
    """

    DECISION_APPROVED = 'approved'
    DECISION_REJECTED = 'rejected'
    DECISION_CHOICES = [
        (DECISION_APPROVED, 'Aprovado'),
        (DECISION_REJECTED, 'Rejeitado'),
    ]

    ticket     = models.ForeignKey(Ticket, on_delete=models.CASCADE,
                                   related_name='approvals', verbose_name="Ticket")
    # SET_NULL para a auditoria sobreviver se o gerente for apagado.
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='approvals_decided', verbose_name="Decidido por")
    decision   = models.CharField(max_length=20, choices=DECISION_CHOICES,
                                  verbose_name="Decisão")
    comment    = models.TextField(blank=True, verbose_name="Parecer")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data")

    class Meta:
        verbose_name = "Aprovação"
        verbose_name_plural = "Aprovações"
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.ticket_id} — {self.get_decision_display()}"

    @property
    def is_approved(self):
        return self.decision == self.DECISION_APPROVED


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
