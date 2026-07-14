# Local kind demonstration for the email-dedup assignment.
#
# Prerequisites: Docker, kind, kubectl, make
#
#   make cluster-up
#   make ingest
#   make port-forward   # then open http://127.0.0.1:8000/docs
#   make evaluate
#   make cluster-down

CLUSTER_NAME ?= email-dedup
NAMESPACE ?= email-dedup
IMAGE ?= email-dedup:local
KUBECTL ?= kubectl
KIND ?= $(shell command -v kind 2>/dev/null || echo $(HOME)/bin/kind)

.PHONY: cluster-up cluster-down status ingest evaluate port-forward \
	build load apply wait-ready help

help:
	@echo "Targets:"
	@echo "  cluster-up     Create kind cluster, build/load image, apply k8s, wait ready"
	@echo "  status         Show pods and deployments"
	@echo "  ingest         Load data/test via Job"
	@echo "  evaluate       Score data/eval in-memory (no DB ingest)"
	@echo "  port-forward   Forward api Service to localhost:8000"
	@echo "  cluster-down   Delete the kind cluster"

build:
	docker build -t $(IMAGE) .

load:
	$(KIND) load docker-image $(IMAGE) --name $(CLUSTER_NAME)

apply:
	$(KUBECTL) apply -f k8s/00-namespace.yaml
	$(KUBECTL) apply -f k8s/01-config.yaml
	$(KUBECTL) apply -f k8s/02-postgres.yaml
	$(KUBECTL) wait --namespace $(NAMESPACE) --for=condition=ready pod \
		-l app=postgres --timeout=120s
	$(KUBECTL) delete job migrate --namespace $(NAMESPACE) --ignore-not-found
	$(KUBECTL) apply -f k8s/03-migrate.yaml
	$(KUBECTL) wait --namespace $(NAMESPACE) --for=condition=complete job/migrate \
		--timeout=120s
	$(KUBECTL) apply -f k8s/04-api.yaml
	$(KUBECTL) apply -f k8s/05-worker.yaml

wait-ready:
	$(KUBECTL) wait --namespace $(NAMESPACE) --for=condition=available \
		deployment/api --timeout=120s
	$(KUBECTL) wait --namespace $(NAMESPACE) --for=condition=available \
		deployment/worker --timeout=120s
	@echo "Waiting for 3 worker pods..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do \
		ready=$$($(KUBECTL) get pods --namespace $(NAMESPACE) -l app=worker \
			--field-selector=status.phase=Running \
			-o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' \
			| grep -c true || true); \
		if [ "$$ready" -ge 3 ]; then echo "workers ready=$$ready"; exit 0; fi; \
		sleep 2; \
	done; \
	echo "timed out waiting for 3 workers"; exit 1

cluster-up:
	@if ! command -v $(KIND) >/dev/null 2>&1; then \
		echo "error: kind not found. Install: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"; \
		exit 1; \
	fi
	@if ! $(KIND) get clusters 2>/dev/null | grep -qx '$(CLUSTER_NAME)'; then \
		$(KIND) create cluster --name $(CLUSTER_NAME); \
	else \
		echo "kind cluster '$(CLUSTER_NAME)' already exists"; \
	fi
	$(MAKE) build load apply wait-ready
	@echo ""
	@echo "Cluster ready. Next:"
	@echo "  make ingest"
	@echo "  make port-forward   # http://127.0.0.1:8000/docs"
	@echo "  make evaluate"
	@echo "  make cluster-down"

status:
	$(KUBECTL) get deploy,pods,svc,job --namespace $(NAMESPACE)

ingest:
	$(KUBECTL) delete job loader-test --namespace $(NAMESPACE) --ignore-not-found
	$(KUBECTL) apply -f k8s/06-loader-test.yaml
	$(KUBECTL) wait --namespace $(NAMESPACE) --for=condition=complete job/loader-test \
		--timeout=300s
	$(KUBECTL) logs --namespace $(NAMESPACE) job/loader-test

evaluate:
	$(KUBECTL) delete job evaluate --namespace $(NAMESPACE) --ignore-not-found
	$(KUBECTL) apply -f k8s/07-evaluate.yaml
	$(KUBECTL) wait --namespace $(NAMESPACE) --for=condition=complete job/evaluate \
		--timeout=300s
	$(KUBECTL) logs --namespace $(NAMESPACE) job/evaluate

port-forward:
	@echo "OpenAPI: http://127.0.0.1:8000/docs  (Ctrl-C to stop)"
	$(KUBECTL) port-forward --namespace $(NAMESPACE) svc/api 8000:8000

cluster-down:
	$(KIND) delete cluster --name $(CLUSTER_NAME)
