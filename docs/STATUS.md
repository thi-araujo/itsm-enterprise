# Status do projeto — ITSM Enterprise

> O Claude Code deve atualizar este arquivo ao concluir cada etapa.

## ✅ Fase 0 — Concluída

## ✅ Fase 1 — Concluída
- Login/logout, dashboard com estatísticas
- CRUD de tickets, categorias, prioridades, status
- SLA automático por prioridade

## ✅ Fase 2 — Concluída (2.1 + 2.2)
- SLA com alerta de vencimento (`is_sla_breached`, `sla_remaining_hours`) + comando `check_sla`
- Fila de atendimento com atribuição manual
- Comentários públicos e internos via HTMX
- Anexos no formulário de criação e na página do ticket
- Notificações internas + e-mail (backend de console em dev)
- CMDB (AssetType, Asset vinculado ao ticket)
- Relatórios com Chart.js (geral e por técnico)
- Acesso pela rede local (`runserver 0.0.0.0:8000`)

## 🔄 Fase 3 — Em andamento
### 3.0 — Refatoração (fazer primeiro)
- [x] Recriar `itsm_project/` (settings.py, urls.py, wsgi.py) — pasta estava ausente do projeto e do git
- [x] Criar comando de management `check_sla` (faltava, embora já citado aqui como concluído)
- [x] Remover o nome antigo do sistema de todo o código-fonte → "ITSM Enterprise"
      (inclui limpeza do `db.sqlite3`: 2 e-mails de usuário e 18 notificações antigas)
- [x] Mover apps para `apps/` mantendo labels (`name='apps.<app>'` + `label='<app>'` nos 6 apps)
- [x] Badges da sidebar (notificações não lidas, tickets sem técnico)
- [x] Mover `CLAUDE.md`, `docs/` e `.claude/` para a raiz — estavam em `itsm_enterprise_kit/`,
      então o Claude Code não lia as regras nem os slash commands
- [x] Política de upload centralizada em `settings.py` (estava duplicada em 5 lugares)
- [x] Avisar o usuário quando um anexo é rejeitado — antes era descartado em silêncio
- [x] `db.sqlite3` e `media/` fora do git (`.gitignore` + `git rm --cached`)
- [x] Trocar `except Exception: pass` por `logger.exception` em `tickets/views.py`
- [x] `fail_silently=False` + `logger` em `notifications/email.py` (o Django engolia erros de SMTP)
- [x] CSS inline do `base.html` → `static/css/itsm.css` (333 → 157 linhas no template)
- [x] Contadores de SLA viraram consulta no banco (`dashboard` e `reports`)
- [x] Imports duplicados do `reports/views.py`
- [x] Renomear "ITSM PRO" → "ITSM Enterprise" em 11 templates (12 ocorrências)
- [x] Primeira suíte de testes: 46 testes nos 6 apps (`python manage.py test`)

### ✅ Correção do CSS órfão — Concluída
O rename de classes tinha sido feito só no CSS: os templates escreviam `itsm-card`,
`stat-card`, `priority-badge`, `ticket-id`… e o CSS definia `.card-itsm`, `.stat`,
`.pbadge`, `.tid`. Nada estourava (o navegador ignora classe sem regra), então
**quase toda a folha de estilo estava inerte** — as telas só tinham o `style=` inline.
- [x] 16 grupos de seletores renomeados no `itsm.css` para o nome que os templates usam:
      `.card-itsm`→`.itsm-card`, `.t-itsm`→`.itsm-table`, `.stat`→`.stat-card`,
      `.stat-val/lbl/ico`→`.stat-value/label/icon`, `.pbadge`→`.priority-badge`,
      `.sbadge`→`.status-badge`, `.p-*`→`.badge-*`, `.s-*`→`.status-*`,
      `.tid`→`.ticket-id`, `.sla-breach`→`.sla-breached`, `.card-header-itsm`→`.itsm-card-header`
