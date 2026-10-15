# Integração com AD/LDAP — como ligar e como diagnosticar

Fase 3.8. O código está em `apps/accounts/ldap_client.py` (fala LDAP),
`apps/accounts/ldap_backend.py` (decide o que gravar no Django) e
`apps/accounts/management/commands/ldap_check.py` (diagnóstico).

**Vem desligado.** Ligar é uma variável de ambiente, depois de rodar o
`ldap_check`.

## O que a integração faz

Quem tem conta no domínio entra no ITSM com o **usuário e a senha de rede**,
sem cadastro nenhum. No primeiro login o sistema cria o usuário no banco do
Django com nome, e-mail e departamento lidos do diretório, e com o papel
(Solicitante / Técnico / Gerente / Administrador) deduzido dos **grupos** de
que a pessoa participa.

```
  Pessoa digita usuário e senha na tela de login
                    │
                    ▼
    ┌───────────────────────────────┐
    │ LdapBackend                   │  bind simples em
    │ apps/accounts/ldap_backend.py │  usuario@exemplo.local
    └───────┬───────────────┬───────┘
       aceito           recusado
            │               │
            ▼               ▼
   cria/atualiza o    ┌──────────────┐
   usuário local e    │ ModelBackend │ ← senha guardada no banco
   aplica o papel     │  (do Django) │   (admin, contas de teste)
   pelos grupos       └──────────────┘
```

A lista está em `AUTHENTICATION_BACKENDS`, no `settings.py`. O Django tenta um
backend por vez, na ordem. **O ModelBackend atrás é intencional:** o
controlador de domínio cair não pode trancar ninguém fora do sistema.

## Estado desta instalação (verificado em 14/10/2026)

| Verificação | Resultado |
|---|---|
| DNS de `exemplo.local` | resolve para `192.168.10.4` |
| Controlador de domínio | `dc01.exemplo.local` = `192.168.10.4` (registro SRV) |
| LDAP na porta 389 | ✅ responde, e a base `DC=exemplo,DC=local` confere |
| Bind de `joao.silva` | ✅ aceito; 7 grupos lidos; papel resolvido como Administrador |
| LDAPS na porta 636 | ❌ a conexão TCP abre e o TLS é derrubado |
| StartTLS na 389 | ❌ o servidor responde `unavailable` |

Os dois sintomas de TLS têm a mesma causa: **o controlador de domínio não tem
certificado de servidor instalado.** O `Test-NetConnection ... -Port 636` diz
"aberta" porque o serviço escuta, mas sem certificado não há handshake. Note
que desligar `ITSM_LDAP_TLS_VALIDATE` **não resolve** isso — não existe
certificado nenhum para validar.

### Por que isso importa

Num bind simples, a senha vai dentro da requisição LDAP. Sem TLS, ela trafega
**em texto claro** pela rede — legível em qualquer captura de pacotes entre a
máquina do ITSM e o DC. É a senha de domínio da pessoa, não uma senha só deste
sistema.

### As duas saídas

**1. Instalar um certificado no DC (o jeito certo).** Normalmente é adicionar a
função **AD CS** (Serviços de Certificados do Active Directory) como Enterprise
CA no domínio. O controlador se inscreve sozinho num certificado de
Controlador de Domínio e passa a atender em LDAPS **sem nenhuma mudança neste
projeto** — a configuração padrão aqui já é a porta 636 com validação ligada.

Depois disso, exporte a CA raiz do domínio e aponte o arquivo:

```powershell
$env:ITSM_LDAP_CA_CERT_FILE = "C:\certs\exemplo-ca.pem"
```

O Windows confia na CA do próprio domínio; o Python tem o seu próprio
repositório de confiança e não herda essa confiança.

**2. Usar a porta 389 sem TLS (provisório).** Funciona hoje, com a senha em
texto claro. Aceitável para testar numa rede controlada. **Não para produção.**

```powershell
$env:ITSM_LDAP_PORT = "389"
```

Nessa configuração o `manage.py check` passa a reclamar — de propósito:

```
WARNINGS:
?: (ldap.W001) LDAP ligado sem TLS: a senha de domínio dos usuários
   trafega em texto claro pela rede.
```

## Passo 1 — diagnosticar

```powershell
.\venv\Scripts\Activate.ps1

python manage.py ldap_check                 # configuração, DNS, porta, TLS
python manage.py ldap_check --user joao.silva   # bind + grupos reais
```

O comando funciona mesmo com `LDAP_ENABLED` desligado — é para isso que ele
existe: validar antes de ligar.

Se a conexão falhar, o `--user` **não** é executado e a senha não é pedida:
sem conexão não há onde autenticar.

O `--user` é o passo que resolve o mapeamento de grupos. Ele imprime os grupos
que a conta **realmente** tem no AD e qual papel o `LDAP_GROUP_ROLE_MAP` atual
daria a ela:

