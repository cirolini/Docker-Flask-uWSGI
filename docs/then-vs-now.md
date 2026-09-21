# Então e agora: o mesmo app, 2019 e 2026

Este repositório é um exemplo que eu usei em palestras e aulas entre 2018 e
2021: um "Hello" em Flask que imprime o hostname do container, servido por
uWSGI numa imagem `python:3-alpine`, com um Jenkinsfile e um manifesto de
Kubernetes. Ele tem 28 estrelas, 19 forks, e a imagem que publiquei no Docker
Hub foi baixada **23.432 vezes**.

Ele nunca foi atualizado. E é exatamente por isso que ele virou um bom caso.

Este documento compara as duas entregas do **mesmo aplicativo** — o código do
app é praticamente idêntico — para mostrar o que mudou em como se constrói,
protege e entrega um container em sete anos, e por que cada mudança existe.
O valor está na comparação, não no app.

Tudo que está aqui foi **medido**, não estimado. Onde eu errei ao medir, ou
afirmei algo que os números depois desmentiram, está registrado na seção
[O que eu errei no caminho](#o-que-eu-errei-no-caminho) — essa parte é, na
minha opinião, a mais útil para quem está aprendendo.

---

## Como reproduzir os números

Local, com Docker e Trivy:

```bash
cd 2026 && make build scan
docker pull --platform linux/amd64 cirolini/flask-uwsgi:latest
docker build -t comp:2019 -f ../2019/Dockerfile ../2019
```

Ou pelo GitHub Actions, em runner amd64 nativo, que publica a tabela no resumo
da execução:

```
Actions > "Comparação 2019 vs 2026" > Run workflow
```

Esse workflow também roda todo dia 1º de cada mês. A resposta muda sozinha com
o tempo — o que, como você vai ver, é o ponto de partida do caso.

---

## Os números

Medições em Apple Silicon (arm64) contra a imagem publicada em 2018 (amd64).
A diferença de arquitetura vale no máximo ~6%: a mesma tag `python:3-alpine`
pesa 52,2 MB em amd64 e 55,5 MB em arm64.

| | Publicada em 2018 | Dockerfile de 2019, hoje | 2026 |
|---|---|---|---|
| Base | Alpine 3.4.6 | Alpine 3.24.2 | Debian 13 (trixie) slim |
| Python | 3.6.4 | 3.14.7 | 3.14.7 |
| Flask | 0.12.2 | 3.1.3 | 3.1.3 |
| Servidor | uWSGI | uWSGI | gunicorn 26.2.0 |
| **Pull (comprimido)** | 100,0 MiB | **181,9 MiB** | **42,5 MiB** |
| Disco (descomprimido) | 474 MB | 712 MB | 208 MB |
| Camadas | 12 | 11 | 10 |
| Usuário | root | root | uid 10001 |
| **CVEs com correção** | **50** | **3** | **0** |
| CVEs totais | 50 | 3 | 151 |
| Build (frio) | — | 66s | 25s |
| Compilador embarcado | sim | sim (73,8 MiB) | não |

Duas linhas dessa tabela precisam de explicação, e as duas são armadilhas
comuns.

### "CVEs totais" não compara o que parece comparar

A imagem de 2026 tem **151 CVEs totais** contra **3** do rebuild Alpine. Lido
de frente, parece que eu piorei tudo ao trocar de base. Não é isso: os 151 são
todos **sem correção disponível**. Debian rastreia e publica vulnerabilidade
menor que decide não corrigir; o banco do Alpine lista sobretudo o que já foi
corrigido. Filtrando por `--ignore-unfixed`, que é o número sobre o qual
alguém consegue agir, a conta é 50 → 3 → **0**.

Comparar contagem bruta de CVE entre distribuições mede **política de
rastreamento**, não risco. É o tipo de número que aparece em slide de
fornecedor de scanner.

### O rebuild engorda a imagem em 82%

Reconstruir o Dockerfile de 2019 hoje, sem mudar nada, derruba os CVEs de 50
para 3 **e aumenta a imagem de 100 MiB para 182 MiB**. Rebuild não é
arquitetura: ele troca as peças podres e deixa o defeito estrutural no lugar.
Qual defeito é esse está na seção seguinte.

---

## Build

### Antes

```dockerfile
FROM python:3-alpine

RUN apk add --virtual .build-dependencies --no-cache \
        python3-dev build-base linux-headers pcre-dev
RUN apk add --no-cache pcre

WORKDIR /app
COPY /app /app
COPY ./requirements.txt /app
RUN pip install -r /app/requirements.txt
RUN apk del .build-dependencies && rm -rf /var/cache/apk/*
```

### Depois

Multi-stage com base fixada por digest, venv montado no builder, nada de
ferramenta de build no runtime. O arquivo inteiro está em
[`2026/Dockerfile`](../2026/Dockerfile), comentado linha a linha.

### Por quê

**`FROM python:3-alpine` entrega software diferente a cada ano.** Essa linha
produziu Python 3.6 em 2018 e produz Python 3.14.7 hoje. Mesmo arquivo, mesmo
commit, dois runtimes separados por oito versões menores — e nenhum registro
de quando a troca aconteceu, porque não houve commit. O mesmo vale para o
`requirements.txt`, que dizia apenas `Flask` e `uwsgi`: Flask 0.12.2 em 2018,
Flask 3.1.3 hoje. Duas versões maiores de distância, sem um diff no meio.

Em 2026 a base é fixada por digest e as dependências por hash. Atualizar deixa
de ser acidente e vira PR do Dependabot, que alguém lê.

**`apk del` numa camada posterior não remove nada da imagem.** Este é o achado
que mais me surpreendeu, e o melhor da aula. O `docker history` do rebuild:

```
147kB   RUN apk del .build-dependencies && rm -rf /var/cache/apk/*
 23MB   RUN pip install -r /app/requirements.txt
439MB   RUN apk add --virtual .build-dependencies ...
```

(`docker history` lista da camada mais recente para a mais antiga: leia de
baixo para cima.)

A camada que instala o toolchain tem **439 MB**. A que "remove" tem **147 kB**,
porque ela só grava marcadores de exclusão. Os bytes continuam na camada
anterior, continuam sendo baixados por quem der `docker pull`, e continuam
extraíveis.

Não acreditei na minha própria afirmação e fui verificar. Dei `docker save`,
descomprimi as camadas e extraí do blob de 155,5 MiB:

```
usr/libexec/gcc/aarch64-alpine-linux-musl/15.2.0/cc1
  35,7 MiB — ELF 64-bit LSB executable, ARM aarch64, stripped
```

Um compilador GCC 15.2.0 íntegro, dentro de uma imagem "limpa". Com o
`cc1plus` junto, são **73,8 MiB só de compilador** em produção. A única
correção de verdade é multi-stage: o que não atravessa para o estágio final
não existe no artefato.

**Dois Pythons na mesma imagem.** A mesma camada carrega
`usr/bin/python3.14` — o Python do Alpine, puxado como dependência do
`python3-dev` — convivendo com o `/usr/local/bin/python3` que a imagem base
compilou do zero. São 1.374 arquivos em `usr/lib/python3.14`: um interpretador
inteiro instalado por engano, nunca usado, e que ninguém notou por sete anos.

**Ordem de cache invertida.** Em 2019 o `COPY /app` vem antes do
`pip install`: trocar um caractere no `app.py` recompilava o uWSGI inteiro. Em
2026 as dependências entram primeiro e o código por último.

**Sem `.dockerignore`.** O `COPY /app /app` levava junto o `.git`, os
`__pycache__` e qualquer arquivo de editor no diretório.

### Efeito medido

| | 2018 | 2026 |
|---|---|---|
| Pull | 100,0 MiB | 42,5 MiB (−58%) |
| Disco | 474 MB | 208 MB (−56%) |
| Build frio | 66s (rebuild 2019) | 25s (−62%) |
| Compilador no artefato | 73,8 MiB | 0 |

---

## Runtime e servidor de aplicação

### uWSGI ou gunicorn?

Troquei, mas o argumento não é o que costuma aparecer nessa discussão.

**uWSGI não está quebrado.** A versão 2.0.31 é de outubro de 2025, e eu
compilei ela sob Python 3.14.7 no rebuild desta comparação — funciona. O que o
projeto diz de si mesmo, no próprio README, é: *"The project is in maintenance mode (only
bugfixes and updates for new languages apis)"*, em vigor desde 24/10/2022, com
o aviso de não esperar resposta rápida em issues. Isso é um sinal a se aprender
a ler, não um obituário.

