#!/usr/bin/env python3
"""
synthesizeData.py
Author: Paul Tran   <tranb9@lasalle.edu>
                    <paulgbtran@gmail.com>
Synthesizes the data for the Campus 250 wiki.

Gathers info from each of the URLs found in data/search/<topic>.txt,
then creates a comprehensive entry for the topic in data/entries/<topic>.txt.
"""

import urllib3
import os
import sys
import time
import re
from html.parser import HTMLParser
from pathlib import Path
rootDir = Path(__file__).parent.parent.parent
sys.path.append(str(rootDir / "scripts"))
import gemini_utils

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-3.5-flash"

# Wikipedia-style section structures per category (mirrors TODO.md)
SECTION_STRUCTURES: dict[str, list[str]] = {
    "historical figure": [
        "Infobox",
        "Lead section",
        "Early life and education",
        "Career",
        "Personal life",
        "Legacy",
        "See also",
        "References",
    ],
    "landmark": [
        "Infobox",
        "Lead section",
        "History",
        "Architecture",
        "Cultural significance",
        "See also",
        "References",
    ],
    "event": [
        "Infobox",
        "Lead section",
        "Background",
        "Course of events",
        "Aftermath",
        "See also",
        "References",
    ],
    "cultural narrative": [
        "Infobox",
        "Lead section",
        "Origins",
        "Development",
        "Impact",
        "See also",
        "References",
    ],
}

PROMPT_TEMPLATE = """\
Create a comprehensive, full-length Wikipedia-style entry for the Philadelphia history topic: {topic}.

The topic belongs to the category: {category}.

Structure the entry using the following sections in order:
{sections}

Guidelines & Length Requirements:
- Tone & Style: Write in an objective, highly detailed, encyclopedic, and neutral tone consistent with standard Wikipedia articles (avoiding stubs, summaries, or high-level overviews; write with full historical context).
- Length & Depth: The generated article must be exhaustive and long-form—aiming for roughly 700 to 1,200 words total. Do not compress or rush the content. Every single section listed under {sections} must be fleshed out with multiple robust paragraphs of deep historical analysis, narrative progression, and factual detail.
- Infobox: The Infobox must be formatted as a structured summary table containing key metadata (e.g., name, dates, location, key figures, significance). It must not be blank.
- Lead Section: The lead section must precede the main sections as a standalone introductory summary of 3 to 4 comprehensive paragraphs defining the topic and outlining its major historical importance.
- Source Integration: Extensively utilize and synthesize the provided source material to anchor all facts, dates, and claims.
- "See also" section: List related Philadelphia history topics as a clean bulleted list.
- "References" section: List the sources used as a structured numbered list with URLs derived from the provided text.

Use the following source material to write the entry:

{info}
"""

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def loadCategory(topic: str) -> str:
    """
    Looks up the category of a topic from data/topics.txt.
    Returns the category string, or 'unknown' if not found.
    """
    try:
        with open(rootDir / "data" / "topics.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "; " in line:
                    name, category = line.rsplit("; ", 1)
                    if name.strip().lower() == topic.strip().lower():
                        return category.strip().lower()
    except FileNotFoundError:
        pass
    return "unknown"

def loadLinks(topic: str) -> list[str]:
    """
    Loads the URLs for a given topic from the search directory.
    """
    try:
        with open(rootDir / "data" / "search" / f"{gemini_utils.sanitize_filename(topic)}.txt", "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error loading links for {topic}: {e}")
        return []

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self.skip = False
        self.skip_tags = {"script", "style", "noscript", "svg", "head", "iframe"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.skip = True

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags:
            self.skip = False

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.fed.append(d)

    def get_text(self):
        return " ".join(self.fed)

def extract_text_from_html(html_content: str, max_chars: int = 25000) -> str:
    """Extracts visible text from HTML, stripping scripts, styles, and markup tags."""
    try:
        parser = HTMLTextExtractor()
        parser.feed(html_content)
        text = parser.get_text()
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception:
        clean = re.sub(r'<script[^>]*>.*?</script>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r'<style[^>]*>.*?</style>', ' ', clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:max_chars]

MAX_URLS_PER_TOPIC = 8
MAX_CHARS_PER_PAGE = 25000
MAX_TOTAL_INFO_CHARS = 180000

def loadInfo(topic: str) -> list[str]:
    """
    Loads text content from the URLs for a given topic from the search directory,
    stripping HTML markup and capping token usage.
    """
    http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5.0, read=10.0))
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    info = []
    links = loadLinks(topic)[:MAX_URLS_PER_TOPIC]
    total_chars = 0

    for url in links:
        if total_chars >= MAX_TOTAL_INFO_CHARS:
            break
        try:
            response = http.request("GET", url, headers=headers)
            raw_html = response.data.decode("utf-8", errors="replace")
            clean_text = extract_text_from_html(raw_html, max_chars=MAX_CHARS_PER_PAGE)
            if clean_text:
                info.append(f"--- Source: {url} ---\n{clean_text}")
                total_chars += len(clean_text)
                print(f"Successfully loaded and parsed {url} ({len(clean_text)} chars).")
        except Exception as e:
            print(f"Error loading {url}: {e}")
            continue
    return info

# ---------------------------------------------------------------------------
# Main 
# ---------------------------------------------------------------------------

def synthesizeData(topic: str) -> None:
    """
    Synthesizes the data for a given topic.
    """
    try:
        info = loadInfo(topic)
        category = loadCategory(topic)
        sections = SECTION_STRUCTURES.get(category, SECTION_STRUCTURES["historical figure"])
        sections_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sections))

        prompt = PROMPT_TEMPLATE.format(
            topic=topic,
            category=category if category != "unknown" else "general Philadelphia history",
            sections=sections_text,
            info="\n".join(info),
        )

        client = genai.Client()
        response = gemini_utils.query_gemini(
            client=client,
            model=MODEL,
            contents=prompt,
        )
        print(f"Successfully synthesized {topic}. Writing to file...") # DEBUG
        os.makedirs(rootDir / "data" / "entries", exist_ok=True)
        with open(rootDir / "data" / "entries" / f"{gemini_utils.sanitize_filename(topic)}.txt", "w", encoding="utf-8") as f:
            f.write(response.text)
    except Exception as e:
        print(f"Error synthesizing data for {topic}: {e}")

