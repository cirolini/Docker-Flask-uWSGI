# Roteiro de aula — 50 minutos

**Disciplina:** Cultura e Práticas DevOps e DevSecOps
**Tema:** o que mudou em entrega de container entre 2019 e 2026, e por quê

A aula inteira gira em torno de um repositório real, com histórico público e
uma imagem no Docker Hub baixada 23 mil vezes. Nada de exemplo sintético: os
erros são meus, os números são medidos na hora.

## Antes da aula

Na máquina que vai projetar:

```bash
git clone https://github.com/cirolini/Docker-Flask-uWSGI
cd Docker-Flask-uWSGI

docker pull --platform linux/amd64 cirolini/flask-uwsgi:latest   # ~100 MB
cd 2026 && make build && make kind-up                            # kind demora
```

Deixe **dois terminais** abertos (2019 e 2026) e a aba de Actions do
repositório no navegador. Tenha `trivy`, `kind` e `kubectl` prontos — cluster
subindo ao vivo come cinco minutos do relógio.

Se a internet falhar, os números estão todos em
[then-vs-now.md](then-vs-now.md); a aula funciona só com o documento.

---

## 0–5 min · A provocação

Abra o Docker Hub em `cirolini/flask-uwsgi` e mostre: **23.432 downloads,
última atualização 16 de março de 2018.**

Rode:

```bash
docker run --rm -p 5000:5000 cirolini/flask-uwsgi:latest
curl -s localhost:5000
```

Sai `Hello World!`. Agora abra `2019/app/app.py` no projetor: o código diz
`Hello Fullstack!`.

> **A pergunta da aula:** de qual commit saiu a imagem que 23 mil pessoas
> baixaram?

Resposta: não dá para saber. Deixe a pergunta no ar.

---

## 5–12 min · O Dockerfile que muda sozinho

Mostre a primeira linha de `2019/Dockerfile`: `FROM python:3-alpine`.

```bash
docker run --rm cirolini/flask-uwsgi:latest python -V     # 3.6.4
docker build -t rebuild -f 2019/Dockerfile 2019 && \
docker run --rm rebuild python -V                         # 3.14.7
```

Mesmo arquivo, mesmo commit, dois runtimes. Idem para o Flask: 0.12.2 → 3.1.3,
duas versões maiores, e o `requirements.txt` diz apenas `Flask`.

> **Pergunta para a turma:** esse build é reproduzível? E se o Flask 4 sair
> amanhã de madrugada?

Conceitos: tag flutuante vs digest, pin de dependência, reprodutibilidade.

---

## 12–22 min · O compilador fantasma *(o momento da aula)*

Peça um palpite antes de mostrar: **reconstruir a imagem de 2019 hoje deixa ela
maior ou menor?** Praticamente todo mundo responde "menor".

```bash
docker images | grep -E "flask-uwsgi|rebuild"
```

100 MiB → 182 MiB. **Cresceu 82%.** Deixe o desconforto durar.

```bash
docker history rebuild --format '{{.Size}}\t{{.CreatedBy}}' | head -5
```

```
147kB   RUN apk del .build-dependencies && rm -rf /var/cache/apk/*
 23MB   RUN pip install -r /app/requirements.txt
439MB   RUN apk add --virtual .build-dependencies ...
```

Instala 439 MB, "remove" com 147 kB. Pergunte por quê antes de explicar
camadas e whiteouts.

O golpe final — extrair o compilador da imagem "limpa":

```bash
docker save rebuild -o /tmp/r.tar && mkdir -p /tmp/r && tar -xf /tmp/r.tar -C /tmp/r
for b in /tmp/r/blobs/sha256/*; do
  tar -tzf "$b" 2>/dev/null | grep -q 'libexec/gcc.*/cc1$' && echo "toolchain em: $b"
done
```

`cc1` tem 35,7 MiB e é um ELF funcional. Com o `cc1plus`, 73,8 MiB de
compilador em produção.

> **Discussão:** por que um compilador dentro do container de produção é
> problema, e não só desperdício?

Leve a turma até: superfície de ataque, ferramenta pronta para quem conseguir
RCE, e a diferença entre "sumiu do filesystem" e "saiu do artefato".

**Conclusão:** a correção é multi-stage. E a lição maior — *rebuild não é
arquitetura*: reconstruir troca as peças podres e mantém o defeito estrutural.

---

## 22–32 min · CVE, e como a métrica engana

```bash
trivy image --scanners vuln cirolini/flask-uwsgi:latest | tail -5     # 50
cd 2026 && trivy image --scanners vuln flask-hello:dev | tail -5      # 151
```

A imagem nova tem **mais** CVEs. Deixe a turma reagir.

```bash
trivy image --scanners vuln --ignore-unfixed flask-hello:dev | tail -3   # 0
```

Zero. Debian publica vulnerabilidade menor que escolhe não corrigir; o banco
do Alpine lista sobretudo o que já foi corrigido.

> **Discussão:** um fornecedor mostra um gráfico "nossa imagem tem 3 CVEs, a do
> concorrente tem 151". O que você pergunta antes de acreditar?

