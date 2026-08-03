#!/usr/bin/env python3
"""
classifier.py

Reads valid_topics.txt and checks if the current category matches the topic correctly
using Gemini. The verified topics are written to classified_topics.txt.
"""
import os
import sys
from pathlib import Path
rootDir = Path(__file__).parent.parent.parent

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Error: GEMINI_API_KEY environment variable is not set.")

    input_file = rootDir / "data" / "factcheck" / "valid_topics.txt"
    output_file = rootDir / "data" / "factcheck" / "classified_topics.txt"

    if not input_file.exists():
        print(f"Error: {input_file} not found. Run topics.py first.")
        return

    client = genai.Client(api_key=api_key)
    verified_entries = []

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        if not line.strip():
            continue
        parts = line.strip().rsplit("; ", 1)
        if len(parts) != 2:
            continue
        topic, category = parts
        
        print(f"Verifying category for {topic}...")
        prompt = (
            f"Is '{topic}' correctly classified as a '{category}' in the context of Philadelphia history? "
            "Reply with 'YES' if it is correct, or 'NO' if it is incorrect. Do not provide any other text."
        )

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=10,
            ),
        )

        answer = response.text.strip().upper()
        if "YES" in answer:
            verified_entries.append(line.strip())
            print(f"  -> Match confirmed.")
        else:
            print(f"  -> Category mismatch: {answer}")

    with open(output_file, "w", encoding="utf-8") as f:
        for entry in verified_entries:
            f.write(f"{entry}\n")
            
    print(f"Saved {len(verified_entries)} verified topics to {output_file}")

class Entry:
    def __init__(self, name, category):
        self.name = name
        self.category = category

def parse():
    entries = []
    output_file = rootDir / "data" / "factcheck" / "classified_topics.txt"
    if not output_file.exists():
        return entries
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f: 
            parts = line.strip().rsplit("; ", 1)
            if len(parts) == 2:
                entries.append(Entry(parts[0], parts[1]))
    return entries

if __name__ == "__main__":
    main()
