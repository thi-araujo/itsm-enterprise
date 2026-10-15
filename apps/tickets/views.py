from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.db.models import Q
from django.conf import settings
import logging
import os

from apps.accounts.models import UserProfile
from apps.accounts.permissions import management_required, staff_required
from . import services
from .models import (Approval, AuditLog, Ticket, Comment, Category, Attachment,
                     Escalation)
from .forms import (TicketForm, TicketUpdateForm, CommentForm,
                    TicketFinishForm, EscalationForm, ApprovalForm)

logger = logging.getLogger(__name__)


def _mensagens_do_erro(erro):
    """Extrai as mensagens de um ValidationError, com ou sem campo.

    As regras em services.py levantam ValidationError — às vezes com um dicionário
    por campo, às vezes com uma mensagem solta. A view só quer o texto.
    """
    if hasattr(erro, 'message_dict'):
        return [m for mensagens in erro.message_dict.values() for m in mensagens]
    return list(erro.messages)


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
    # A trilha de auditoria segue a mesma regra: "Prioridade: Crítica →
    # Baixa" é conversa interna da equipe.
    if perfil.can_manage_tickets:
        escalations = ticket.escalations.select_related('from_user', 'to_user')
        audit_logs  = ticket.audit_logs.select_related('user')
        finish_form = TicketFinishForm(instance=ticket)
        escalate_form = EscalationForm(user=request.user)
    else:
        escalations = ticket.escalations.none()
        audit_logs  = ticket.audit_logs.none()
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
        'audit_logs':    audit_logs,
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
            # save_as informa o autor para a auditoria (Fase 3.4); o evento
            # 'created' é gravado pelo próprio save() do model.
            ticket.save_as(request.user)

            try:
                from apps.notifications.email import (notify_approval_requested,
                                                      notify_ticket_created,
                                                      notify_ticket_opened)
                # Enquanto não houver aprovação não há nada que um técnico
                # possa fazer, então o aviso vai para quem decide.
                if precisa_aprovacao:
                    notify_approval_requested(ticket)
                else:
                    notify_ticket_created(ticket)
                # Recibo para quem abriu, nos dois casos — ele precisa do
                # número do chamado independentemente de quem foi avisado.
                notify_ticket_opened(ticket)
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
                    AuditLog.registrar(ticket, request.user,
                                       AuditLog.ACTION_ATTACHED, arquivo.name)
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
            # commit=False + save_as: o form prepara, o model audita sabendo
            # quem alterou. Um form.save() direto gravaria sem autor.
            updated = form.save(commit=False)
            updated.save_as(request.user)
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

    A regra em si está em services.finalizar_chamado, compartilhada com a
    API REST. Aqui ficam só o formulário, as mensagens e o redirect.
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        return redirect('tickets:detail', pk=pk)

    form = TicketFinishForm(request.POST, instance=ticket)
    if not form.is_valid():
        for erro in form.errors.get('solution', ['Informe a solução.']):
            messages.error(request, erro)
        return redirect('tickets:detail', pk=pk)

    try:
        services.finalizar_chamado(ticket, request.user,
                                   form.cleaned_data['solution'])
    except ValidationError as erro:
        for mensagem in _mensagens_do_erro(erro):
            messages.error(request, mensagem)
        return redirect('tickets:detail', pk=pk)

    messages.success(request, f'Chamado #{ticket.pk:04d} finalizado com sucesso!')
    return redirect('tickets:detail', pk=pk)


@login_required
@staff_required
def ticket_escalate(request, pk):
    """Repassa o chamado a outro membro da equipe, com motivo registrado.

    A regra está em services.escalonar_chamado; o form cuida de oferecer só
    destinos válidos (ver EscalationForm).
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        return redirect('tickets:detail', pk=pk)

    # `user=request.user` tira o próprio usuário da lista de destinos: um POST
    # forjado escalonando para si mesmo cai como destino inválido.
    form = EscalationForm(request.POST, user=request.user)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect('tickets:detail', pk=pk)

    try:
        escalation = services.escalonar_chamado(
            ticket, request.user,
            form.cleaned_data['to_user'], form.cleaned_data['reason'])
    except ValidationError as erro:
        for mensagem in _mensagens_do_erro(erro):
            messages.error(request, mensagem)
        return redirect('tickets:detail', pk=pk)

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
    """Casca HTML da decisão. A regra está em services.decidir_aprovacao."""
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.method != 'POST':
        return redirect('tickets:detail', pk=pk)

    form = ApprovalForm(request.POST, decision=decision)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect('tickets:detail', pk=pk)

    try:
        approval = services.decidir_aprovacao(
            ticket, request.user, decision, form.cleaned_data['comment'])
    except ValidationError as erro:
        for mensagem in _mensagens_do_erro(erro):
            messages.error(request, mensagem)
        return redirect('tickets:detail', pk=pk)

    if approval.is_approved:
        messages.success(
            request,
            f'Chamado #{ticket.pk:04d} aprovado e liberado para a fila. '
            f'SLA até {timezone.localtime(ticket.sla_deadline):%d/%m/%Y %H:%M}.')
    else:
        messages.success(
            request,
            f'Chamado #{ticket.pk:04d} rejeitado. O solicitante foi avisado.')
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
            # services.comentar_chamado já força is_internal=False para
            # quem não pode ver nota interna, mesmo com o POST forjado.
            comment = services.comentar_chamado(
                ticket, request.user,
                form.cleaned_data['content'],
                form.cleaned_data.get('is_internal', False))
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
            AuditLog.registrar(ticket, request.user,
                               AuditLog.ACTION_ATTACHED, arquivo.name)
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
                ticket.save_as(request.user)
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