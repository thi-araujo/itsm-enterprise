from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, F
from django.utils import timezone
from datetime import timedelta
import json

from apps.accounts.models import UserProfile
from apps.accounts.permissions import management_required
from apps.tickets import stats
from apps.tickets.models import Ticket


@login_required
@management_required
def report_dashboard(request):
    """Relatório geral. As agregações vêm de apps/tickets/stats.py, as mesmas
    que o dashboard e a API usam."""
    try:
        days = max(1, int(request.GET.get('days', 30)))
    except (TypeError, ValueError):
        days = 30

    since   = timezone.now() - timedelta(days=days)
    tickets = Ticket.objects.filter(created_at__gte=since)

    dados = stats.estatisticas_de(tickets)
    sla   = dados['sla_cumprimento']

    # Chamados com prazo estourado e ainda em atendimento — sem recorte de
    # período, porque um atraso antigo continua sendo um atraso hoje.
    breached_open = (Ticket.objects
                     .exclude(status__in=Ticket.CLOSED_STATUSES)
                     .filter(sla_deadline__lt=timezone.now())
                     .count())

    context = {
        'days':             days,
        'total':            dados['total'],
        'resolved':         dados['resolvidos'],
        'sla_pct':          sla['percentual'] or 0,
        'breached_open':    breached_open,
        'tempo_medio':      dados['tempo_medio_resolucao_horas'],
        'by_status_json':   json.dumps(dados['por_status']),
        'by_priority_json': json.dumps(dados['por_prioridade']),
        'by_type_json':     json.dumps(dados['por_tipo']),
        'by_category_json': json.dumps(dados['por_categoria']),
        'by_tech_json':     json.dumps(dados['por_tecnico']),
        # A chave muda de 'dia'/'total' para 'date'/'count' porque é o que o
        # template já espera no Chart.js.
        'daily_json':       json.dumps([{'date': d['dia'], 'count': d['total']}
                                        for d in stats.volume_diario(tickets, days)]),
        'by_category':      dados['por_categoria'],
        'by_tech':          dados['por_tecnico'],
    }
    return render(request, 'reports/dashboard.html', context)


@login_required
@management_required
def report_technician(request):
    days  = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    techs = User.objects.filter(
        profile__role__in=UserProfile.STAFF_ROLES).select_related('profile')
    data  = []

    for tech in techs:
        qs       = Ticket.objects.filter(assignee=tech, created_at__gte=since)
        resolved = qs.filter(status__in=['resolved', 'closed'],
                             resolved_at__isnull=False,
                             sla_deadline__isnull=False)
        sla_ok         = resolved.filter(resolved_at__lte=F('sla_deadline')).count()
        com_sla        = resolved.count()
        total_resolved = qs.filter(status__in=['resolved', 'closed']).count()
        data.append({
            'tech':     tech,
            'total':    qs.count(),
            'open':     qs.filter(status='open').count(),
            'progress': qs.filter(status='in_progress').count(),
            'resolved': total_resolved,
            'sla_ok':   sla_ok,
            'sla_pct':  round((sla_ok / com_sla * 100) if com_sla else 0, 1),
        })

    data.sort(key=lambda x: x['total'], reverse=True)
    return render(request, 'reports/technician.html', {'data': data, 'days': days})