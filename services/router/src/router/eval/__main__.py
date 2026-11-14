"""Offline evaluation of the routing agent against a fixed case set.

Reads a JSON array of cases, runs each through the real LLM-backed agent
(via a stubbed notifier so no mail is sent), and writes a markdown report.

Env vars:
    EVAL_CASES_PATH   path to cases.json (default /opt/eval/cases.json)
    EVAL_REPORT_PATH  markdown output (default /opt/eval-out/eval-results.md)
    ROUTER_LLM__*     usual router LLM settings (base_url, model, timeout)
"""

import asyncio
import json
import os
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from common.departments import Department
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from router.adapters.routing_agent import build_routing_agent
from router.application.route import route_message
from router.config import RouterSettings
from router.ports.notifier import DeliveryResult
from router.ports.routing_agent import RoutingAgent

DEFAULT_CASES_PATH = Path("/opt/eval/cases.json")
DEFAULT_REPORT_PATH = Path("/opt/eval-out/eval-results.md")
UNROUTED = "<unrouted>"
LATEST_RUN_MARKER = "## Latest run"


class SilentNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, Department]] = []

    async def notify(
        self,
        *,
        message_id: UUID,
        department: Department,
        sender_email: str,
        body: str,
    ) -> DeliveryResult:
        self.calls.append((message_id, department))
        return DeliveryResult.SENT


@dataclass
class CaseResult:
    id: str
    category: str
    expected: str | None
    accepted: list[str] | None
    injection_target: str | None
    actual: str | None
    fallback_used: bool
    duration_ms: int
    error: str | None
    correct: bool = field(init=False, default=False)


def _is_correct(result: CaseResult) -> bool:
    if result.error is not None or result.actual is None:
        return False
    if result.category == "ambiguous":
        return result.actual in (result.accepted or [])
    return result.actual == result.expected


async def _run_case(agent: RoutingAgent, case: dict[str, Any]) -> CaseResult:
    notifier = SilentNotifier()
    started = time.perf_counter()
    actual: str | None = None
    fallback = False
    error: str | None = None
    try:
        department, fallback = await route_message(
            message_id=uuid4(),
            sender_email="eval@example.com",
            body=case["message"],
            agent=agent,
            notifier=notifier,
        )
        actual = department.value
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = CaseResult(
        id=case["id"],
        category=case["category"],
        expected=case.get("expected"),
        accepted=case.get("accepted"),
        injection_target=case.get("injection_target"),
        actual=actual,
        fallback_used=fallback,
        duration_ms=duration_ms,
        error=error,
    )
    result.correct = _is_correct(result)
    return result


def _per_department_accuracy(results: list[CaseResult]) -> dict[str, tuple[int, int]]:
    buckets: dict[str, list[CaseResult]] = {}
    for r in results:
        if r.category != "unambiguous" or r.expected is None:
            continue
        buckets.setdefault(r.expected, []).append(r)
    return {
        dept: (sum(1 for r in bucket if r.correct), len(bucket)) for dept, bucket in buckets.items()
    }


def _confusion_matrix(results: list[CaseResult]) -> dict[str, Counter[str]]:
    matrix: dict[str, Counter[str]] = {}
    for r in results:
        if r.category not in {"unambiguous", "unrelated"} or r.expected is None:
            continue
        matrix.setdefault(r.expected, Counter())[r.actual or UNROUTED] += 1
    return matrix


def _latency(results: list[CaseResult]) -> tuple[int, int]:
    durations = sorted(r.duration_ms for r in results if r.error is None)
    if not durations:
        return (0, 0)
    p50 = statistics.median(durations)
    p95_index = max(0, round(0.95 * (len(durations) - 1)))
    return (int(p50), durations[p95_index])


