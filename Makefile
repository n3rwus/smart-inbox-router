sync:  ; uv sync --all-packages
lint:  ; uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
fmt:   ; uv run ruff format . && uv run ruff check --fix .
test:  ; uv run pytest --cov=router --cov=notifier --cov=common --cov-fail-under=80
up:    ; docker compose up -d
smoke: ; ./scripts/smoke_test.sh