# Automações de SLA — como rodar e como agendar

Fase 3.7. A lógica está em `apps/tickets/automation.py`; o comando
`manage.py check_sla` é só a casca que imprime o resultado.

## O que o comando faz

Três passagens, nesta ordem:

| # | Passagem | Quando age | O que faz |
|---|---|---|---|
| 1 | **Aviso prévio** | passou de `SLA_WARNING_PERCENT` do prazo e ainda não venceu | notifica o técnico responsável (ou a equipe, se não houver) |
| 2 | **Vencimento** | prazo estourado | notifica a equipe (o que o comando já fazia antes) |
| 3 | **Escalonamento automático** | prazo estourado | repassa o chamado ao gerente com menos carga |

A ordem importa: avisar antes de notificar o vencimento evita mandar "está
acabando" depois de "já venceu".

## Comandos

```powershell
.\venv\Scripts\Activate.ps1

python manage.py check_sla              # execução normal
python manage.py check_sla --dry-run    # mostra o que faria, sem gravar nada
python manage.py check_sla --quiet      # só o resumo (para o log do agendador)
```

**Rode o `--dry-run` primeiro.** Se o sistema ficou um tempo sem rodar o
comando, a primeira execução real processa todo o acúmulo de uma vez —
vários escalonamentos e vários e-mails no mesmo instante. O `--dry-run`
mostra o tamanho do acúmulo antes.

> No `--dry-run` os destinos se repetem, porque a carga de cada gerente não
> muda sem gravar. Na execução real a distribuição se reequilibra a cada
> atribuição.

## Configuração (`itsm_project/settings.py`)

```python
SLA_WARNING_PERCENT = 80      # avisa a partir de 80% do prazo
SLA_AUTO_ESCALATE   = True    # False desliga só o escalonamento
```

As horas de cada prioridade (Crítica 2h · Alta 8h · Média 24h · Baixa 72h)
ficam em `Ticket.sla_hours_for_priority`.

## Agendar no Windows (Agendador de Tarefas)

Rodando de 15 em 15 minutos. **Execute o PowerShell como Administrador** e
ajuste o caminho se o projeto estiver em outra pasta:

```powershell
$projeto = "C:\Users\Thiago\PycharmProjects\itsm_enterprise"
$python  = "$projeto\venv\Scripts\python.exe"

schtasks /Create `
  /TN "ITSM Enterprise - check_sla" `
  /TR "cmd /c cd /d `"$projeto`" && `"$python`" manage.py check_sla --quiet >> `"$projeto\logs\check_sla.log`" 2>&1" `
  /SC MINUTE /MO 15 /RL LIMITED /F
```

Antes da primeira execução, crie a pasta do log:

```powershell
New-Item -ItemType Directory -Force "$projeto\logs"
```

Conferir, rodar na hora e remover:

```powershell
schtasks /Query  /TN "ITSM Enterprise - check_sla" /V /FO LIST
schtasks /Run    /TN "ITSM Enterprise - check_sla"
schtasks /Delete /TN "ITSM Enterprise - check_sla" /F
```

O log vai para `logs\check_sla.log` (a pasta `logs/` está no `.gitignore`).

### Observações

- A tarefa roda independentemente do `runserver`: ela usa o mesmo banco, não
  a aplicação web.
- Em produção com PostgreSQL, o caminho natural é trocar o Agendador por
  Celery Beat — as funções de `automation.py` já estão separadas do comando
  justamente para isso.

## Idempotência

O comando pode rodar quantas vezes quiser sem repetir trabalho. Três campos
de controle no `Ticket`:

| Campo | Impede |
|---|---|
| `sla_warning_notified` | reenviar o aviso prévio |
| `sla_breach_notified` | reenviar o aviso de vencimento |
| `sla_escalated_at` | escalonar o mesmo chamado duas vezes |

## O que as automações *não* fazem

- **Não alteram a prioridade.** Ela é o que define o prazo; mexer nela depois
  do vencimento apagaria a evidência de que o SLA foi furado e distorceria os
  relatórios.
- **Não alteram o `sla_deadline`.** O prazo original fica como registro.
- **Não reatribuem** um chamado que já está com gerente ou admin — repassar
  de gerente para gerente é só ruído. O chamado é marcado para não voltar a
  ser avaliado.
- **Não quebram** se não houver nenhum gerente cadastrado: registram um
  aviso no log e seguem.

## Rastro das ações automáticas

Toda ação automática é gravada com autor nulo, e a trilha de auditoria
(Fase 3.4) mostra isso como **"Sistema"**:

```
Sistema    Escalonou — SLA vencido — para Gerente Um
Sistema    Técnico Responsável: — → Gerente Um
```

O escalonamento também cria uma `Escalation` (Fase 3.2) com `from_user`
nulo e o motivo preenchido:

> *Escalonamento automático: SLA vencido em 28/05/2026 16:46. Prioridade Alta.*
