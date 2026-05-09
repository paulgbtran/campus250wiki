#!/usr/bin/env python3
import os
import sys
import time
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types

import classifier

"""
search.py
Find sources for topics in topics.txt.

This script takes each entry from classified list entries and
searches for sources related to each entry, then outputting
the sources found in a text file containing all online locations
related to each entry.
"""

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"

PROMPT_TEMPLATE = (
    "Find credible online sources for the following Philadelphia history topic: {topic}. "
    "Return only a list of URLs, one per line, with no additional commentary."
)

def searchTopic(topic: str): 
    # Resolve API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "Error: GEMINI_API_KEY environment variable is not set.\n"
            "Set it with:  export GEMINI_API_KEY='your-key-here'  (Linux/macOS)\n"
            "              set GEMINI_API_KEY=your-key-here        (Windows CMD)\n"
            "              $env:GEMINI_API_KEY='your-key-here'     (PowerShell)"
        )

    # Initialize the Gemini client
    client = genai.Client(api_key=api_key)

    print(f"Querying {MODEL} for {topic}...")

    response = client.models.generate_content(
        model=MODEL,
        contents=PROMPT_TEMPLATE.format(topic=topic),
        config=types.GenerateContentConfig(
            temperature=0.4,          # lower temperature for factual output
            max_output_tokens=8192,   # allow a long list
        ),
    )

    # Ensure output directory exists, then write search results
    output_path = Path("data/search") / f"{topic}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.text, encoding="utf-8")

def main() -> None:
    # Populates entries list with topics from topics.txt
    entries = classifier.parse()
    # Loops through each entry, searching for sources
    for entry in entries:
        searchTopic(entry.name)
        # Prevents waiting after the last entry
        if entry != entries[-1]:
            time.sleep(12)
    print("All searches complete.")

if __name__ == "__main__":
    main()
