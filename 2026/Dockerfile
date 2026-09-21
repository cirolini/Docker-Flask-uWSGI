# syntax=docker/dockerfile:1

# ============================================================================
# O mesmo app de 2019, construído com as práticas de 2026.
# Cada decisão aqui responde a um achado da auditoria — docs/then-vs-now.md.
# ============================================================================

# Base fixada por digest, não por tag. `python:3-alpine` do Dockerfile de 2019
# entregava Python 3.6 em 2018 e entrega Python 3.14 hoje: a mesma linha, dois
# runtimes diferentes, sem nenhum commit registrando a troca. O digest faz o
# build ser reproduzível; atualizá-lo vira um PR do Dependabot, que é revisável.
ARG PYTHON_IMAGE=python:3.14-slim-trixie@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2

# ---------------------------------------------------------------------------
# Estágio 1: builder — monta o virtualenv. Nada daqui vai para a imagem final.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

# uv fixado por digest também: é o que instala as dependências, então é parte
# da cadeia de suprimentos tanto quanto elas.
COPY --from=ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 /uv /usr/local/bin/uv

WORKDIR /build

# `--without-pip`: o virtualenv de produção não precisa de instalador. Em 2019
# pip, setuptools e wheel ficavam na imagem final — e foram responsáveis por
# 6 dos 21 CVEs HIGH medidos naquela imagem. Ferramenta de build não é runtime.
RUN python -m venv --without-pip /opt/venv

# Só o requirements primeiro: assim mudar código do app não invalida a camada
# de dependências. Em 2019 o COPY do app vinha antes do pip install, então
# trocar um caractere no app.py recompilava o uWSGI inteiro do zero.
COPY requirements.txt .

# --require-hashes recusa qualquer artefato cujo sha256 não bata com o que está
# no requirements.txt. Em 2019 o arquivo dizia só "Flask" e "uwsgi": qualquer
# release nova, inclusive uma comprometida, entrava calada no próximo build.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
        --python /opt/venv/bin/python \
        --require-hashes \
        --no-cache \
        -r requirements.txt

# ---------------------------------------------------------------------------
# Estágio 2: runtime — só o interpretador, o venv e o código.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# Rótulos OCI: é isto que liga a imagem de volta ao commit que a gerou. A imagem
# publicada em 2018 não tem nenhum, e por isso não há como descobrir de que
# código ela saiu — ela diz "Hello World!" e o repositório diz "Hello Fullstack!".
LABEL org.opencontainers.image.title="flask-hello-2026" \
      org.opencontainers.image.description="Flask + hostname: o exemplo de 2019 entregue do jeito de 2026" \
      org.opencontainers.image.source="https://github.com/cirolini/Docker-Flask-uWSGI" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Usuário não-root com UID numérico fixo. Numérico, e não nome, porque o
# `runAsNonRoot` do Kubernetes precisa provar que o UID != 0 antes de subir o
# container — com nome de usuário ele não consegue verificar e recusa o pod.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

# A imagem base traz pip no site-packages do interpretador, e o pip vendoriza
# setuptools e msgpack. O app roda inteiro pelo /opt/venv, então esse pip é peso
# morto — mas o scanner o enxerga, e ele responde por 100% dos CVEs corrigíveis
# tanto desta imagem quanto do rebuild de 2019. Sair do Alpine não resolveria:
# as duas bases carregam o mesmo pip.
RUN python3 -c "\
import glob, os, shutil, sysconfig; \
purelib = sysconfig.get_paths()['purelib']; \
[shutil.rmtree(p, ignore_errors=True) for p in glob.glob(os.path.join(purelib, 'pip*'))]" \
    && ! python3 -c "import pip" 2>/dev/null

WORKDIR /app

COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --chown=10001:10001 app/ ./app/
COPY --chown=10001:10001 gunicorn.conf.py ./

USER 10001:10001

EXPOSE 5000

# Sem curl nem wget na imagem — um binário a mais é superfície de ataque a mais,
# e o Python já está aqui. Em 2019 não havia healthcheck nenhum.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2).status == 200 else 1)"]

# Forma exec, não shell: assim o gunicorn é o PID 1 e recebe o SIGTERM do
# Kubernetes direto. Na forma shell quem recebe é o /bin/sh, que não repassa,
# e o pod só morre no fim do terminationGracePeriod — 30 segundos de 503.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.main:app"]
