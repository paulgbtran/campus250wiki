#!/usr/bin/env python3
"""
sources.py
Finds credible websites for Philadelphia history research and appends
them to sources.list. This list is used by search.py to restrict
article-level searches to approved domains.

This script makes a single Gemini query asking for authoritative
reference websites (homepages/base URLs), not per-topic article links —
that is handled by search.py.
"""
from pathlib import Path
from urllib.parse import urlparse

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"
SOURCES_LIST = Path(__file__).parent / "sources.list"

PROMPT = """\
You are a research librarian helping build a Philadelphia history encyclopedia.

List credible, authoritative websites that would be good general references \
for researching Philadelphia history topics such as historical figures, \
landmarks, events, and cultural narratives.

Include only the base homepage URL for each site (e.g. https://www.britannica.com/). \
Focus on encyclopedias, museums, government archives, universities, \
historical societies, and reputable news/magazine outlets.

Return ONLY a plain list of base URLs, one per line. \
No commentary, no bullet points, no numbering, no markdown.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def loadExistingUrls() -> set[str]:
    """Returns the set of URLs already recorded in sources.list."""
    if not SOURCES_LIST.exists():
        return set()
    urls = set()
    for line in SOURCES_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.add(line)
    return urls

def parseUrls(text: str) -> list[str]:
    """Extracts valid-looking base URLs from the model's response."""
    urls = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•* \t")
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
    return urls

# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def findSources() -> None:
    """
    Asks Gemini for credible Philadelphia history research websites and
    appends any new ones to sources.list without overwriting existing content.
    """
    client = genai.Client()
    existing_urls = loadExistingUrls()

    print(f"Querying {MODEL} for credible Philadelphia history sources...")
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=PROMPT,
            config=types.GenerateContentConfig(
                temperature=0.2,        # low temp for factual output
                max_output_tokens=2048,
            ),
        )
    except Exception as e:
        print(f"Error querying Gemini: {e}")
        return

    candidates = parseUrls(response.text)
    new_urls = [url for url in candidates if url not in existing_urls]

    if not new_urls:
        print("No new sources found.")
        return

    # Append new URLs to sources.list (preserve all existing content)
    with open(SOURCES_LIST, "a", encoding="utf-8") as f:
        existing_text = SOURCES_LIST.read_text(encoding="utf-8") if SOURCES_LIST.exists() else ""
        if existing_text and not existing_text.endswith("\n"):
            f.write("\n")
        for url in new_urls:
            print(f"  + {url}")
            f.write(url + "\n")

    print(f"\nDone. {len(new_urls)} new source(s) added to {SOURCES_LIST}.")


def main() -> None:
    findSources()


if __name__ == "__main__":
    main()