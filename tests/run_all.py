#!/usr/bin/env python3
"""Run every tests/test_*.py and report a combined result (no pytest needed).

    python3 tests/run_all.py
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    tests = sorted(HERE.glob("test_*.py"))
    failed: list[str] = []
    total_pass = 0
    for test in tests:
        result = subprocess.run([sys.executable, str(test)], capture_output=True, text=True)
        last = (result.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"{test.name:28} {last}")
        if result.returncode != 0:
            failed.append(test.name)
            if result.stderr.strip():
                print(result.stderr.strip())
        else:
            digits = "".join(ch for ch in last.split("/")[0] if ch.isdigit())
            total_pass += int(digits) if digits else 0
    print("-" * 50)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"ALL GREEN — {total_pass} tests across {len(tests)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
