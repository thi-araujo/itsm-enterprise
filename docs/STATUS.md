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
- ~~`report_dashboard` roda uma query por dia no gráfico de volume diário~~
  **resolvido na Fase 3.6** (`TruncDate` em `apps/tickets/stats.py`, travado por
  `assertNumQueries(1)`).
- O JS de badges segue inline no `base.html` porque usa `{% url %}`. A Fase 3.6
  mostrou o caminho: passar a URL por `data-attribute` (foi o que o
  `static/js/dashboard.js` fez). Falta aplicar no `base.html`.

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

### ✅ 3.5 — API REST (DRF) — Concluída
**Refactor que sustenta a fase:** as regras que mudam o estado de um chamado
(finalizar, escalonar, decidir aprovação, comentar) saíram das views para
`apps/tickets/services.py`. A tela HTML e a API chamam **a mesma função** — sem
isso haveria duas implementações da mesma regra, divergindo na primeira
mudança. Os 201 testes existentes foram a rede de segurança: passaram todos
depois do refactor, sem alteração.

- [x] `djangorestframework>=3.15` — única dependência nova
- [x] App `apps/api/` (`serializers.py`, `views.py`, `permissions.py`, `urls.py`)
      com prefixo versionado **`/api/v1/`**
- [x] Autenticação por **token** (`POST /api/v1/token/`) e por **sessão**
      (API navegável no browser). O token vem primeiro no settings de
      propósito: só ele monta o desafio, então sem credencial a resposta é
      **401** e não 403
- [x] **O RBAC da Fase 3.1 vale na API de graça**: `get_queryset()` usa
      `Ticket.objects.visible_to(user)`. Chamado alheio devolve **404**, como
      no HTML
- [x] Notas internas filtradas no queryset — não trafegam para o solicitante
- [x] `IsStaff` / `IsManagement` / `ReadOnlyOrStaff` espelhando os decorators,
      lendo as mesmas propriedades do `UserProfile`
- [x] Ações: `finalizar`, `escalonar`, `aprovar`, `rejeitar`, `comentarios`,
      `anexos`, `escalonamentos`, `auditoria`, `aprovacoes`
- [x] `/eu/` devolve papel e permissões, para o cliente não adivinhar
- [x] `/estatisticas/` com números agregados já filtrados por perfil — é o
      endpoint que a **Fase 3.6** vai consumir
- [x] `/categorias/` e `/ativos/` (somente leitura), `/tecnicos/`
- [x] Filtros iguais aos da tela (`status`, `priority`, `assignee=me|unassigned`,
      `search`, `ordering`), paginação de 25 e throttling (20/min anônimo,
      1000/h autenticado)
- [x] Status do workflow fora do `PATCH`: o serializer remove
      `pending_approval` e `rejected` das `choices`, e o DRF recusa um PATCH
      forjado sem validação extra — mesma técnica do formulário HTML
- [x] `DELETE` não existe em chamado (405): o histórico é o registro
- [x] `docs/API.md` com endpoints, exemplos de `curl` e tabela de erros
- [x] 60 testes novos — suíte total: **261 testes**

**Três bugs que os testes pegaram** (e que teriam passado despercebidos):
1. `serializer.save()` na abertura gravava o chamado **sem autor**, então a
   entrada "Abriu o chamado" saía como "Sistema". Corrigido montando a
   instância antes e salvando uma vez com `save_as` — o que também fez o
   status de aprovação valer já no INSERT, deixando o SLA nulo naturalmente.
2. O mesmo no `PATCH`: o `_audit_user` agora vai na instância **antes** do
   `serializer.save()`.
3. O solicitante recebia **403 ao comentar** no próprio chamado, porque a
   permissão de escrita do ViewSet valia para a ação `comentarios`.

**Verificado com `curl` contra o servidor rodando:** 401 sem credencial;
token obtido por usuário+senha; abertura (201); solução "ok" recusada com
**a mesma mensagem da tela**; `PATCH` assumindo o chamado (200); `PATCH` com
`status=rejected` recusado (400); finalização (200); e a trilha de auditoria
com o autor correto em todas as cinco entradas. O chamado de teste foi
removido do banco.