A razão prática de trocar é de **custo de empacotamento**:

| | uWSGI 2.0.31 | gunicorn 26.2.0 |
|---|---|---|
| Distribuição no PyPI | só sdist | wheel puro, 223 KB |
| Build precisa de | toolchain C completo | nada |
| Dependências de runtime | pcre | nenhuma |
| Postura do upstream | só correção desde 2022 | ativo |

O uWSGI não publica wheel. **Todo build compila C do zero** — e é exatamente
por isso que o Dockerfile de 2019 precisa de `build-base`, `linux-headers`,
`pcre-dev` e `python3-dev`. Aquela camada de 439 MB existe para servir um
"Hello World". Com gunicorn, o estágio de build não tem compilador nenhum, o
que elimina uma classe inteira de risco de cadeia de suprimentos além de
encolher a imagem.

A documentação do próprio Flask lista o Gunicorn primeiro entre as opções
auto-hospedadas.

### O que o `wsgi.ini` de 2019 não tinha

```ini
[uwsgi]
module = wsgi:app
master = true
processes = 5
http-socket = 0.0.0.0:5000
die-on-term = true
```

**Sem `need-app`.** Sem essa diretiva, o uWSGI sobe feliz mesmo quando a
aplicação falha ao importar, e serve 500 parecendo perfeitamente saudável.
Gerador silencioso de incidente.

