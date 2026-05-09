#!/usr/bin/env python3
"""
topics.py
Generate a list of Philadelphia-related historical topics.

Queries Google Gemini to list historical figures, landmarks, events, and
cultural narratives/shifts related to Philadelphia, then writes the results
to a text file with one entry per line.
"""

import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "topics.txt"

BASE_PROMPT = (
    "List all notable historical figures, landmarks, events, and cultural "
    "narratives or shifts related to Philadelphia, Pennsylvania. "
    "Return **only** the list — one entry per line, no numbering, no bullet "
    "points, no extra commentary. Each line should contain the name or short "
    "description of the item followed by its category in parentheses, for "
    "example:\n\n"
    "Benjamin Franklin; Historical Figure\n"
    "Independence Hall; Landmark\n"
    "Constitutional Convention of 1787; Event\n"
    "The Great Migration's impact on Philadelphia; Cultural Narrative\n\n"
    "Be thorough and include entries spanning Philadelphia's full 250-year "
    "history, from its founding by William Penn in 1682 through the present day."
)


def build_prompt(existing_entries: list[str]) -> str:
    """Return the generation prompt, instructing the model to skip known entries."""
    if not existing_entries:
        return BASE_PROMPT
    existing_block = "\n".join(existing_entries)
    return (
        BASE_PROMPT
        + "\n\nThe following entries already exist — do NOT repeat them; "
        "only return entries that are not already in this list:\n\n"
        + existing_block
    )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Resolve API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "Error: GEMINI_API_KEY environment variable is not set.\n"
            "Set it with:  export GEMINI_API_KEY='your-key-here'  (Linux/macOS)\n"
            "              set GEMINI_API_KEY=your-key-here        (Windows CMD)\n"
            "              $env:GEMINI_API_KEY='your-key-here'     (PowerShell)"
        )

    # Load existing topics so we can merge rather than overwrite
    existing_lines: list[str] = []
    if OUTPUT_FILE.exists():
        raw = OUTPUT_FILE.read_text(encoding="utf-8")
        existing_lines = [l.strip() for l in raw.splitlines() if l.strip()]
        print(f"Found {len(existing_lines)} existing topics in {OUTPUT_FILE}")

    # Build a normalised set for fast duplicate detection (case-insensitive)
    existing_normalised = {l.lower() for l in existing_lines}

    # Initialize the Gemini client
    client = genai.Client(api_key=api_key)

    print(f"Querying {MODEL} for new Philadelphia historical topics …")

    prompt = build_prompt(existing_lines)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,          # lower temperature for factual output
            max_output_tokens=8192,   # allow a long list
        ),
    )

    # Extract the text from the response
    text = response.text.strip()
    if not text:
        sys.exit("Error: Gemini returned an empty response.")

    # Clean up and deduplicate against existing entries
    new_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and line.strip().lower() not in existing_normalised
    ]

    if not new_lines:
        print("No new topics found — file is already up to date.")
        return

    # Merge: existing entries first, then new ones
    merged = existing_lines + new_lines

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write the merged list (one entry per line)
    OUTPUT_FILE.write_text("\n".join(merged) + "\n", encoding="utf-8")

    print(
        f"✓ Added {len(new_lines)} new topics "
        f"(total {len(merged)}) to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