### ✅ 3.6 — Dashboard avançado — Concluída
- [x] `apps/tickets/stats.py` — uma fonte para as agregações, usada pela API,
      pelo dashboard e pelos relatórios. Antes a conta estava duplicada entre a
      API e os relatórios; com o dashboard entrando, viraria uma terceira cópia
- [x] **Pendência nº 3 resolvida**: o volume diário fazia um `count()` por dia
      (até 30 consultas para um gráfico). Agora é **uma** consulta com
      `TruncDate`, e o teste usa `assertNumQueries(1)` — se o laço voltar, falha
- [x] Os dias sem chamado são preenchidos com zero em Python: o banco não
      devolve linha para dia vazio e o gráfico ficaria com buracos
- [x] **Pendência nº 4 encaminhada**: o JS do dashboard vive em
      `static/js/dashboard.js`, com a URL da API chegando por
      `data-stats-url` — era o que faltava para tirar o JS do template
- [x] `/api/v1/estatisticas/` ganhou `volume_diario`, `por_tipo`,
      `sla_cumprimento`, `tempo_medio_resolucao_horas`, `sla_em_risco`,
      `resolvidos` e `periodo_dias`
- [x] Chaves limpas no JSON (`{nome, total}`), e não o `category__name` cru do
      ORM — é contrato público. Template dos relatórios ajustado
- [x] **A view continua calculando a primeira carga**: se o `fetch` falhar, a
      página mostra números corretos em vez de zeros, e o aviso vira
      "falha ao atualizar (dados da última carga)"
- [x] Seletor de período (Tudo / 7 / 30 / 90 dias) sem recarregar a página, e
      atualização automática a cada 60s com "atualizado às HH:MM"
- [x] Três gráficos Chart.js: rosca por status, barras por prioridade, linha do
      volume diário. Atualizados com `.update()` em vez de recriados, para não
      piscar nem vazar instâncias
- [x] Dois KPIs novos para a equipe: **cumprimento de SLA** e **tempo médio de
      resolução**; mais "SLA em risco" e "sem técnico"
- [x] O solicitante **não** vê os KPIs de gestão nem recebe `por_tecnico` /
      `sla_cumprimento` / `sem_tecnico` no JSON — são números da equipe
- [x] `report_dashboard` aceita `?days=abc` sem quebrar (antes estourava
      `ValueError`) e usa `CLOSED_STATUSES` no contador de atrasados
- [x] 32 testes novos — suíte total: **293 testes**

**Detalhe de implementação:** `stats.STATUS_RESOLVIDOS` é `('resolved',
'closed')`, de propósito diferente de `Ticket.CLOSED_STATUSES`, que inclui
`rejected`. Um chamado rejeitado foi encerrado, mas **não** foi resolvido — e
contá-lo distorceria o cumprimento de SLA. Há teste para isso.

**Verificado no navegador** (servidor rodando): `dashboard.js` servido (HTTP
200); endpoint devolvendo os 7 campos novos; `tecnico1` e `gerente1` com os
KPIs e os 3 gráficos; `Paulo` sem os KPIs, com `data-pode-gerenciar="0"` e
total 1 contra 13 da equipe.

### ✅ 3.8 — Integração AD/LDAP — Concluída
- [x] **`ldap3` em vez de `django-auth-ldap`**: o caminho usual depende do
      `python-ldap`, extensão em C que **não compila** nesta máquina
      (`Unable to find a compatible Visual Studio installation`, sem wheel
      para Windows/Python 3.14). O `ldap3` é Python puro e o backend de
      autenticação são ~120 linhas — com o bônus de deixar o mapeamento
      grupo → papel explícito em código
- [x] `apps/accounts/ldap_client.py` — a única parte que sabe o que é LDAP.
      Separado do backend justamente para os testes poderem trocá-lo
- [x] `apps/accounts/ldap_backend.py` — `LdapBackend`, e o
      `AUTHENTICATION_BACKENDS` com o **ModelBackend atrás**: o controlador
      de domínio cair não pode trancar ninguém fora do sistema
