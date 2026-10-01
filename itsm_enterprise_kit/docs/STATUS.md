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
- [ ] Remover "RAVEN" de todo o projeto → "ITSM Enterprise"
- [ ] Mover apps para `apps/` mantendo labels
- [ ] Badges da sidebar (notificações não lidas, tickets sem técnico)

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
