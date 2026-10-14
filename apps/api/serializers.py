"""Serializers da API REST (Fase 3.5).

Convenção adotada: os relacionamentos aparecem **expandidos na leitura**
(`requester` vira um objeto com id, username e nome) e são **escritos por
id** (`assignee_id`). Assim quem consome a API não precisa de uma segunda
requisição só para descobrir o nome de quem abriu o chamado.
"""

from django.contrib.auth.models import User
from rest_framework import serializers

from apps.accounts.models import UserProfile
from apps.cmdb.models import Asset, AssetType
from apps.tickets.models import (Approval, AuditLog, Attachment, Category,
                                 Comment, Escalation, Ticket)


class UserMiniSerializer(serializers.ModelSerializer):
    """Usuário reduzido ao que interessa a quem consome a API."""

    nome  = serializers.SerializerMethodField()
    papel = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'username', 'nome', 'papel']

    def get_nome(self, user):
        return user.get_full_name() or user.username

    def get_papel(self, user):
        perfil = getattr(user, 'profile', None)
        return perfil.get_role_display() if perfil else None


class EuSerializer(serializers.ModelSerializer):
    """`/api/v1/eu/` — quem sou eu, meu papel e o que posso fazer.

    Existe para o cliente da API não ter de adivinhar as permissões: ele
    pergunta uma vez e já sabe quais telas montar.
    """

    nome         = serializers.SerializerMethodField()
    papel        = serializers.CharField(source='profile.role', read_only=True)
    papel_nome   = serializers.CharField(source='profile.get_role_display', read_only=True)
    departamento = serializers.CharField(source='profile.department', read_only=True)
    permissoes   = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'username', 'nome', 'email', 'papel', 'papel_nome',
                  'departamento', 'permissoes']

    def get_nome(self, user):
        return user.get_full_name() or user.username

    def get_permissoes(self, user):
        perfil = user.profile
        return {
            'ver_todos_chamados': perfil.can_see_all_tickets,
            'ver_fila':           perfil.can_see_queue,
            'ver_cmdb':           perfil.can_see_cmdb,
            'ver_notas_internas': perfil.can_see_internal_notes,
            'gerenciar_chamados': perfil.can_manage_tickets,
            'ver_relatorios':     perfil.can_see_reports,
            'aprovar':            perfil.can_approve,
        }


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ['id', 'name', 'description', 'icon', 'requires_approval']


class AssetTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AssetType
        fields = ['id', 'name']


class AssetSerializer(serializers.ModelSerializer):
    asset_type = AssetTypeSerializer(read_only=True)

    class Meta:
        model  = Asset
        fields = '__all__'


class CommentSerializer(serializers.ModelSerializer):
    author = UserMiniSerializer(read_only=True)

    class Meta:
        model  = Comment
        fields = ['id', 'author', 'content', 'is_internal', 'created_at']
        read_only_fields = ['author', 'created_at']


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserMiniSerializer(read_only=True)
    tamanho     = serializers.CharField(source='file_size_display', read_only=True)

    class Meta:
        model  = Attachment
        fields = ['id', 'filename', 'file_size', 'tamanho', 'uploaded_by', 'created_at']


class EscalationSerializer(serializers.ModelSerializer):
    from_user = UserMiniSerializer(read_only=True)
    to_user   = UserMiniSerializer(read_only=True)

    class Meta:
        model  = Escalation
        fields = ['id', 'from_user', 'to_user', 'reason', 'created_at']


class ApprovalSerializer(serializers.ModelSerializer):
    decided_by = UserMiniSerializer(read_only=True)

    class Meta:
        model  = Approval
        fields = ['id', 'decision', 'comment', 'decided_by', 'created_at']


class AuditLogSerializer(serializers.ModelSerializer):
    autor   = serializers.CharField(source='author_display', read_only=True)
    resumo  = serializers.CharField(source='summary', read_only=True)

    class Meta:
        model  = AuditLog
        fields = ['id', 'action', 'autor', 'resumo', 'field',
                  'old_value', 'new_value', 'description', 'created_at']


# ══════════════════════════════════════════════════════════════════
# Chamados
# ══════════════════════════════════════════════════════════════════


class TicketListSerializer(serializers.ModelSerializer):
    """Versão enxuta para a listagem — sem descrição nem solução."""

    requester     = UserMiniSerializer(read_only=True)
    assignee      = UserMiniSerializer(read_only=True)
    category      = CategorySerializer(read_only=True)
    status_nome   = serializers.CharField(source='get_status_display', read_only=True)
    priority_nome = serializers.CharField(source='get_priority_display', read_only=True)
    sla_vencido   = serializers.BooleanField(source='is_sla_breached', read_only=True)
    sla_percentual = serializers.IntegerField(source='sla_elapsed_percent', read_only=True)

    class Meta:
        model  = Ticket
        fields = ['id', 'title', 'ticket_type', 'status', 'status_nome',
                  'priority', 'priority_nome', 'requester', 'assignee',
                  'category', 'sla_deadline', 'sla_vencido', 'sla_percentual',
                  'created_at', 'updated_at']


