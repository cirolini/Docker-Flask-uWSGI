# Docker-Flask-uWSGI

O mesmo "Hello" em Flask — imprime uma saudação e o hostname do container —
entregue do jeito de **2019** e do jeito de **2026**, lado a lado.

Este repositório foi um exemplo que usei em palestras e aulas entre 2018 e
2021. Em vez de atualizá-lo, preservei o original e construí a versão moderna
ao lado. O aplicativo é o mesmo de propósito: **o assunto é como se constrói,
protege e entrega um container**, não o que o app faz.

📖 **[docs/then-vs-now.md](docs/then-vs-now.md)** — o estudo de caso completo,
com os números medidos e o porquê de cada decisão.
🎓 **[docs/aula.md](docs/aula.md)** — roteiro de aula de 50 minutos.

---

## As duas versões

<table>
<tr>
<th width="50%">2019 — como era</th>
<th width="50%">2026 — como é hoje</th>
</tr>
<tr valign="top">
<td>

**[`2019/`](2019/)** — intocado, exatamente como estava
(tag [`legacy-2019`](../../releases/tag/legacy-2019))

- `python:3-alpine`, tag flutuante
- uWSGI, compilado a cada build
- `Flask` e `uwsgi` sem versão fixada
- estágio único, roda como root
- Jenkinsfile, registry em `127.0.0.1`
- manifesto sem sonda, limite ou `securityContext`

```bash
docker build -t hello:2019 2019
docker run -p 5000:5000 hello:2019
curl localhost:5000
```

</td>
<td>

**[`2026/`](2026/)** — mesma saída, outra entrega

- `python:3.14-slim-trixie`, fixado por digest
- gunicorn, wheel puro, sem compilador
- dependências com versão exata e hash
- multi-stage, uid 10001, rootfs read-only
- GitHub Actions com scan, SBOM e assinatura
- manifesto com sondas, PDB e `securityContext`

```bash
cd 2026
make build
make run
curl localhost:5000
```

</td>
</tr>
</table>

---

## Os números

Mesmo aplicativo, medido nas duas pontas:

| | Publicada em 2018 | 2026 | |
|---|---|---|---|
| Pull (comprimido) | 100,0 MiB | **42,5 MiB** | −58% |
| Disco | 474 MB | **208 MB** | −56% |
| CVEs com correção disponível | 50 | **0** | |
| Build a frio | 66s | **25s** | −62% |
| Compilador embarcado | 73,8 MiB | **0** | |
| Usuário | root | **uid 10001** | |
| Sobe com Pod Security `restricted` | **não** | sim | |

A última linha é a mais direta: aplicado num namespace com Pod Security
Admission em `restricted`, o manifesto de 2019 é recusado e **nenhum pod
sobe**. Ele não é só inseguro em 2026 — não é admitido.

Reproduza você mesmo: Actions → **Comparação 2019 vs 2026** → Run workflow.
Roda em runner amd64 nativo e publica a tabela no resumo da execução.

---

## Rodando o de 2026

Precisa de [Docker](https://docs.docker.com/get-docker/),
[uv](https://docs.astral.sh/uv/), [Trivy](https://trivy.dev/),
[kind](https://kind.sigs.k8s.io/) e kubectl.

```bash
cd 2026
make help          # lista tudo

make venv test     # testes
make build scan    # imagem e scan de vulnerabilidade
make run           # local, com o mesmo endurecimento do Kubernetes

make demo          # cluster kind de 3 nós, deploy e verificação
make drain         # mostra o PodDisruptionBudget segurando um dreno
make kind-down     # destrói o cluster
```

---

## Estrutura

```
2019/          o repositório original, sem alterações
2026/          app, Dockerfile, manifestos Kubernetes e Makefile
docs/          o estudo de caso e o roteiro de aula
.github/       pipeline, comparação automatizada e Dependabot
```

---

## Um aviso para quem chegou pelo Docker Hub

A imagem **`cirolini/flask-uwsgi:latest` está congelada desde 16/03/2018** e
não corresponde ao código deste repositório — ela imprime `Hello World!`,
enquanto o `app.py` imprime `Hello Fullstack!` desde 2021. Tem 50
vulnerabilidades com correção disponível, roda como root, e é amd64 apenas.

Ela continua publicada de propósito: é a evidência central do estudo de caso,
e derrubá-la quebraria os 23 mil downloads de quem a referencia. **Não use em
produção.** Se quiser rodar algo, use o `2026/`.

Isso é o que uma tag `latest` sem procedência significa na prática: um
artefato sem dono, sem data e sem ligação com código nenhum. A versão de 2026
publica por digest, assinado, com SBOM — e a assinatura é verificável por
qualquer pessoa:

```bash
cosign verify \
  --certificate-identity-regexp '^https://github.com/cirolini/Docker-Flask-uWSGI/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/cirolini/docker-flask-uwsgi@sha256:...
```

---

## Licença e uso

[MIT](LICENSE). Material de aula de **Cultura e Práticas DevOps e DevSecOps**
(Unisinos) — se for usar em aula, um link de volta é bem-vindo.
