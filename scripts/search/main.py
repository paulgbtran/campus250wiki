#!/usr/bin/env python3
"""
main.py

Executes the pipeline scripts in sequential order:
1. topics.py
2. classifier.py
3. sources.py
4. search.py
5. synthesizeData.py

Tracks and prints wall-clock time and estimated Gemini token cost after
each script and again as a grand total at the end of the run.
"""

import sys
import subprocess
import time
import os
from pathlib import Path

# Bring gemini_utils onto the path so we can read/reset the token ledger
rootDir = Path(__file__).parent.parent.parent
sys.path.append(str(rootDir / "scripts"))
import gemini_utils

SCRIPTS = [
    "topics.py",
    "classifier.py",
    "sources.py",
    "search.py",
    "synthesizeData.py",
]

# Model used by the pipeline scripts (keep in sync with the individual scripts)
PIPELINE_MODEL = "gemini-3.5-flash"

# ---------------------------------------------------------------------------
# Per-script time limits (seconds). None = no limit.
# ---------------------------------------------------------------------------
SCRIPT_TIMEOUTS: dict[str, int | None] = {
    "topics.py":        15 * 60,   # 15 min
    "classifier.py":    None,       # instant -- no limit needed
    "sources.py":       15 * 60,   # 15 min
    "search.py":        15 * 60,   # 15 min
    "synthesizeData.py": 90 * 60,  # 90 min
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    """Returns a human-readable duration string (e.g. '2m 34s')."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"

def _ledger_delta(before: dict, after: dict) -> dict:
    """Returns the token counts added between two ledger snapshots."""
    return {
        "prompt_tokens":  after["prompt_tokens"]  - before["prompt_tokens"],
        "output_tokens":  after["output_tokens"]  - before["output_tokens"],
        "total_tokens":   after["total_tokens"]   - before["total_tokens"],
    }

def _print_script_summary(script_name: str, elapsed: float, delta: dict) -> None:
    cost = gemini_utils.tokens_to_usd(
        delta["prompt_tokens"], delta["output_tokens"], PIPELINE_MODEL
    )
    print(
        f"\n--- {script_name} finished ---\n"
        f"  Time taken  : {_fmt_duration(elapsed)}\n"
        f"  Tokens used : {delta['total_tokens']:,}  "
        f"(prompt {delta['prompt_tokens']:,} / output {delta['output_tokens']:,})\n"
        f"  Est. cost   : ${cost:.6f}\n"
    )

def _print_total_summary(run_elapsed: float, results: list[dict]) -> None:
    total_prompt  = sum(r["delta"]["prompt_tokens"]  for r in results)
    total_output  = sum(r["delta"]["output_tokens"]  for r in results)
    total_tokens  = sum(r["delta"]["total_tokens"]   for r in results)
    total_cost    = gemini_utils.tokens_to_usd(total_prompt, total_output, PIPELINE_MODEL)

    print("=" * 55)
    print("  PIPELINE COMPLETE -- SUMMARY")
    print("=" * 55)

    col_w = max(len(r["script"]) for r in results)
    header = f"  {'Script':<{col_w}}  {'Time':>8}  {'Tokens':>10}  {'Cost':>12}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for r in results:
        cost = gemini_utils.tokens_to_usd(
            r["delta"]["prompt_tokens"], r["delta"]["output_tokens"], PIPELINE_MODEL
        )
        print(
            f"  {r['script']:<{col_w}}  "
            f"{_fmt_duration(r['elapsed']):>8}  "
            f"{r['delta']['total_tokens']:>10,}  "
            f"${cost:>11.6f}"
        )

    print("  " + "-" * (len(header) - 2))
    print(
        f"  {'TOTAL':<{col_w}}  "
        f"{_fmt_duration(run_elapsed):>8}  "
        f"{total_tokens:>10,}  "
        f"${total_cost:>11.6f}"
    )
    print("=" * 55)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        current_dir = Path(__file__).parent.resolve()
        python_exe = sys.executable

        # Reset the token ledger so this run starts from zero
        gemini_utils.reset_ledger()

        run_start = time.perf_counter()
        results: list[dict] = []

        for script_name in SCRIPTS:
            script_path = current_dir / script_name
            print(f"\n=== Running {script_name} ===")
            if not script_path.exists():
                print(
                    f"Warning: {script_name} not found at {script_path}. "
                    "Attempting to run via subprocess anyway..."
                )

            ledger_before = gemini_utils.read_ledger()
            script_start  = time.perf_counter()

            # Pass the per-script timeout into the subprocess via env var
            script_env = dict(os.environ)
            timeout = SCRIPT_TIMEOUTS.get(script_name)
            if timeout is not None:
                script_env["PIPELINE_TIMEOUT_SECONDS"] = str(timeout)
            else:
                script_env.pop("PIPELINE_TIMEOUT_SECONDS", None)

            result = subprocess.run([python_exe, str(script_path)], env=script_env)

            elapsed      = time.perf_counter() - script_start
            ledger_after = gemini_utils.read_ledger()
            delta        = _ledger_delta(ledger_before, ledger_after)

            _print_script_summary(script_name, elapsed, delta)

            results.append({"script": script_name, "elapsed": elapsed, "delta": delta})

            if result.returncode != 0:
                print(f"Error: {script_name} failed with return code {result.returncode}.")
                sys.exit(result.returncode)

        run_elapsed = time.perf_counter() - run_start
        _print_total_summary(run_elapsed, results)

    except Exception as e:
        print(f"Error running search main pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
