"""Cold-start and per-response runtime benchmark for the submission agent.

The organizer may run submissions under CPU, memory, and timeout restrictions.
This script measures what those limits would apply to:

* cold start: catalog load plus index construction in a fresh process
* steady state: per-response latency across every public session
* memory: peak process working set, which includes the SQLite C allocations
  that `tracemalloc` cannot see

It never scores the agent and never writes `results.json`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

from evaluator.local_evaluator import (
    MAX_TURNS,
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
    normalize_recommendations,
)
from starter.agent import Agent


def _memory_counters() -> tuple[int, int] | None:
    """Return (current_rss, peak_rss) in bytes, or None when unavailable."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        # HANDLE is pointer-sized; without an explicit restype ctypes truncates
        # the pseudo-handle to 32 bits and the call silently fails.
        current_process = ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype = wintypes.HANDLE
        probe = ctypes.windll.psapi.GetProcessMemoryInfo
        probe.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        probe.restype = wintypes.BOOL
        if not probe(current_process(), ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
    try:
        import resource
    except ImportError:
        return None
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    return peak, peak


def _percentile(ordered: list[float], fraction: float) -> float:
    """Nearest-rank percentile; deterministic and free of interpolation."""
    if not ordered:
        return 0.0
    rank = max(1, min(len(ordered), int(-(-fraction * len(ordered) // 1))))
    return ordered[rank - 1]


def _mb(value: int | None) -> float | None:
    return None if value is None else round(value / (1024 * 1024), 1)


def measure_cold_start(catalog_path: str, trace_heap: bool) -> tuple[Agent, dict]:
    """Build the agent once and report how long it took and what it cost.

    `tracemalloc` traces every allocation and inflates the build several-fold,
    so heap tracing is opt-in and its timing is reported as untrustworthy.
    Process RSS is measured either way and is the number an organizer memory
    cap would actually apply to.
    """
    before = _memory_counters()
    if trace_heap:
        tracemalloc.start()
    start = time.perf_counter()
    agent = Agent(catalog_path=catalog_path)
    elapsed = time.perf_counter() - start
    traced_current = traced_peak = None
    if trace_heap:
        traced_current, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    after = _memory_counters()
    return agent, {
        "index_build_seconds": round(elapsed, 3),
        "index_build_timing_valid": not trace_heap,
        "python_heap_peak_mb": _mb(traced_peak),
        "python_heap_retained_mb": _mb(traced_current),
        "process_rss_mb": _mb(after[0]) if after else None,
        "process_rss_delta_mb": (
            _mb(after[0] - before[0]) if before and after else None
        ),
    }


def measure_responses(
    agent: Agent,
    samples: list[dict],
    catalog_ids: set[str],
    categories: dict[str, list[str]],
    products: dict[str, dict],
) -> dict:
    latencies: list[float] = []
    turns_per_session: list[int] = []
    start = time.perf_counter()
    for index, sample in enumerate(samples):
        session_id = f"bench_{index:04d}"
        agent.reset(session_id, sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        card, behavior = materialize_hidden_fields(sample, products)
        effective = {**sample, "intent_card": card, "behavior": behavior}
        disclosed: set[str] = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = initial_message(
            effective, coarse_category(categories.get(target, [])), disclosed
        )
        turns = 0
        for turn in range(1, MAX_TURNS + 1):
            call_start = time.perf_counter()
            response = agent.respond(session_id, user_message, turn, TOP_K)
            latencies.append((time.perf_counter() - call_start) * 1000.0)
            turns = turn
            ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
            if override_applied and target in ranked:
                break
            if turn == MAX_TURNS:
                break
            override = effective.get("behavior", {}).get("override") or {}
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                new_value = str(override.get("new_value", ""))
                if new_value:
                    disclosed.add(new_value)
                user_message = str(
                    override.get("message", "Actually, please ignore my earlier preference.")
                )
            else:
                user_message, boundary_used = customer_reply(
                    effective, response.get("ask_attribute"), disclosed, boundary_used
                )
        turns_per_session.append(turns)
    wall_clock = time.perf_counter() - start
    ordered = sorted(latencies)
    peak = _memory_counters()
    return {
        "sessions": len(samples),
        "responses": len(latencies),
        "turns_per_session_mean": round(statistics.fmean(turns_per_session), 3),
        "wall_clock_seconds": round(wall_clock, 3),
        "latency_ms": {
            "mean": round(statistics.fmean(ordered), 3),
            "p50": round(_percentile(ordered, 0.50), 3),
            "p90": round(_percentile(ordered, 0.90), 3),
            "p95": round(_percentile(ordered, 0.95), 3),
            "p99": round(_percentile(ordered, 0.99), 3),
            "max": round(ordered[-1], 3),
        },
        "process_rss_peak_mb": _mb(peak[1]) if peak else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent runtime and memory benchmark")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--public-set", default="data/public_set.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--trace-heap",
        action="store_true",
        help="Also trace Python heap allocations; inflates the cold-start timing.",
    )
    args = parser.parse_args()

    # Load the simulator's own catalog copy first so its footprint is charged
    # to the harness, not to the agent under test.
    samples = load_jsonl(args.public_set)
    catalog_ids, categories, products = catalog_index(args.catalog)
    harness = _memory_counters()
    harness_rss = harness[0] if harness else None

    agent, cold_start = measure_cold_start(args.catalog, args.trace_heap)
    if harness_rss is not None and cold_start["process_rss_mb"] is not None:
        cold_start["agent_rss_delta_mb"] = _mb(
            int(cold_start["process_rss_mb"] * 1024 * 1024) - harness_rss
        )
    steady_state = measure_responses(agent, samples, catalog_ids, categories, products)
    report = {
        "benchmark": "runtime-v1",
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "harness_rss_mb": _mb(harness_rss),
        "cold_start": cold_start,
        "steady_state": steady_state,
        "notes": (
            "process_rss includes SQLite C allocations that tracemalloc omits. "
            "harness_rss_mb is the simulator's own catalog copy, which the organizer "
            "harness pays for instead; agent_rss_delta_mb is the agent's own footprint. "
            "Latency excludes the one-time cold start. Values are hardware-dependent."
        ),
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