- [x] Badge de status voltou a ter a cor do status: os 6 lugares usavam
      `style="background:rgba(79,142,247,.1)…"` fixo (tudo azul) e agora usam
      `class="status-badge status-{{ ticket.status }}"`
- [x] `.toast-msg` ganhou `transition: opacity` — o JS de auto-dismiss zerava a
      opacidade de uma vez e o aviso sumia de supetão
- [x] 3 testes novos (`IdentidadeVisualTests`) que falham se CSS e templates
      voltarem a divergir — suíte total: **72 testes**

### Pendências conhecidas
- Variáveis CSS canônicas são sem prefixo (`--bg`, `--text`…) e os `--itsm-*` são apelidos;
  o CLAUDE.md pede o prefixo `--itsm-`. São 83 usos sem prefixo nos templates.
- Os templates reimplementam em `style=` inline o que o `itsm.css` já define:
  `.itsm-card-header`, `.comment-box`, `.att-item`, `.info-row`, `.empty-state`,
  `.section-title`, `.dot-*`, `.sla-ok`, `.sla-warn`, `.btn-outline-itsm` seguem
  definidos e sem uso. Trocar o inline por essas classes é o próximo passo do CSS.
- `report_dashboard` roda uma query por dia no gráfico de volume diário (até 30 queries).
- O JS de badges segue inline no `base.html` porque usa `{% url %}` — não dá para mover
  para um arquivo .js sem passar as URLs por outro caminho.

### ✅ 3.1 — RBAC — Concluída
- [x] Model `UserProfile` com perfil: solicitante, tecnico, gerente, admin
- [x] Criação automática do perfil via signal (padrão: solicitante; superuser nasce admin)
- [x] Solicitante vê e acessa apenas os próprios chamados (lista, detalhe, dashboard)
      — chamado alheio devolve **404**, não 403, para não vazar que ele existe
- [x] Técnico vê todos os chamados, fila e CMDB
- [x] Gerente/Admin veem tudo + relatórios
- [x] Sidebar oculta menus conforme o perfil
- [x] Notas internas invisíveis para solicitantes — filtradas **no queryset**,
      não escondidas no template (senão o texto ficaria no código-fonte da página)
- [x] `is_staff` deixou de significar "técnico": quem atende vem de `profile.role`
      (`is_staff` é só a permissão de acesso ao /admin/ do Django)
- [x] Usuário `tecnico1` criado para testar o perfil Técnico, e incluído no `seed_data.py`
- [x] Migração de dados `0002_popula_perfis_existentes` (reversível) para os usuários que já existiam
- [x] 23 testes novos de RBAC — suíte total: **69 testes**

**Quadro de acesso verificado:**

| Usuário | Papel | Fila | CMDB | Relatórios | Chamados visíveis |
|---|---|---|---|---|---|
| `admin` | Administrador | ✅ | ✅ | ✅ | 13 de 13 |
| `Thiago` | Administrador | ✅ | ✅ | ✅ | 13 de 13 |
| `tecnico1` | Técnico | ✅ | ✅ | ❌ | 13 de 13 |
| `Paulo` | Solicitante | ❌ | ❌ | ❌ | 1 de 13 |
| `Leandro` | Solicitante | ❌ | ❌ | ❌ | 2 de 13 |

### ✅ 3.2 — Fluxo de atendimento — Concluída
- [x] Campos `solution` e `resolved_by` no `Ticket` (`resolved_at` já existia)
      — `resolved_by` existe porque o `assignee` pode mudar depois da resolução
      e a trilha de quem resolveu se perderia
- [x] Botão **Finalizar chamado**: solução obrigatória (mínimo 10 caracteres),
      status vai a **Resolvido** e não a Fechado — no ITIL quem fecha é o
      solicitante, depois de confirmar
- [x] A solução entra no histórico como comentário público e vai no corpo do
      e-mail ao solicitante (antes o aviso dizia só "foi resolvido")
