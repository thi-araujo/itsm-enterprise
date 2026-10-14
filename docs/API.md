# API REST — ITSM Enterprise

Fase 3.5. Base: **`/api/v1/`**. Implementação em `apps/api/`.

As regras de negócio **não estão aqui**: ficam em `apps/tickets/services.py`,
as mesmas que as telas HTML usam. A API só traduz JSON e códigos HTTP.

## Autenticação

Duas formas, nesta ordem de precedência:

### Token (integrações)

```bash
# 1. trocar usuário+senha por um token
curl -X POST http://localhost:8000/api/v1/token/ \
     -d "username=tecnico1&password=tecnico123"
# {"token":"9f1c0a7b4e2d8f36a5b90c1e7d4a82f6b3e05c91"}

# 2. usar o token em todas as chamadas
curl http://localhost:8000/api/v1/eu/ \
     -H "Authorization: Token 9f1c0a7b4e2d..."
```

Os tokens são gerenciáveis em `/admin/authtoken/tokenproxy/` — dá para criar
e revogar por ali.

### Sessão (navegador)

Estando logado no sistema, abra `http://localhost:8000/api/v1/` no browser:
o DRF monta uma interface navegável, com formulários para testar cada
endpoint.

Sem credencial, a resposta é **401** com `WWW-Authenticate: Token`.

## Permissões

A API respeita o RBAC da Fase 3.1 — ela **não** é um caminho alternativo
para ver o que a tela esconde.

| Papel | Chamados que vê | Pode |
|---|---|---|
| Solicitante | só os próprios (alheio = **404**) | abrir, comentar, consultar |
| Técnico | todos | tudo acima + alterar, finalizar, escalonar, CMDB |
| Gerente / Admin | todos | tudo acima + aprovar e rejeitar |

- Notas internas são filtradas **no queryset**: não trafegam para o
  solicitante.
- Trilha de auditoria e histórico de escalonamento: só a equipe (**403**).
- Solicitante não faz `PATCH`, nem no próprio chamado (**403**).
- `DELETE` não existe em chamado (**405**): o histórico é o registro.

## Endpoints

### Chamados

| Método | Rota | Quem |
|---|---|---|
| `GET` | `/tickets/` | autenticado (lista já filtrada pelo perfil) |
| `POST` | `/tickets/` | autenticado |
| `GET` | `/tickets/{id}/` | autenticado + visibilidade |
| `PATCH` | `/tickets/{id}/` | equipe |
| `POST` | `/tickets/{id}/finalizar/` | equipe |
| `POST` | `/tickets/{id}/escalonar/` | equipe |
| `POST` | `/tickets/{id}/aprovar/` | gerência |
| `POST` | `/tickets/{id}/rejeitar/` | gerência |
| `GET`/`POST` | `/tickets/{id}/comentarios/` | autenticado |
| `GET` | `/tickets/{id}/anexos/` | autenticado |
| `GET` | `/tickets/{id}/aprovacoes/` | autenticado |
| `GET` | `/tickets/{id}/escalonamentos/` | equipe |
| `GET` | `/tickets/{id}/auditoria/` | equipe |

**Filtros da listagem** (iguais aos da tela):

```
?status=open|in_progress|waiting|resolved|closed|pending_approval|rejected
?priority=low|medium|high|critical
?assignee=me | unassigned | <id>
?search=texto          (título, descrição, id)
?ordering=created_at | -priority | sla_deadline ...
?page=2                (25 por página)
```

### Apoio

| Método | Rota | Quem | O quê |
|---|---|---|---|
| `GET` | `/eu/` | autenticado | identidade, papel e **permissões** |
| `GET` | `/estatisticas/` | autenticado | números agregados (`?days=N`) |
| `GET` | `/categorias/` | autenticado | somente leitura; mostra `requires_approval` |
| `GET` | `/ativos/` | equipe | CMDB (`?search=`) |
| `GET` | `/tecnicos/` | equipe | quem pode receber chamados |
| `POST` | `/token/` | — | troca usuário+senha por token |