- [x] Provisionamento **just-in-time**: o usuário é criado no primeiro login
      com nome, e-mail e departamento lidos do diretório. Sem importação em
      massa — quem nunca entrar não ocupa linha no banco
- [x] **Senha do AD não é guardada** (`set_unusable_password`): senão uma
      cópia do hash ficaria no `db.sqlite3` e trocar a senha no domínio não
      revogaria o acesso ao ITSM
- [x] Papel pelo grupo do AD (`LDAP_GROUP_ROLE_MAP`), **lista ordenada** e não
      dicionário: o primeiro que casar vence, então quem está em `ITSM-Admins`
      e `ITSM-Tecnicos` sai como Administrador em vez de depender da ordem em
      que o AD devolveu os grupos
- [x] Busca do usuário com `iexact`: o `sAMAccountName` do AD não diferencia
      maiúsculas e o `username` do Django sim — sem isso, o AD devolvendo
      `Thiago` criaria uma segunda conta ao lado do `thiago` existente
- [x] **Usuário que já existia não é rebaixado**: sem grupo casando, o papel
      atual é mantido. Senão o `thiago` (Administrador criado à mão) viraria
      Solicitante no primeiro login pelo AD. A senha local também é preservada
- [x] `UserProfile.from_ldap` e `ldap_last_sync`, com a coluna **Origem**
      ("Active Directory" / "Local") na lista de usuários do `/admin/` — antes
      de tentar redefinir a senha de alguém por lá
- [x] **`manage.py ldap_check`**: separa DNS, porta, TLS e bind, e o
      `--user <conta>` imprime os **grupos reais** da pessoa e o papel que ela
      receberia. Sem ele, configurar o mapa de grupos seria tentativa e erro
      às cegas. A senha é pedida por `getpass`, nunca por argumento
- [x] `apps/accounts/checks.py` — 4 avisos no `manage.py check`
      (`ldap.W001`..`W004`) para configuração perigosa aparecer no terminal de
      quem sobe o sistema, e não só na documentação
- [x] Tela de login avisa "use seu usuário e senha de rede do domínio
      exemplo.local" quando o AD está ligado
- [x] Tudo por variável de ambiente (`ITSM_LDAP_*`) e **desligado por padrão**:
      a suíte não toca a rede e quem clonar o projeto não trava no login
- [x] Nome com queda para trás: conta sem `givenName`/`sn` (comum em AD
      montado à mão) tem o nome lido do `displayName` ou do CN do DN — senão o
      ITSM mostraria `joao.silva` em toda tela em vez de "Thiago Araujo"
- [x] `ldap_check --user` avisa quando a conta não tem `mail` no AD: o ITSM
      manda e-mail em abertura, comentário, resolução e vencimento de SLA, e
      sem endereço essas mensagens não têm para onde ir
- [x] `ldap_check --user <conta> --list` confere as contas do diretório em
      massa: mostra o que o ITSM leria de cada uma e o papel resultante,
      usando as mesmas funções do login. Exclui contas de computador, que no
      AD também têm `objectClass=user`
- [x] **`Domain Users` → Solicitante**: todo usuário do domínio entra e abre
      chamado pelo `LDAP_DEFAULT_ROLE`, sem configuração. O grupo **não** foi
      acrescentado ao `LDAP_GROUP_ROLE_MAP` de propósito: ele casaria com
      *toda* conta, e casar sobrescreve o papel — o Técnico promovido à mão
      em /admin/ voltaria a Solicitante no login seguinte. 4 testes
      (`DomainUsersAbreChamadoTests`) travam isso, um deles demonstrando o
      rebaixamento que o acréscimo causaria
- [x] **Motivo real da recusa do AD** (`MOTIVOS_AD` + `_motivo_da_recusa`): o
      LDAP recusa todo bind como `invalidCredentials` e esconde a causa no
      campo `data` do texto de diagnóstico. Sem decodificar, "senha errada" e
      "precisa trocar a senha no próximo logon" (`data 773` — o estado
      **padrão** de toda conta nova no AD, que faz a conta nunca entrar) são
      a mesma mensagem. O `ldap_check --user` agora nomeia a causa e diz o que
      fazer, e separa isso de "bind aceito mas a conta não apareceu na busca"
      (base errada × sem permissão de leitura), que era o outro caminho de
      recusa silenciosa