- [x] Botão **Escalonar**: destino obrigatório (só quem tem papel de equipe,
      e nunca o próprio usuário — ele sai do queryset do form) e motivo
      obrigatório com mínimo de 10 caracteres
- [x] Model `Escalation` com `from_user`/`to_user`/`reason`, ambos `SET_NULL`
      para o registro de auditoria sobreviver se o usuário for apagado
- [x] Escalonar troca o `assignee`, leva `open` → `in_progress` e notifica
      quem recebeu, com o motivo
- [x] Chamado resolvido ou fechado não finaliza nem escalona de novo
      (`Ticket.is_in_attendance`, com `can_be_finished`/`can_be_escalated`)
- [x] Histórico de escalonamento é interno: filtrado **no queryset**, como as
      notas internas. O solicitante vê a solução (é para ele) e não vê o motivo
- [x] Notificação `ticket_escalated` + `Escalation` no /admin/
- [x] 27 testes novos — suíte total: **99 testes**

**Migrações:** `tickets.0003_ticket_resolved_by_ticket_solution_escalation`
e `notifications.0002_alter_notification_type` (só `choices`, sem mudança de schema).

**Fluxo verificado no banco de desenvolvimento** (dentro de transação revertida,
nada foi gravado): `tecnico1` escalona para `Thiago` → `in_progress`; solução "ok"
recusada com aviso na tela; solução válida → `resolved` + `resolved_by`; o
solicitante vê a solução e **não** vê o motivo do escalonamento; os botões
desaparecem para ele e o de escalonar desaparece para a equipe após resolver.

### ✅ 3.3 — Workflows de aprovação — Concluída
- [x] `Category.requires_approval` — o gatilho fica na **categoria**, não no tipo
      do chamado, para a política ser um checkbox no /admin/ em vez de um deploy
- [x] Dois status novos: **Aguardando Aprovação** e **Rejeitado**, ambos fora do
      `<select>` do painel de gestão (`Ticket.WORKFLOW_STATUSES`) — são estados
      do workflow, não escolha do técnico. O Django valida contra as `choices`,
      então um POST forjado com eles também é recusado
- [x] **O SLA só começa a contar na aprovação** (`Ticket.start_sla`). Antes, um
      chamado crítico (SLA 2h) parado no fim de semana esperando o gerente
      nasceria já vencido, e o `check_sla` alertaria sobre um chamado que
      ninguém podia atender
- [x] Model `Approval` com `decided_by`/`decision`/`comment` (FK e `SET_NULL`,
      mesmo padrão da `Escalation`)
- [x] Fila de aprovação em `/tickets/aprovacoes/`, mais antigo primeiro, com
      badge de contagem na sidebar
- [x] Aprovar → status `open` + SLA iniciado + chamado entra na fila.
      Rejeitar → status `rejected` (terminal), motivo obrigatório (mín. 10 car.)
- [x] O parecer **o solicitante vê** — ao contrário do motivo de escalonamento,
      que é interno: ele precisa saber por que o pedido foi negado
- [x] O chamado pendente **não aparece** na fila dos técnicos nem no badge de
      "sem técnico", e o painel de gestão fica escondido até a aprovação
- [x] Notificações `approval_requested` (só para gerentes e admins, pois antes
      da decisão não há nada que um técnico faça) e `approval_decided`
- [x] Usuário `gerente1` criado para testar o perfil Gerente, e incluído no
      `seed_data.py` junto com a flag de aprovação da categoria de acesso
- [x] Badge do polling da sidebar passou a respeitar o perfil: antes o
      solicitante consultava o contador da fila a cada 60s e tomava um
      redirect silencioso
- [x] 34 testes novos — suíte total: **133 testes**

**Migrações:** `tickets.0004` (campo + status + model `Approval`),
`tickets.0005_categoria_acesso_exige_aprovacao` (dados, reversível) e
`notifications.0003_alter_notification_type` (só `choices`).

