from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from .models import Notification


def _create_notification(user, ntype, title, message, ticket_id=None):
    Notification.objects.create(
        user=user, type=ntype, title=title,
        message=message, ticket_id=ticket_id
    )


def _send_email(subject, body, recipients):
    if not recipients:
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
    except Exception as e:
        print(f"[RAVEN EMAIL] Erro: {e}")


def notify_ticket_created(ticket):
    admins = User.objects.filter(is_staff=True).exclude(email='')
    emails = list(admins.values_list('email', flat=True))
    subject = f"[RAVEN] Novo Ticket #{ticket.pk:04d} — {ticket.get_priority_display()}"
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
        f"— RAVEN ITSM"
    )
    _send_email(subject, body, emails)
    for admin in User.objects.filter(is_staff=True):
        _create_notification(
            admin, 'ticket_created',
            f"Novo ticket #{ticket.pk:04d}: {ticket.title[:60]}",
            body, ticket_id=ticket.pk
        )


def notify_ticket_assigned(ticket):
    if not ticket.assignee:
        return
    subject = f"[RAVEN] Ticket #{ticket.pk:04d} atribuído a você"
    body = (
        f"Olá, {ticket.assignee.get_full_name() or ticket.assignee.username}!\n\n"
        f"O ticket abaixo foi atribuído a você:\n\n"
        f"  ID:         #{ticket.pk:04d}\n"
        f"  Título:     {ticket.title}\n"
        f"  Prioridade: {ticket.get_priority_display()}\n"
        f"  SLA:        {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M') if ticket.sla_deadline else '—'}\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— RAVEN ITSM"
    )
    emails = [ticket.assignee.email] if ticket.assignee.email else []
    _send_email(subject, body, emails)
    _create_notification(
        ticket.assignee, 'ticket_assigned',
        f"Ticket #{ticket.pk:04d} atribuído a você",
        body, ticket_id=ticket.pk
    )


def notify_ticket_resolved(ticket):
    subject = f"[RAVEN] Ticket #{ticket.pk:04d} resolvido"
    body = (
        f"Olá, {ticket.requester.get_full_name() or ticket.requester.username}!\n\n"
        f"Seu chamado foi resolvido.\n\n"
        f"  ID:     #{ticket.pk:04d}\n"
        f"  Título: {ticket.title}\n\n"
        f"Acesse para confirmar: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— RAVEN ITSM"
    )
    emails = [ticket.requester.email] if ticket.requester.email else []
    _send_email(subject, body, emails)
    _create_notification(
        ticket.requester, 'ticket_resolved',
        f"Seu ticket #{ticket.pk:04d} foi resolvido",
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

    subject = f"[RAVEN] Novo comentário no Ticket #{ticket.pk:04d}"
    body = (
        f"{comment.author.get_full_name() or comment.author.username} comentou:\n\n"
        f"\"{comment.content[:300]}\"\n\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— RAVEN ITSM"
    )
    emails = [u.email for u in notify_users if u.email]
    _send_email(subject, body, emails)
    for user in notify_users:
        _create_notification(
            user, 'comment_added',
            f"Comentário no ticket #{ticket.pk:04d}",
            body, ticket_id=ticket.pk
        )


def notify_sla_breach(ticket):
    if ticket.sla_breach_notified:
        return
    notify_users = list(User.objects.filter(is_staff=True))
    if ticket.assignee and ticket.assignee not in notify_users:
        notify_users.append(ticket.assignee)

    subject = f"[RAVEN] ⚠️ SLA VENCIDO — Ticket #{ticket.pk:04d}"
    body = (
        f"ATENÇÃO: O prazo de SLA foi ultrapassado.\n\n"
        f"  ID:          #{ticket.pk:04d}\n"
        f"  Título:      {ticket.title}\n"
        f"  Prioridade:  {ticket.get_priority_display()}\n"
        f"  SLA venceu:  {ticket.sla_deadline.strftime('%d/%m/%Y %H:%M')}\n"
        f"  Responsável: {ticket.assignee.username if ticket.assignee else 'Não atribuído'}\n\n"
        f"Ação imediata necessária!\n"
        f"Acesse: http://localhost:8000/tickets/{ticket.pk}/\n\n"
        f"— RAVEN ITSM"
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