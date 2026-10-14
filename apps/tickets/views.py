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
from apps.accounts.permissions import management_required, staff_required
from .models import Approval, Ticket, Comment, Category, Attachment, Escalation
from .forms import (TicketForm, TicketUpdateForm, CommentForm,
                    TicketFinishForm, EscalationForm, ApprovalForm)

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

    # O histórico de escalonamento é informação interna da equipe, e segue a
    # mesma regra das notas internas: fica fora do queryset do solicitante,
    # não escondido no template.
    if perfil.can_manage_tickets:
        escalations = ticket.escalations.select_related('from_user', 'to_user')
        finish_form = TicketFinishForm(instance=ticket)
        escalate_form = EscalationForm(user=request.user)
    else:
        escalations = ticket.escalations.none()
        finish_form = None
        escalate_form = None

    # Aprovação (Fase 3.3). O parecer da decisão o solicitante VÊ — é para
    # ele —, ao contrário do motivo do escalonamento, que é interno.
    approval_form = ApprovalForm() if perfil.can_approve else None

    context = {
        'ticket':        ticket,
        'comment_form':  comment_form,
        'update_form':   update_form,
        'finish_form':   finish_form,
        'escalate_form': escalate_form,
        'approval_form': approval_form,
        'last_approval': ticket.last_approval,
        'comments':      comments,
        'attachments':   attachments,
        'escalations':   escalations,
        'perfil':        perfil,
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

            # Workflow de aprovação: categorias marcadas no /admin/ fazem o
            # chamado nascer aguardando o gerente, e o save() do model deixa o
            # SLA nulo até a aprovação.
            precisa_aprovacao = bool(ticket.category and ticket.category.requires_approval)
            if precisa_aprovacao:
                ticket.status = 'pending_approval'
            ticket.save()

            try:
                from apps.notifications.email import (notify_approval_requested,
                                                      notify_ticket_created)
                # Enquanto não houver aprovação não há nada que um técnico
                # possa fazer, então o aviso vai para quem decide.
                if precisa_aprovacao:
                    notify_approval_requested(ticket)
                else:
                    notify_ticket_created(ticket)
            except Exception:
                logger.exception('Falha ao notificar criação do ticket #%s', ticket.pk)

            if precisa_aprovacao:
                messages.success(
                    request,
                    f'Ticket #{ticket.pk:04d} criado e enviado para aprovação. '
                    f'O prazo de SLA começa a contar quando o gerente aprovar.')
            else:
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

    context = {
        'form': form,
        # Avisa de antemão quais categorias passam por aprovação, para o
        # solicitante não se surpreender com o chamado parado.
        'approval_categories': Category.objects.filter(requires_approval=True),
        **_politica_de_upload(),
    }
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
@staff_required
def ticket_finish(request, pk):
    """Finaliza o chamado exigindo a solução (Fase 3.2).

    Leva a "Resolvido", não a "Fechado": no ITIL quem fecha é o solicitante,
    depois de confirmar. "Resolvido" significa "o técnico terminou, aguardando
    confirmação".
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        return redirect('tickets:detail', pk=pk)

    if not ticket.can_be_finished:
        messages.error(request, 'Este chamado já está resolvido ou fechado.')
        return redirect('tickets:detail', pk=pk)

    form = TicketFinishForm(request.POST, instance=ticket)
    if not form.is_valid():
        # Mostra o erro de validação do form (solução vazia ou curta demais).
        for erro in form.errors.get('solution', ['Informe a solução.']):
            messages.error(request, erro)
        return redirect('tickets:detail', pk=pk)

    ticket = form.save(commit=False)
    ticket.status      = 'resolved'
    ticket.resolved_by = request.user
    # resolved_at é preenchido pelo save() do model quando o status vira
    # 'resolved' — não repetir aqui.
    ticket.save()

    # A solução também entra no histórico como comentário público, para o
    # solicitante ler na mesma linha do tempo dos outros comentários.
    Comment.objects.create(
        ticket=ticket, author=request.user, is_internal=False,
        content=f"Chamado finalizado.\n\nSolução: {ticket.solution}",
    )

    try:
        from apps.notifications.email import notify_ticket_resolved
        notify_ticket_resolved(ticket)
    except Exception:
        logger.exception('Falha ao notificar resolução do ticket #%s', pk)

    messages.success(request, f'Chamado #{ticket.pk:04d} finalizado com sucesso!')
    return redirect('tickets:detail', pk=pk)


@login_required
@staff_required
def ticket_escalate(request, pk):
    """Repassa o chamado a outro membro da equipe, com motivo registrado."""
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        return redirect('tickets:detail', pk=pk)

    if not ticket.can_be_escalated:
        messages.error(request, 'Chamado resolvido ou fechado não pode ser escalonado.')
        return redirect('tickets:detail', pk=pk)

    # `user=request.user` tira o próprio usuário da lista de destinos: um POST
    # forjado escalonando para si mesmo cai como destino inválido.
    form = EscalationForm(request.POST, user=request.user)
    if not form.is_valid():
        for campo, erros in form.errors.items():
            for erro in erros:
                messages.error(request, erro)
        return redirect('tickets:detail', pk=pk)

    escalation           = form.save(commit=False)
    escalation.ticket    = ticket
    escalation.from_user = request.user
    escalation.save()

    ticket.assignee = escalation.to_user
    # Um chamado escalonado está em atendimento, não mais só "aberto".
    if ticket.status == 'open':
        ticket.status = 'in_progress'
    ticket.save()

    try:
        from apps.notifications.email import notify_ticket_escalated
        notify_ticket_escalated(escalation)
    except Exception:
        logger.exception('Falha ao notificar escalonamento do ticket #%s', pk)

    destino = escalation.to_user.get_full_name() or escalation.to_user.username
    messages.success(request, f'Chamado escalonado para {destino}.')
    return redirect('tickets:detail', pk=pk)


# ══════════════════════════════════════════════════════════════════
# Workflow de aprovação — Fase 3.3
# ══════════════════════════════════════════════════════════════════


@login_required
@management_required
def approval_queue(request):
    """Fila dos chamados que aguardam decisão do gerente."""
    pending = (Ticket.objects.filter(status='pending_approval')
               .select_related('requester', 'category')
               .order_by('created_at'))   # mais antigo primeiro: quem espera mais, decide antes

    context = {
        'pending': pending,
        'total':   pending.count(),
    }
    return render(request, 'tickets/approvals.html', context)


def _decidir_aprovacao(request, pk, decision):
    """Registra uma decisão de aprovação. Compartilhado por aprovar/rejeitar.

    Os dois caminhos validam o mesmo parecer, gravam o mesmo histórico e
    mandam a mesma notificação — só o efeito no status muda.
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        return redirect('tickets:detail', pk=pk)

    # Impede decidir duas vezes, ou decidir um chamado que nunca precisou de
    # aprovação (um POST direto na URL, por exemplo).
    if not ticket.is_awaiting_approval:
        messages.error(request, 'Este chamado não está aguardando aprovação.')
        return redirect('tickets:detail', pk=pk)

    form = ApprovalForm(request.POST, decision=decision)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect('tickets:detail', pk=pk)

    approval            = form.save(commit=False)
    approval.ticket     = ticket
    approval.decided_by = request.user
    approval.decision   = decision
    approval.save()

    if approval.is_approved:
        ticket.status = 'open'
        # O relógio do SLA começa AGORA, não na abertura: o chamado ficou
        # parado esperando uma decisão que não era do solicitante nem da
        # equipe. Ver Ticket.start_sla.
        ticket.start_sla()
        aviso = (f'Chamado #{ticket.pk:04d} aprovado e liberado para a fila. '
                 f'SLA até {ticket.sla_deadline.strftime("%d/%m/%Y %H:%M")}.')
    else:
        ticket.status = 'rejected'
        aviso = f'Chamado #{ticket.pk:04d} rejeitado. O solicitante foi avisado.'
    ticket.save()

    # O parecer também entra na linha do tempo, como comentário público: é
    # informação que o solicitante pode ver.
    if approval.comment:
        rotulo = 'Aprovação' if approval.is_approved else 'Rejeição'
        Comment.objects.create(
            ticket=ticket, author=request.user, is_internal=False,
            content=f"{rotulo} do chamado.\n\n{approval.comment}",
        )

    try:
        from apps.notifications.email import notify_approval_decided
        notify_approval_decided(approval)
    except Exception:
        logger.exception('Falha ao notificar decisão de aprovação do ticket #%s', pk)

    messages.success(request, aviso)
    return redirect('tickets:detail', pk=pk)


@login_required
@management_required
def ticket_approve(request, pk):
    """Aprova o chamado: libera para a fila e inicia a contagem do SLA."""
    return _decidir_aprovacao(request, pk, Approval.DECISION_APPROVED)


@login_required
@management_required
def ticket_reject(request, pk):
    """Rejeita o chamado, com motivo obrigatório. Status terminal."""
    return _decidir_aprovacao(request, pk, Approval.DECISION_REJECTED)


@login_required
@management_required
def pending_approval_count(request):
    """Contador do badge "Aprovações" na sidebar."""
    from django.http import JsonResponse
    return JsonResponse({'count': Ticket.objects.filter(status='pending_approval').count()})


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