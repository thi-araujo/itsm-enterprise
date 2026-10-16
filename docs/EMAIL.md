# E-mail — quem recebe o quê, e como ligar o SMTP

O código de envio está em `apps/notifications/email.py`. A configuração fica no
`.env` (molde em `.env.example`), e o `manage.py check` reclama de configuração
perigosa ou incompleta.

## Vem desligado, e é por isso que o e-mail "não chega"

Sem `ITSM_EMAIL_HOST` definido, o backend é o **console**: as mensagens são
impressas no terminal onde o `runserver` está rodando e **nada sai da
máquina**. É o padrão de propósito — quem clona o projeto não precisa de um
servidor de SMTP, e ninguém dispara e-mail de verdade sem querer enquanto
testa.

O `manage.py check` diz isso em voz alta:

```
WARNINGS:
?: (email.W001) E-mail em modo console: nenhuma mensagem sai da máquina.
   HINT: As mensagens são impressas no terminal do runserver. Para enviar de
   verdade, defina ITSM_EMAIL_HOST no .env (ver docs/EMAIL.md).
```

Para ver a mensagem que *teria* sido enviada, abra um chamado e olhe o
terminal do `runserver`: o e-mail aparece inteiro, com cabeçalho e corpo.

## Quem recebe o quê

| Evento | Solicitante | Técnico responsável | Equipe | Gerência |
|---|---|---|---|---|
| **Abertura do chamado** | ✅ recibo com o número | — | ✅ ordem de serviço | — |
| Abertura que exige aprovação | ✅ recibo, sem prazo | — | — | ✅ pedido de decisão |
| Aprovado / rejeitado | ✅ com o parecer | — | — | — |
| Chamado atribuído | — | ✅ | — | — |
| Comentário **público** | ✅ | ✅ | — | — |
| Comentário **interno** | ❌ nunca | ✅ | — | — |
| Chamado resolvido | ✅ com a solução | — | — | — |
| Escalonamento | ❌ é interno | ✅ quem recebeu | — | — |
| SLA em risco (80%) | — | ✅ (ou a equipe, se não houver) | — | — |
| SLA vencido | — | — | ✅ | — |
| Escalonamento automático por SLA | — | ✅ quem recebeu | — | — |

Duas decisões que explicam a tabela:

**O recibo de abertura é separado do aviso da equipe.** São públicos
diferentes e textos diferentes: o da equipe é uma ordem de serviço, com a
descrição inteira; o do solicitante é um comprovante, com o número do chamado
e o prazo. `notify_ticket_opened` e `notify_ticket_created` são funções
distintas por isso.

**O recibo não gera notificação do sino.** A pessoa acabou de clicar em
"criar" e está vendo o chamado na tela; o valor do e-mail é ser um
comprovante na caixa de entrada, com o número.

Quem está **sem endereço** no cadastro não recebe e-mail nenhum — continua
recebendo as notificações internas do sino, que não dependem de SMTP. Para
contas vindas do AD, o endereço é o atributo `mail`; o
`ldap_check --user <conta> --list` lista quem está sem ele.

## Ligar o SMTP

Preencha no `.env`:

```ini
ITSM_EMAIL_HOST=smtp.gmail.com
ITSM_EMAIL_PORT=587
ITSM_EMAIL_USER=itsm@suaempresa.com
ITSM_EMAIL_PASSWORD=<a senha ou a senha de app>
```

O remetente (`ITSM_EMAIL_FROM`) pode ficar **vazio**: o padrão é a própria
conta do SMTP, que é o que Microsoft 365 e Gmail exigem.

### Microsoft 365 (conta corporativa do tenant)

```ini
ITSM_EMAIL_HOST=smtp.office365.com
ITSM_EMAIL_PORT=587
```

Requisitos do lado da Microsoft:

- **SMTP AUTH habilitado na caixa.** Ele vem desligado por padrão em tenants
  novos. No Exchange admin center: *Usuários ativos → a conta → Email apps →*
  **Authenticated SMTP**.
- A conta precisa de licença com caixa de correio (uma conta só de
  autenticação, sem caixa, não envia).

> ⚠️ **Prazo da Microsoft.** A autenticação básica no SMTP (usuário e senha,
> que é o que o Django usa) está em retirada no Exchange Online. A data foi
> **adiada para o fim de dezembro de 2026**: a partir daí ela fica desligada
> por padrão nos tenants existentes, e o administrador ainda pode reativá-la;
> tenants criados depois não a terão. A remoção definitiva deve ser anunciada
> no segundo semestre de 2027. Quando isso valer, o sintoma é
> `550 5.7.30 Basic authentication is not supported for Client Submission`,
> e a saída é OAuth2, um conector de retransmissão SMTP no tenant, ou a Graph
> API — nenhum deles sai de graça no backend padrão do Django.

### Outlook.com / Hotmail (conta pessoal)

```ini
ITSM_EMAIL_HOST=smtp-mail.outlook.com
ITSM_EMAIL_PORT=587
```

É um serviço diferente do Microsoft 365, com regras próprias. A Microsoft vem
empurrando as contas pessoais para OAuth também, e o que funciona hoje varia
conforme a conta tenha ou não verificação em duas etapas (com ela, é preciso
uma senha de app). **Para um sistema que envia em nome da empresa, conta
pessoal não é a escolha certa de todo modo**: o endereço do remetente é
pessoal, e a caixa está sujeita a limites de envio baixos.

### Gmail

```ini
ITSM_EMAIL_HOST=smtp.gmail.com
ITSM_EMAIL_PORT=587
```