```
Grupos (3)
                               Domain Users
                               ITSM-Tecnicos
                               Suporte, Nível 2

Papel que este usuário receberia no ITSM
  [ok]    Técnico — por casar com o LDAP_GROUP_ROLE_MAP
```

A senha é pedida na hora, por `getpass`, e **nunca** vai como argumento:
argumento de linha de comando fica no histórico do PowerShell e aparece na
lista de processos.

## Passo 2 — ajustar o mapa de grupos

Em `itsm_project/settings.py`:

```python
LDAP_GROUP_ROLE_MAP = [
    ('Domain Admins', 'admin'),
]
LDAP_DEFAULT_ROLE = 'requester'
```

**Só um grupo, e isso é deliberado.** Num domínio real a maioria dos grupos
existe para conceder acesso a compartilhamentos, impressoras e aplicações, e é
distribuída por **GPO, automaticamente** — foi o que apareceu no levantamento
deste projeto, em que todos os grupos do domínio, menos os internos do
Windows, eram de File Server.

Mapear um desses para um papel do ITSM daria privilégio de atendimento a quem
só recebeu acesso a uma pasta: **escalonamento de privilégio pela GPO**, sem
ninguém ter decidido isso. É uma armadilha fácil, porque o nome do grupo
costuma sugerir função (`GRP-Technical` parece ser "o grupo dos técnicos",
e é a lista de quem acessa o compartilhamento da equipe técnica).

Há um teste (`MapaDeGruposDoProjetoTests`) que falha quando o mapa cresce —
não para impedir o acréscimo, mas para que ele passe por uma revisão.

Então o fluxo é:

1. A pessoa entra pela primeira vez e é criada como **Solicitante**.
2. Você promove a Técnico ou Gerente em **/admin/ → Perfis de Acesso**.
3. **O login seguinte não desfaz isso**: sem grupo casando, o papel atual é
   mantido. Esta é a regra que faz o ajuste manual ser durável.

É o caminho certo para um domínio pequeno: 13 contas, e o papel de cada uma
muda raramente. Se um dia existir um grupo criado **exatamente** para definir
papel no ITSM, acrescente-o ao mapa — a lista é ordenada, com o papel mais
privilegiado primeiro.

`Domain Admins` → `admin` fica porque é o grupo da própria administração do
domínio. Vale saber do acoplamento: quem for adicionado a `Domain Admins` por
um motivo de infraestrutura ganha o ITSM inteiro. Para desacoplar, esvazie o
mapa — e aí até o primeiro administrador do ITSM é definido à mão.

### `Domain Users` abre chamado — e não entra no mapa

**Todo usuário do domínio já entra como Solicitante e já abre chamado.** Não
há nada a configurar para isso: é o `LDAP_DEFAULT_ROLE`, que vale para quem
autentica e não casa com nenhum grupo do mapa. Como `Domain Users` é o grupo
primário de toda conta do AD — o diretório a coloca lá na criação, e não dá
para tirar —, "quem está em `Domain Users`" e "todo mundo que tem conta no
domínio" são o mesmo conjunto de pessoas.

Acrescentar `('Domain Users', 'requester')` ao mapa parece dizer a mesma
coisa, e **quebraria o passo 3 do fluxo acima.** Com o grupo no mapa, toda
conta passa a casar; casar faz o diretório sobrescrever o papel; e o Técnico
promovido à mão em /admin/ voltaria a Solicitante no login seguinte. O ajuste
manual deixaria de ser durável — e o sintoma apareceria dias depois, como
"o técnico perdeu o acesso à fila sozinho".

Fora do mapa (como está), ninguém casa: quem é novo cai no `LDAP_DEFAULT_ROLE`
e quem já tem papel o mantém. Os dois comportamentos ficam travados por
`DomainUsersAbreChamadoTests`, inclusive o rebaixamento — um teste mostra que
ele aconteceria, para o motivo não se perder.

## Conferir as contas em massa

```powershell
python manage.py ldap_check --user joao.silva --list
```

Faz o bind uma vez (a senha é pedida só uma vez) e mostra, para cada conta de
pessoa do diretório, o que o ITSM leria dela e o papel que ela receberia:

```
  CONTA                 NOME                      E-MAIL                        DEPARTAMENTO      PAPEL
  ----------------------------------------------------------------------------------------------------
  joao.silva         Thiago Araujo             joao.silva@exemplo.local     TI                Administrador
  paulo.silva           Paulo Silva               paulo.silva@exemplo.local       —                 Solicitante (padrão)

  13 conta(s).
  [aviso] 1 sem e-mail: não receberão as notificações por e-mail do ITSM.
```

As contas de **computador** ficam de fora: no AD elas também têm
`objectClass=user` e a lista viria com os PCs do domínio no meio das pessoas.

