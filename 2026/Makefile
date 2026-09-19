# Ciclo local completo do app de 2026, do build ao cluster.
#
# Existe para que a aula não dependa de nuvem nem de credencial: `make demo`
# sobe um cluster de três nós, constrói, implanta e prova que funcionou.

SHELL := /bin/bash
.DEFAULT_GOAL := help

IMAGEM     ?= flask-hello
TAG        ?= dev
CLUSTER    ?= flask-hello
NAMESPACE  ?= flask-hello
PORTA      ?= 8080

.PHONY: help
help: ## Lista os alvos disponíveis
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- qualidade --

.PHONY: venv
venv: ## Cria o venv local com as dependências de desenvolvimento
	uv venv --python 3.14
	uv pip install --require-hashes -r requirements-dev.txt

.PHONY: test
test: ## Roda os testes
	.venv/bin/pytest

.PHONY: lint
lint: ## Roda o ruff
	.venv/bin/ruff check .

.PHONY: compile-deps
compile-deps: ## Recompila requirements*.txt a partir do pyproject.toml
	uv pip compile pyproject.toml --generate-hashes \
		--python-version 3.14 --python-platform linux -o requirements.txt
	uv pip compile pyproject.toml --extra dev --generate-hashes \
		--python-version 3.14 --python-platform linux -o requirements-dev.txt

# ------------------------------------------------------------------ imagem --

.PHONY: build
build: ## Constrói a imagem
	docker build -t $(IMAGEM):$(TAG) .

.PHONY: scan
scan: ## Escaneia a imagem com o mesmo portão do CI
	@echo "== CVEs com correção disponível (portão do CI) =="
	trivy image --scanners vuln --severity HIGH,CRITICAL \
		--ignore-unfixed --exit-code 1 $(IMAGEM):$(TAG)
	@echo "== relatório completo, incluindo o que não tem correção =="
	trivy image --scanners vuln --severity HIGH,CRITICAL $(IMAGEM):$(TAG)

.PHONY: sbom
sbom: ## Gera o SBOM em SPDX
	syft $(IMAGEM):$(TAG) -o spdx-json=sbom.spdx.json
	@echo "sbom.spdx.json gerado"

.PHONY: run
run: ## Roda o container local com o mesmo endurecimento do Kubernetes
	docker run --rm -p 5000:5000 \
		--read-only --tmpfs /dev/shm:rw,size=64m \
		--cap-drop ALL --security-opt no-new-privileges \
		--user 10001:10001 \
		$(IMAGEM):$(TAG)

# --------------------------------------------------------------- kubernetes --

.PHONY: kind-up
kind-up: ## Sobe o cluster kind de três nós
	kind create cluster --config k8s/kind.yaml --wait 120s
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	@echo
	@echo "Aplicando Pod Security Admission em modo restricted."
	@echo "É o perfil mais rígido do Kubernetes, e é aqui que o manifesto de"
	@echo "2019 seria recusado: root, sem seccomp e com todas as capabilities."
	kubectl label namespace $(NAMESPACE) \
		pod-security.kubernetes.io/enforce=restricted \
		pod-security.kubernetes.io/enforce-version=latest --overwrite

.PHONY: load
load: build ## Carrega a imagem local no cluster kind
	kind load docker-image $(IMAGEM):$(TAG) --name $(CLUSTER)

.PHONY: deploy
deploy: load ## Implanta no cluster kind
	@# `kustomize edit` reescreve o arquivo no lugar. Renderizando a partir de
	@# uma cópia temporária, o k8s/ versionado nunca fica sujo - e o manifesto
	@# aplicado continua sendo exatamente o deste commit.
	@tmp=$$(mktemp -d) && cp k8s/*.yaml $$tmp/ && \
		( cd $$tmp && kustomize edit set image \
			ghcr.io/cirolini/docker-flask-uwsgi=$(IMAGEM):$(TAG) && \
			kustomize build . ) | kubectl apply -n $(NAMESPACE) -f - && \
		rm -rf $$tmp
	kubectl rollout status -n $(NAMESPACE) deployment/flask-hello --timeout=120s

.PHONY: smoke
smoke: ## Prova que o deploy funcionou, de dentro do cluster
	@echo "== pods =="
	@kubectl get pods -n $(NAMESPACE) \
		-o custom-columns=NOME:.metadata.name,NÓ:.spec.nodeName,PRONTO:.status.containerStatuses[0].ready
	@echo
	@# De dentro de um pod do app: testa DNS do Service e roteamento, sem
	@# precisar de imagem extra - e um pod de curl avulso seria recusado pelo
	@# Pod Security Admission deste namespace, como qualquer outro.
	@echo "== GET / através do Service (de dentro do cluster) =="
	@kubectl exec -n $(NAMESPACE) deploy/flask-hello -- python -c \
		"import urllib.request as u; print(u.urlopen('http://flask-hello/').read().decode())"
	@echo
	@echo "== GET /healthz =="
	@kubectl exec -n $(NAMESPACE) deploy/flask-hello -- python -c \
		"import urllib.request as u; print(u.urlopen('http://flask-hello/healthz').read().decode())"

.PHONY: verify
verify: ## Confere o endurecimento no pod que está rodando
	@echo "== usuário efetivo dentro do container =="
	@kubectl exec -n $(NAMESPACE) deploy/flask-hello -- id
	@echo
	@echo "== o root filesystem é read-only? =="
	@kubectl exec -n $(NAMESPACE) deploy/flask-hello -- \
		sh -c 'touch /teste 2>&1 || echo "  escrita recusada, como esperado"'
	@echo
	@echo "== securityContext efetivo =="
	@kubectl get pod -n $(NAMESPACE) -l app.kubernetes.io/name=flask-hello \
		-o jsonpath='{.items[0].spec.containers[0].securityContext}' | python3 -m json.tool

.PHONY: drain
drain: ## Drena um nó para ver o PodDisruptionBudget agindo
	@no=$$(kubectl get pods -n $(NAMESPACE) -l app.kubernetes.io/name=flask-hello \
		-o jsonpath='{.items[0].spec.nodeName}'); \
	echo "drenando $$no - o PDB (minAvailable 2) deve segurar o ritmo"; \
	kubectl drain $$no --ignore-daemonsets --delete-emptydir-data --timeout=90s; \
	kubectl uncordon $$no

.PHONY: port-forward
port-forward: ## Expõe o Service em localhost:$(PORTA)
	@echo "abra http://localhost:$(PORTA)/"
	kubectl port-forward -n $(NAMESPACE) svc/flask-hello $(PORTA):80

.PHONY: logs
logs: ## Segue os logs (JSON) de todas as réplicas
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=flask-hello -f --max-log-requests=10

.PHONY: kind-down
kind-down: ## Destrói o cluster
	kind delete cluster --name $(CLUSTER)

.PHONY: demo
demo: kind-up deploy smoke verify ## Ciclo completo, do zero ao app respondendo
