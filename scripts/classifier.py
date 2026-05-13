#!/usr/bin/env python3
"""
classifier.py
Author: Paul Tran   <tranb9@lasalle.edu>
                    <paulgbtran@gmail.com>
Sorts topics.txt into categories before searching.

This script reads the topics.txt file, which contains a list of
Philadelphia-related historical topics, and sorts them into categories.
"""

class Entry:
    def __init__(self, name, category):
        self.name = name
        self.category = category

def parse():
    entries = []
    with open("../data/topics.txt", "r", encoding="utf-8") as f:
        for line in f: 
            name, category = line.strip().rsplit("; ", 1)
            entries.append(Entry(name, category))
    return entries

def main() -> None:
    entries = parse()
    for entry in entries:
        print(f"{entry.name}: {entry.category}")
        
if __name__ == "__main__":
    main()