"""Automações de SLA (Fase 3.7).

A lógica vive aqui, e não dentro do comando `check_sla`, por dois motivos:
os testes exercitam as funções direto, sem precisar rodar o comando; e mais
tarde a API ou um agendador de verdade podem chamar as mesmas funções.
Comando de management com regra de negócio dentro só dá para testar por fora.

Toda ação automática é registrada com autor nulo, o que a trilha de
auditoria (Fase 3.4) mostra como **"Sistema"**.

Os limites vêm do settings (`SLA_WARNING_PERCENT`, `SLA_AUTO_ESCALATE`) —
nenhum número cravado aqui.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import UserProfile
from .models import AuditLog, Escalation, Ticket

logger = logging.getLogger(__name__)


def _ativos():
    """Chamados que ainda contam SLA: nem encerrados, nem sem prazo.

    Chamado aguardando aprovação tem `sla_deadline` nulo (o relógio só começa
    na aprovação), então o filtro do prazo já o deixa de fora.
    """
    return (Ticket.objects
            .exclude(status__in=Ticket.CLOSED_STATUSES)
            .filter(sla_deadline__isnull=False))


# ══════════════════════════════════════════════════════════════════
# 1. Aviso prévio — antes de vencer
# ══════════════════════════════════════════════════════════════════


def tickets_em_risco():
    """Chamados que passaram do limite de aviso e ainda não venceram."""
    agora = timezone.now()
    candidatos = (_ativos()
                  .filter(sla_warning_notified=False, sla_deadline__gt=agora)
                  .select_related('requester', 'assignee'))
    # O percentual depende de sla_started_at e precisa ser calculado em
    # Python: é uma razão entre dois intervalos, não um filtro simples.
    return [t for t in candidatos if t.sla_at_risk]


def avisar_sla_proximo(dry_run=False):
    """Manda o aviso prévio e devolve a lista de chamados avisados."""
    from apps.notifications.email import notify_sla_warning

    avisados = []
    for ticket in tickets_em_risco():
        if not dry_run:
            try:
                notify_sla_warning(ticket)
            except Exception:
                logger.exception('Falha ao avisar SLA em risco do ticket #%s', ticket.pk)
            # A marca é gravada mesmo se a notificação falhar: o erro já foi
            # para o log e reenviar a cada 15 minutos não resolveria nada.
            #
            # `update()` em vez de save(): é campo de controle interno, não
            # muda nada que interesse à trilha de auditoria — e o update()
            # não passa pelo save(), então não gera entrada (ver Fase 3.4).
            Ticket.objects.filter(pk=ticket.pk).update(sla_warning_notified=True)
        avisados.append(ticket)
    return avisados


# ══════════════════════════════════════════════════════════════════
# 2. Notificação de vencimento — o que o comando já fazia
# ══════════════════════════════════════════════════════════════════


def tickets_vencidos_sem_aviso():
    return list(_ativos()
                .filter(sla_deadline__lt=timezone.now(), sla_breach_notified=False)
                .select_related('requester', 'assignee'))


def notificar_sla_vencido(dry_run=False):
    """Avisa a equipe dos SLAs estourados. `notify_sla_breach` já marca o
    `sla_breach_notified`."""
    from apps.notifications.email import notify_sla_breach

    notificados = []
    for ticket in tickets_vencidos_sem_aviso():
        if not dry_run:
            try:
                notify_sla_breach(ticket)
            except Exception:
                logger.exception('Falha ao notificar SLA vencido do ticket #%s', ticket.pk)
        notificados.append(ticket)
    return notificados


# ══════════════════════════════════════════════════════════════════
# 3. Escalonamento automático — agir depois de vencer
# ══════════════════════════════════════════════════════════════════


def _gerente_com_menos_carga():
    """O gerente ou admin com menos chamados ativos atribuídos.

    Pegar sempre o primeiro da lista empilharia tudo na mesma pessoa. O
    desempate é pelo username, para o resultado ser determinístico (e os
    testes, previsíveis).
    """
    return (User.objects
            .filter(profile__role__in=UserProfile.MANAGEMENT_ROLES)
            .annotate(carga=Count('assigned_tickets',
                                  filter=~Q(assigned_tickets__status__in=Ticket.CLOSED_STATUSES)))
            .order_by('carga', 'username')
            .first())


def tickets_para_escalonar():
    """Vencidos que ainda não foram escalonados automaticamente."""
    return list(_ativos()
                .filter(sla_deadline__lt=timezone.now(), sla_escalated_at__isnull=True)
                .select_related('assignee', 'assignee__profile'))


def escalonar_sla_vencido(dry_run=False):
    """Repassa o chamado vencido a um gerente — "subir um nível" do ITIL.

    Devolve a lista de (ticket, destino), com `destino` nulo quando o chamado
    foi apenas marcado sem troca de responsável.

    A prioridade NÃO é alterada de propósito: ela é o que define o prazo, e
    mexer nela depois do vencimento apagaria a evidência de que o SLA foi
    furado e distorceria os relatórios.
    """
    from apps.notifications.email import notify_ticket_escalated

    if not settings.SLA_AUTO_ESCALATE:
        return []

    resultado = []
    for ticket in tickets_para_escalonar():
        # Já está com um gerente: repassar de gerente para gerente é ruído.
        perfil_atual = getattr(ticket.assignee, 'profile', None)
        if perfil_atual is not None and perfil_atual.can_approve:
            if not dry_run:
                Ticket.objects.filter(pk=ticket.pk).update(sla_escalated_at=timezone.now())
                AuditLog.registrar(
                    ticket, None, AuditLog.ACTION_ESCALATED,
                    'SLA vencido — chamado já estava com a gerência')
            resultado.append((ticket, None))
            continue

        destino = _gerente_com_menos_carga()
        if destino is None:
            # Nenhum gerente cadastrado: registra e segue, sem estourar.
            logger.warning(
                'SLA vencido no ticket #%s, mas não há gerente para escalonar.',
                ticket.pk)
            resultado.append((ticket, None))
            continue

        if not dry_run:
            vencimento = timezone.localtime(ticket.sla_deadline).strftime('%d/%m/%Y %H:%M')
            escalation = Escalation.objects.create(
                ticket=ticket,
                from_user=None,          # "Sistema" na tela
                to_user=destino,
                reason=(f'Escalonamento automático: SLA vencido em {vencimento}. '
                        f'Prioridade {ticket.get_priority_display()}.'),
            )
            ticket.assignee = destino
            ticket.sla_escalated_at = timezone.now()
            # save() sem save_as: a auditoria registra a troca de responsável
            # com autor nulo, que a tela mostra como "Sistema".
            ticket.save()
            AuditLog.registrar(
                ticket, None, AuditLog.ACTION_ESCALATED,
                f'SLA vencido — para {destino.get_full_name() or destino.username}')
            try:
                notify_ticket_escalated(escalation)
            except Exception:
                logger.exception('Falha ao notificar escalonamento automático do #%s',
                                 ticket.pk)

        resultado.append((ticket, destino))
    return resultado


# ══════════════════════════════════════════════════════════════════


def executar_automacoes(dry_run=False):
    """Roda as três automações na ordem e devolve o resumo.

    A ordem importa: avisar antes de notificar o vencimento evita mandar
    "está acabando" depois de "já venceu".
    """
    return {
        'avisados':    avisar_sla_proximo(dry_run=dry_run),
        'vencidos':    notificar_sla_vencido(dry_run=dry_run),
        'escalonados': escalonar_sla_vencido(dry_run=dry_run),
    }