A senha normal da conta **é recusada**. É obrigatório:

1. ativar a **verificação em duas etapas** na conta Google;
2. gerar uma **senha de app** (16 caracteres) e usá-la em
   `ITSM_EMAIL_PASSWORD`.

É o caminho que exige menos do servidor e o mais previsível dos três para
testar agora. Para uso corporativo de verdade, o Google Workspace com um
domínio próprio é o equivalente ao Microsoft 365.

A senha de app é mostrada em quatro grupos de quatro letras
(`abcd efgh ijkl mnop`). **Cole sem os espaços** — com eles o valor fica com
19 caracteres e a autenticação é recusada.

#### Quando a porta 587 está bloqueada

Verificado nesta instalação (16/10/2026): a rede **bloqueia a 587 de saída** e
deixa a 465 passar. O sintoma é `TimeoutError: timed out` dentro de
`socket.create_connection` — a conexão TCP nem abre, então não há diálogo SMTP
nenhum. Senha errada daria `535 Username and Password not accepted`, bem
diferente.

Para separar a rede do resto:

```powershell
Test-NetConnection smtp.gmail.com -Port 587
Test-NetConnection smtp.gmail.com -Port 465
```

`TcpTestSucceeded : False` significa bloqueio antes de sair da máquina —
firewall local, antivírus ou o provedor. A 587 e a 25 são as portas
historicamente usadas por malware para enviar spam, e são as primeiras a ser
filtradas.

A saída é trocar **só a porta** no `.env`:

```ini
ITSM_EMAIL_PORT=465
```

Nada mais muda: `EMAIL_USE_SSL` e `EMAIL_USE_TLS` são derivados da porta no
`settings.py`. Não defina `ITSM_EMAIL_USE_TLS` nem `ITSM_EMAIL_USE_SSL` à mão —
ligar os dois é o `email.E001`.

As duas portas são seguras, de formas diferentes: a 587 conecta em claro e
**sobe** para TLS com o comando `STARTTLS`; a 465 já **nasce** cifrada (SSL
implícito). A 465 chegou a ser considerada obsoleta e foi reabilitada como
padrão. Nenhuma das duas manda a senha em claro.

## Testar o envio

O Django tem um comando pronto para isso — não precisa abrir chamado:

```powershell
.\venv\Scripts\Activate.ps1
python manage.py check                     # confere a configuração primeiro
python manage.py sendtestemail seu@endereco.com
```

Se a configuração estiver errada, a exceção aparece aqui, direto no terminal.
No fluxo normal do sistema a falha é registrada no log e **engolida** de
propósito (ver abaixo), então o `sendtestemail` é o lugar certo para
diagnosticar.

Depois, o teste de ponta a ponta: abra um chamado com um usuário que tenha
endereço cadastrado e confira a caixa de entrada.

### Mexeu no `.env`? Reinicie o `runserver`

Variável de ambiente é lida **uma vez**, quando o processo nasce. O autoreload
do Django observa arquivos `.py` — o `.env` não é um deles, então editá-lo não
reinicia nada e o servidor continua com a configuração antiga.

Foi o que aconteceu aqui: a porta já estava corrigida para 465 no arquivo, o
`sendtestemail` (processo novo) enviava, e o chamado aberto pela tela falhava
com `TimeoutError` — o `runserver` em pé desde antes ainda usava a 587. Ctrl+C
e subir de novo resolve.

O mesmo vale para as variáveis `ITSM_LDAP_*`.

## Avisos do `manage.py check`

| ID | Quando |
|---|---|
| `email.W001` | backend de console: nada sai da máquina |
| `email.E001` | `USE_TLS` e `USE_SSL` ligados juntos — são incompatíveis |
| `email.W002` | SMTP sem usuário ou sem senha |
| `email.W003` | remetente de domínio diferente da conta do SMTP |
| `email.W004` | SMTP sem timeout |

O `email.W003` é a causa clássica de "o código está certo e o e-mail não
chega": Microsoft 365 e Gmail recusam mensagem cujo remetente não seja a caixa
autenticada. Deixe `ITSM_EMAIL_FROM` vazio e o problema não existe.

O `email.E001` é **erro**, não aviso, porque o Django levanta exceção só na
hora do envio — e aí o `_send_email` a registra e engole, de modo que o
chamado é criado e o e-mail nunca sai, sem nada na tela.

## Por que uma falha de SMTP não derruba o chamado

```python
except Exception:
    logger.exception('Falha ao enviar e-mail "%s" para %s', subject, recipients)
```

Criar um chamado não pode falhar porque o servidor de e-mail está fora do ar —
o chamado é o registro do trabalho, o e-mail é o aviso. Mas o
`fail_silently=False` no `send_mail` é deliberado: com `True`, o Django
engoliria o erro **antes** deste `except` e a falha não deixaria rastro
nenhum.

O efeito colateral a conhecer: **o sintoma de configuração errada é o
silêncio.** É para compensar isso que existem os avisos do `manage.py check` e
o `sendtestemail`.

## Limitação conhecida: o envio é síncrono

As mensagens saem dentro do ciclo da requisição. Um SMTP lento deixa quem
abriu o chamado esperando, até o `ITSM_EMAIL_TIMEOUT` (10s por padrão). Num
volume maior, o caminho é uma fila — Celery, com as mesmas funções de
`email.py` chamadas por uma task, do mesmo jeito que `automation.py` já está
separado do comando `check_sla`.

Os links do corpo das mensagens apontam para `http://localhost:8000`. Em uso
real isso precisa virar o endereço do servidor; hoje está cravado nas funções
de `email.py`.