**Sem `harakiri`.** Nenhum timeout de request. Um request travado prendia um
worker para sempre; cinco derrubavam o app com o pod ainda marcado como
saudável. Em 2026 o `timeout = 30` do gunicorn cobre isso.

**`processes = 5` fixo.** Sem relação nenhuma com o limite de CPU do pod — que
também não existia. Em 2026 o número vem da CPU disponível e o manifesto do
Kubernetes manda via `WEB_CONCURRENCY`, porque quem conhece o limite é ele.

**`http-socket` exposto direto.** É o parser mínimo do uWSGI, não feito para
encarar cliente não confiável, e era a porta de entrada do pod.

**Logs não estruturados.** Linhas de texto que nenhum backend de log parseia
sem regex. Em 2026 tudo sai em JSON de uma linha, configurado via
`logconfig_dict` para valer **também no processo master** — sem isso a saída
fica metade JSON, metade texto, e nada consegue ler os dois.

### O que 2019 acertou

`die-on-term = true`. Essa é sutil: sem ela o uWSGI trata SIGTERM como "recarregar",
e o Kubernetes fica esperando até o fim do período de graça para então mandar
SIGKILL. O eu de 2018 acertou a diretiva não-óbvia. `master = true` também
está certo.

### E o `/healthz`

Em 2019 não havia endpoint de saúde: a única rota era `/`, que renderiza HTML.
Sonda e usuário fazem perguntas diferentes, e a sonda bate a cada poucos
segundos em cada réplica. Em 2026 há `/healthz` devolvendo JSON, e a linha de
acesso dele é filtrada do log — senão o log de acesso vira quase só isso.

---

## Cadeia de suprimentos

### O problema em uma frase

A imagem `cirolini/flask-uwsgi:latest` foi publicada em **16/03/2018** e nunca
mais. Ela imprime `Hello World!`. O `app.py` neste repositório imprime
`Hello Fullstack!` desde 2021. O README mandava as pessoas rodarem uma imagem
que **não corresponde a commit nenhum** que se possa revisar — e 23.432
downloads depois, não existe nenhuma forma de descobrir de que código ela saiu.

Sem procedência, sem SBOM, sem assinatura, sem digest. `latest` é uma promessa
que ninguém assinou.

### O que mudou

| | 2019 | 2026 |
|---|---|---|
| Referência da imagem | tag `latest`, móvel | digest `sha256:...` |
| Base | tag flutuante | digest fixado |
| Dependências Python | `Flask`, sem versão | versão exata + hash sha256 |
| Actions do pipeline | — | fixadas por SHA de commit |
| Inventário | nenhum | SBOM SPDX (97 pacotes) |
| Assinatura | nenhuma | cosign keyless + Rekor |
| Ligação com o código | nenhuma | rótulos OCI + identidade no certificado |

**Actions fixadas por SHA, não por tag.** Tag em Git é móvel: quem controla o
repositório da action pode reapontar `v4` para outro código a qualquer momento.
Foi assim que o `tj-actions/changed-files` foi comprometido em março de 2025
(CVE-2025-30066): um token roubado reapontou as tags `v1` a `v45.0.7` para um
commit malicioso que despejava segredos nos logs de build, públicos. Mais de 23
mil repositórios dependiam daquela action. Se a base é fixada por digest e as dependências
por hash, as actions — que rodam com acesso ao token e ao registry — não podem
ser a exceção.

