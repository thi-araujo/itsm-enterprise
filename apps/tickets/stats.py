"""Agregações de chamados (Fase 3.6).

Mesmo princípio do `services.py`: a conta mora num lugar só. Três consumidores
usam estas funções — a API (`/api/v1/estatisticas/`), o dashboard e os
relatórios. Antes a agregação estava duplicada entre a API e os relatórios; com
o dashboard entrando, viraria uma terceira cópia.

Todas as funções recebem um **queryset**, nunca o model. Assim quem chama
decide o recorte — e, principalmente, aplica o `visible_to` do RBAC antes:
o solicitante vê os números dos próprios chamados.
"""

from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

# Status que contam como "o atendimento terminou bem". Diferente de
# Ticket.CLOSED_STATUSES, que inclui 'rejected' — um chamado rejeitado foi
# encerrado, mas não foi resolvido.
STATUS_RESOLVIDOS = ('resolved', 'closed')

# Máximo de pontos no gráfico de volume diário.
MAX_DIAS_NO_GRAFICO = 90


def _contagem_por(queryset, campo):
    """`{valor: quantidade}` para um campo de escolhas."""
    return {item[campo]: item['count']
            for item in queryset.values(campo).annotate(count=Count('id'))}


def volume_diario(queryset, dias=30):
    """Série `[{'dia': 'dd/mm', 'total': n}]` dos últimos `dias`.

    Uma consulta só. A versão anterior fazia um `count()` por dia — até 30
    consultas para montar um gráfico. `TruncDate` agrupa no banco.

    Os dias sem chamado não voltam do banco (não existe linha para eles), e
    sem preencher com zero o gráfico ficaria com buracos. Por isso a série é
    montada em Python a partir do dicionário.
    """
    dias = max(1, min(dias, MAX_DIAS_NO_GRAFICO))
    hoje = timezone.localdate()
    primeiro_dia = hoje - timezone.timedelta(days=dias - 1)

    por_dia = {
        item['dia']: item['total']
        for item in (queryset
                     .filter(created_at__date__gte=primeiro_dia)
                     .annotate(dia=TruncDate('created_at'))
                     .values('dia')
                     .annotate(total=Count('id')))
    }

    serie = []
    for deslocamento in range(dias):
        dia = primeiro_dia + timezone.timedelta(days=deslocamento)
        serie.append({'dia': dia.strftime('%d/%m'),
                      'total': por_dia.get(dia, 0)})
    return serie


def cumprimento_de_sla(queryset):
    """Percentual dos chamados resolvidos que ficaram dentro do prazo.

    Considera só os que têm prazo e data de resolução — um chamado sem SLA
    definido não pode ser julgado cumprido nem furado. A comparação é feita
    no banco com `F()`, sem trazer os registros para a memória.
    """
    resolvidos = queryset.filter(status__in=STATUS_RESOLVIDOS,
                                 resolved_at__isnull=False,
                                 sla_deadline__isnull=False)
    total = resolvidos.count()
    if not total:
        return {'no_prazo': 0, 'atrasados': 0, 'avaliados': 0, 'percentual': None}

    no_prazo = resolvidos.filter(resolved_at__lte=F('sla_deadline')).count()
    return {
        'no_prazo':   no_prazo,
        'atrasados':  total - no_prazo,
        'avaliados':  total,
        'percentual': round(no_prazo / total * 100, 1),
    }


def tempo_medio_de_resolucao_horas(queryset):
    """Média de horas entre a abertura e a resolução.

    Devolve None quando não há nada resolvido — melhor que zero, que seria
    lido como "resolvemos instantaneamente".
    """
    media = (queryset
             .filter(status__in=STATUS_RESOLVIDOS, resolved_at__isnull=False)
             .aggregate(media=Avg(F('resolved_at') - F('created_at')))['media'])
    if media is None:
        return None
    return round(media.total_seconds() / 3600, 1)


def estatisticas_de(queryset, dias=None):
    """Todos os números do dashboard de uma vez.

    `dias` recorta por período e é ecoado na resposta, para o cliente saber
    de que janela os números vieram.
    """
    if dias:
        desde = timezone.now() - timezone.timedelta(days=dias)
        queryset = queryset.filter(created_at__gte=desde)

    from .models import Ticket   # import local: evita ciclo com models.py

    agora = timezone.now()
    em_aberto = queryset.exclude(status__in=Ticket.CLOSED_STATUSES)

    return {
        'periodo_dias':    dias,
        'total':           queryset.count(),
        'por_status':      _contagem_por(queryset, 'status'),
        'por_prioridade':  _contagem_por(queryset, 'priority'),
        'por_tipo':        _contagem_por(queryset, 'ticket_type'),
        'em_aberto':       em_aberto.count(),
        'sem_tecnico':     em_aberto.filter(assignee__isnull=True).count(),
        'sla_vencido':     em_aberto.filter(sla_deadline__lt=agora).count(),
        'sla_em_risco':    _contar_em_risco(em_aberto),
        'aguardando_aprovacao': queryset.filter(status='pending_approval').count(),
        'resolvidos':      queryset.filter(status__in=STATUS_RESOLVIDOS).count(),
        'sla_cumprimento': cumprimento_de_sla(queryset),
        'tempo_medio_resolucao_horas': tempo_medio_de_resolucao_horas(queryset),
        'por_categoria': _top_categorias(queryset),
        'por_tecnico':   _top_tecnicos(queryset),
        'volume_diario': volume_diario(queryset, dias or 30),
    }


def _top_categorias(queryset, limite=6):
    """`[{'nome', 'total'}]` — chaves limpas, e não o `category__name` cru do
    ORM, porque isto vai no JSON público da API."""
    return [{'nome': item['category__name'], 'total': item['count']}
            for item in (queryset.exclude(category__isnull=True)
                         .values('category__name')
                         .annotate(count=Count('id'))
                         .order_by('-count')[:limite])]


def _top_tecnicos(queryset, limite=10):
    """`[{'username', 'nome', 'total'}]` com o nome já montado."""
    resultado = []
    for item in (queryset.exclude(assignee__isnull=True)
                 .values('assignee__username', 'assignee__first_name',
                         'assignee__last_name')
                 .annotate(count=Count('id')).order_by('-count')[:limite]):
        nome = f"{item['assignee__first_name']} {item['assignee__last_name']}".strip()
        resultado.append({
            'username': item['assignee__username'],
            'nome':     nome or item['assignee__username'],
            'total':    item['count'],
        })
    return resultado


def _contar_em_risco(em_aberto):
    """Quantos passaram do limite de aviso do SLA sem vencer (Fase 3.7).

    O percentual decorrido é uma razão entre dois intervalos e depende de
    `sla_started_at`, então é calculado em Python — mas sobre um queryset já
    estreitado aos que ainda têm prazo correndo.
    """
    agora = timezone.now()
    candidatos = em_aberto.filter(sla_deadline__gt=agora,
                                  sla_deadline__isnull=False)
    return sum(1 for ticket in candidatos if ticket.sla_at_risk)
