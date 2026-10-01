from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tickets.models import Ticket
from apps.notifications.email import notify_sla_breach


class Command(BaseCommand):
    help = "Verifica tickets com SLA vencido e dispara notificações."

    def handle(self, *args, **options):
        tickets_vencidos = Ticket.objects.exclude(
            status__in=['resolved', 'closed']
        ).filter(
            sla_deadline__lt=timezone.now(),
            sla_breach_notified=False,
        )

        total = tickets_vencidos.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nenhum ticket com SLA vencido encontrado."))
            return

        for ticket in tickets_vencidos:
            notify_sla_breach(ticket)
            self.stdout.write(
                self.style.WARNING(f"SLA vencido notificado: ticket #{ticket.pk:04d} — {ticket.title}")
            )

        self.stdout.write(self.style.SUCCESS(f"Total de tickets notificados: {total}"))
