import logging

from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from apps.accounts.models import UserProfile
from .models import Notification


def _equipe():
    """Usuários que recebem avisos de chamado: técnico, gerente e admin."""
    return User.objects.filter(profile__role__in=UserProfile.STAFF_ROLES)


def _aprovadores():
    """Quem decide as aprovações: gerente e admin (ver UserProfile.can_approve)."""
    return User.objects.filter(profile__role__in=UserProfile.MANAGEMENT_ROLES)

logger = logging.getLogger(__name__)


def _create_notification(user, ntype, title, message, ticket_id=None):
    Notification.objects.create(
        user=user, type=ntype, title=title,
        message=message, ticket_id=ticket_id
    )


def _send_email(subject, body, recipients):
    """Envia um e-mail sem deixar que uma falha interrompa o fluxo do ticket.

    A exceção é registrada no log, nunca propagada: criar um chamado não pode
    falhar porque o servidor de e-mail está fora do ar.
    """
    if not recipients:
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            # fail_silently=False de propósito. Com True, o Django engole os
            # erros de SMTP antes do except abaixo e a falha não deixa rastro
            # nenhum — perigoso quando apontarmos para o SMTP real.
            fail_silently=False,
        )
    except Exception:
        logger.exception('Falha ao enviar e-mail "%s" para %s', subject, recipients)


