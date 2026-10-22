#!/usr/bin/env python3
"""
search.py

Finds a list of credible URLs to factcheck from (e.g. National Park Service, 
Britannica, Philadelphia Inquirer) for each verified topic.
Outputs a txt file for each topic in data/factcheck/search.
"""
import os
import sys
from pathlib import Path
import time
from urllib.parse import urlparse

rootDir = Path(__file__).parent.parent.parent
sys.path.append(str(rootDir / "scripts"))
import gemini_utils

from google import genai
from google.genai import types


MODEL = "gemini-3.5-flash"

PROMPT_TEMPLATE = """\
Find credible online sources specifically about the Philadelphia history topic: "{topic}".

Please restrict your search to highly credible fact-checking sources, such as:
- National Park Service (nps.gov)
- Encyclopedia Britannica (britannica.com)
- Philadelphia Inquirer (inquirer.com)
- History.com
- PBS (pbs.org)
- .edu domains
- .gov domains

Return ONLY a plain list of full article or page URLs (one per line). \
No commentary, no bullet points, no numbering, no markdown.
"""

def parseUrls(text: str) -> list[str]:
    """Extracts valid-looking URLs from a block of model output text."""
    urls = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•* \t")
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
    return urls

def searchTopic(topic: str, client: genai.Client) -> None:
    try:
        print(f"Finding factchecking sources for: {topic}...")
        prompt = PROMPT_TEMPLATE.format(topic=topic)

        response = gemini_utils.query_gemini(
            client=client,
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )

        urls = parseUrls(response.text)
        
        output_path = rootDir / "data" / "factcheck" / "search" / f"{topic}.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        existing: list[str] = []
        if output_path.exists():
            existing = [u for u in output_path.read_text(encoding="utf-8").splitlines() if u.strip()]

        seen = set(existing)
        new_urls = [u for u in urls if u not in seen]
        combined = existing + new_urls

        output_path.write_text("\n".join(combined), encoding="utf-8")
        print(f"  Saved {len(combined)} URL(s) ({len(new_urls)} new) -> {output_path}")
    except Exception as e:
        print(f"Error searching topic {topic}: {e}")

def main():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            sys.exit("Error: GEMINI_API_KEY environment variable is not set.")

        client = genai.Client(api_key=api_key)

        entries_dir = rootDir / "data" / "entries"
        if not entries_dir.exists():
            print(f"Error: {entries_dir} not found. Run the search pipeline first.")
            return

        topics = [f.stem for f in entries_dir.glob("*.txt")]
        if not topics:
            print("No entries found in data/entries/. Nothing to search.")
            return

        for topic in topics:
            searchTopic(topic, client)
    except Exception as e:
        print(f"Error in factcheck search main: {e}")

if __name__ == "__main__":
    main()
