from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from apps.tickets import stats
from apps.tickets.models import Ticket


@login_required
def index(request):
    """Painel de controle.

    A view calcula os números da PRIMEIRA carga de propósito, mesmo havendo
    o `/api/v1/estatisticas/`: se o fetch falhar — rede, erro de JS, extensão
    do navegador bloqueando — a página mostra números corretos em vez de
    zeros. O JavaScript (static/js/dashboard.js) apenas atualiza o que já
    está na tela, a cada 60 segundos.
    """
    # RBAC: o dashboard do solicitante mostra os números dos chamados dele.
    tickets = Ticket.objects.visible_to(request.user)
    perfil  = request.user.profile

    dados = stats.estatisticas_de(tickets)
    por_status = dados['por_status']

    estatisticas = {
        'total':        dados['total'],
        'open':         por_status.get('open', 0),
        'in_progress':  por_status.get('in_progress', 0),
        'resolved':     dados['resolvidos'],
        'critical':     dados['por_prioridade'].get('critical', 0),
        'sla_risk':     dados['sla_vencido'],
        'sla_em_risco': dados['sla_em_risco'],
        'sem_tecnico':  dados['sem_tecnico'],
        'aguardando_aprovacao': dados['aguardando_aprovacao'],
        'sla_percentual': dados['sla_cumprimento']['percentual'],
        'tempo_medio':    dados['tempo_medio_resolucao_horas'],
    }

    recent_tickets = tickets.select_related('requester', 'assignee', 'category')[:10]

    # Para a equipe, "meus chamados" são os atribuídos a ela. Para o
    # solicitante, são os que ele abriu — senão o bloco ficaria sempre vazio.
    if perfil.can_attend:
        my_tickets = tickets.filter(assignee=request.user)
    else:
        my_tickets = tickets.filter(requester=request.user)
    my_tickets = my_tickets.exclude(status='closed')[:5]

    context = {
        'perfil':         perfil,
        'stats':          estatisticas,
        'recent_tickets': recent_tickets,
        'my_tickets':     my_tickets,
    }
    return render(request, 'dashboard/index.html', context)