**cosign keyless.** Não existe chave privada para guardar, rotacionar ou vazar.
O cosign troca o token OIDC do job por um certificado de curta duração da
Fulcio e registra a assinatura no log público Rekor. Quem verificar depois
consegue provar que a imagem saiu **daquele workflow, naquele repositório**:

```bash
cosign verify \
  --certificate-identity-regexp '^https://github.com/cirolini/Docker-Flask-uWSGI/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/cirolini/docker-flask-uwsgi@sha256:...
```

Essa é a pergunta que o pipeline de 2019 não conseguia responder de jeito
nenhum.

**Fixar versão sem processo de atualização é dívida com data marcada.** É
literalmente a imagem de 2018: congelada, e por isso com 50 CVEs corrigíveis
acumulados. O digest responde "o que foi construído"; o Dependabot responde
"quando isso é revisado". Um sem o outro não resolve.

### Efeito medido

CVEs **com correção disponível**: 50 → 0.

Vale notar de onde vinham os 3 CVEs residuais do rebuild de 2019, porque eu
errei o diagnóstico na primeira tentativa: não eram dependência solta do app.
Eram `setuptools` e `msgpack` **vendorizados dentro do pip** que a imagem base
instala em `/usr/local/lib/python3.14/site-packages/pip/_vendor/`. Alpine e
Debian carregam o mesmo pip, e por isso tinham exatamente os mesmos 3. O venv
de produção não precisa de instalador: removendo o pip do estágio de runtime, a
conta foi a zero.

---

## Pipeline

### Antes

```groovy
stage "Unit Test"
    teste = "fullstack"

stage "Deploy PROD"
    input "Deploy to PROD?"
    customImage.push('latest')
    sh "kubectl apply -f https://raw.githubusercontent.com/.../master/k8s_app.yaml"
    sh "kubectl set image deployment app app=${imageName} --record"
```

### Por quê

**Um estágio de teste que não testa.** O corpo inteiro do `Unit Test` é uma
atribuição de string. Ele passa sempre, inclusive com o app quebrado. **Um
pipeline verde que não testa nada é pior que nenhum pipeline**, porque fabrica
confiança. Em 2026 são 11 testes em pytest e o build não começa antes de eles
passarem.

**O manifesto vem de uma branch móvel, em tempo de deploy.** O build fixa a
imagem no SHA do commit e então busca sua definição de infraestrutura de uma
URL na `master`. Código do commit X, infraestrutura de onde a master estiver
naquele segundo. Os dois não têm relação nenhuma.

Isso não é hipótese: ao mover os arquivos para `2019/` neste próprio trabalho,
aquela URL passou a dar 404 — inclusive para os forks que ainda rodam esse
pipeline. Escolhi deixar quebrar e documentar. É o primeiro exemplo do caso.

**Conflito entre `latest` e SHA.** O `apply` instala `:latest`, e o comando
seguinte sobrescreve com a tag do commit. Duas fontes de verdade e uma corrida
entre elas nas três réplicas.

**`kubectl --record` não existe mais.** A flag foi removida. O substituto é a
anotação `kubernetes.io/change-cause`. Esse pipeline não roda em cluster
nenhum hoje.

**`input` dentro de `node {}`.** Segurava um executor do Jenkins enquanto
esperava, possivelmente por dias. E sem `submitter`: qualquer pessoa com acesso
ao Jenkins aprovava produção.

**Registry em `127.0.0.1:30400`, sem autenticação, em HTTP.** Em 2026 é GHCR
com o `GITHUB_TOKEN` efêmero do job, sob um bloco `permissions:` explícito.

**Zero controle de cadeia de suprimentos.** Nada escaneava, inventariava ou
assinava a imagem antes de ela ir para produção.

### Depois

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml): lint e teste →
build com cache → Trivy → SBOM → publicação por digest → assinatura.

Duas decisões que valem explicar:

**O scan roda antes do push.** Se a imagem não passa, ela não chega ao
registry. Em 2019 a imagem ia para o registry e para produção sem ninguém
jamais ter olhado dentro.

**O portão bloqueia só no que tem correção.** `--ignore-unfixed` com
`HIGH,CRITICAL`. O relatório completo, incluindo o que não tem correção, vai
para a aba Security. Registrar é diferente de barrar — travar o pipeline em
CVE que ninguém pode corrigir só ensina o time a ignorar o scanner.

