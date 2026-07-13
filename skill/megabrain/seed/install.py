#!/usr/bin/env python3
"""Compatibility entry point for MegaBrain onboarding."""

from pathlib import Path
import runpy
import sys


if len(sys.argv) == 1 or sys.argv[1].startswith("-"):
    sys.argv.insert(1, "setup")
runpy.run_path(
    str(Path(__file__).resolve().parent / "skill" / "megabrain" / "scripts" / "bootstrap.py"),
    run_name="__main__",
)