- [x] **Busca da conta pelo `sAMAccountName` ou pelo `userPrincipalName`**:
      no AD os dois são campos independentes e o bind simples é validado
      contra o **UPN**. A conta cujo nome curto não é o prefixo do UPN
      (`lara@dominio` + `sAMAccountName=lara.souza`) autenticava e não era
      encontrada — busca com `success` e zero entradas, senha aceita e login
      falhando em seguida, sem o usuário chegar a ser criado. Era a causa real
      de "só o administrador entra". O `username` gravado no Django é sempre o
      `sAMAccountName` real, e o `ldap_check` mostra os dois identificadores e
      avisa quando divergem
- [x] `ldap_check --user <conta> --list` passou a rodar **mesmo quando a conta
      do `--user` não é encontrada**: o bind passou, a credencial serve para
      consultar, e é nesse caso que a listagem resolve a dúvida
- [x] 81 testes novos — suíte total: **374 testes**

**Migração:** `accounts.0003_userprofile_from_ldap_userprofile_ldap_last_sync`.

**Dependência nova:** `ldap3>=2.9` (único acréscimo ao `requirements.txt`).

**Levantamento real do domínio** (14/10/2026): `exemplo.local` resolve para
`192.168.10.4`; o DC é `dc01.exemplo.local` pelo registro SRV; **LDAP na 389
responde** e a base `DC=exemplo,DC=local` foi confirmada pelos naming contexts
do servidor. **Bind real validado** com `joao.silva` na 389: 7 grupos
lidos, papel resolvido como Administrador. **O `LDAP_GROUP_ROLE_MAP` tem só
`Domain Admins`**: no levantamento, todos os grupos do domínio (fora os
internos do Windows) eram de File Server, concedidos por GPO — mapeá-los daria
privilégio de atendimento a quem só recebeu acesso a um compartilhamento. O papel de Técnico/Gerente é dado à mão
em /admin/, e o login seguinte não desfaz (sem grupo casando, o papel atual é
mantido). `MapaDeGruposDoProjetoTests` falha quando o mapa cresce.

> ⚠️ **O DC não tem certificado de servidor instalado.** A 636 abre a conexão
> TCP e derruba o TLS (`WinError 10054`); o StartTLS na 389 responde
> `unavailable`. Mesma causa nos dois. Desligar `ITSM_LDAP_TLS_VALIDATE`
> **não** resolve — não há certificado para validar. O padrão do projeto
> continua 636 com validação ligada, de propósito: instalar o AD CS
> (Enterprise CA) faz o LDAPS passar a funcionar sem mudar nada aqui. O
> atalho é `ITSM_LDAP_PORT=389`, com a senha de domínio em texto claro na
> rede — e o `manage.py check` reclamando. Ver `docs/AD_LDAP.md`.

**Dois testes de segurança que merecem destaque:** senha em branco não chega
ao servidor (bind com senha vazia é bind **anônimo**, que o AD aceita — a
autenticação "passaria" em branco); e username com curinga não casa com
qualquer conta (o que a pessoa digita é escapado antes de entrar no filtro
LDAP — mesma classe de problema que SQL injection).

**Não implementado, de propósito:** SSO (Kerberos/SPNEGO) exigiria `gssapi`
— outra extensão em C, mesmo problema do `python-ldap` — e que a máquina
estivesse no domínio (esta está em `WORKGROUP`). Desativação automática de
conta demitida exigiria rotina periódica, como o `check_sla`.

### Pendência desta fase
- Conta desabilitada no AD deixa de autenticar, mas segue existindo e
  aparecendo nos seletores do ITSM até alguém desativá-la no `/admin/`.
- A aprovação por departamento (pendência da Fase 3.3) ficou **mais perto**:
  o `UserProfile.department` agora é preenchido pelo diretório, que era o
  dado que faltava.
