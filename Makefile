TRIVY_VERSION    ?= 0.67.0
GITLEAKS_VERSION ?= v8.28.0
TRIVY = docker run --rm -v "$(CURDIR):/src" -v trivy-cache:/root/.cache/trivy -w /src \
	aquasec/trivy:$(TRIVY_VERSION)
TRIVY_FLAGS = --severity HIGH,CRITICAL --exit-code 1 --skip-version-check

.DEFAULT_GOAL := help

.PHONY: help sync lint fmt test test-integration check hooks smoke eval load \
	up down ps logs clean \
	images image-check \
	security sec-secrets sec-deps sec-config sec-images \
	gpu gpu-docker gpu-watch

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\nTargets:\n"} \
		/^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# --- Python ---
sync: ## Install all workspace packages
	uv sync --all-packages

lint: ## Run ruff format check, ruff lint, mypy and lint-imports
	uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports

fmt: ## Format code with ruff and apply safe fixes
	uv run ruff format . && uv run ruff check --fix .

test: ## Run unit tests with coverage
	uv run pytest --cov

test-integration: ## Run integration tests against compose services
	docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test \
		run --rm integration-tests

check: ## Run all pre-commit hooks on all files
	uv run pre-commit run --all-files

hooks: ## Install pre-commit git hooks
	uv run pre-commit install

smoke: ## Run the end-to-end smoke test against the local stack
	./scripts/smoke_test.sh

eval: ## Run the routing evaluation suite
	docker compose -f docker-compose.yml -f docker-compose.eval.yml --profile eval \
		run --rm --build --user "$$(id -u):$$(id -g)" eval

load: ## Run the intake load test (INTAKE=N CONCURRENCY=M)
	python3 scripts/load_test.py --intake $${INTAKE:-200} --concurrency $${CONCURRENCY:-50}

# --- Docker Compose ---
up: ## Start the compose stack in the background
	docker compose up -d

down: ## Stop the compose stack (keeps volumes)
	docker compose down

ps: ## List compose services
	docker compose ps

logs: ## Tail logs from all services
	docker compose logs -f

clean: ## Stop the stack and remove its volumes
	docker compose down -v

# --- Images ---
images: ## Build router and notifier images
	docker build --build-arg SERVICE=router   -t sir/router:dev .
	docker build --build-arg SERVICE=notifier -t sir/notifier:dev .

image-check: images ## Build images and sanity-check runtime UID and entrypoint
	docker run --rm sir/router:dev python -c "import router, common; print('router ok')"
	docker run --rm sir/notifier:dev python -c "import notifier, common; print('notifier ok')"
	@test "$$(docker run --rm sir/router:dev id -u)" = "10001" && echo "user ok"
	@docker run --rm sir/notifier:dev agent >/dev/null 2>&1; test $$? -eq 64 && echo "entrypoint ok"

# --- Security ---
security: sec-secrets sec-deps sec-config sec-images ## Run all security scans

sec-secrets: ## Scan git history for secrets with gitleaks
	docker run --rm -v "$(CURDIR):/repo" ghcr.io/gitleaks/gitleaks:$(GITLEAKS_VERSION) \
		git /repo --redact --verbose

sec-deps: ## Scan dependencies with trivy fs
	$(TRIVY) fs --scanners vuln,secret $(TRIVY_FLAGS) --ignore-unfixed .

sec-config: ## Scan config files with trivy config
	$(TRIVY) config $(TRIVY_FLAGS) .

sec-images: images ## Scan built images with trivy image
	mkdir -p .trivy
	docker save sir/router:dev   -o .trivy/router.tar
	docker save sir/notifier:dev -o .trivy/notifier.tar
	$(TRIVY) image --input .trivy/router.tar   $(TRIVY_FLAGS) --ignore-unfixed
	$(TRIVY) image --input .trivy/notifier.tar $(TRIVY_FLAGS) --ignore-unfixed

# --- GPU ---
gpu: ## Show host GPU status
	nvidia-smi

gpu-docker: ## Check Docker CUDA access
	docker run --rm --gpus all ubuntu:24.04 nvidia-smi

gpu-watch: ## Watch GPU usage every second
	watch -n 1 nvidia-smi
