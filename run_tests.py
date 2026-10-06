#!/usr/bin/env python
"""
Root E2E Test Suite Runner for Furniture Prompt Generator Studio.
Delegates to tests/run_tests.py.
"""
import sys
from pathlib import Path

# Add tests directory
TESTS_DIR = Path(__file__).resolve().parent / "tests"
sys.path.insert(0, str(TESTS_DIR))

from run_tests import main

if __name__ == "__main__":
    sys.exit(main())
