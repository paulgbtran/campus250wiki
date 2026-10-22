#!/usr/bin/env python3
"""
classifier.py
Author: Paul Tran   <tranb9@lasalle.edu>
                    <paulgbtran@gmail.com>
Sorts topics.txt into categories before searching.

This script reads the topics.txt file, which contains a list of
Philadelphia-related historical topics, and sorts them into categories.
"""
from pathlib import Path
rootDir = Path(__file__).parent.parent.parent

class Entry:
    def __init__(self, name, category):
        self.name = name
        self.category = category

def parse():
    entries = []
    try:
        with open(rootDir / "data" / "topics.txt", "r", encoding="utf-8") as f:
            for line in f: 
                if ";" in line:
                    details = line.rsplit(";", 1)
                    print(details)
                    name = details[0]
                    category = details[1].strip().replace("\n", "")
                    entries.append(Entry(name, category))
                else: continue
    except Exception as e:
        print(f"Error parsing topics in search classifier: {e}")
    return entries

def main() -> None:
    try:
        entries = parse()
        for entry in entries:
            print(f"{entry.name}: {entry.category}")
    except Exception as e:
        print(f"Error in search classifier main: {e}")
        
if __name__ == "__main__":
    main()