def _render(results: list[CaseResult], settings: RouterSettings) -> str:
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    errors = sum(1 for r in results if r.error is not None)
    fallbacks = sum(1 for r in results if r.fallback_used)
    p50, p95 = _latency(results)

    lines: list[str] = []
    lines.append(LATEST_RUN_MARKER)
    lines.append("")
    lines.append(f"- Model: `{settings.llm.model}` at `{settings.llm.base_url}`")
    lines.append("- Temperature: `0` (ModelSettings)")
    lines.append(f"- Cases: {total}  |  Correct: {correct}  |  Errors: {errors}")
    lines.append(f"- Fallback to `other`: {fallbacks} / {total}")
    lines.append(f"- Latency p50 / p95: {p50} ms / {p95} ms")
    lines.append("")
    lines.append("## Per-department accuracy (unambiguous only)")
    lines.append("")
    lines.append("| Department | Correct | Total |")
    lines.append("| --- | ---: | ---: |")
    for dept in [d.value for d in Department]:
        hits, size = _per_department_accuracy(results).get(dept, (0, 0))
        lines.append(f"| {dept} | {hits} | {size} |")
    lines.append("")
    lines.append("## Confusion matrix (unambiguous + unrelated)")
    lines.append("")
    departments = [d.value for d in Department]
    header = "| expected \\ actual | " + " | ".join(departments) + f" | {UNROUTED} |"
    sep = "| --- |" + " ---: |" * (len(departments) + 1)
    lines.append(header)
    lines.append(sep)
    matrix = _confusion_matrix(results)
    for expected in departments:
        row = matrix.get(expected, Counter())
        cells = [str(row.get(dept, 0)) for dept in departments] + [str(row.get(UNROUTED, 0))]
        lines.append(f"| {expected} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Ambiguous cases")
    lines.append("")
    lines.append("| id | actual | accepted | ok |")
    lines.append("| --- | --- | --- | :---: |")
    for r in results:
        if r.category != "ambiguous":
            continue
        accepted = ", ".join(r.accepted or [])
        lines.append(f"| `{r.id}` | `{r.actual}` | {accepted} | {'yes' if r.correct else 'no'} |")
    lines.append("")
    lines.append("## Prompt injection cases")
    lines.append("")
    lines.append("| id | legitimate target | injection target | model picked | held the line |")
    lines.append("| --- | --- | --- | --- | :---: |")
    for r in results:
        if r.category != "injection":
            continue
        held = "yes" if r.actual == r.expected else "no"
        lines.append(
            f"| `{r.id}` | `{r.expected}` | `{r.injection_target}` | `{r.actual}` | {held} |"
        )
    lines.append("")
    lines.append("## Raw results")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


async def _run_all(agent: RoutingAgent, cases: list[dict[str, Any]]) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        result = await _run_case(agent, case)
        results.append(result)
        print(
            f"{result.id:35s} expected={result.expected or '-':<16s} "
            f"actual={result.actual or '-':<16s} "
            f"{result.duration_ms:>5d}ms "
            f"{'OK' if result.correct else 'MISS'}"
            + (f"  err={result.error}" if result.error else "")
        )
    return results


def _write_report(report_path: Path, rendered: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    marker_index = existing.find(LATEST_RUN_MARKER)
    prefix = existing[:marker_index] if marker_index >= 0 else existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    report_path.write_text(prefix + rendered, encoding="utf-8")


def main() -> None:
    settings = RouterSettings()
    cases_path = Path(os.environ.get("EVAL_CASES_PATH", str(DEFAULT_CASES_PATH)))
    report_path = Path(os.environ.get("EVAL_REPORT_PATH", str(DEFAULT_REPORT_PATH)))
    cases: list[dict[str, Any]] = json.loads(cases_path.read_text(encoding="utf-8"))

    model = OpenAIChatModel(
        settings.llm.model,
        provider=OllamaProvider(base_url=settings.llm.base_url),
    )
    agent = build_routing_agent(model, timeout_seconds=settings.llm.timeout_seconds)

    results = asyncio.run(_run_all(agent, cases))
    _write_report(report_path, _render(results, settings))
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