**Fluxo verificado no banco de desenvolvimento** (transação revertida, nada
gravado): chamado crítico em "Acesso e Permissões" nasce `pending_approval`
com `sla_deadline` nulo e fora da fila; técnico tentando aprovar leva 302;
`gerente1` vê na fila de aprovação; rejeitar sem motivo é recusado; aprovar
inicia o SLA em exatamente 2h e libera para a fila; `Paulo` vê o parecer e
não vê os botões; decidir duas vezes é recusado; categoria normal segue
nascendo `open` com SLA na abertura.

### Pendência desta fase
- Qualquer gerente/admin aprova qualquer chamado. O refinamento natural é a
  aprovação pelo gerente **do departamento** do solicitante — o campo
  `UserProfile.department` existe mas está preenchido só para `tecnico1` e
  `gerente1`.

### ✅ 3.4 — Auditoria — Concluída
- [x] Model `AuditLog` (ticket, user, action, field, old_value, new_value,
      description) com índice em `(ticket, -created_at)`
- [x] **Captura automática**: o `Ticket` guarda um retrato dos campos auditados
      no `from_db` e o `save()` compara. Alteração feita pela view, pelo
      `/admin/`, pelo `manage.py shell` ou pelo `check_sla` — todas registradas,
      sem depender de alguém lembrar de chamar o log
- [x] Campos acompanhados (`Ticket.AUDITED_FIELDS`): status, prioridade,
      técnico, categoria, prazo SLA, título e solução
- [x] `old_value`/`new_value` guardam **texto já formatado** ("Crítica",
      "Técnico Um"), não o código nem o id: se o usuário for renomeado ou
      apagado, a entrada continua dizendo o que estava escrito na época
- [x] `Ticket.save_as(user)` informa o autor; sem autor a tela mostra
      **"Sistema"** — correto para o `check_sla`
- [x] `TicketAdmin.save_model` preenche o autor nas alterações feitas pelo
      `/admin/` (verificado: a edição pelo admin aparece com o nome do usuário)
- [x] Eventos que não são mudança de campo registrados pelas views:
      `created`, `commented` (marcando nota interna), `attached` (com o nome do
      arquivo), `escalated`, `approved`, `rejected`
- [x] Cartão "Histórico de alterações" na página do chamado, **só para a
      equipe** e filtrado no queryset — "Prioridade: Crítica → Baixa" é
      conversa interna
- [x] `AuditLogAdmin` somente leitura (`has_add/change/delete_permission` →
      `False`): log de auditoria editável não é log de auditoria
- [x] 27 testes novos — suíte total: **160 testes**

**Migração:** `tickets.0006_auditlog`.

**Limitação conhecida e testada:** `QuerySet.update()` vai direto ao SQL e não
passa pelo `save()`, então não é auditado. Hoje o projeto só usa `update()` em
`sla_breach_notified`, que não está em `AUDITED_FIELDS`. Há um teste que fixa
esse comportamento (`test_update_do_queryset_nao_e_auditado`).

