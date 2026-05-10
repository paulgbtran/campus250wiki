#!/usr/bin/env python3
"""
search.py
Find sources for topics in topics.txt.

This script takes each entry from the classified topic list and searches
for article URLs related to that entry, restricting results to the
approved domains listed in sources.list. Results are written to
data/search/<topic>.txt.
"""
import time
from pathlib import Path
from urllib.parse import urlparse

from google import genai
from google.genai import types

import classifier

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"
SOURCES_LIST = Path(__file__).parent / "sources.list"

PROMPT_TEMPLATE = """\
Find credible online sources specifically about the Philadelphia history topic: "{topic}".

Only return URLs from the following approved websites:
{approved_domains}

Return ONLY a plain list of full article or page URLs (one per line). \
No commentary, no bullet points, no numbering, no markdown.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def loadApprovedDomains() -> list[str]:
    """
    Reads sources.list and returns a list of approved base URLs
    (skipping comment lines and blank lines).
    """
    if not SOURCES_LIST.exists():
        print(f"Warning: {SOURCES_LIST} not found. Searches will not be domain-filtered.")
        return []
    domains = []
    for line in SOURCES_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            domains.append(line)
    return domains

def parseUrls(text: str) -> list[str]:
    """Extracts valid-looking URLs from a block of model output text."""
    urls = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•* \t")
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
    return urls

def isApprovedDomain(url: str, approved_domains: list[str]) -> bool:
    """Returns True if the URL's domain matches any approved domain."""
    netloc = urlparse(url).netloc.lower()
    for base in approved_domains:
        approved_netloc = urlparse(base).netloc.lower()
        if netloc == approved_netloc or netloc.endswith("." + approved_netloc):
            return True
    return False

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def searchTopic(topic: str, client: genai.Client, approved_domains: list[str]) -> None:
    """
    Queries Gemini for article URLs about a topic restricted to approved
    domains, then writes the filtered results to data/search/<topic>.txt.
    """
    print(f"Searching for: {topic}...")

    domain_list = "\n".join(f"  - {d}" for d in approved_domains) if approved_domains else "  (any credible source)"
    prompt = PROMPT_TEMPLATE.format(topic=topic, approved_domains=domain_list)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,        # low temp for factual URL output
            max_output_tokens=8192,
        ),
    )

    # Post-filter: keep only URLs from approved domains
    candidates = parseUrls(response.text)
    if approved_domains:
        filtered = [url for url in candidates if isApprovedDomain(url, approved_domains)]
        rejected = len(candidates) - len(filtered)
        if rejected:
            print(f"  Filtered out {rejected} URL(s) not in sources.list")
    else:
        filtered = candidates

    output_path = Path("data/search") / f"{topic}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(filtered), encoding="utf-8")
    print(f"  Saved {len(filtered)} URL(s) -> {output_path}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    client = genai.Client()
    approved_domains = loadApprovedDomains()
    entries = classifier.parse()

    for i, entry in enumerate(entries):
        searchTopic(entry.name, client, approved_domains)

    print("All searches complete.")

if __name__ == "__main__":
    main()