Testei o portão nas duas pontas: a imagem de 2026 passa, a de 2018 é barrada.

### O `input "Deploy to PROD?"`, traduzido

[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) usa
`environment: producao`, e o job fica pendente até um revisor obrigatório
aprovar (Settings → Environments → Required reviewers).

| | Jenkins 2019 | GitHub Actions 2026 |
|---|---|---|
| Custo da espera | segura um executor | job pendente, zero runner |
| Quem aprova | qualquer um com acesso | lista definida no environment |
| Registro | nenhum | quem, quando, qual execução |
| O que implanta | `latest` + manifesto da master | digest, com assinatura verificada |

O workflow **recusa tag e exige digest**: tag pode mudar entre a aprovação e o
deploy, e aí aprovou-se uma coisa e implantou-se outra.

---

## Deploy

### Antes

```yaml
containers:
  - name: app
    image: "127.0.0.1:30400/app:latest"
    imagePullPolicy: Always
    ports:
      - name: http
        containerPort: 5000
```

É o container inteiro. Sem `resources`, sem sonda, sem `securityContext`.

### O teste que decide a discussão

Subi um cluster kind de três nós com Kubernetes 1.37, marquei o namespace com
Pod Security Admission em `restricted` — o perfil mais rígido — e apliquei o
`2019/k8s_app.yaml` sem alterar uma linha:

```
deployment.apps/app created
Error creating: pods "app-65c6d664f7-njcdg" is forbidden:
  violates PodSecurity "restricted:latest":
  allowPrivilegeEscalation != false, unrestricted capabilities,
  runAsNonRoot != true, seccompProfile
```

O Deployment é aceito. **Zero pods sobem.** `No resources found in namespace`.

Aquele manifesto não é apenas inseguro em 2026 — ele **não é admitido**. Não é
uma questão de boa prática, é uma questão de o pod existir ou não.

O de 2026, no mesmo namespace: 3/3 réplicas, respondendo pelo Service,
rodando como `uid=10001(app)`, e `touch /teste` devolvendo
`Read-only file system`.

### Por quê, item a item

**Sondas.** Não havia nenhuma. São três perguntas diferentes: `startupProbe`
("já terminou de subir?") segura as outras durante o boot; `livenessProbe`
("travou?") **reinicia** o pod, e por isso precisa ser conservadora — uma
liveness nervosa transforma lentidão em loop de restart; `readinessProbe`
("pode receber tráfego?") só tira do Service, e é ela que faz o rollout não
derrubar requisição. Sem readiness, em 2019, todo deploy mandava tráfego para
pods que ainda estavam subindo.

**Recursos.** Sem `requests`/`limits` o pod fica na classe **BestEffort**:
primeiro a ser despejado sob pressão, sem garantia nenhuma de CPU. Combinado
com o `processes = 5` do uWSGI, eram cinco processos brigando pelo que
sobrasse do nó.

**Imagem por tag móvel.** Com `:latest`, `kubectl rollout undo` volta para a
mesma tag. **O rollback não reverte nada.** Digest resolve.

**PodDisruptionBudget.** Cobre o que nenhuma sonda cobre: interrupção
*voluntária* — `drain` para manutenção, upgrade de nó, autoscaler compactando
o cluster. Em 2019 um único `drain` podia levar as três réplicas juntas.

Drenei o nó que tinha os três pods, com `minAvailable: 2`:

```
evicting pod flask-hello-6f77b5ddf4-4s8jl
error when evicting (will retry after 5s):
  Cannot evict pod as it would violate the pod's disruption budget.
pod/flask-hello-6f77b5ddf4-fw9xf evicted
```

O PDB barrou e repetiu, despejando um pod por vez. O app nunca ficou abaixo de
duas réplicas prontas.

**`replicas: 3` sem espalhamento não é alta disponibilidade.** São três cópias
do mesmo ponto único de falha, se o scheduler empilhar as três num nó. Uma
ressalva honesta: uso `whenUnsatisfiable: ScheduleAnyway`, que é preferência e
não garantia — depois do dreno, as três réplicas realmente acabaram no mesmo
nó. `DoNotSchedule` daria a garantia ao custo de deixar pods `Pending` num
cluster pequeno. É uma escolha, não mágica.