A listagem usa as **mesmas funções** do login (`_montar_usuario`,
`papel_para_grupos`), então o que ela mostra é o que o login gravaria — uma
segunda implementação divergiria na primeira mudança.

## Passo 3 — ligar

```powershell
$env:ITSM_LDAP_ENABLED = "1"
python manage.py runserver 0.0.0.0:8000
```

Para ligar de forma permanente, troque o padrão no `settings.py` ou defina a
variável no ambiente do serviço. Com o LDAP ligado, a tela de login passa a
avisar "Use seu usuário e senha de rede do domínio exemplo.local".

## Todas as configurações

Todas leem variável de ambiente, para nada sensível entrar em arquivo
versionado. Os padrões estão em `itsm_project/settings.py`.

| Variável de ambiente | Padrão | O que faz |
|---|---|---|
| `ITSM_LDAP_ENABLED` | `0` | liga o backend do AD |
| `ITSM_LDAP_SERVER` | `dc01.exemplo.local` | controlador de domínio |
| `ITSM_LDAP_PORT` | `636` | 636 = LDAPS, 389 = LDAP puro |
| `ITSM_LDAP_START_TLS` | `0` | cifra a conexão na 389 (exige certificado no DC) |
| `ITSM_LDAP_TLS_VALIDATE` | `1` | valida o certificado do servidor |
| `ITSM_LDAP_CA_CERT_FILE` | — | arquivo `.pem` da CA do domínio |
| `ITSM_LDAP_DOMAIN` | `exemplo.local` | sufixo do UPN no bind |
| `ITSM_LDAP_SEARCH_BASE` | `DC=exemplo,DC=local` | onde procurar a conta |
| `ITSM_LDAP_TIMEOUT` | `5` | segundos; é o que se espera na tela quando o DC não responde |
| `ITSM_LDAP_BIND_DN` | — | conta de serviço (opcional, ver abaixo) |
| `ITSM_LDAP_BIND_PASSWORD` | — | senha dela — **só** por variável de ambiente |
| `ITSM_LDAP_NESTED_GROUPS` | `0` | segue grupos aninhados (uma consulta a mais) |

`LDAP_USE_SSL` é derivado: liga sozinho quando a porta é 636.

### Nome do servidor, e não o IP

O padrão é o nome `dc01.exemplo.local`, embora o DC seja o `192.168.10.4`.
Isso é de propósito: um certificado é emitido para o **nome** da máquina, então
validar o certificado por IP falharia sempre. Use o IP apenas como última
saída, numa máquina onde o DNS do domínio não esteja disponível:

```powershell
$env:ITSM_LDAP_SERVER = "192.168.10.4"
$env:ITSM_LDAP_PORT   = "389"     # por IP, a validação de certificado não vale
```

### Conta de serviço — normalmente não precisa

O bind é feito com o **próprio usuário que está entrando**, e os atributos e
grupos dele são lidos já autenticados como ele — um usuário de domínio comum
tem permissão de leitura no diretório. Então não há credencial de serviço para
guardar, o que elimina a pior parte do problema.

Preencha `ITSM_LDAP_BIND_DN` / `ITSM_LDAP_BIND_PASSWORD` só se o seu AD
restringir essa leitura. Nesse caso a senha vai **por variável de ambiente**,
nunca no `settings.py`.

### Grupos aninhados

`memberOf` traz apenas os grupos **diretos**. Se na sua estrutura o grupo
`Suporte-N1` é membro de `ITSM-Tecnicos`, quem está só em `Suporte-N1` não
apareceria como Técnico. Ligando `ITSM_LDAP_NESTED_GROUPS=1`, o sistema
pergunta ao AD pela cadeia completa (usando o *matching rule in chain*), ao
custo de uma consulta a mais por login.

## O que acontece no banco do Django

| | Comportamento |
|---|---|
| Usuário novo | criado no primeiro login (*just-in-time*), com papel pelos grupos |
| Senha | **não é guardada**: `set_unusable_password()` |
| Logins seguintes | nome, e-mail, departamento e papel atualizados; nenhuma conta duplicada |
| Usuário que já existia | papel do AD aplicado **só se algum grupo casar**; senha local preservada |
| Caixa do username | busca `iexact`: o AD devolvendo `Thiago` acha o `thiago` existente |
| Conta inativa no ITSM | não entra, mesmo com a senha certa no AD |
| Campo vazio no AD | não apaga o valor que já estava preenchido |
| Conta sem `givenName`/`sn` | o nome vem do `displayName` ou do CN do DN |

Duas decisões que merecem explicação:

**A senha do AD não fica no Django.** Sem isso, uma cópia do hash ficaria no
`db.sqlite3`, e trocar ou bloquear a senha no domínio não revogaria o acesso ao
ITSM. Como efeito colateral, a conta do AD **não** consegue entrar quando o
LDAP está desligado — ela não tem senha local para conferir.