O `/eu/` existe para o cliente não adivinhar permissões:

```json
{
  "username": "tecnico1",
  "papel": "technician",
  "papel_nome": "Técnico",
  "permissoes": {
    "ver_todos_chamados": true,
    "ver_fila": true,
    "ver_cmdb": true,
    "ver_notas_internas": true,
    "gerenciar_chamados": true,
    "ver_relatorios": false,
    "aprovar": false
  }
}
```

## Exemplos

```bash
TOKEN="Authorization: Token 9f1c0a7b4e2d..."
API="http://localhost:8000/api/v1"

# abrir um chamado
curl -X POST $API/tickets/ -H "$TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"VPN caindo","description":"Cai a cada 5 min",
       "ticket_type":"incident","priority":"high"}'

# os meus, em aberto
curl "$API/tickets/?assignee=me&status=open" -H "$TOKEN"

# assumir o chamado 14
curl -X PATCH $API/tickets/14/ -H "$TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"in_progress","assignee_id":5}'

# finalizar (solução obrigatória, mínimo 10 caracteres)
curl -X POST $API/tickets/14/finalizar/ -H "$TOKEN" -H "Content-Type: application/json" \
  -d '{"solution":"Troquei o cabo do switch da sala 3."}'

# escalonar
curl -X POST $API/tickets/14/escalonar/ -H "$TOKEN" -H "Content-Type: application/json" \
  -d '{"to_user":6,"reason":"Precisa de acesso ao firewall de borda."}'

# aprovar (só gerência)
curl -X POST $API/tickets/15/aprovar/ -H "$TOKEN" -H "Content-Type: application/json" \
  -d '{"comment":"Liberado pelo gestor da área."}'

# comentar
curl -X POST $API/tickets/14/comentarios/ -H "$TOKEN" -H "Content-Type: application/json" \
  -d '{"content":"Em análise","is_internal":false}'
```

## Erros

Formato padrão do DRF, com as mensagens em português — **as mesmas que
aparecem na tela**, porque vêm das constantes de `services.py`:

```json
{"solution": ["Descreva a solução com pelo menos 10 caracteres — ela vai para o solicitante e fica no histórico do chamado."]}
```

| Código | Quando |
|---|---|
| `400` | dado inválido ou regra de negócio violada |
| `401` | sem credencial, ou token inválido |
| `403` | autenticado, mas sem permissão para a operação |
| `404` | não existe **ou** não é visível para este usuário |
| `405` | método não permitido (ex.: `DELETE` em chamado) |
| `429` | limite de requisições estourado |

## Limites

```python
'DEFAULT_THROTTLE_RATES': {'anon': '20/min', 'user': '1000/hour'}
```

Uma integração com defeito não derruba o banco. Ajuste em
`itsm_project/settings.py`, bloco `REST_FRAMEWORK`.

## Decisões de projeto

- **Relacionamentos expandidos na leitura, por id na escrita.** `requester`
  vem como objeto (`{id, username, nome, papel}`); `assignee_id` grava.
  Evita uma segunda requisição só para descobrir o nome de quem abriu.
- **Versão no caminho** (`/api/v1/`): no dia em que um campo mudar de forma,
  a v2 nasce ao lado e quem já integrou continua funcionando.
- **Status do workflow fora do `PATCH`.** `pending_approval` e `rejected` são
  definidos pelas ações de aprovação. O serializer remove as duas opções das
  `choices`, e o DRF valida contra elas — um PATCH forjado recebe 400 sem
  precisar de validação extra.
- **Sem Swagger/OpenAPI por ora.** A API navegável do DRF resolve a
  exploração manual. Se um gerador de cliente for necessário,
  `drf-spectacular` é um pacote e meia hora de trabalho.
