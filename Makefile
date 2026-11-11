TRIVY_VERSION    ?= 0.67.0
GITLEAKS_VERSION ?= v8.28.0
TRIVY = docker run --rm -v "$(CURDIR):/src" -v trivy-cache:/root/.cache/trivy -w /src \
	aquasec/trivy:$(TRIVY_VERSION)
TRIVY_FLAGS = --severity HIGH,CRITICAL --exit-code 1 --skip-version-check

.PHONY: sync lint fmt test test-integration check hooks smoke \
	up down ps logs clean \
	images image-check \
	security sec-secrets sec-deps sec-config sec-images \
	gpu gpu-docker gpu-watch

# --- Python ---
sync:  ; uv sync --all-packages
lint:  ; uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
fmt:   ; uv run ruff format . && uv run ruff check --fix .
test:  ; uv run pytest --cov
test-integration:
	docker compose -f docker-compose.yml -f docker-compose.test.yml \
		run --rm integration-tests
check: ; uv run pre-commit run --all-files
hooks: ; uv run pre-commit install
smoke: ; ./scripts/smoke_test.sh

# --- Docker Compose ---
up:    ; docker compose up -d
down:  ; docker compose down
ps:    ; docker compose ps
logs:  ; docker compose logs -f
clean: ; docker compose down -v

# --- Images ---
images:
	docker build --build-arg SERVICE=router   -t sir/router:dev .
	docker build --build-arg SERVICE=notifier -t sir/notifier:dev .

image-check: images
	docker run --rm sir/router:dev python -c "import router, common; print('router ok')"
	docker run --rm sir/notifier:dev python -c "import notifier, common; print('notifier ok')"
	@test "$$(docker run --rm sir/router:dev id -u)" = "10001" && echo "user ok"
	@docker run --rm sir/notifier:dev agent >/dev/null 2>&1; test $$? -eq 64 && echo "entrypoint ok"

# --- Security ---
security: sec-secrets sec-deps sec-config sec-images

sec-secrets:
	docker run --rm -v "$(CURDIR):/repo" ghcr.io/gitleaks/gitleaks:$(GITLEAKS_VERSION) \
		git /repo --redact --verbose

sec-deps:
	$(TRIVY) fs --scanners vuln,secret $(TRIVY_FLAGS) --ignore-unfixed .

sec-config:
	$(TRIVY) config $(TRIVY_FLAGS) .

sec-images: images
	mkdir -p .trivy
	docker save sir/router:dev   -o .trivy/router.tar
	docker save sir/notifier:dev -o .trivy/notifier.tar
	$(TRIVY) image --input .trivy/router.tar   $(TRIVY_FLAGS) --ignore-unfixed
	$(TRIVY) image --input .trivy/notifier.tar $(TRIVY_FLAGS) --ignore-unfixed

# --- GPU ---
gpu:        ; nvidia-smi
gpu-docker: ; docker run --rm --gpus all ubuntu:24.04 nvidia-smi
gpu-watch:  ; watch -n 1 nvidia-smi
