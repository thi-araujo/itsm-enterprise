from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from tickets.models import Ticket


@login_required
def index(request):
    tickets = Ticket.objects.all()
    
    stats = {
        'total':       tickets.count(),
        'open':        tickets.filter(status='open').count(),
        'in_progress': tickets.filter(status='in_progress').count(),
        'resolved':    tickets.filter(status='resolved').count(),
        'critical':    tickets.filter(priority='critical').count(),
        'sla_risk':    sum(1 for t in tickets if t.is_sla_breached),
    }
    
    recent_tickets = tickets.select_related('requester', 'assignee', 'category')[:10]
    my_tickets = tickets.filter(assignee=request.user).exclude(status='closed')[:5]
    
    # Por prioridade
    priority_data = tickets.values('priority').annotate(count=Count('id'))
    
    context = {
        'stats': stats,
        'recent_tickets': recent_tickets,
        'my_tickets': my_tickets,
        'priority_data': list(priority_data),
    }
    return render(request, 'dashboard/index.html', context)
