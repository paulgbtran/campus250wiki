#!/usr/bin/env python3
"""
topics.py

Checks if the topics listed in data/topics.txt have corresponding entry files
in data/entries/. If an entry exists, the topic is valid and written to
data/factcheck/valid_topics.txt for further processing.
"""
from pathlib import Path
import os

rootDir = Path(__file__).parent.parent.parent

def main():
    topics_file = rootDir / "data" / "topics.txt"
    entries_dir = rootDir / "data" / "entries"
    output_dir = rootDir / "data" / "factcheck"
    output_file = output_dir / "valid_topics.txt"

    if not topics_file.exists():
        print(f"Error: {topics_file} not found.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    
    valid_entries = []
    
    with open(topics_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().rsplit("; ", 1)
            if len(parts) != 2:
                continue
            name, category = parts
            
            # Check if entry file exists
            entry_file = entries_dir / f"{name}.txt"
            if entry_file.exists():
                valid_entries.append(line.strip())
                print(f"Found entry for topic: {name}")
            else:
                print(f"No entry found for topic: {name}")
                
    with open(output_file, "w", encoding="utf-8") as f:
        for entry in valid_entries:
            f.write(f"{entry}\n")
            
    print(f"Saved {len(valid_entries)} valid topics to {output_file}")

if __name__ == "__main__":
    main()
