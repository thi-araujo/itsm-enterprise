"""Regras de negócio do atendimento, independentes de transporte (Fase 3.5).

Aqui ficam as operações que mudam o estado de um chamado: finalizar,
escalonar e decidir uma aprovação.

**Por que existe este módulo.** As mesmas regras precisam valer na tela HTML
e na API REST. Se cada uma tivesse a sua cópia, no dia em que o mínimo da
solução mudasse de 10 para 20 caracteres alguém mudaria num lugar e
esqueceria o outro. Aqui há uma implementação; a view cuida de `messages` e
`redirect`, e a API cuida de JSON e código HTTP.

As funções levantam `django.core.exceptions.ValidationError` quando a regra
é violada. Cada camada traduz: a view vira `messages.error`, o DRF vira
HTTP 400 com a mesma mensagem.
"""

import logging

from django.core.exceptions import ValidationError

from .models import Approval, AuditLog, Comment, Escalation

logger = logging.getLogger(__name__)

# Mínimo de caracteres dos textos livres. Fonte única: o form e a API leem
# daqui, como a política de upload lê do settings.
MIN_SOLUTION_LENGTH = 10
MIN_REASON_LENGTH   = 10

ERRO_SOLUCAO_CURTA = (
    'Descreva a solução com pelo menos 10 caracteres — '
    'ela vai para o solicitante e fica no histórico do chamado.')
ERRO_MOTIVO_CURTO = (
    'Explique o motivo com pelo menos 10 caracteres — '
    'quem receber o chamado precisa entender o contexto.')
ERRO_REJEICAO_CURTA = (
    'Explique o motivo da rejeição com pelo menos 10 caracteres — '
    'o solicitante precisa saber por que o pedido foi negado.')


def _notificar(funcao, *args, acao=''):
    """Executa uma notificação sem deixar a falha derrubar a operação.

    Um chamado não pode deixar de ser finalizado porque o servidor de SMTP
    está fora do ar — mas a falha tem de aparecer no log.
    """
    try:
        funcao(*args)
    except Exception:
        logger.exception('Falha ao notificar %s', acao or funcao.__name__)


# ══════════════════════════════════════════════════════════════════
# Finalizar (Fase 3.2)
# ══════════════════════════════════════════════════════════════════


def finalizar_chamado(ticket, user, solution):
    """Finaliza o chamado exigindo a solução.

    Leva a "Resolvido", não a "Fechado": no ITIL quem fecha é o solicitante,
    depois de confirmar. "Resolvido" significa "o técnico terminou,
    aguardando confirmação".
    """
    from apps.notifications.email import notify_ticket_resolved

    if not ticket.can_be_finished:
        raise ValidationError('Este chamado já está resolvido ou fechado.')

    solution = (solution or '').strip()
    if len(solution) < MIN_SOLUTION_LENGTH:
        raise ValidationError({'solution': ERRO_SOLUCAO_CURTA})

    ticket.solution    = solution
    ticket.status      = 'resolved'
    ticket.resolved_by = user
    # resolved_at é preenchido pelo save() do model quando o status vira
    # 'resolved' — não repetir aqui.
    ticket.save_as(user)

    # A solução também entra no histórico como comentário público, para o
    # solicitante ler na mesma linha do tempo dos outros comentários.
    Comment.objects.create(
        ticket=ticket, author=user, is_internal=False,
        content=f"Chamado finalizado.\n\nSolução: {ticket.solution}",
    )

    _notificar(notify_ticket_resolved, ticket, acao=f'resolução do ticket #{ticket.pk}')
    return ticket


# ══════════════════════════════════════════════════════════════════
# Escalonar (Fase 3.2)
# ══════════════════════════════════════════════════════════════════