**O nome tem queda para trás.** Conta de AD montada à mão costuma não ter
`givenName` e `sn` preenchidos — o nome existe só no `displayName`, ou apenas no
CN do DN (`CN=Thiago Araujo,OU=Usuarios,...`). Nesse caso o nome é lido de lá e
cortado no primeiro espaço. Sem isso o ITSM mostraria `joao.silva` em toda
tela, em vez de "Thiago Araujo".

**Usuário que já existia não é rebaixado.** Se alguém não casa com nenhum grupo
do mapa, o papel atual é mantido. Sem essa regra, o `thiago` (Administrador
criado à mão) viraria Solicitante no primeiro login pelo AD.

No `/admin/`, a coluna **Origem** na lista de usuários mostra "Active Directory"
ou "Local", e o perfil guarda a data da última sincronização. Vale olhar antes
de tentar redefinir a senha de alguém pelo Django: para conta do AD, a senha se
troca no domínio.

## Por que `ldap3` e não `django-auth-ldap`

O caminho usual no Django é `django-auth-ldap`, que depende do `python-ldap` —
uma extensão escrita em C. Nesta máquina ela **não compila**:

```
error: Unable to find a compatible Visual Studio installation.
ERROR: Failed building wheel for python-ldap
```

Não há wheel pronta para Windows + Python 3.14, e compilar exigiria o Visual
Studio Build Tools mais os headers do OpenLDAP. O `ldap3` é Python puro, instala
em qualquer lugar, e o backend de autenticação são ~120 linhas. De quebra, o
mapeamento de grupo para papel fica explícito em código em vez de escondido
numa configuração.

## Atributos que valem preencher no AD

O `ldap_check --user` avisa quando a conta está sem eles:

- **`mail` vazio → a pessoa não recebe as notificações por e-mail do ITSM.**
  O sistema manda e-mail em abertura, comentário, resolução e vencimento de
  SLA; sem endereço, essas mensagens não têm para onde ir. As notificações
  internas (o sino na barra) continuam funcionando, porque não dependem de
  e-mail.
- **`department` vazio** → o campo fica em branco no perfil. É também o dado
  de que a aprovação por departamento vai depender.
- **`givenName` / `sn` vazios** → funciona, pela queda para trás descrita
  acima, mas preencher no AD é melhor que depender do CN.

## Limitações conhecidas

- **Não há SSO.** Entrar sem digitar a senha (Kerberos/SPNEGO) exigiria
  `gssapi` — outra extensão em C, mesmo problema — e que a máquina do servidor
  estivesse no domínio. Esta está em `WORKGROUP`.
- **Não há importação em massa** do AD. O usuário nasce no primeiro login.
  Quem nunca usar o sistema nunca ocupa uma linha no banco.
- **A desativação não é automática.** Conta desabilitada no AD deixa de
  autenticar (o bind falha), mas o usuário continua existindo e aparecendo nos
  seletores do ITSM. Desativar no `/admin/` resolve; sincronizar isso sozinho
  exigiria uma rotina periódica, como o `check_sla` da Fase 3.7.
- **A aprovação ainda não usa o departamento do AD.** O `department` passou a
  ser preenchido pelo diretório, o que é o dado que faltava para a pendência da
  Fase 3.3 (aprovação pelo gerente do departamento do solicitante).

## Testes

67 testes em `apps/accounts/tests_ldap.py`, nenhum deles tocando a rede. Duas
estratégias:

1. A maioria substitui `ldap_backend.autenticar` por uma função falsa e
   exercita a **regra**: que papel sai de quais grupos, o que acontece no
   segundo login, o que acontece quando o AD cai.
2. `ClienteLdapComServidorFalsoTests` usa o modo `MOCK_SYNC` do próprio
   `ldap3`, um diretório em memória. Esse exercita a biblioteca de verdade — o
   filtro de busca, a leitura dos atributos, o parser de DN — e pega erros que
   um mock escrito à mão nunca pegaria.

Dois testes merecem destaque porque fixam comportamentos de segurança:

- **senha em branco não chega ao servidor.** Bind com senha vazia é um bind
  **anônimo**, que o AD aceita — a autenticação "passaria" com a senha em
  branco. Há guarda no backend e no cliente.
- **o mapa de grupos não cresce em silêncio.** `MapaDeGruposDoProjetoTests`
  verifica o mapa que está no `settings.py` de verdade, não um mapa de teste:
  qualquer grupo novo faz a suíte falhar, forçando a revisão.
- **username com curinga não casa com qualquer conta.** O que a pessoa digita é
  escapado antes de entrar no filtro LDAP; sem isso, `*` casaria com a primeira
  conta do diretório. É a mesma classe de problema que SQL injection.
