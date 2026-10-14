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

### 3.2 — Fluxo de atendimento
- [ ] Campo **Solução** no ticket
- [ ] Botão **Finalizar chamado** (exige solução, muda status, notifica solicitante)
- [ ] **Escalonar** para outro técnico/membro da equipe com motivo
- [ ] Histórico de escalonamentos (model próprio)

### 3.3 a 3.8
- [ ] Workflows de aprovação
- [ ] API REST (DRF)
- [ ] Auditoria
- [ ] Dashboard avançado
- [ ] Automações (escalonamento por SLA)
- [ ] Integração AD/LDAP
