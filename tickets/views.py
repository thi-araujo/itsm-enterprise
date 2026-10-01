from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.db.models import Q
from django.conf import settings
import os

from django.conf import settings
from .models import Ticket, Comment, Category, Attachment
from .forms import TicketForm, TicketUpdateForm, CommentForm

@login_required
def ticket_list(request):
    tickets = Ticket.objects.select_related('requester', 'assignee', 'category')

    status   = request.GET.get('status', '')
    priority = request.GET.get('priority', '')
    search   = request.GET.get('search', '')
    assignee = request.GET.get('assignee', '')

    if status:   tickets = tickets.filter(status=status)
    if priority: tickets = tickets.filter(priority=priority)
    if assignee == 'me':
        tickets = tickets.filter(assignee=request.user)
    elif assignee == 'unassigned':
        tickets = tickets.filter(assignee__isnull=True)
    if search:
        tickets = tickets.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(pk__icontains=search)
        )

    context = {
        'tickets':         tickets,
        'status_filter':   status,
        'priority_filter': priority,
        'search':          search,
        'assignee_filter': assignee,
        'total':           tickets.count(),
    }
    if request.htmx:
        return render(request, 'partials/ticket_table.html', context)
    return render(request, 'tickets/list.html', context)


@login_required
def ticket_detail(request, pk):
    ticket       = get_object_or_404(Ticket, pk=pk)
    comment_form = CommentForm()
    update_form  = TicketUpdateForm(instance=ticket)
    comments     = ticket.comments.select_related('author')
    attachments  = ticket.attachments.select_related('uploaded_by')

    context = {
        'ticket':       ticket,
        'comment_form': comment_form,
        'update_form':  update_form,
        'comments':     comments,
        'attachments':  attachments,
    }
    return render(request, 'tickets/detail.html', context)


@login_required
def ticket_create(request):
    if request.method == 'POST':
        form = TicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.requester = request.user
            ticket.save()

            try:
                from notifications.email import notify_ticket_created
                notify_ticket_created(ticket)
            except Exception:
                pass
            # Processa anexo opcional
            f = request.FILES.get('attachment')
            if f:
                ext     = os.path.splitext(f.name)[1].lower()
                allowed = getattr(settings, 'ALLOWED_UPLOAD_EXTENSIONS',
                          ['.pdf','.doc','.docx','.xls','.xlsx',
                           '.png','.jpg','.jpeg','.txt','.log','.zip'])
                max_mb  = getattr(settings, 'MAX_UPLOAD_SIZE_MB', 10)
                if ext in allowed and f.size <= max_mb * 1024 * 1024:
                    Attachment.objects.create(
                        ticket=ticket,
                        uploaded_by=request.user,
                        file=f,
                        filename=f.name,
                        file_size=f.size,
                    )
            messages.success(request, f'Ticket #{ticket.pk:04d} criado com sucesso!')
            return redirect('tickets:detail', pk=ticket.pk)
    else:
        form = TicketForm()
    return render(request, 'tickets/create.html', {'form': form})


@login_required
def ticket_update_status(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        form = TicketUpdateForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            try:
                from notifications.email import notify_ticket_assigned, notify_ticket_resolved
                if updated.assignee:
                    notify_ticket_assigned(updated)
                if updated.status == 'resolved':
                    notify_ticket_resolved(updated)
            except Exception:
                pass
            messages.success(request, 'Ticket atualizado!')
    return redirect('tickets:detail', pk=pk)


@login_required
def add_comment(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.ticket = ticket
            comment.author = request.user
            comment.save()
            try:
                from notifications.email import notify_comment_added
                notify_comment_added(comment)
            except Exception:
                pass
            if request.htmx:
                return render(request, 'partials/comment_item.html', {'comment': comment})
    return redirect('tickets:detail', pk=pk)


@login_required
def upload_attachment(request, pk):
    ticket  = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST' and request.FILES.get('file'):
        f       = request.FILES['file']
        ext     = os.path.splitext(f.name)[1].lower()
        allowed = ['.pdf', '.doc', '.docx', '.xls', '.xlsx',
                   '.png', '.jpg', '.jpeg', '.txt', '.log', '.zip']
        max_mb  = 10

        if ext not in allowed:
            messages.error(request, f'Tipo não permitido: {ext}')
        elif f.size > max_mb * 1024 * 1024:
            messages.error(request, f'Arquivo muito grande. Máximo: {max_mb}MB')
        else:
            att = Attachment.objects.create(
                ticket=ticket,
                uploaded_by=request.user,
                file=f,
                filename=f.name,
                file_size=f.size,
            )
            if request.htmx:
                return render(request, 'partials/attachment_item.html', {'att': att})
            messages.success(request, f'"{f.name}" enviado com sucesso!')
    return redirect('tickets:detail', pk=pk)


@login_required
def download_attachment(request, pk, att_pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    att    = get_object_or_404(Attachment, pk=att_pk, ticket=ticket)
    if not att.file:
        raise Http404
    response = HttpResponse(att.file, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{att.filename}"'
    return response


@login_required
def queue_view(request):
    open_tickets = Ticket.objects.filter(
        status__in=['open', 'in_progress', 'waiting']
    ).select_related('requester', 'assignee', 'category').order_by('-priority', 'created_at')

    unassigned  = open_tickets.filter(assignee__isnull=True)
    my_queue    = open_tickets.filter(assignee=request.user)
    technicians = User.objects.filter(is_staff=True)

    context = {
        'unassigned':  unassigned,
        'my_queue':    my_queue,
        'technicians': technicians,
    }
    return render(request, 'tickets/queue.html', context)


@login_required
def assign_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        tech_id = request.POST.get('assignee_id')
        if tech_id:
            try:
                tech = User.objects.get(pk=tech_id, is_staff=True)
                ticket.assignee = tech
                if ticket.status == 'open':
                    ticket.status = 'in_progress'
                ticket.save()
                messages.success(request, f'Atribuído a {tech.get_full_name() or tech.username}!')
            except User.DoesNotExist:
                messages.error(request, 'Técnico não encontrado.')
    return redirect('tickets:queue')


@login_required
def unassigned_count(request):
    from django.http import JsonResponse
    count = Ticket.objects.filter(
        status__in=['open', 'in_progress', 'waiting'],
        assignee__isnull=True
    ).count()
    return JsonResponse({'count': count})