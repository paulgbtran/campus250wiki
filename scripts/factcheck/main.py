#!/usr/bin/env python3
"""
main.py

Executes the factchecking pipeline scripts in sequential order:
1. search.py
2. factcheck.py

Assumes entries already exist in data/entries/.
Skips re-categorization (topics.py / classifier.py).
"""

import sys
import subprocess
from pathlib import Path

SCRIPTS = [
    "search.py",
    "factcheck.py",
]

def main() -> None:
    try:
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
    except Exception as e:
        print(f"Error running factcheck main pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
