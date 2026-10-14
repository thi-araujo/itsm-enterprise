from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.db.models import Q
from django.conf import settings
import logging
import os

from apps.accounts.models import UserProfile
from apps.accounts.permissions import staff_required
from .models import Ticket, Comment, Category, Attachment
from .forms import TicketForm, TicketUpdateForm, CommentForm

logger = logging.getLogger(__name__)


def _validar_anexo(arquivo):
    """Valida extensão e tamanho de um arquivo enviado.

    Devolve (True, None) se o arquivo é aceito, ou (False, mensagem) com o
    texto pronto para exibir ao usuário. A política vem de
    settings.ALLOWED_UPLOAD_EXTENSIONS / MAX_UPLOAD_SIZE_MB.
    """
    ext = os.path.splitext(arquivo.name)[1].lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        permitidas = ', '.join(settings.ALLOWED_UPLOAD_EXTENSIONS)
        rotulo = f'"{ext}"' if ext else 'arquivo sem extensão'
        return False, f'Tipo não permitido: {rotulo}. Aceitos: {permitidas}.'

    limite = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if arquivo.size > limite:
        tamanho = arquivo.size / (1024 * 1024)
        return False, (f'Arquivo muito grande ({tamanho:.1f} MB). '
                       f'Máximo: {settings.MAX_UPLOAD_SIZE_MB} MB.')
    return True, None


def _politica_de_upload():
    """Política de upload formatada para os templates (accept, rótulo, limite)."""
    return {
        'upload_accept':     ','.join(settings.ALLOWED_UPLOAD_EXTENSIONS),
        'upload_extensions': ', '.join(e.lstrip('.').upper()
                                       for e in settings.ALLOWED_UPLOAD_EXTENSIONS),
        'upload_max_mb':     settings.MAX_UPLOAD_SIZE_MB,
    }