**`automountServiceAccountToken`.** O pod não fala com a API do Kubernetes,
mas carregava um token válido montado — credencial de graça para quem
conseguisse execução remota dentro do container.

**`type: LoadBalancer`.** Para um exemplo de aula, isso provisiona e cobra um
balanceador de nuvem, e expõe o app direto na internet sem TLS nem política de
rede. Em 2026 é `ClusterIP`; quem publica num cluster real é um Ingress.

---

## O que eu errei no caminho

Deixei esta seção por último de propósito. A auditoria pareceria mais
competente sem ela, e seria menos útil.

**Confundi tamanho comprimido com descomprimido.** Li o `full_size` da API do
Docker Hub — 104.840.715 bytes — e reportei "100 MB" como o tamanho da imagem.
É o tamanho **comprimido**, o que se baixa da rede. Em disco no nó aquela
imagem ocupa 474 MB. Três comandos davam três respostas diferentes
(`docker images` 474MB, `docker inspect` 100 MiB, o tar do `docker save`
100 MiB) e eu demorei a perceber que mediam coisas distintas. A tabela deste
documento separa as duas colunas por isso.

**Diagnostiquei errado os 3 CVEs residuais.** Afirmei que vinham de
dependência não fixada. Não vinham: eram `setuptools` e `msgpack`
vendorizados dentro do pip da imagem base. Descobri porque o Trivy apontava
pacotes que o `importlib.metadata` jurava não existir — foi a contradição que
abriu o caso.

**Minha verificação de "o pip foi removido?" deu falso negativo.** Rodei
`importlib.util.find_spec('pip')` de dentro do venv, que foi criado com
`--without-pip`. Claro que deu ausente. O pip estava no interpretador base o
tempo todo, em outro caminho. Verificação que só olha onde você espera não é
verificação.

**Quase reportei um falso achado sobre amd64.** O build do Dockerfile de 2019
falhou em amd64 na minha máquina e eu ia registrar "não constrói mais em
amd64". Fui atrás: com `--no-build-isolation` o uWSGI compila normalmente em
amd64 (84s, wheel gerado). A falha era da emulação qemu — o passo de
compilação morria sem emitir **uma linha**, que é assinatura de processo
morto, não de erro de compilação. Por isso existe o workflow de comparação
rodando em runner amd64 nativo.

**Escrevi um teste de fumaça que a minha própria política rejeitou.** O
`make smoke` usava um pod de `curl` sem `securityContext`, e o Pod Security
Admission do namespace barrou ele exatamente como barrou o manifesto de 2019.

**Meu `make deploy` sujava o repositório.** `kustomize edit` reescreve o
arquivo versionado no lugar, e meu comando de restaurar falhava em silêncio.

**Meu pipeline teria quebrado no primeiro push.** Eu usei
`IMAGE_NAME: ${{ github.repository }}`, que aqui é `cirolini/Docker-Flask-uWSGI`
— com maiúsculas. Nome de imagem em registry OCI precisa ser minúsculo.

**Removi o cabeçalho do `uv` do requirements.txt por estética.** É por ele que
o Dependabot reconhece arquivo compilado e regera os hashes junto. Sem o
cabeçalho, ele trocaria a versão e deixaria o hash velho — PR verde, build
quebrado.

A lição comum a todas: **medir é diferente de supor, e verificar é diferente
de olhar onde você espera que esteja.**

---

## O que provavelmente vai envelhecer mal

Escrever isto em 2026 sabendo como 2019 envelheceu obriga à honestidade.
Meus candidatos:

- **Python 3.14 e Debian trixie** vão sair de suporte. O digest fixado vira o
  problema se o Dependabot for desligado — é a mesma armadilha de 2018, só que
  mais lenta.
- **cosign e Sigstore** ainda estão consolidando formato. `cosign attest` já
  mudou de assinatura antes.
- **gunicorn com workers síncronos** é a escolha conservadora hoje. Granian
  (Rust, 2.8.3 em setembro de 2026) é o candidato mais interessante a
  substituto, e provavelmente esta seção vai parecer datada primeiro.
- **A contagem de CVE como métrica.** Já é ruim; a tendência é piorar conforme
  scanners competem em quem reporta mais.
- **Pod Security Admission** substituiu PodSecurityPolicy, que foi removida.
  Nada garante que ele seja o fim da linha.

Se você está lendo isto em 2033: o exercício é o mesmo. Rode
`make scan`, rode o workflow de comparação, e veja o que os números dizem
agora.
