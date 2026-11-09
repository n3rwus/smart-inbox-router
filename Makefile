TRIVY_VERSION    ?= 0.67.0
GITLEAKS_VERSION ?= v8.28.0
TRIVY = docker run --rm -v "$(CURDIR):/src" -v trivy-cache:/root/.cache/trivy -w /src \
        aquasec/trivy:$(TRIVY_VERSION)
TRIVY_FLAGS = --severity HIGH,CRITICAL --exit-code 1 --skip-version-check

.PHONY: security sec-deps sec-config sec-secrets sec-images images

security: sec-secrets sec-deps sec-config sec-images

sec-secrets:
	docker run --rm -v "$(CURDIR):/repo" ghcr.io/gitleaks/gitleaks:$(GITLEAKS_VERSION) \
	  git /repo --redact --verbose

sec-deps:
	$(TRIVY) fs --scanners vuln,secret $(TRIVY_FLAGS) --ignore-unfixed .

sec-config:
	$(TRIVY) config $(TRIVY_FLAGS) .

images:
	docker build --build-arg SERVICE=router   -t sir/router:dev .
	docker build --build-arg SERVICE=notifier -t sir/notifier:dev .

sec-images: images   ## CVE w obrazach
	mkdir -p .trivy
	docker save sir/router:dev   -o .trivy/router.tar
	docker save sir/notifier:dev -o .trivy/notifier.tar
	$(TRIVY) image --input .trivy/router.tar   $(TRIVY_FLAGS) --ignore-unfixed
	$(TRIVY) image --input .trivy/notifier.tar $(TRIVY_FLAGS) --ignore-unfixed

sync:  ; uv sync --all-packages
lint:  ; uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
fmt:   ; uv run ruff format . && uv run ruff check --fix .
test:  ; uv run pytest --cov=router --cov=notifier --cov=common --cov-fail-under=80
up:    ; docker compose up -d
smoke: ; ./scripts/smoke_test.sh
hooks: ; uv run pre-commit install
check: ; uv run pre-commit run --all-files