Conceitos: CVE corrigível vs total, política de rastreamento por distro,
métrica que vira teatro.

Feche com a história dos 3 CVEs residuais: eu diagnostiquei errado, achei que
era dependência solta, e eram `setuptools` e `msgpack` dentro do `pip/_vendor`
da imagem base. Tirar o pip do runtime zerou a conta. **Verificar é diferente
de olhar onde você espera que esteja.**

---

## 32–42 min · O manifesto que não sobe mais

```bash
kubectl create namespace demo
kubectl label namespace demo pod-security.kubernetes.io/enforce=restricted
kubectl apply -n demo -f 2019/k8s_app.yaml
kubectl get pods -n demo
```

`No resources found in demo namespace.`

```bash
kubectl get events -n demo --field-selector reason=FailedCreate | head -3
```

`pods "app-..." is forbidden: violates PodSecurity "restricted:latest"` — com
quatro violações de uma vez.

> Não é "má prática". O pod **não existe**.

Agora o de 2026:

```bash
cd 2026 && make deploy smoke verify
```

3/3 réplicas, `uid=10001`, `touch /teste` → `Read-only file system`.

E o PodDisruptionBudget agindo:

```bash
make drain
```

`Cannot evict pod as it would violate the pod's disruption budget`, com retry
a cada 5s.

> **Discussão:** readiness, liveness e startup respondem a três perguntas
> diferentes. Quais? O que acontece se você usar liveness onde queria
> readiness?

(Resposta: reinicia o pod em vez de só tirá-lo do balanceamento — lentidão
momentânea vira loop de restart.)

---

## 42–50 min · Quem assina o que você implanta

Volte à pergunta dos 5 minutos iniciais: **de qual commit saiu aquela imagem?**

Mostre `2019/Jenkinsfile` no projetor e leia em voz alta:

```groovy
stage "Unit Test"
    teste = "fullstack"
```

Deixe rir. Depois: **um pipeline verde que não testa nada é pior que nenhum
pipeline**, porque fabrica confiança.

Duas linhas abaixo:

```groovy
sh "kubectl apply -f https://raw.githubusercontent.com/.../master/k8s_app.yaml"
```

> **Pergunta:** o build fixa a imagem no SHA do commit. De onde vem o
> manifesto?

De uma branch móvel, em tempo de deploy. E hoje essa URL dá **404**, porque eu
movi os arquivos para `2019/` — quebrando os forks que ainda rodam esse
pipeline. O caso se provou sozinho.

Feche com o contraste, na aba Actions:

| | 2019 | 2026 |
|---|---|---|
| Teste | string | 11 testes, bloqueiam o build |
| Scan | nenhum | antes do push; não passou, não sobe |
| Inventário | nenhum | SBOM SPDX |
| Assinatura | nenhuma | cosign keyless + Rekor |
| Aprovação de prod | `input`, qualquer um | environment, revisor obrigatório |

E o comando que responde a pergunta inicial:

```bash
cosign verify \
  --certificate-identity-regexp '^https://github.com/cirolini/Docker-Flask-uWSGI/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/cirolini/docker-flask-uwsgi@sha256:...
```

> **Fechamento:** em 2019 eu não tinha como provar de onde vinha o que ia para
> produção. Nenhuma das ferramentas de hoje é sobre burocracia — são todas
> sobre conseguir responder essa pergunta.

---

## Exercícios

1. **Reproduza os números.** Rode a comparação e traga a tabela. Os valores
   batem com os de [then-vs-now.md](then-vs-now.md)? Se não, por quê?
2. **Quebre o portão.** Adicione ao `2026/pyproject.toml` uma dependência com
   CVE conhecido e corrigível. O CI deve barrar. Por que `--ignore-unfixed`
   muda o resultado?
3. **Consertando 2019 sem reescrever.** Qual é a **menor** mudança no
   `2019/Dockerfile` que tira o compilador da imagem final? Meça o antes e o
   depois.
4. **Faça o pod de 2019 ser admitido.** Qual é o conjunto mínimo de campos a
   acrescentar em `2019/k8s_app.yaml` para ele passar no `restricted`? O app
   ainda funciona depois? *(Dica: ele roda como root e escreve em disco.)*
5. **Ache o próximo.** Leia a seção "O que provavelmente vai envelhecer mal" e
   escreva a sua previsão para 2033, com justificativa.

## Se sobrar tempo

- `2019/app/wsgi.ini` tem **uma** diretiva que o eu de 2018 acertou e que a
  maioria dos tutoriais da época errava. Qual, e o que acontece sem ela?
  *(`die-on-term`; sem ela o SIGTERM do Kubernetes vira "recarregar" e o pod
  só morre no SIGKILL.)*
- Por que fixar action do GitHub por SHA e não por tag? *(tj-actions/changed-files, CVE-2025-30066, março de 2025: tags reapontadas para commit malicioso.)*
- uWSGI está morto? *(Não — 2.0.31 é de out/2025. Está em maintenance mode
  desde 2022 e só distribui sdist. A troca é de custo, não obituário.)*
