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

### 3.1 — RBAC
- [ ] Model `UserProfile` com perfil: solicitante, tecnico, gerente, admin
- [ ] Criação automática do perfil via signal (padrão: solicitante)
- [ ] Solicitante vê e acessa apenas os próprios chamados (lista, detalhe, dashboard)
- [ ] Técnico vê todos os chamados, fila e CMDB
- [ ] Gerente/Admin veem tudo + relatórios
- [ ] Sidebar oculta menus conforme o perfil
- [ ] Notas internas invisíveis para solicitantes

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