class TicketSerializer(serializers.ModelSerializer):
    """Detalhe e escrita.

    Status, técnico e prioridade são graváveis, mas o `ReadOnlyOrStaff` já
    barra o solicitante antes de chegar aqui. Os campos de workflow
    (aguardando aprovação, rejeitado) saem das opções de status: são
    definidos pelas ações de aprovação, não por um PATCH — a mesma regra do
    formulário HTML, lendo a mesma constante.
    """

    requester   = UserMiniSerializer(read_only=True)
    assignee    = UserMiniSerializer(read_only=True)
    resolved_by = UserMiniSerializer(read_only=True)
    category    = CategorySerializer(read_only=True)

    # Escrita por id, leitura expandida acima.
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category',
        write_only=True, required=False, allow_null=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(profile__role__in=UserProfile.STAFF_ROLES),
        source='assignee', write_only=True, required=False, allow_null=True)

    status_nome    = serializers.CharField(source='get_status_display', read_only=True)
    priority_nome  = serializers.CharField(source='get_priority_display', read_only=True)
    tipo_nome      = serializers.CharField(source='get_ticket_type_display', read_only=True)
    sla_vencido    = serializers.BooleanField(source='is_sla_breached', read_only=True)
    sla_percentual = serializers.IntegerField(source='sla_elapsed_percent', read_only=True)
    sla_horas_restantes = serializers.IntegerField(source='sla_remaining_hours', read_only=True)
    sla_em_risco   = serializers.BooleanField(source='sla_at_risk', read_only=True)
    pode_finalizar = serializers.BooleanField(source='can_be_finished', read_only=True)
    aguardando_aprovacao = serializers.BooleanField(source='is_awaiting_approval',
                                                    read_only=True)

    class Meta:
        model  = Ticket
        fields = [
            'id', 'title', 'description', 'ticket_type', 'tipo_nome',
            'status', 'status_nome', 'priority', 'priority_nome',
            'requester', 'assignee', 'assignee_id',
            'category', 'category_id',
            'solution', 'resolved_by',
            'sla_started_at', 'sla_deadline', 'sla_vencido', 'sla_percentual',
            'sla_horas_restantes', 'sla_em_risco', 'sla_escalated_at',
            'pode_finalizar', 'aguardando_aprovacao',
            'created_at', 'updated_at', 'resolved_at', 'closed_at',
        ]
        read_only_fields = [
            'requester', 'solution', 'resolved_by',
            'sla_started_at', 'sla_deadline', 'sla_escalated_at',
            'created_at', 'updated_at', 'resolved_at', 'closed_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mesma regra do TicketUpdateForm: o DRF valida contra as choices,
        # então tirar as opções daqui já recusa um PATCH forjado.
        self.fields['status'].choices = {
            valor: rotulo for valor, rotulo in Ticket.STATUS_CHOICES
            if valor not in Ticket.WORKFLOW_STATUSES
        }


class TicketCreateSerializer(serializers.ModelSerializer):
    """Abertura de chamado. O solicitante não escolhe status nem técnico.

    O `requester` vem do usuário autenticado, e o status inicial é decidido
    pela view (uma categoria que exige aprovação faz o chamado nascer
    aguardando o gerente — Fase 3.3).
    """

    class Meta:
        model  = Ticket
        fields = ['id', 'title', 'description', 'ticket_type', 'priority',
                  'category', 'asset']

    def validate_title(self, title):
        if len(title.strip()) < 5:
            raise serializers.ValidationError(
                'O título precisa ter pelo menos 5 caracteres.')
        return title.strip()


# ══════════════════════════════════════════════════════════════════
# Ações (os corpos dos POST). Validam formato; a regra está em services.py
# ══════════════════════════════════════════════════════════════════


class FinalizarSerializer(serializers.Serializer):
    solution = serializers.CharField(label='Solução')


class EscalonarSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(profile__role__in=UserProfile.STAFF_ROLES),
        label='Escalonar para')
    reason = serializers.CharField(label='Motivo')

    def validate_to_user(self, to_user):
        # Escalonar para si mesmo não faz sentido. No HTML o próprio usuário
        # sai do <select>; aqui a checagem é explícita.
        if to_user == self.context['request'].user:
            raise serializers.ValidationError(
                'Não é possível escalonar o chamado para você mesmo.')
        return to_user


class DecidirSerializer(serializers.Serializer):
    comment = serializers.CharField(label='Parecer', required=False,
                                    allow_blank=True, default='')
