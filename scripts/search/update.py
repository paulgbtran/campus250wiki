#!/usr/bin/env python3
"""
update.py
Author: Paul Tran   <tranb9@lasalle.edu>
                    <paulgbtran@gmail.com>

Standalone script to re-synthesize existing wiki articles.

Re-runs synthesis for every topic that already has an entry in
data/entries/, pulling the latest search URLs from data/search/ and
re-generating the article text via Gemini.

Meant to be run independently — NOT invoked by main.py or any other
pipeline script.

Usage
-----
  # Re-synthesize all articles
  python update.py

  # Re-synthesize specific topics only
  python update.py "Benjamin Franklin" "Independence Hall"

  # Stop after N minutes (finishes the current article before stopping)
  python update.py --timeout 60

  # Combine: specific topics with a time cap
  python update.py --timeout 30 "Benjamin Franklin" "Independence Hall"
"""

import argparse
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — make scripts/ importable
# ---------------------------------------------------------------------------
_scriptDir = Path(__file__).parent
_rootDir   = _scriptDir.parent.parent
sys.path.insert(0, str(_rootDir / "scripts"))
sys.path.insert(0, str(_scriptDir))

import gemini_utils
from synthesizeData import synthesizeData          # re-use existing synthesis logic

MODEL = "gemini-3.5-flash"

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    """Human-readable duration string, e.g. '2m 34s'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"

def _ledger_delta(before: dict, after: dict) -> dict:
    return {
        "prompt_tokens":  after["prompt_tokens"]  - before["prompt_tokens"],
        "output_tokens":  after["output_tokens"]  - before["output_tokens"],
        "total_tokens":   after["total_tokens"]   - before["total_tokens"],
    }

def _print_topic_summary(topic: str, elapsed: float, delta: dict) -> None:
    cost = gemini_utils.tokens_to_usd(delta["prompt_tokens"], delta["output_tokens"], MODEL)
    print(
        f"  [+] Done  |  {_fmt_duration(elapsed):>8}  |  "
        f"{delta['total_tokens']:>8,} tokens  |  ${cost:.6f}"
    )

def _print_final_summary(run_elapsed: float, results: list[dict]) -> None:
    if not results:
        print("\nNo articles were updated.")
        return

    total_prompt = sum(r["delta"]["prompt_tokens"] for r in results)
    total_output = sum(r["delta"]["output_tokens"] for r in results)
    total_tokens = sum(r["delta"]["total_tokens"]  for r in results)
    total_cost   = gemini_utils.tokens_to_usd(total_prompt, total_output, MODEL)

    col_w  = max(len(r["topic"]) for r in results)
    header = f"  {'Topic':<{col_w}}  {'Time':>8}  {'Tokens':>10}  {'Cost':>12}"
    sep    = "  " + "-" * (len(header) - 2)

    print("\n" + "=" * 60)
    print("  UPDATE RUN COMPLETE -- SUMMARY")
    print("=" * 60)
    print(header)
    print(sep)

    for r in results:
        cost = gemini_utils.tokens_to_usd(
            r["delta"]["prompt_tokens"], r["delta"]["output_tokens"], MODEL
        )
        print(
            f"  {r['topic']:<{col_w}}  "
            f"{_fmt_duration(r['elapsed']):>8}  "
            f"{r['delta']['total_tokens']:>10,}  "
            f"${cost:>11.6f}"
        )

    print(sep)
    print(
        f"  {'TOTAL':<{col_w}}  "
        f"{_fmt_duration(run_elapsed):>8}  "
        f"{total_tokens:>10,}  "
        f"${total_cost:>11.6f}"
    )
    print("=" * 60)

# ---------------------------------------------------------------------------
# Core update logic
# ---------------------------------------------------------------------------

def _resolve_topics(requested: list[str]) -> list[str]:
    """
    Returns the ordered list of topics to update.

    If specific topics were requested via CLI, validates that each has a
    search file and an existing entry, then returns them in that order.

    If no topics were specified, returns all topics that have both a search
    file (data/search/<topic>.txt) and an existing entry
    (data/entries/<topic>.txt), sorted alphabetically.
    """
    search_dir  = _rootDir / "data" / "search"
    entries_dir = _rootDir / "data" / "entries"

    if requested:
        valid = []
        for t in requested:
            safe_t = gemini_utils.sanitize_filename(t)
            if not (search_dir / f"{safe_t}.txt").exists():
                print(f"  Warning: no search file found for '{t}' -- skipping.")
                continue
            if not (entries_dir / f"{safe_t}.txt").exists():
                print(f"  Warning: no existing entry for '{t}' -- skipping (use synthesizeData.py for new topics).")
                continue
            valid.append(t)
        return valid

    # All topics that have both a search file and an existing entry
    return sorted(
        t.stem
        for t in entries_dir.glob("*.txt")
        if (search_dir / f"{t.stem}.txt").exists()
    )


def run_update(topics: list[str], timeout_sec: int | None) -> None:
    """
    Re-synthesizes each topic in order, tracking time and token cost.
    Stops cleanly between articles if the timeout is reached.
    """
    if not topics:
        print("Nothing to update.")
        return

    # Reset the ledger so this run's numbers are isolated
    gemini_utils.reset_ledger()

    print(f"\nUpdating {len(topics)} article(s)" +
          (f" -- time limit: {timeout_sec // 60}m" if timeout_sec else "") + "\n")

    run_start = time.perf_counter()
    results: list[dict] = []

    for i, topic in enumerate(topics, 1):
        # --- Timeout check (between articles, never mid-call) ---
        if timeout_sec is not None:
            elapsed_so_far = time.perf_counter() - run_start
            if elapsed_so_far >= timeout_sec:
                print(
                    f"\n[!] Time limit reached ({timeout_sec // 60}m) after "
                    f"{i - 1}/{len(topics)} article(s). Stopping."
                )
                break

        print(f"[{i}/{len(topics)}] Updating: {topic}")

        ledger_before = gemini_utils.read_ledger()
        topic_start   = time.perf_counter()

        try:
            synthesizeData(topic)
        except Exception as e:
            print(f"  Error updating '{topic}': {e}")

        topic_elapsed = time.perf_counter() - topic_start
        ledger_after  = gemini_utils.read_ledger()
        delta         = _ledger_delta(ledger_before, ledger_after)

        _print_topic_summary(topic, topic_elapsed, delta)
        results.append({"topic": topic, "elapsed": topic_elapsed, "delta": delta})

    run_elapsed = time.perf_counter() - run_start
    _print_final_summary(run_elapsed, results)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-synthesize existing Campus 250 wiki articles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python update.py                          # update all articles\n"
            "  python update.py 'Benjamin Franklin'      # update one article\n"
            "  python update.py --timeout 60             # stop after 60 minutes\n"
        ),
    )
    parser.add_argument(
        "topics",
        nargs="*",
        metavar="TOPIC",
        help="Topic name(s) to update. Omit to update all existing articles.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="MINUTES",
        help="Stop after this many minutes (finishes the current article first).",
    )
    args = parser.parse_args()

    timeout_sec = args.timeout * 60 if args.timeout else None

    topics = _resolve_topics(args.topics)
    if not topics:
        print("No eligible topics found. Make sure data/search/ and data/entries/ are populated.")
        sys.exit(0)

    run_update(topics, timeout_sec)


if __name__ == "__main__":
    main()