def escalonar_chamado(ticket, user, to_user, reason):
    """Repassa o chamado a outro membro da equipe, com motivo registrado.

    Quem valida se `to_user` pode receber é a camada de cima (o queryset do
    form, ou o serializer), porque é lá que está a lista de opções oferecida
    ao usuário.
    """
    from apps.notifications.email import notify_ticket_escalated

    if not ticket.can_be_escalated:
        raise ValidationError('Chamado resolvido ou fechado não pode ser escalonado.')

    reason = (reason or '').strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise ValidationError({'reason': ERRO_MOTIVO_CURTO})

    escalation = Escalation.objects.create(
        ticket=ticket, from_user=user, to_user=to_user, reason=reason)

    ticket.assignee = to_user
    # Um chamado escalonado está em atendimento, não mais só "aberto".
    if ticket.status == 'open':
        ticket.status = 'in_progress'
    ticket.save_as(user)

    # A troca de responsável e de status já é auditada pelo save(); esta
    # entrada registra o evento em si, com o destino.
    destino = to_user.get_full_name() or to_user.username
    AuditLog.registrar(ticket, user, AuditLog.ACTION_ESCALATED, f'para {destino}')

    _notificar(notify_ticket_escalated, escalation,
               acao=f'escalonamento do ticket #{ticket.pk}')
    return escalation


# ══════════════════════════════════════════════════════════════════
# Aprovação (Fase 3.3)
# ══════════════════════════════════════════════════════════════════


def decidir_aprovacao(ticket, user, decision, comment=''):
    """Registra a decisão do gerente sobre um chamado em aprovação.

    Aprovar libera para a fila e inicia a contagem do SLA; rejeitar encerra o
    chamado. O parecer é opcional ao aprovar e obrigatório ao rejeitar: negar
    um pedido sem dizer por que deixa o solicitante sem saber o que fazer.
    """
    from apps.notifications.email import notify_approval_decided

    if decision not in (Approval.DECISION_APPROVED, Approval.DECISION_REJECTED):
        raise ValidationError({'decision': 'Decisão inválida.'})

    # Impede decidir duas vezes, ou decidir um chamado que nunca precisou de
    # aprovação (um POST direto na URL, por exemplo).
    if not ticket.is_awaiting_approval:
        raise ValidationError('Este chamado não está aguardando aprovação.')

    comment = (comment or '').strip()
    aprovado = decision == Approval.DECISION_APPROVED
    if not aprovado and len(comment) < MIN_REASON_LENGTH:
        raise ValidationError({'comment': ERRO_REJEICAO_CURTA})

    approval = Approval.objects.create(
        ticket=ticket, decided_by=user, decision=decision, comment=comment)

    if aprovado:
        ticket.status = 'open'
        # O relógio do SLA começa AGORA, não na abertura: o chamado ficou
        # parado esperando uma decisão que não era do solicitante nem da
        # equipe. Ver Ticket.start_sla.
        ticket.start_sla()
    else:
        ticket.status = 'rejected'
    ticket.save_as(user)

    AuditLog.registrar(
        ticket, user,
        AuditLog.ACTION_APPROVED if aprovado else AuditLog.ACTION_REJECTED,
        comment[:200])

    # O parecer também entra na linha do tempo, como comentário público: é
    # informação que o solicitante pode ver.
    if comment:
        rotulo = 'Aprovação' if aprovado else 'Rejeição'
        Comment.objects.create(
            ticket=ticket, author=user, is_internal=False,
            content=f"{rotulo} do chamado.\n\n{comment}",
        )

    _notificar(notify_approval_decided, approval,
               acao=f'decisão de aprovação do ticket #{ticket.pk}')
    return approval


# ══════════════════════════════════════════════════════════════════
# Comentário
# ══════════════════════════════════════════════════════════════════


def comentar_chamado(ticket, user, content, is_internal=False):
    """Registra um comentário. Solicitante nunca cria nota interna."""
    from apps.notifications.email import notify_comment_added

    content = (content or '').strip()
    if not content:
        raise ValidationError({'content': 'O comentário não pode ficar vazio.'})

    # A regra não confia no formulário nem no JSON: quem não pode ver nota
    # interna também não pode criar uma, mesmo forjando a requisição.
    if not user.profile.can_see_internal_notes:
        is_internal = False

    comment = Comment.objects.create(
        ticket=ticket, author=user, content=content, is_internal=is_internal)

    AuditLog.registrar(ticket, user, AuditLog.ACTION_COMMENTED,
                       'nota interna' if comment.is_internal else '')
    _notificar(notify_comment_added, comment,
               acao=f'comentário no ticket #{ticket.pk}')
    return comment