def main() -> None:
    try:
        search_dir  = rootDir / "data" / "search"
        entries_dir = rootDir / "data" / "entries"

        all_topics = [f[:-4] for f in os.listdir(search_dir) if f.endswith(".txt")]

        # ---------------------------------------------------------------------------
        # Timeout setup -- read limit passed by main.py via env var
        # ---------------------------------------------------------------------------
        timeout_sec = int(os.environ.get("PIPELINE_TIMEOUT_SECONDS", 0)) or None
        start_time  = time.perf_counter()

        # Prioritize topics with no entry file yet (newly discovered topics).
        # This guarantees all new topics are synthesized before the clock runs out.
        new_topics  = [t for t in all_topics if not (entries_dir / f"{t}.txt").exists()]
        done_topics = [t for t in all_topics if     (entries_dir / f"{t}.txt").exists()]
        ordered     = new_topics + done_topics

        if timeout_sec:
            print(
                f"[i] Time limit: {timeout_sec // 60}m -- "
                f"synthesizing {len(new_topics)} new topic(s) first, "
                f"then {len(done_topics)} existing topic(s) if time allows."
            )

        for topic in ordered:
            if timeout_sec is not None:
                elapsed = time.perf_counter() - start_time
                if elapsed >= timeout_sec:
                    print(
                        f"\n[!] Time limit reached ({timeout_sec // 60}m). "
                        "Stopping synthesis -- all new topics have been prioritised."
                    )
                    break

            synthesizeData(topic)

    except Exception as e:
        print(f"Error in synthesizeData main: {e}")

if __name__ == "__main__":
    main()
