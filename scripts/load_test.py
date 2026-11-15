#!/usr/bin/env python3
"""Intake load test: POST /api/v1/messages concurrently, record latencies.

Stdlib only. Launches `--concurrency` worker threads that pull from a shared
queue of `--intake` POST tasks, reports p50/p95/max, 2xx/5xx/other counts
and total wall time. Exit code non-zero if any request was not 202.
"""

import argparse
import json
import os
import queue
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_API = "http://127.0.0.1:8000"


def _post_once(api: str, timeout: float) -> tuple[int, float]:
    body = json.dumps(
        {
            "email": f"load-{uuid.uuid4().hex}@example.com",
            "message": "load test message, please route somewhere.",
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 -- loopback API, caller-supplied URL
        f"{api}/api/v1/messages",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception:
        status = 0
    return status, (time.perf_counter() - start) * 1000.0


def _worker(
    api: str,
    timeout: float,
    tasks: "queue.Queue[int]",
    results: list[tuple[int, float]],
    lock: threading.Lock,
) -> None:
    while True:
        try:
            tasks.get_nowait()
        except queue.Empty:
            return
        status, duration_ms = _post_once(api, timeout)
        with lock:
            results.append((status, duration_ms))
        tasks.task_done()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.environ.get("API", DEFAULT_API))
    parser.add_argument("--intake", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    tasks: queue.Queue[int] = queue.Queue()
    for i in range(args.intake):
        tasks.put(i)

    results: list[tuple[int, float]] = []
    lock = threading.Lock()
    threads = [
        threading.Thread(target=_worker, args=(args.api, args.timeout, tasks, results, lock))
        for _ in range(args.concurrency)
    ]
    wall_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_ms = (time.perf_counter() - wall_start) * 1000.0

    durations = sorted(d for _, d in results)
    accepted = sum(1 for s, _ in results if s == 202)
    server_errors = sum(1 for s, _ in results if 500 <= s < 600)
    other = len(results) - accepted - server_errors

    def pct(p: float) -> float:
        if not durations:
            return 0.0
        return durations[max(0, round(p * (len(durations) - 1)))]

    p50 = statistics.median(durations) if durations else 0.0
    p95 = pct(0.95)
    peak = durations[-1] if durations else 0.0

    print(f"intake={args.intake} concurrency={args.concurrency} wall={wall_ms:.0f}ms")
    print(f"accepted(202)={accepted}  server_errors(5xx)={server_errors}  other={other}")
    print(f"latency p50={p50:.1f}ms p95={p95:.1f}ms max={peak:.1f}ms")
    return 0 if accepted == args.intake and server_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
