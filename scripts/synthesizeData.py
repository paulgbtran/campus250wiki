#!/usr/bin/env python3
"""
synthesizeData.py
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

PROMPT_TEMPLATE = (
    "Create a comprehensive entry for the Philadelphia history topic: {topic}. "
    "Use the following information to create the entry:\n\n{info}\n\n"
)

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def loadLinks(topic: str) -> list[str]:
    """
    Loads the URLs for a given topic from the search directory.
    """
    with open(f"data/search/{topic}.txt", "r", encoding="utf-8") as f:
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
    client = genai.Client()
    response = client.models.generate_content(
        model=MODEL,
        contents=PROMPT_TEMPLATE.format(topic=topic, info="\n".join(info)),
    )
    print(f"Successfully synthesized {topic}. Writing to file...") # DEBUG
    os.makedirs("data/entries", exist_ok=True)
    with open(f"data/entries/{topic}.txt", "w", encoding="utf-8") as f:
        f.write(response.text)

def main() -> None:
    for topic in os.listdir("data/search"):
        if topic.endswith(".txt"):
            synthesizeData(topic[:-4])

if __name__ == "__main__":
    main()
