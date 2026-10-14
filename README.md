# ITSM Enterprise

**Sistema de Help Desk corporativo construído em Django, inspirado no ServiceNow.**

Gestão completa do ciclo de vida de chamados de TI: abertura, triagem, SLA por
prioridade, fluxo de aprovação, escalonamento, trilha de auditoria, inventário
de ativos, API REST e autenticação integrada ao Active Directory.

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.1-092E20?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.18-A30000)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap&logoColor=white)
![HTMX](https://img.shields.io/badge/HTMX-1.9-3366CC)
![Testes](https://img.shields.io/badge/testes-356%20passando-brightgreen)

---

## Índice

- [Em uma olhada](#em-uma-olhada)
- [Funcionalidades](#funcionalidades)
- [Stack](#stack)
- [Instalação](#instalação)
- [Papéis e permissões](#papéis-e-permissões)
- [API REST](#api-rest)
- [Integração com Active Directory](#integração-com-active-directory)
- [Automação de SLA](#automação-de-sla)
- [Testes](#testes)
- [Arquitetura](#arquitetura)
- [Documentação](#documentação)
- [Decisões de projeto](#decisões-de-projeto)
- [Licença](#licença)

---

## Em uma olhada

| | |
|---|---|
| **Domínio** | ITSM / Service Desk corporativo |
| **Código** | ~10.100 linhas de Python versionadas |
| **Testes** | 356 automatizados, sem dependência de rede |
| **Models** | 11 (chamado, comentário, anexo, escalonamento, aprovação, auditoria, ativo, notificação, perfil…) |
| **Apps** | 7 (`accounts`, `tickets`, `cmdb`, `notifications`, `reports`, `dashboard`, `api`) |
| **Autenticação** | sessão, token (API) e **Active Directory** via LDAP |
| **Banco** | SQLite em desenvolvimento, PostgreSQL em produção |

<!--
  CAPTURAS DE TELA — adicione as imagens em docs/img/ e descomente:

  ![Dashboard](docs/img/dashboard.png)
  ![Detalhe do chamado](docs/img/chamado.png)
  ![Fila de atendimento](docs/img/fila.png)
-->

---

## Funcionalidades

### 🎫 Chamados

- Abertura com categoria, tipo (incidente / problema / requisição), prioridade
  e ativo de TI vinculado
- Comentários **públicos e internos** — a nota interna é filtrada no
  *queryset*, não escondida no template, então não trafega no HTML para quem
  não pode vê-la
- Anexos com política centralizada: `.pdf .doc .docx .xls .xlsx .png .jpg
  .jpeg .txt .log .zip`, máximo de 10 MB, com aviso ao usuário quando o
  arquivo é recusado
- Atualização de partes da página sem recarregar, via HTMX

### ⏱️ SLA

- Prazo automático por prioridade: **Crítica 2h · Alta 8h · Média 24h ·
  Baixa 72h**
- Indicadores de prazo decorrido, risco e vencimento na página do chamado
- **Aviso prévio** a 80% do prazo para o responsável
- **Escalonamento automático** do chamado vencido para o gerente com menos
  carga, com balanceamento e desempate determinístico
- O relógio do SLA **só começa depois da aprovação**, quando a categoria exige
  uma — senão um chamado crítico parado no fim de semana nasceria vencido

### 🔄 Fluxo de atendimento

- Fila de atendimento com atribuição manual
- **Finalizar** com solução obrigatória (mínimo 10 caracteres), que entra no
  histórico e vai no e-mail ao solicitante
- **Escalonar** para outro membro da equipe com motivo obrigatório; o destino
  nunca inclui o próprio usuário
- Chamado resolvido ou fechado não é finalizado nem escalonado de novo

### ✅ Workflow de aprovação

- O gatilho é um *checkbox* na **categoria** (`requires_approval`), então a
  política muda no `/admin/` e não num deploy
- Fila de aprovação dedicada, com badge de contagem na barra lateral
- Aprovar libera o chamado e inicia o SLA; rejeitar exige parecer, que **o
  solicitante vê** — ao contrário do motivo de escalonamento, que é interno
- Os status `Aguardando Aprovação` e `Rejeitado` ficam fora do seletor da
  equipe: são estados do workflow, não escolha do técnico

### 🔍 Auditoria

- Trilha cronológica por chamado: status, prioridade, responsável, categoria,
  prazo, título e solução
- **Captura automática** no `save()` do model — alteração feita pela tela,
  pelo `/admin/`, pelo `shell` ou por uma rotina agendada é registrada sem
  depender de alguém lembrar de chamar o log
- Os valores são gravados **já formatados** ("Crítica", "Técnico Um"): se o
  usuário for renomeado ou removido, a entrada continua dizendo o que estava
  escrito na época
- Ação automática aparece como **"Sistema"**
- O log é somente leitura no `/admin/` — log de auditoria editável não é log
  de auditoria

### 📊 Dashboard e relatórios

- KPIs por perfil, seletor de período (7 / 30 / 90 dias / tudo) e atualização
  automática a cada 60 s
- Três gráficos Chart.js: rosca por status, barras por prioridade e linha de
  volume diário
- Cumprimento de SLA e tempo médio de resolução
- O servidor renderiza a primeira carga: se o `fetch` falhar, a página mostra
  números corretos em vez de zeros

### 🖥️ CMDB

Catálogo de ativos de TI por tipo, vinculáveis ao chamado.

### 🔔 Notificações

Notificações internas (sino na barra superior) e por e-mail, em abertura,
comentário, atribuição, resolução, escalonamento, aprovação e eventos de SLA.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.14 · Django 6.1 |
| API | Django REST Framework 3.18 (token + sessão) |
| Banco | SQLite (dev) → PostgreSQL (produção) |
| Frontend | Bootstrap 5.3 · HTMX 1.9 · Chart.js 4.4 |
| Diretório | `ldap3` (LDAP em Python puro) |
| Estáticos | WhiteNoise |

---

## Instalação

```bash
git clone https://github.com/<seu-usuario>/itsm-enterprise.git
cd itsm-enterprise

python -m venv venv
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse **http://localhost:8000/**.

Para popular o banco com categorias, ativos e chamados de exemplo:

```bash
python manage.py shell < seed_data.py
```

> Os usuários criados pelo `seed_data.py` têm **senhas triviais, de
> desenvolvimento**. Não use esse script em ambiente exposto.

### Antes de ir para produção

```python
# itsm_project/settings.py
DEBUG = False
ALLOWED_HOSTS = ['itsm.suaempresa.com']
SECRET_KEY = os.environ['ITSM_SECRET_KEY']   # fora do código
```

E troque o SQLite por PostgreSQL, o backend de e-mail de console por SMTP real
e rode `collectstatic`.

---

## Papéis e permissões

Controle de acesso por papel (RBAC), em `UserProfile.role`. As permissões são
propriedades do perfil — nenhuma view ou template compara o papel na mão.

| | Solicitante | Técnico | Gerente | Admin |
|---|:---:|:---:|:---:|:---:|
| Abrir e acompanhar os próprios chamados | ✅ | ✅ | ✅ | ✅ |
| Ver todos os chamados | — | ✅ | ✅ | ✅ |
| Fila de atendimento e CMDB | — | ✅ | ✅ | ✅ |
| Notas internas e trilha de auditoria | — | ✅ | ✅ | ✅ |
| Alterar status, prioridade e responsável | — | ✅ | ✅ | ✅ |
| Finalizar e escalonar | — | ✅ | ✅ | ✅ |
| Relatórios gerenciais | — | — | ✅ | ✅ |
| Aprovar e rejeitar | — | — | ✅ | ✅ |

Chamado de outro usuário devolve **404**, e não 403 — um 403 confirmaria que o
chamado existe.

---

## API REST

Base **`/api/v1/`**, autenticação por token ou sessão, paginação de 25 e
*throttling*.

```bash
# token
curl -X POST http://localhost:8000/api/v1/token/ -d "username=tecnico1&password=..."

# abrir um chamado
curl -X POST http://localhost:8000/api/v1/tickets/ \
     -H "Authorization: Token <seu-token>" -H "Content-Type: application/json" \
     -d '{"title":"VPN caindo","description":"Cai a cada 5 min",
          "ticket_type":"incident","priority":"high"}'

# finalizar
curl -X POST http://localhost:8000/api/v1/tickets/14/finalizar/ \
     -H "Authorization: Token <seu-token>" -H "Content-Type: application/json" \
     -d '{"solution":"Troquei o cabo do switch da sala 3."}'
```

A API **não é um caminho alternativo** para ver o que a tela esconde: o mesmo
RBAC vale nela, notas internas são filtradas no *queryset* e as mensagens de
erro são as mesmas da interface, porque vêm das mesmas funções.

Endpoints, filtros e tabela de erros: **[`docs/API.md`](docs/API.md)**.

---

## Integração com Active Directory

Quem tem conta no domínio entra com o **usuário e a senha de rede**, sem
cadastro. No primeiro login o usuário é criado com nome, e-mail e departamento
lidos do diretório, e o papel pode vir dos grupos do AD.

```python
AUTHENTICATION_BACKENDS = [
    'apps.accounts.ldap_backend.LdapBackend',      # senha conferida no AD
    'django.contrib.auth.backends.ModelBackend',   # senha no banco local
]
```

A ordem é deliberada: o controlador de domínio cair não tranca ninguém fora do
sistema. Decisões principais:

- **A senha do AD nunca é gravada** (`set_unusable_password`) — uma cópia do
  hash no banco faria com que trocar a senha no domínio não revogasse o acesso
- **LDAPS (636) com validação de certificado é o padrão**; usar LDAP puro
  exige uma decisão explícita, e o `manage.py check` passa a reclamar
- Nenhuma credencial em arquivo versionado: tudo por variável de ambiente
- Vem **desligado**, para quem clonar o projeto não travar no login

Diagnóstico sem adivinhação:

```bash
python manage.py ldap_check                        # DNS, porta, TLS
python manage.py ldap_check --user <conta>         # bind + grupos reais
python manage.py ldap_check --user <conta> --list  # confere todas as contas
```

Configuração completa: **[`docs/AD_LDAP.md`](docs/AD_LDAP.md)**.

---

## Automação de SLA

```bash
python manage.py check_sla --dry-run   # mostra o que faria, sem gravar
python manage.py check_sla             # execução normal
python manage.py check_sla --quiet     # só o resumo, para o log do agendador
```

Três passagens: aviso prévio → notificação de vencimento → escalonamento
automático. **Idempotente** — rodar de 15 em 15 minutos não repete trabalho.

Agendamento (Agendador de Tarefas do Windows ou Celery Beat) e detalhes:
**[`docs/AUTOMACAO_SLA.md`](docs/AUTOMACAO_SLA.md)**.

---

## Testes

```bash
python manage.py test                        # suíte completa
python manage.py test apps.tickets           # um app
python manage.py test apps.accounts.tests_ldap
```

**356 testes, nenhum dependendo de rede ou de serviço externo.**

| Módulo | Testes | Cobre |
|---|---:|---|
| `accounts` | 28 | RBAC, visibilidade, perfis |
| `accounts` (LDAP) | 63 | mapeamento de grupos, provisionamento, cadeia de backends |
| `tickets` | 21 | CRUD, SLA, comentários, anexos |
| `tickets` (fluxo) | 27 | finalizar, escalonar |
| `tickets` (aprovação) | 34 | workflow, início do SLA |
| `tickets` (auditoria) | 27 | captura automática, autoria |
| `tickets` (automação) | 41 | aviso, vencimento, balanceamento |
| `tickets` (estatísticas) | 32 | agregações, N+1 |
| `api` | 60 | permissões, serializers, ações |
| `cmdb` · `notifications` · `reports` · `dashboard` | 23 | — |

Alguns testes existem para **travar decisões**, não só para verificar código:
que o volume diário não volte a fazer uma consulta por dia
(`assertNumQueries(1)`), que o CSS e os templates não divirjam de novo, e que
um grupo de compartilhamento de arquivos não vire papel de atendimento.

---

## Arquitetura

```
itsm_enterprise/
├── manage.py
├── requirements.txt
├── itsm_project/              # settings, urls, wsgi
├── apps/
│   ├── accounts/              # perfis, RBAC, autenticação, LDAP
│   │   ├── ldap_client.py     # fala LDAP (isolado para ser testável)
│   │   ├── ldap_backend.py    # backend de autenticação do Django
│   │   └── checks.py          # avisos no manage.py check
│   ├── tickets/               # chamados, SLA, aprovação, auditoria
│   │   ├── services.py        # regras de negócio (tela e API usam as mesmas)
│   │   ├── stats.py           # agregações do dashboard e dos relatórios
│   │   └── automation.py      # automações de SLA
│   ├── cmdb/                  # ativos de TI
│   ├── notifications/         # notificações internas e e-mail
│   ├── reports/               # relatórios
│   ├── dashboard/             # painel principal
│   └── api/                   # API REST — prefixo /api/v1/
├── templates/                 # base.html + uma pasta por app + partials/
├── static/                    # css/, js/, img/
├── media/                     # uploads (fora do versionamento)
└── docs/                      # documentação técnica
```

---

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [`docs/API.md`](docs/API.md) | endpoints, filtros, exemplos, erros |
| [`docs/AD_LDAP.md`](docs/AD_LDAP.md) | integração com o Active Directory |
| [`docs/AUTOMACAO_SLA.md`](docs/AUTOMACAO_SLA.md) | automações e agendamento |
| [`docs/STATUS.md`](docs/STATUS.md) | o que foi entregue em cada fase, com as decisões |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | plano de evolução |
| [`SETUP.md`](SETUP.md) | guia de instalação detalhado |

---

## Decisões de projeto

Algumas escolhas que explicam a forma do código:

**Regra de negócio em `services.py`, nunca na view ou no serializer.**
Finalizar, escalonar, aprovar e comentar são funções chamadas pela tela HTML e
pela API. Sem isso haveria duas implementações da mesma regra, divergindo na
primeira mudança — e as mensagens de erro da API já não seriam as da tela.

**RBAC no *queryset*, não no template.** Esconder no template deixaria o
conteúdo no código-fonte da página. `Ticket.objects.visible_to(user)` é a
fronteira, e a API herda isso de graça.

**Auditoria no `save()` do model, não nas views.** Captura por fora é captura
que alguém esquece de chamar. A limitação conhecida está documentada e
testada: `QuerySet.update()` vai direto ao SQL e não é auditado.

**`ldap3` em vez de `django-auth-ldap`.** O caminho usual depende do
`python-ldap`, extensão em C que exige toolchain de compilação no Windows. O
`ldap3` é Python puro e o backend são ~120 linhas — com o mapeamento de grupos
explícito em código em vez de escondido numa configuração.

**Separar o cliente LDAP do backend de autenticação.** É o que permite testar
todo o mapeamento de grupos e o provisionamento sem um servidor de verdade —
e parte dos testes ainda exercita a biblioteca real, com o diretório em
memória do `ldap3`.

---

## Licença

Este repositório ainda **não tem licença definida**. Sem um arquivo `LICENSE`,
o padrão legal é "todos os direitos reservados": o código fica visível, mas
ninguém pode reutilizá-lo. Para permitir reuso, adicione uma licença —
[MIT](https://choosealicense.com/licenses/mit/) é a escolha usual para
projetos de portfólio.

---

## Autor

**Thiago Araújo** — Analista de Infraestrutura de TI.

Projeto desenvolvido para estudo de Django em profundidade, aplicando práticas
de ITSM do dia a dia de infraestrutura: SLA, aprovação, auditoria, CMDB e
integração com diretório corporativo.
