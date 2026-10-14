"""Verifica os SLAs e dispara as automações (Fase 3.7).

Feito para rodar sozinho, de 15 em 15 minutos, no Agendador de Tarefas do
Windows. A lógica fica em apps/tickets/automation.py — aqui só a casca que
lê as opções e imprime o resultado.

    python manage.py check_sla
    python manage.py check_sla --dry-run    # mostra sem gravar nada
    python manage.py check_sla --quiet      # só o resumo final
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tickets.automation import executar_automacoes


class Command(BaseCommand):
    help = ("Avisa os SLAs em risco, notifica os vencidos e escalona "
            "automaticamente para a gerência.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Mostra o que seria feito sem gravar nada no banco.')
        parser.add_argument(
            '--quiet', action='store_true',
            help='Imprime só o resumo final (para o log do agendador).')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        quiet   = options['quiet']

        if dry_run and not quiet:
            self.stdout.write(self.style.WARNING(
                'MODO SIMULAÇÃO (--dry-run): nada será gravado.'))
            # O destino é escolhido pelo gerente com menos chamados ativos.
            # Como a simulação não grava, a carga não muda entre um chamado e
            # o seguinte e todos acabam apontando para a mesma pessoa. Numa
            # execução real a distribuição se reequilibra a cada atribuição.
            self.stdout.write(
                '  Atenção: na simulação os destinos se repetem, porque a '
                'carga de cada\n  gerente não muda sem gravar. Na execução '
                'real a distribuição se reequilibra.')

        resumo = executar_automacoes(dry_run=dry_run)

        if not quiet:
            self._listar(
                resumo['avisados'],
                f"SLA em risco (acima de {settings.SLA_WARNING_PERCENT}% do prazo)",
                self.style.WARNING,
                lambda t: f"{t.sla_elapsed_percent}% do prazo")

            self._listar(
                resumo['vencidos'], "SLA vencido — equipe notificada",
                self.style.ERROR,
                lambda t: f"venceu em {timezone.localtime(t.sla_deadline):%d/%m %H:%M}")

            if settings.SLA_AUTO_ESCALATE:
                self._listar_escalonamentos(resumo['escalonados'])
            else:
                self.stdout.write(
                    '\nEscalonamento automático desligado '
                    '(SLA_AUTO_ESCALATE = False no settings).')

        total = sum(len(v) for v in resumo.values())
        estilo = self.style.SUCCESS if total == 0 else self.style.WARNING
        prefixo = '[simulação] ' if dry_run else ''
        self.stdout.write(estilo(
            f"\n{prefixo}{len(resumo['avisados'])} aviso(s) de risco · "
            f"{len(resumo['vencidos'])} vencimento(s) notificado(s) · "
            f"{len(resumo['escalonados'])} escalonamento(s) automático(s)."))

    # ── Saída ─────────────────────────────────────────────────────

    def _listar(self, tickets, titulo, estilo, detalhe):
        self.stdout.write(f"\n{titulo}: {len(tickets)}")
        for ticket in tickets:
            self.stdout.write(estilo(
                f"  #{ticket.pk:04d} {ticket.title[:50]:<52} {detalhe(ticket)}"))

    def _listar_escalonamentos(self, escalonados):
        self.stdout.write(f"\nEscalonamento automático: {len(escalonados)}")
        for ticket, destino in escalonados:
            if destino is None:
                self.stdout.write(
                    f"  #{ticket.pk:04d} {ticket.title[:50]:<52} "
                    f"sem troca de responsável")
            else:
                nome = destino.get_full_name() or destino.username
                self.stdout.write(self.style.WARNING(
                    f"  #{ticket.pk:04d} {ticket.title[:50]:<52} → {nome}"))