def notify_ticket_created(ticket):
    emails = list(_equipe().exclude(email='').values_list('email', flat=True))
    subject = f"[ITSM Enterprise] Novo Ticket #{ticket.pk:04d} — {ticket.get_priority_display()}"
    body = (
        f"Um novo ticket foi aberto.\n\n"
        f"  ID:          #{ticket.pk:04d}\n"
        f"  Título:      {ticket.title}\n"
        f"  Tipo:        {ticket.get_ticket_type_display()}\n"
        f"  Prioridade:  {ticket.get_priority_display()}\n"
        f"  Solicitante: {ticket.requester.get_full_name() or ticket.requester.username}\n"
        f"  SLA:         {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M') if ticket.sla_deadline else '—'}\n\n"
        f"Descrição:\n{ticket.description}\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    _send_email(subject, body, emails)
    for membro in _equipe():
        _create_notification(
            membro, 'ticket_created',
            f"Novo ticket #{ticket.pk:04d}: {ticket.title[:60]}",
            body, ticket_id=ticket.pk
        )


def notify_ticket_assigned(ticket):
    if not ticket.assignee:
        return
    subject = f"[ITSM Enterprise] Ticket #{ticket.pk:04d} atribuído a você"
    body = (
        f"Olá, {ticket.assignee.get_full_name() or ticket.assignee.username}!\n\n"
        f"O ticket abaixo foi atribuído a você:\n\n"
        f"  ID:         #{ticket.pk:04d}\n"
        f"  Título:     {ticket.title}\n"
        f"  Prioridade: {ticket.get_priority_display()}\n"
        f"  SLA:        {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M') if ticket.sla_deadline else '—'}\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [ticket.assignee.email] if ticket.assignee.email else []
    _send_email(subject, body, emails)
    _create_notification(
        ticket.assignee, 'ticket_assigned',
        f"Ticket #{ticket.pk:04d} atribuído a você",
        body, ticket_id=ticket.pk
    )


def notify_ticket_resolved(ticket):
    subject = f"[ITSM Enterprise] Ticket #{ticket.pk:04d} resolvido"
    # A solução vai no corpo do e-mail: avisar "foi resolvido" sem dizer o que
    # foi feito obriga o solicitante a abrir o sistema só para descobrir.
    atendente = ticket.resolved_by or ticket.assignee
    body = (
        f"Olá, {ticket.requester.get_full_name() or ticket.requester.username}!\n\n"
        f"Seu chamado foi resolvido.\n\n"
        f"  ID:     #{ticket.pk:04d}\n"
        f"  Título: {ticket.title}\n"
    )
    if atendente:
        body += f"  Por:    {atendente.get_full_name() or atendente.username}\n"
    if ticket.solution:
        body += f"\nSolução aplicada:\n{ticket.solution}\n"
    body += (
        f"\nSe o problema persistir, comente no chamado.\n\n"
        f"Acesse para confirmar: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [ticket.requester.email] if ticket.requester.email else []
    _send_email(subject, body, emails)
    _create_notification(
        ticket.requester, 'ticket_resolved',
        f"Seu ticket #{ticket.pk:04d} foi resolvido",
        body, ticket_id=ticket.pk
    )


def notify_approval_requested(ticket):
    """Avisa os aprovadores de que um chamado aguarda decisão (Fase 3.3).

    Vai para gerentes e admins, e não para a equipe toda: enquanto não houver
    aprovação, não há nada que um técnico possa fazer com este chamado.
    """
    aprovadores = list(_aprovadores())
    categoria = ticket.category.name if ticket.category else '—'
    subject = f"[ITSM Enterprise] Aprovação necessária — Ticket #{ticket.pk:04d}"
    body = (
        f"Um chamado aguarda sua aprovação.\n\n"
        f"  ID:          #{ticket.pk:04d}\n"
        f"  Título:      {ticket.title}\n"
        f"  Categoria:   {categoria}\n"
        f"  Prioridade:  {ticket.get_priority_display()}\n"
        f"  Solicitante: {ticket.requester.get_full_name() or ticket.requester.username}\n\n"
        f"Descrição:\n{ticket.description}\n\n"
        f"O prazo de SLA só começa a contar depois da aprovação.\n\n"
        f"Aprovar ou rejeitar: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [u.email for u in aprovadores if u.email]
    _send_email(subject, body, emails)
    for aprovador in aprovadores:
        _create_notification(
            aprovador, 'approval_requested',
            f"Aprovação necessária: #{ticket.pk:04d} — {ticket.title[:50]}",
            body, ticket_id=ticket.pk
        )


def notify_approval_decided(approval):
    """Avisa o solicitante da decisão, com o parecer do gerente.

    Ao contrário do motivo de escalonamento, que é interno, este parecer é
    para o solicitante: ele precisa saber por que o pedido foi negado.
    """
    ticket   = approval.ticket
    decisor  = approval.decided_by
    aprovado = approval.is_approved
    titulo   = 'aprovado' if aprovado else 'rejeitado'

    subject = f"[ITSM Enterprise] Ticket #{ticket.pk:04d} {titulo}"
    body = (
        f"Olá, {ticket.requester.get_full_name() or ticket.requester.username}!\n\n"
        f"Seu chamado foi {titulo}"
        f"{' por ' + (decisor.get_full_name() or decisor.username) if decisor else ''}.\n\n"
        f"  ID:     #{ticket.pk:04d}\n"
        f"  Título: {ticket.title}\n"
    )
    if approval.comment:
        rotulo = 'Parecer' if aprovado else 'Motivo da rejeição'
        body += f"\n{rotulo}:\n{approval.comment}\n"
    if aprovado:
        body += ("\nO chamado entrou na fila de atendimento e o prazo de SLA "
                 "começou a contar agora.\n")
    else:
        body += ("\nO chamado foi encerrado como rejeitado. Se precisar, abra "
                 "um novo chamado com as informações solicitadas.\n")
    body += (
        f"\nAcesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )

    emails = [ticket.requester.email] if ticket.requester.email else []
    _send_email(subject, body, emails)
    _create_notification(
        ticket.requester, 'approval_decided',
        f"Seu ticket #{ticket.pk:04d} foi {titulo}",
        body, ticket_id=ticket.pk
    )


def notify_ticket_escalated(escalation):
    """Avisa quem recebeu o chamado escalonado, com o motivo do repasse."""
    ticket  = escalation.ticket
    destino = escalation.to_user
    if not destino:
        return

    origem = escalation.from_user
    por    = f" por {origem.get_full_name() or origem.username}" if origem else ""
    subject = f"[ITSM Enterprise] Ticket #{ticket.pk:04d} escalonado para você"
    body = (
        f"Olá, {destino.get_full_name() or destino.username}!\n\n"
        f"Um chamado foi escalonado para você{por}.\n\n"
        f"  ID:         #{ticket.pk:04d}\n"
        f"  Título:     {ticket.title}\n"
        f"  Prioridade: {ticket.get_priority_display()}\n"
        f"  SLA:        {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M') if ticket.sla_deadline else '—'}\n\n"
        f"Motivo do escalonamento:\n{escalation.reason}\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [destino.email] if destino.email else []
    _send_email(subject, body, emails)
    _create_notification(
        destino, 'ticket_escalated',
        f"Ticket #{ticket.pk:04d} escalonado para você",
        body, ticket_id=ticket.pk
    )


def notify_comment_added(comment):
    if comment.is_internal:
        return
    ticket = comment.ticket
    notify_users = set()
    if ticket.requester != comment.author:
        notify_users.add(ticket.requester)
    if ticket.assignee and ticket.assignee != comment.author:
        notify_users.add(ticket.assignee)

    subject = f"[ITSM Enterprise] Novo comentário no Ticket #{ticket.pk:04d}"
    body = (
        f"{comment.author.get_full_name() or comment.author.username} comentou:\n\n"
        f"\"{comment.content[:300]}\"\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [u.email for u in notify_users if u.email]
    _send_email(subject, body, emails)
    for user in notify_users:
        _create_notification(
            user, 'comment_added',
            f"Comentário no ticket #{ticket.pk:04d}",
            body, ticket_id=ticket.pk
        )


def notify_sla_warning(ticket):
    """Aviso prévio: o prazo está perto de estourar (Fase 3.7).

    Vai para o técnico responsável e, se não houver nenhum, para a equipe —
    um chamado sem responsável perto de vencer é problema de todos.
    """
    if ticket.assignee:
        destinatarios = [ticket.assignee]
    else:
        destinatarios = list(_equipe())

    restante = ticket.sla_remaining_hours
    percentual = ticket.sla_elapsed_percent
    vencimento = (timezone.localtime(ticket.sla_deadline).strftime('%d/%m/%Y %H:%M')
                  if ticket.sla_deadline else '—')

    subject = f"[ITSM Enterprise] ⏰ SLA em risco — Ticket #{ticket.pk:04d}"
    body = (
        f"O prazo deste chamado está perto de vencer.\n\n"
        f"  ID:          #{ticket.pk:04d}\n"
        f"  Título:      {ticket.title}\n"
        f"  Prioridade:  {ticket.get_priority_display()}\n"
        f"  Responsável: {ticket.assignee.username if ticket.assignee else 'Não atribuído'}\n"
        f"  Vence em:    {vencimento}\n"
        f"  Decorrido:   {percentual}% do prazo"
        f"{f' — restam cerca de {restante}h' if restante is not None else ''}\n\n"
        f"Se o prazo estourar, o chamado é escalonado automaticamente para a "
        f"gerência.\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [u.email for u in destinatarios if u.email]
    _send_email(subject, body, emails)
    for user in destinatarios:
        _create_notification(
            user, 'sla_warning',
            f"⏰ SLA em risco: #{ticket.pk:04d} ({percentual}% do prazo)",
            body, ticket_id=ticket.pk
        )


def notify_sla_breach(ticket):
    if ticket.sla_breach_notified:
        return
    notify_users = list(_equipe())
    if ticket.assignee and ticket.assignee not in notify_users:
        notify_users.append(ticket.assignee)

    subject = f"[ITSM Enterprise] ⚠️ SLA VENCIDO — Ticket #{ticket.pk:04d}"
    body = (
        f"ATENÇÃO: O prazo de SLA foi ultrapassado.\n\n"
        f"  ID:          #{ticket.pk:04d}\n"
        f"  Título:      {ticket.title}\n"
        f"  Prioridade:  {ticket.get_priority_display()}\n"
        f"  SLA venceu:  {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M')}\n"
        f"  Responsável: {ticket.assignee.username if ticket.assignee else 'Não atribuído'}\n\n"
        f"Ação imediata necessária!\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— ITSM Enterprise"
    )
    emails = [u.email for u in notify_users if u.email]
    _send_email(subject, body, emails)
    for user in notify_users:
        _create_notification(
            user, 'sla_breach',
            f"⚠️ SLA VENCIDO: Ticket #{ticket.pk:04d}",
            body, ticket_id=ticket.pk
        )
    ticket.sla_breach_notified = True
    ticket.save(update_fields=['sla_breach_notified'])