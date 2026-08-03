#!/usr/bin/env python3
"""
main.py

Executes the pipeline scripts in sequential order:
1. topics.py
2. categories.py
3. sources.py
4. search.py
5. synthesizeData.py
"""

import sys
import subprocess
from pathlib import Path

SCRIPTS = [
    "topics.py",
    "classifier.py",
    "sources.py",
    "search.py",
    "synthesizeData.py",
]

def main() -> None:
    current_dir = Path(__file__).parent.resolve()
    python_exe = sys.executable

    for script_name in SCRIPTS:
        script_path = current_dir / script_name
        print(f"=== Running {script_name} ===")
        if not script_path.exists():
            print(f"Warning: {script_name} not found at {script_path}. Attempting to run via subprocess anyway...")
        
        result = subprocess.run([python_exe, str(script_path)])
        if result.returncode != 0:
            print(f"Error: {script_name} failed with return code {result.returncode}.")
            sys.exit(result.returncode)

if __name__ == "__main__":
    main()
