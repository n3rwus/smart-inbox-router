# Development

Everything here runs locally, without Docker, without Ollama, without the
network. The integration layer that does need the stack is called out
explicitly.

## Layout

    libs/common/              shared infra: db, errors, logging, email headers, smtp
    services/router/
      src/router/
        api/                  FastAPI routes
        adapters/             SQLAlchemy repo, pydantic-ai agent, httpx notifier
        application/          use cases: submit_message, process_next, route_message
        domain/               Message, MessageStatus, Department catalog, prompt
        ports/                protocols the application depends on
      tests/                  unit tests + fakes.py
    services/notifier/
      src/notifier/           same hex layout: api/adapters/application/domain/ports
      tests/
        integration/          needs MailHog on a compose network
    scripts/                  smoke_test.sh, load_test.py

## Hexagonal boundaries

`pyproject.toml` has import-linter contracts that fail `make lint` if the
boundaries break. The ones that matter day to day:

- `router.domain` and `router.application` cannot import `router.adapters`,
  `fastapi`, `sqlalchemy`, `pydantic_ai`, or `httpx`.
- `notifier.domain` cannot import `notifier.adapters`, `fastapi`,
  `sqlalchemy`, `aiosmtplib`, or `mcp`.
- `common.db`, `common.departments`, `common.email_headers`,
  `common.errors`, `common.settings`, `common.timeouts` cannot import
  `common.http`, `common.smtp`, `fastapi`, or `aiosmtplib`.

Practical consequence: put new business logic in `domain/` or `application/`;
framework and IO calls live in `adapters/`.

## Tests

Pytest defaults are set in `pyproject.toml`: `asyncio_mode = "auto"`,
`addopts = "--import-mode=importlib -m 'not integration'"`, coverage source
across `common`, `router`, `notifier` with `fail_under = 80`.

    make test                                       # whole unit suite
    uv run pytest services/router/tests/test_worker.py
    uv run pytest services/router/tests/test_worker.py::test_claim_and_mark_sent

Integration tests are marked `@pytest.mark.integration` and live under
`services/*/tests/integration/`. They expect the compose network and are
excluded from the default run. To run them:

    make test-integration

That boots the compose stack (plus a dedicated `integration-tests`
service defined in `docker-compose.test.yml`) and runs the marked suite
inside it.

Two real-stack scripts are useful alongside the suites:

    make smoke          # scripts/smoke_test.sh: POST a message, poll GET, check MailHog
    make eval           # docker-compose.eval.yml: the 23 cases through the real agent
    make load           # scripts/load_test.py: 200 POSTs at concurrency 50

`make eval` writes `docs/eval-latest-run.md` on every run. The commentary in
`docs/eval-results.md` is written by hand.

## Quality tools

    make fmt     # ruff format + ruff check --fix
    make lint    # ruff format --check, ruff check, mypy strict, lint-imports
    make check   # run every pre-commit hook on every file
    make hooks   # install pre-commit hooks

Pre-commit is split across stages. On `pre-commit`: formatting, lint, secret
scans (gitleaks, trivy fs). On `commit-msg`: Conventional Commits check. On
`pre-push`: `mypy`, `lint-imports`, and `pytest --cov`. A plain `git commit`
does not run mypy or the test suite; run `make lint test` locally before
pushing if you want the full gate.

## Conventions

- TDD. Write the failing test first (`test: ...`), then the minimum code to
  turn it green (`feat: ...`), then refactor (`refactor: ...`). Conventional
  Commits are enforced by the `commit-msg` hook.
- Settings use `pydantic-settings` with the `__` nested separator. Example:
  `LLM__MODEL` maps to `settings.llm.model`.
- Database schema changes go through Alembic (`services/*/src/*/migrations`),
  never `metadata.create_all()`. There is a test
  (`test_migrations.py`) that boots an empty database, runs `upgrade head`,
  and compares the resulting schema to the ORM metadata.

## Adding a department

The department catalog is checked in two independent places and a
completeness test is there to catch anyone who forgets the second place.
To add one, walk this path:

1. Add the value to `common.departments.Department` (`StrEnum`).
2. Add the description to
   `router.domain.departments.DEPARTMENT_DESCRIPTIONS`. The completeness
   test in `services/router/tests/test_departments_catalog.py` asserts the
   keys match the enum exactly; it will fail until you do this.
3. Add the recipient address to
   `notifier.domain.recipients._RECIPIENTS`. A `KeyError` on first
   delivery is how the notifier would otherwise fail, so this is required.
4. Consider adding a prompt tie-break rule if the new department overlaps
   with an existing one; see the Polish `kadry` vs `human-resources` case
   in `router.adapters.routing_agent.TIE_BREAK_RULES`.
5. Add at least one unambiguous eval case in
   `services/router/tests/eval/cases.json` so the metric in
   `docs/eval-results.md` moves with the change.
