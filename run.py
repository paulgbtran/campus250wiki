#!/usr/bin/env python3
"""
run.py

Primary controller for the Campus 250 wiki pipeline.

Runs the following pipelines in order:
  1. Search pipeline   -- scripts/search/main.py
  2. Factcheck pipeline -- scripts/factcheck/main.py

Output from each pipeline is streamed live to the console AND appended
to pipeline.log in the project root. The log is never cleared or
overwritten; every run appends a new timestamped block.

Usage
-----
  python run.py
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR    = Path(__file__).parent
LOG_FILE    = ROOT_DIR / "pipeline.log"
SCRIPTS_DIR = ROOT_DIR / "scripts"

PIPELINES = [
    ("Search",   SCRIPTS_DIR / "search"    / "main.py"),
    ("Factcheck", SCRIPTS_DIR / "factcheck" / "main.py"),
]

# ---------------------------------------------------------------------------
# Bring gemini_utils onto the path so we can read the token ledger
# (each sub-pipeline main.py resets the ledger at startup, so after a
# subprocess finishes the ledger file contains only that pipeline's totals)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(SCRIPTS_DIR))
import gemini_utils

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _stream_and_capture(cmd: list[str]) -> tuple[str, int]:
    """
    Runs *cmd* as a subprocess, streams its combined stdout/stderr to the
    console in real time, and returns (captured_text, return_code).
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    proc.wait()
    return "".join(lines), proc.returncode


def _append_log(text: str) -> None:
    """Appends *text* to pipeline.log, creating the file if needed."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    run_start   = time.perf_counter()
    run_time    = datetime.now()
    python_exe  = sys.executable

    # Determine how many runs have already been logged
    run_number = 1
    if LOG_FILE.exists():
        content = LOG_FILE.read_text(encoding="utf-8")
        run_number = content.count("RUN STARTED") + 1

    header = (
        "\n"
        "=" * 80 + "\n"
        f"  RUN #{run_number}  |  STARTED: {run_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "=" * 80 + "\n"
    )
    print(header)
    _append_log(header)

    # Accumulate totals across all pipelines
    grand_prompt_tokens  = 0
    grand_output_tokens  = 0
    grand_total_tokens   = 0
    grand_cost_usd       = 0.0
    pipeline_results: list[dict] = []

    for label, script_path in PIPELINES:
        if not script_path.exists():
            msg = f"[!] {label} pipeline script not found at {script_path} -- skipping.\n"
            print(msg)
            _append_log(msg)
            continue

        section_header = (
            "\n"
            + "-" * 80 + "\n"
            + f"  PIPELINE: {label.upper()}  |  {datetime.now().strftime('%H:%M:%S')}\n"
            + "-" * 80 + "\n"
        )
        print(section_header)
        _append_log(section_header)

        pipe_start = time.perf_counter()
        captured, returncode = _stream_and_capture([python_exe, str(script_path)])
        pipe_elapsed = time.perf_counter() - pipe_start

        # Read the ledger — sub-pipeline reset it at startup, so this
        # holds only this pipeline's token usage.
        ledger = gemini_utils.read_ledger()
        p_tok  = ledger["prompt_tokens"]
        o_tok  = ledger["output_tokens"]
        t_tok  = ledger["total_tokens"]
        cost   = gemini_utils.tokens_to_usd(p_tok, o_tok, "gemini-3.5-flash")

        grand_prompt_tokens += p_tok
        grand_output_tokens += o_tok
        grand_total_tokens  += t_tok
        grand_cost_usd      += cost

        pipeline_results.append({
            "label":   label,
            "elapsed": pipe_elapsed,
            "tokens":  t_tok,
            "cost":    cost,
        })

        # Append captured output to the log
        _append_log(captured)

        # Append per-pipeline stats footer
        pipeline_footer = (
            "\n"
            f"  [{label} pipeline finished]\n"
            f"  Wall time : {_fmt_duration(pipe_elapsed)}\n"
            f"  Tokens    : {t_tok:,}  "
            f"(prompt {p_tok:,} / output {o_tok:,})\n"
            f"  Est. cost : ${cost:.6f} USD\n"
        )
        if returncode != 0:
            pipeline_footer += f"  [!] Exited with return code {returncode}\n"

        print(pipeline_footer)
        _append_log(pipeline_footer)

        if returncode != 0:
            error_msg = (
                f"\nError: {label} pipeline exited with code {returncode}. "
                "Stopping controller.\n"
            )
            print(error_msg)
            _append_log(error_msg)
            _write_summary(run_time, run_number, pipeline_results,
                           grand_prompt_tokens, grand_output_tokens,
                           grand_total_tokens, grand_cost_usd,
                           time.perf_counter() - run_start,
                           aborted=True)
            sys.exit(returncode)

    run_elapsed = time.perf_counter() - run_start
    _write_summary(
        run_time, run_number, pipeline_results,
        grand_prompt_tokens, grand_output_tokens,
        grand_total_tokens, grand_cost_usd,
        run_elapsed,
    )


def _write_summary(
    run_time: datetime,
    run_number: int,
    results: list[dict],
    total_prompt: int,
    total_output: int,
    total_tokens: int,
    total_cost: float,
    run_elapsed: float,
    aborted: bool = False,
) -> None:
    status = "ABORTED" if aborted else "COMPLETE"

    col_w  = max((len(r["label"]) for r in results), default=8)
    header = f"  {'Pipeline':<{col_w}}  {'Time':>10}  {'Tokens':>12}  {'Cost (USD)':>14}"
    sep    = "  " + "-" * (len(header) - 2)

    rows = ""
    for r in results:
        rows += (
            f"  {r['label']:<{col_w}}  "
            f"{_fmt_duration(r['elapsed']):>10}  "
            f"{r['tokens']:>12,}  "
            f"${r['cost']:>13.6f}\n"
        )

    summary = (
        "\n"
        + "=" * 80 + "\n"
        + f"  RUN #{run_number} {status}  |  {run_time.strftime('%Y-%m-%d %H:%M:%S')}  |  "
        + f"Total time: {_fmt_duration(run_elapsed)}\n"
        + "=" * 80 + "\n"
        + header + "\n"
        + sep + "\n"
        + rows
        + sep + "\n"
        + f"  {'TOTAL':<{col_w}}  "
        + f"{_fmt_duration(run_elapsed):>10}  "
        + f"{total_tokens:>12,}  "
        + f"${total_cost:>13.6f}\n"
        + "=" * 80 + "\n"
    )

    print(summary)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(summary)

    print(f"-> Log appended to: {LOG_FILE}")


if __name__ == "__main__":
    main()

