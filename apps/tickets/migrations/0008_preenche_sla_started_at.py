"""Preenche `sla_started_at` nos chamados que já existiam.

Para eles, `created_at` é exatamente o momento em que o relógio começou:
nenhum passou pelo workflow de aprovação (Fase 3.3), que é o único caso em
que a contagem começa depois da abertura.

Sem isso, `sla_elapsed_percent` cairia no `created_at` por fallback — o
resultado seria o mesmo, mas o campo ficaria nulo para sempre e a origem do
número ficaria implícita. Preencher deixa o dado explícito.

Reversível: o `migrate tickets 0007` devolve os campos para nulo.
"""

from django.db import migrations


def preencher(apps, schema_editor):
    Ticket = apps.get_model('tickets', 'Ticket')
    # Só quem tem prazo: chamado aguardando aprovação tem sla_deadline nulo e
    # o relógio dele ainda não começou.
    for ticket in Ticket.objects.filter(sla_deadline__isnull=False,
                                        sla_started_at__isnull=True):
        ticket.sla_started_at = ticket.created_at
        # update direto no banco: o save() do model dispararia a auditoria
        # (Fase 3.4) e encheria a trilha de entradas de uma migração.
        Ticket.objects.filter(pk=ticket.pk).update(
            sla_started_at=ticket.created_at)


def limpar(apps, schema_editor):
    Ticket = apps.get_model('tickets', 'Ticket')
    Ticket.objects.update(sla_started_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0007_ticket_sla_escalated_at_ticket_sla_started_at_and_more'),
    ]

    operations = [
        migrations.RunPython(preencher, limpar),
    ]
