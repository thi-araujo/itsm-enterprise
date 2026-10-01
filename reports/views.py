from django.shortcuts import render

# Create your views here.
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
import json

from tickets.models import Ticket


@login_required
def report_dashboard(request):
    days  = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    tickets = Ticket.objects.filter(created_at__gte=since)

    # Por status
    by_status = {
        item['status']: item['count']
        for item in tickets.values('status').annotate(count=Count('id'))
    }

    # Por prioridade
    by_priority = {
        item['priority']: item['count']
        for item in tickets.values('priority').annotate(count=Count('id'))
    }

    # Por categoria (top 6)
    by_category = list(
        tickets.exclude(category__isnull=True)
               .values('category__name')
               .annotate(count=Count('id'))
               .order_by('-count')[:6]
    )

    # Por tipo
    by_type = {
        item['ticket_type']: item['count']
        for item in tickets.values('ticket_type').annotate(count=Count('id'))
    }

    # Por técnico (top 8)
    by_tech = list(
        tickets.exclude(assignee__isnull=True)
               .values('assignee__username',
                       'assignee__first_name',
                       'assignee__last_name')
               .annotate(count=Count('id'))
               .order_by('-count')[:8]
    )

    # Volume diário (últimos N dias, máx 30)
    daily = []
    for i in range(min(days, 30)):
        day   = timezone.now().date() - timedelta(days=i)
        count = Ticket.objects.filter(created_at__date=day).count()
        daily.append({'date': day.strftime('%d/%m'), 'count': count})
    daily.reverse()

    # KPIs
    total    = tickets.count()
    resolved = tickets.filter(status__in=['resolved', 'closed']).count()

    # SLA compliance
    resolved_qs = tickets.filter(
        status__in=['resolved', 'closed'],
        resolved_at__isnull=False,
        sla_deadline__isnull=False,
    )
    sla_ok = sum(
        1 for t in resolved_qs
        if t.resolved_at and t.sla_deadline and t.resolved_at <= t.sla_deadline
    )
    sla_total = resolved_qs.count()
    sla_pct   = round((sla_ok / sla_total * 100) if sla_total else 0, 1)

    breached_open = Ticket.objects.filter(
        sla_deadline__lt=timezone.now(),
        status__in=['open', 'in_progress', 'waiting'],
    ).count()

    context = {
        'days':             days,
        'total':            total,
        'resolved':         resolved,
        'sla_pct':          sla_pct,
        'breached_open':    breached_open,
        'by_status_json':   json.dumps(by_status),
        'by_priority_json': json.dumps(by_priority),
        'by_type_json':     json.dumps(by_type),
        'by_category_json': json.dumps(by_category),
        'by_tech_json':     json.dumps(by_tech),
        'daily_json':       json.dumps(daily),
        'by_category':      by_category,
        'by_tech':          by_tech,
    }
    return render(request, 'reports/dashboard.html', context)


@login_required
def report_technician(request):
    days  = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    techs = User.objects.filter(is_staff=True)
    data  = []

    for tech in techs:
        qs       = Ticket.objects.filter(assignee=tech, created_at__gte=since)
        resolved = qs.filter(status__in=['resolved', 'closed'],
                             resolved_at__isnull=False,
                             sla_deadline__isnull=False)
        sla_ok   = sum(
            1 for t in resolved
            if t.resolved_at and t.sla_deadline and t.resolved_at <= t.sla_deadline
        )
        total_resolved = qs.filter(status__in=['resolved', 'closed']).count()
        data.append({
            'tech':     tech,
            'total':    qs.count(),
            'open':     qs.filter(status='open').count(),
            'progress': qs.filter(status='in_progress').count(),
            'resolved': total_resolved,
            'sla_ok':   sla_ok,
            'sla_pct':  round((sla_ok / resolved.count() * 100)
                              if resolved.count() else 0, 1),
        })

    data.sort(key=lambda x: x['total'], reverse=True)
    return render(request, 'reports/technician.html', {'data': data, 'days': days})