@login_required
def ticket_list(request):
    # RBAC: solicitante vê só os próprios chamados (ver Ticket.visible_to).
    tickets = (Ticket.objects.visible_to(request.user)
               .select_related('requester', 'assignee', 'category'))

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
    # Chamado de outro usuário devolve 404 para o solicitante: um 403
    # confirmaria que o chamado existe.
    ticket       = get_object_or_404(Ticket.objects.visible_to(request.user), pk=pk)
    perfil       = request.user.profile
    comment_form = CommentForm()
    update_form  = TicketUpdateForm(instance=ticket)
    comments     = ticket.comments.select_related('author')
    attachments  = ticket.attachments.select_related('uploaded_by')

    # As notas internas saem do QUERYSET, não do template: esconder com
    # {% if %} deixaria o texto no HTML, visível no "ver código-fonte".
    if not perfil.can_see_internal_notes:
        comments = comments.filter(is_internal=False)

    context = {
        'ticket':       ticket,
        'comment_form': comment_form,
        'update_form':  update_form,
        'comments':     comments,
        'attachments':  attachments,
        'perfil':       perfil,
        **_politica_de_upload(),
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
                from apps.notifications.email import notify_ticket_created
                notify_ticket_created(ticket)
            except Exception:
                logger.exception('Falha ao notificar criação do ticket #%s', ticket.pk)

            messages.success(request, f'Ticket #{ticket.pk:04d} criado com sucesso!')

            # Anexo opcional: se for rejeitado, o ticket continua criado, mas o
            # usuário precisa saber que o arquivo não foi salvo.
            arquivo = request.FILES.get('attachment')
            if arquivo:
                aceito, erro = _validar_anexo(arquivo)
                if aceito:
                    Attachment.objects.create(
                        ticket=ticket,
                        uploaded_by=request.user,
                        file=arquivo,
                        filename=arquivo.name,
                        file_size=arquivo.size,
                    )
                else:
                    messages.error(request, f'O anexo NÃO foi salvo. {erro}')

            return redirect('tickets:detail', pk=ticket.pk)
    else:
        form = TicketForm()

    context = {'form': form, **_politica_de_upload()}
    return render(request, 'tickets/create.html', context)


@login_required
@staff_required
def ticket_update_status(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        form = TicketUpdateForm(request.POST, instance=ticket)
        if form.is_valid():
            updated = form.save()
            try:
                from apps.notifications.email import notify_ticket_assigned, notify_ticket_resolved
                if updated.assignee:
                    notify_ticket_assigned(updated)
                if updated.status == 'resolved':
                    notify_ticket_resolved(updated)
            except Exception:
                logger.exception('Falha ao notificar atualização do ticket #%s', pk)
            messages.success(request, 'Ticket atualizado!')
    return redirect('tickets:detail', pk=pk)


@login_required
def add_comment(request, pk):
    ticket = get_object_or_404(Ticket.objects.visible_to(request.user), pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.ticket = ticket
            comment.author = request.user
            # Solicitante não cria nota interna, mesmo forjando o POST.
            if not request.user.profile.can_see_internal_notes:
                comment.is_internal = False
            comment.save()
            try:
                from apps.notifications.email import notify_comment_added
                notify_comment_added(comment)
            except Exception:
                logger.exception('Falha ao notificar comentário no ticket #%s', pk)
            if request.htmx:
                return render(request, 'partials/comment_item.html', {'comment': comment})
    return redirect('tickets:detail', pk=pk)


@login_required
def upload_attachment(request, pk):
    ticket = get_object_or_404(Ticket.objects.visible_to(request.user), pk=pk)
    if request.method == 'POST' and request.FILES.get('file'):
        arquivo      = request.FILES['file']
        aceito, erro = _validar_anexo(arquivo)

        if not aceito:
            if request.htmx:
                # O formulário usa hx-swap="beforeend" em #attachments-list.
                # Sem retarget, o redirect do fim desta view faria o HTMX
                # injetar a página inteira dentro da lista de anexos.
                resposta = render(request, 'partials/attachment_error.html',
                                  {'erro': erro})
                resposta['HX-Retarget'] = '#attach-error'
                resposta['HX-Reswap']   = 'innerHTML'
                return resposta
            messages.error(request, erro)
        else:
            att = Attachment.objects.create(
                ticket=ticket,
                uploaded_by=request.user,
                file=arquivo,
                filename=arquivo.name,
                file_size=arquivo.size,
            )
            if request.htmx:
                return render(request, 'partials/attachment_item.html', {'att': att})
            messages.success(request, f'"{arquivo.name}" enviado com sucesso!')
    return redirect('tickets:detail', pk=pk)


@login_required
def download_attachment(request, pk, att_pk):
    ticket = get_object_or_404(Ticket.objects.visible_to(request.user), pk=pk)
    att    = get_object_or_404(Attachment, pk=att_pk, ticket=ticket)
    if not att.file:
        raise Http404
    response = HttpResponse(att.file, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{att.filename}"'
    return response


@login_required
@staff_required
def queue_view(request):
    open_tickets = Ticket.objects.filter(
        status__in=['open', 'in_progress', 'waiting']
    ).select_related('requester', 'assignee', 'category').order_by('-priority', 'created_at')

    unassigned  = open_tickets.filter(assignee__isnull=True)
    my_queue    = open_tickets.filter(assignee=request.user)
    # Quem pode receber chamados vem do perfil, não da flag de acesso ao
    # /admin/ do Django — são coisas diferentes.
    technicians = User.objects.filter(
        profile__role__in=UserProfile.STAFF_ROLES).select_related('profile')

    context = {
        'unassigned':  unassigned,
        'my_queue':    my_queue,
        'technicians': technicians,
    }
    return render(request, 'tickets/queue.html', context)


@login_required
@staff_required
def assign_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        tech_id = request.POST.get('assignee_id')
        if tech_id:
            try:
                tech = User.objects.get(pk=tech_id,
                                        profile__role__in=UserProfile.STAFF_ROLES)
                ticket.assignee = tech
                if ticket.status == 'open':
                    ticket.status = 'in_progress'
                ticket.save()
                messages.success(request, f'Atribuído a {tech.get_full_name() or tech.username}!')
            except User.DoesNotExist:
                messages.error(request, 'Técnico não encontrado.')
    return redirect('tickets:queue')


@login_required
@staff_required
def unassigned_count(request):
    from django.http import JsonResponse
    count = Ticket.objects.filter(
        status__in=['open', 'in_progress', 'waiting'],
        assignee__isnull=True
    ).count()
    return JsonResponse({'count': count})