#!/usr/bin/env python3
"""
factcheck.py

Reads from data/entries/{topic}.txt and makes necessary changes to it
based on factchecking, then logs the changes to data/factcheck/{topic}.txt.
"""
import os
import sys
from pathlib import Path
import time

rootDir = Path(__file__).parent.parent.parent

from google import genai
from google.genai import types

import classifier

MODEL = "gemini-2.5-flash"

PROMPT_TEMPLATE = """\
You are an expert historian and fact-checker. Please fact-check the following wiki entry about "{topic}".
Use the following credible URLs as a starting point for your research if needed (you may rely on your internal knowledge if the URLs are not directly accessible):
{urls}

Please carefully review the provided text and correct any factual inaccuracies. 

Output your response in the following exact format:

=== CORRECTED TEXT ===
[Insert the fully corrected wiki entry text here, preserving the original markdown formatting]
=== CHANGELOG ===
[Insert a bulleted list of the specific factual changes you made, and why. If no changes were needed, write "No changes needed."]

Original Text:
{original_text}
"""

def processTopic(topic: str, client: genai.Client) -> None:
    entry_path = rootDir / "data" / "entries" / f"{topic}.txt"
    search_path = rootDir / "data" / "factcheck" / "search" / f"{topic}.txt"
    log_path = rootDir / "data" / "factcheck" / f"{topic}.txt"

    if not entry_path.exists():
        print(f"Skipping {topic} - entry file not found.")
        return

    original_text = entry_path.read_text(encoding="utf-8")
    
    urls = ""
    if search_path.exists():
        urls = search_path.read_text(encoding="utf-8")

    print(f"Fact-checking: {topic}...")
    prompt = PROMPT_TEMPLATE.format(topic=topic, urls=urls, original_text=original_text)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
        ),
    )

    output = response.text
    
    if "=== CORRECTED TEXT ===" in output and "=== CHANGELOG ===" in output:
        parts = output.split("=== CORRECTED TEXT ===")
        if len(parts) < 2:
            print(f"Error parsing response for {topic}")
            return
            
        subparts = parts[1].split("=== CHANGELOG ===")
        corrected_text = subparts[0].strip()
        changelog = subparts[1].strip()
        
        # Write corrected text
        entry_path.write_text(corrected_text, encoding="utf-8")
        # Write changelog
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(changelog, encoding="utf-8")
        
        print(f"  -> Fact-check complete. Updated {entry_path} and logged to {log_path}")
    else:
        print(f"  -> Unexpected response format for {topic}. Skipping.")

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Error: GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)
    entries = classifier.parse()

    for entry in entries:
        processTopic(entry.name, client)
        time.sleep(2)  # rate limiting

if __name__ == "__main__":
    main()
