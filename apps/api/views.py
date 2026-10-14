"""ViewSets da API REST (Fase 3.5).

Duas ideias organizam este arquivo:

1. **O RBAC vem do queryset.** `Ticket.objects.visible_to(user)`, escrito na
   Fase 3.1 para as telas, passa a valer na API sem uma linha nova de regra.
   Chamado alheio devolve **404** (e não 403), como no HTML: um 403
   confirmaria que o chamado existe.

2. **As regras de negócio vêm de services.py.** Finalizar, escalonar,
   aprovar e comentar chamam as mesmas funções que as views HTML. A API só
   traduz `ValidationError` em HTTP 400 com a mesma mensagem que aparece na
   tela.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.accounts.models import UserProfile
from apps.cmdb.models import Asset
from apps.tickets import services
from apps.tickets.models import Approval, Category, Ticket

from .permissions import IsManagement, IsStaff, ReadOnlyOrStaff
from .serializers import (ApprovalSerializer, AssetSerializer,
                          AttachmentSerializer, AuditLogSerializer,
                          CategorySerializer, CommentSerializer,
                          DecidirSerializer, EscalationSerializer,
                          EscalonarSerializer, EuSerializer,
                          FinalizarSerializer, TicketCreateSerializer,
                          TicketListSerializer, TicketSerializer,
                          UserMiniSerializer)


def _erro_de_validacao(erro):
    """Traduz um ValidationError do Django para o corpo de erro do DRF.

    As regras em services.py levantam o ValidationError do Django (que serve
    para views e para models), não o do DRF. Aqui o formato é ajustado para
    a resposta JSON sair igual à de qualquer outro erro da API.
    """
    if hasattr(erro, 'message_dict'):
        detalhe = erro.message_dict
    else:
        detalhe = {'detail': erro.messages}
    return Response(detalhe, status=status.HTTP_400_BAD_REQUEST)


class TicketViewSet(viewsets.ModelViewSet):
    """Chamados.

    Lista e detalhe respeitam o perfil de acesso; escrita exige equipe.
    """

    permission_classes = [IsAuthenticated, ReadOnlyOrStaff]
    filter_backends    = [SearchFilter, OrderingFilter]
    search_fields      = ['title', 'description', 'id']
    ordering_fields    = ['created_at', 'updated_at', 'priority', 'status',
                          'sla_deadline']
    ordering           = ['-created_at']
    http_method_names  = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        # É aqui que o RBAC da Fase 3.1 entra na API, de graça.
        queryset = (Ticket.objects.visible_to(self.request.user)
                    .select_related('requester', 'assignee', 'category',
                                    'resolved_by'))

        parametros = self.request.query_params
        if parametros.get('status'):
            queryset = queryset.filter(status=parametros['status'])
        if parametros.get('priority'):
            queryset = queryset.filter(priority=parametros['priority'])

        assignee = parametros.get('assignee')
        if assignee == 'me':
            queryset = queryset.filter(assignee=self.request.user)
        elif assignee == 'unassigned':
            queryset = queryset.filter(assignee__isnull=True)
        elif assignee:
            queryset = queryset.filter(assignee_id=assignee)

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return TicketListSerializer
        if self.action == 'create':
            return TicketCreateSerializer
        return TicketSerializer

    # ── Abertura ──────────────────────────────────────────────────

    def create(self, request, *args, **kwargs):
        """Abre o chamado. Qualquer autenticado pode — inclusive solicitante.

        O `ReadOnlyOrStaff` barraria o POST, então a permissão é relaxada
        só aqui: abrir chamado é o que o solicitante mais faz.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Monta a instância sem salvar para decidir o status ANTES do save():
        #
        # 1. o save() do model só deixa o SLA nulo se o chamado já nascer
        #    'pending_approval' (Fase 3.3) — corrigir depois exigiria limpar
        #    o prazo na mão;
        # 2. `save_as` registra o autor na trilha de auditoria (Fase 3.4).
        #    Com `serializer.save()` o INSERT aconteceria sem autor e a
        #    entrada "Abriu o chamado" sairia como "Sistema".
        ticket = Ticket(requester=request.user, **serializer.validated_data)
        precisa_aprovacao = bool(ticket.category and ticket.category.requires_approval)
        if precisa_aprovacao:
            ticket.status = 'pending_approval'
        ticket.save_as(request.user)

        from apps.notifications.email import (notify_approval_requested,
                                              notify_ticket_created)
        services._notificar(
            notify_approval_requested if precisa_aprovacao else notify_ticket_created,
            ticket, acao=f'criação do ticket #{ticket.pk}')

        saida = TicketSerializer(ticket, context=self.get_serializer_context())
        return Response(saida.data, status=status.HTTP_201_CREATED)

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        return super().get_permissions()

    def perform_update(self, serializer):
        # O autor vai na instância antes do save() do serializer: é esse
        # save que grava, e a trilha de auditoria (Fase 3.4) lê o
        # `_audit_user` de lá. Chamar save_as() depois não ajudaria — nessa
        # altura o campo já mudou e a entrada sairia como "Sistema".
        serializer.instance._audit_user = self.request.user
        serializer.save()

    # ── Ações do fluxo de atendimento (Fase 3.2) ──────────────────

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsStaff])
    def finalizar(self, request, pk=None):
        """Finaliza o chamado. Exige a solução (mínimo 10 caracteres)."""
        ticket = self.get_object()
        entrada = FinalizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.finalizar_chamado(ticket, request.user,
                                       entrada.validated_data['solution'])
        except DjangoValidationError as erro:
            return _erro_de_validacao(erro)
        return Response(TicketSerializer(ticket, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsStaff])
    def escalonar(self, request, pk=None):
        """Repassa o chamado a outro membro da equipe, com motivo."""
        ticket = self.get_object()
        entrada = EscalonarSerializer(data=request.data,
                                      context=self.get_serializer_context())
        entrada.is_valid(raise_exception=True)
        try:
            escalation = services.escalonar_chamado(
                ticket, request.user,
                entrada.validated_data['to_user'],
                entrada.validated_data['reason'])
        except DjangoValidationError as erro:
            return _erro_de_validacao(erro)
        return Response(EscalationSerializer(escalation).data,
                        status=status.HTTP_201_CREATED)

    # ── Workflow de aprovação (Fase 3.3) ──────────────────────────

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticated, IsManagement])
    def aprovar(self, request, pk=None):
        """Aprova o chamado: libera para a fila e inicia a contagem do SLA."""
        return self._decidir(request, Approval.DECISION_APPROVED)

    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticated, IsManagement])
    def rejeitar(self, request, pk=None):
        """Rejeita o chamado. O motivo é obrigatório."""
        return self._decidir(request, Approval.DECISION_REJECTED)

    def _decidir(self, request, decision):
        ticket = self.get_object()
        entrada = DecidirSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            approval = services.decidir_aprovacao(
                ticket, request.user, decision,
                entrada.validated_data.get('comment', ''))
        except DjangoValidationError as erro:
            return _erro_de_validacao(erro)
        return Response(ApprovalSerializer(approval).data,
                        status=status.HTTP_201_CREATED)

    # ── Sub-recursos ──────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'], url_path='comentarios',
            permission_classes=[IsAuthenticated])
    def comentarios(self, request, pk=None):
        """Comentários do chamado.

        As notas internas saem do QUERYSET, não da serialização: filtrar
        depois deixaria o texto trafegar até aqui sem necessidade.
        """
        ticket = self.get_object()

        if request.method == 'POST':
            entrada = CommentSerializer(data=request.data)
            entrada.is_valid(raise_exception=True)
            try:
                # services força is_internal=False para quem não pode criar
                # nota interna, mesmo que o JSON peça True.
                comment = services.comentar_chamado(
                    ticket, request.user,
                    entrada.validated_data['content'],
                    entrada.validated_data.get('is_internal', False))
            except DjangoValidationError as erro:
                return _erro_de_validacao(erro)
            return Response(CommentSerializer(comment).data,
                            status=status.HTTP_201_CREATED)

        comments = ticket.comments.select_related('author', 'author__profile')
        if not request.user.profile.can_see_internal_notes:
            comments = comments.filter(is_internal=False)
        return Response(CommentSerializer(comments, many=True).data)

    @action(detail=True, methods=['get'])
    def anexos(self, request, pk=None):
        ticket = self.get_object()
        anexos = ticket.attachments.select_related('uploaded_by')
        return Response(AttachmentSerializer(anexos, many=True).data)

    @action(detail=True, methods=['get'], url_path='escalonamentos',
            permission_classes=[IsAuthenticated, IsStaff])
    def escalonamentos(self, request, pk=None):
        """Histórico de escalonamentos — interno da equipe (Fase 3.2)."""
        ticket = self.get_object()
        registros = ticket.escalations.select_related('from_user', 'to_user')
        return Response(EscalationSerializer(registros, many=True).data)

    @action(detail=True, methods=['get'],
            permission_classes=[IsAuthenticated, IsStaff])
    def auditoria(self, request, pk=None):
        """Trilha de auditoria — interna da equipe (Fase 3.4)."""
        ticket = self.get_object()
        registros = ticket.audit_logs.select_related('user')
        return Response(AuditLogSerializer(registros, many=True).data)

    @action(detail=True, methods=['get'], url_path='aprovacoes')
    def aprovacoes(self, request, pk=None):
        """Decisões de aprovação. O parecer é visível ao solicitante."""
        ticket = self.get_object()
        return Response(ApprovalSerializer(ticket.approvals.all(), many=True).data)


class CategoryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """Categorias — somente leitura. Alterar é tarefa do /admin/."""

    queryset           = Category.objects.all()
    serializer_class   = CategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None


class AssetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    """Ativos do CMDB — somente a equipe, como na tela."""

    queryset           = Asset.objects.select_related('asset_type')
    serializer_class   = AssetSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    filter_backends    = [SearchFilter, OrderingFilter]
    search_fields      = ['name', 'asset_tag', 'serial', 'ip_address']
    ordering           = ['name']


class TecnicoViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Quem pode receber chamados — para montar um seletor de técnico."""

    serializer_class   = UserMiniSerializer
    permission_classes = [IsAuthenticated, IsStaff]
    pagination_class   = None

    def get_queryset(self):
        return (User.objects
                .filter(profile__role__in=UserProfile.STAFF_ROLES)
                .select_related('profile').order_by('username'))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def eu(request):
    """`/api/v1/eu/` — identidade e permissões de quem está autenticado."""
    return Response(EuSerializer(request.user).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estatisticas(request):
    """Números agregados, já respeitando o perfil de acesso.

    O solicitante recebe os números dos próprios chamados; a equipe, de
    todos. Serve ao dashboard (e é o que a Fase 3.6 vai consumir, em vez de
    repetir essas contas no template).

    Aceita `?days=N` para recortar por período.
    """
    tickets = Ticket.objects.visible_to(request.user)

    dias = request.query_params.get('days')
    if dias:
        try:
            desde = timezone.now() - timezone.timedelta(days=int(dias))
            tickets = tickets.filter(created_at__gte=desde)
        except (TypeError, ValueError):
            return Response({'days': ['Informe um número inteiro de dias.']},
                            status=status.HTTP_400_BAD_REQUEST)

    agora = timezone.now()
    por_status = {item['status']: item['count']
                  for item in tickets.values('status').annotate(count=Count('id'))}
    por_prioridade = {item['priority']: item['count']
                      for item in tickets.values('priority').annotate(count=Count('id'))}

    abertos = tickets.exclude(status__in=Ticket.CLOSED_STATUSES)

    return Response({
        'total':            tickets.count(),
        'por_status':       por_status,
        'por_prioridade':   por_prioridade,
        'em_aberto':        abertos.count(),
        'sem_tecnico':      abertos.filter(assignee__isnull=True).count(),
        'sla_vencido':      abertos.filter(sla_deadline__lt=agora).count(),
        'aguardando_aprovacao': tickets.filter(status='pending_approval').count(),
        'por_categoria': list(
            tickets.exclude(category__isnull=True)
                   .values('category__name')
                   .annotate(count=Count('id')).order_by('-count')[:6]),
        'por_tecnico': list(
            tickets.exclude(assignee__isnull=True)
                   .values('assignee__username')
                   .annotate(count=Count('id')).order_by('-count')[:10]),
    })
