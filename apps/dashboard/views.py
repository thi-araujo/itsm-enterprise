from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.utils import timezone
from apps.tickets.models import Ticket


@login_required
def index(request):
    # RBAC: o dashboard do solicitante mostra os números dos chamados dele.
    tickets = Ticket.objects.visible_to(request.user)
    perfil  = request.user.profile
    
    stats = {
        'total':       tickets.count(),
        'open':        tickets.filter(status='open').count(),
        'in_progress': tickets.filter(status='in_progress').count(),
        'resolved':    tickets.filter(status='resolved').count(),
        'critical':    tickets.filter(priority='critical').count(),
        # Mesma regra de Ticket.is_sla_breached, porém resolvida no banco:
        # antes isso carregava todos os tickets em memória a cada carga.
        'sla_risk':    tickets.filter(sla_deadline__lt=timezone.now())
                              .exclude(status__in=['resolved', 'closed']).count(),
    }
    
    recent_tickets = tickets.select_related('requester', 'assignee', 'category')[:10]

    # Para a equipe, "meus chamados" são os atribuídos a ela. Para o
    # solicitante, são os que ele abriu — senão o bloco ficaria sempre vazio.
    if perfil.can_attend:
        my_tickets = tickets.filter(assignee=request.user)
    else:
        my_tickets = tickets.filter(requester=request.user)
    my_tickets = my_tickets.exclude(status='closed')[:5]
    
    # Por prioridade
    priority_data = tickets.values('priority').annotate(count=Count('id'))
    
    context = {
        'perfil': perfil,
        'stats': stats,
        'recent_tickets': recent_tickets,
        'my_tickets': my_tickets,
        'priority_data': list(priority_data),
    }
    return render(request, 'dashboard/index.html', context)
