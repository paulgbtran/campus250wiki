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
from pathlib import Path

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "gemini-2.5-flash"

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
Create a comprehensive Wikipedia-style entry for the Philadelphia history topic: {topic}.

The topic belongs to the category: {category}.

Structure the entry using the following sections in order:
{sections}

Guidelines:
- Write in an encyclopedic, neutral tone similar to Wikipedia.
- The Infobox should be a concise summary table of key facts (name, dates, location, etc.). Infobox content must not be blank.
- The Lead section should be a brief, standalone summary of the topic (2-4 sentences).
- Fill each subsequent section with detailed, well-organized prose.
- The "See also" section should list related Philadelphia history topics as a bullet list.
- The "References" section should list the sources used, formatted as a numbered list with URLs.

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
        with open("../data/topics.txt", "r", encoding="utf-8") as f:
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
    with open(f"../data/search/{topic}.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def loadInfo(topic: str) -> list[str]:
    """
    Loads the information for a given topic from the search directory.
    """
    http = urllib3.PoolManager()
    info = []
    for url in loadLinks(topic):
        try:
            response = http.request("GET", url)
            info.append(response.data.decode("utf-8"))
            print(f"Successfully loaded {url}. Reading...") # DEBUG
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
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )
    print(f"Successfully synthesized {topic}. Writing to file...") # DEBUG
    os.makedirs("../data/entries", exist_ok=True)
    with open(f"../data/entries/{topic}.txt", "w", encoding="utf-8") as f:
        f.write(response.text)

def main() -> None:
    for topic in os.listdir("../data/search"):
        if topic.endswith(".txt"):
            synthesizeData(topic[:-4])

if __name__ == "__main__":
    main()