**Decisão:** `Escalation` e `Approval` continuam existindo. Eu havia sugerido
que o `AuditLog` os "unificaria" — estava errado: aqueles guardam dados
estruturados que o sistema consulta (motivo, decisão, parecer) e que a Fase 3.7
vai usar. O `AuditLog` é a trilha cronológica e **recebe** entradas deles.
Auditar os ativos do CMDB exigiria `ContentType`/`GenericForeignKey`; fica
registrado como caminho futuro, fora do escopo do ROADMAP ("log de todas as
ações **no chamado**").

**Linha do tempo verificada no banco real** (transação revertida): abertura →
aprovação (3 entradas: `approved`, Status, Prazo SLA) → técnico assume (Status,
Prioridade, Técnico) → nota interna → escalonamento (`escalated` + Técnico) →
finalização (Status, Solução). 12 entradas, nenhuma sem autor; `Paulo` não vê o
cartão nem o texto no HTML; salvar sem alterar nada não gera entrada.

### ✅ 3.7 — Automações por SLA — Concluída
- [x] `sla_started_at` no `Ticket` — sem saber quando o relógio começou não dá
      para dizer "já passou 80% do prazo". Calcular `sla_deadline - 24h` erraria
      se a prioridade tivesse sido alterada depois da abertura
- [x] Migração de dados `0008` (reversível) preenchendo `sla_started_at` com o
      `created_at` nos 13 chamados existentes — valor correto, nenhum deles
      passou por aprovação
- [x] `sla_elapsed_percent` e `sla_at_risk` no model; `start_sla()` da Fase 3.3
      passou a marcar o início
- [x] **Aviso prévio** a partir de `SLA_WARNING_PERCENT` (80%) — o tipo de
      notificação `sla_warning` existia desde a Fase 2 e nunca havia sido usado.
      Vai para o responsável, ou para a equipe se o chamado não tiver dono
- [x] **Escalonamento automático** do chamado vencido para o **gerente com
      menos chamados ativos** (desempate por `username`, para ser
      determinístico) — pegar sempre o primeiro empilharia tudo na mesma pessoa
- [x] Reaproveita `Escalation` (3.2) com `from_user` nulo e `AuditLog` (3.4)
      com autor nulo → a trilha mostra **"Sistema — Escalonou para Gerente Um"**
- [x] Pula o chamado que já está com gerente/admin (marca para não reavaliar,
      sem trocar o responsável) e não quebra se não houver nenhum gerente
- [x] **Não altera prioridade nem prazo**: a prioridade é a origem do SLA e
      mexer nela depois do vencimento apagaria a evidência do furo
- [x] Lógica em `apps/tickets/automation.py`, separada do comando — testável
      sem rodar o comando e reutilizável por Celery/API depois
- [x] `check_sla` ganhou `--dry-run` e `--quiet`; passou a usar
      `Ticket.CLOSED_STATUSES` em vez da lista `['resolved','closed']` cravada,
      que era de antes da Fase 3.3 e ignorava `rejected`
- [x] Limites em `settings.py` (`SLA_WARNING_PERCENT`, `SLA_AUTO_ESCALATE`),
      exercitados nos testes com `@override_settings`
- [x] Painel de SLA do chamado mostra "Prazo decorrido %" e a data do
      escalonamento automático
- [x] `docs/AUTOMACAO_SLA.md` com o comando pronto do Agendador de Tarefas
      do Windows (de 15 em 15 minutos) e `logs/` no `.gitignore`
- [x] 41 testes novos — suíte total: **201 testes**

**Migrações:** `tickets.0007` (3 campos) e `tickets.0008_preenche_sla_started_at`
(dados, reversível).

**Idempotência:** `sla_warning_notified`, `sla_breach_notified` e
`sla_escalated_at` garantem que rodar de 15 em 15 minutos não repete trabalho.

**Execução real verificada no banco de desenvolvimento** (transação revertida):
1 aviso de risco a 85% do prazo; 9 chamados vencidos processados — 7 repassados
e distribuídos entre `admin`, `Thiago` e `gerente1` (**3 chamados ativos para
cada um**, carga equilibrada), 2 pulados por já estarem com a gerência; trilha
mostrando "Sistema"; **segunda execução não repetiu nada** (0 · 0 · 0).

> ⚠️ A primeira execução real vai processar o acúmulo dos 9 chamados vencidos
> de uma vez, com os e-mails correspondentes. Rode `--dry-run` antes.

### 3.5, 3.6 e 3.8
- [ ] API REST (DRF)
- [ ] Dashboard avançado
- [ ] Automações (escalonamento por SLA)
- [ ] Integração AD/LDAP
