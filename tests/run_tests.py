#!/usr/bin/env python
"""
E2E Test Suite Runner for Furniture Prompt Generator Studio.
Executes pytest across tests/ with structured reporting and proper exit codes.
Can be executed from project root or tests/ directory:
    python run_tests.py
    python -m tests.run_tests
"""
import os
import sys
from pathlib import Path

# Identify directories
SCRIPT_DIR = Path(__file__).resolve().parent
if SCRIPT_DIR.name == "tests":
    PROJECT_ROOT = SCRIPT_DIR.parent
    TESTS_DIR = SCRIPT_DIR
else:
    PROJECT_ROOT = SCRIPT_DIR
    TESTS_DIR = SCRIPT_DIR / "tests"

# Ensure PROJECT_ROOT is at head of sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_preflight_environment():
    """Checks required packages and project structure before running tests."""
    print("=" * 70)
    print(" Furniture Prompt Generator Studio - E2E Test Suite Runner ")
    print("=" * 70)
    print(f"Project Root : {PROJECT_ROOT}")
    print(f"Tests Dir    : {TESTS_DIR}")
    print(f"Python Exec  : {sys.executable}")
    print(f"Python Ver   : {sys.version.split()[0]}")

    missing_pkgs = []
    for pkg in ["pytest", "fastapi", "PIL", "pydantic", "google.genai"]:
        try:
            __import__(pkg)
        except ImportError:
            missing_pkgs.append(pkg)

    if missing_pkgs:
        print(f"\n[WARNING] Missing recommended test dependencies: {', '.join(missing_pkgs)}")
        print("Install them via: pip install -r requirements.txt pytest\n")

    # Check implementation readiness
    app_file = PROJECT_ROOT / "app.py"
    random_file = PROJECT_ROOT / "services" / "random_scenarios.py"
    gemini_file = PROJECT_ROOT / "services" / "gemini_service.py"

    print("\n--- Implementation Readiness Audit ---")
    print(f"  app.py                      : {'FOUND' if app_file.exists() else 'PENDING IMPLEMENTATION'}")
    print(f"  services/random_scenarios.py: {'FOUND' if random_file.exists() else 'PENDING IMPLEMENTATION'}")
    print(f"  services/gemini_service.py  : {'FOUND' if gemini_file.exists() else 'PENDING IMPLEMENTATION'}")
    print("=" * 70)


def main():
    check_preflight_environment()

    try:
        import pytest
    except ImportError:
        print("\n[ERROR] 'pytest' is not installed. Please run: pip install pytest")
        return 1

    # Pytest arguments
    pytest_args = [
        str(TESTS_DIR),
        "-v",
        "--tb=short",
        "-rA"
    ]

    # Forward any additional CLI args passed to this script
    if len(sys.argv) > 1:
        pytest_args.extend(sys.argv[1:])

    print(f"\nRunning command: pytest {' '.join(pytest_args)}\n")
    exit_code = pytest.main(pytest_args)

    print("\n" + "=" * 70)
    if exit_code == 0:
        print("  ALL TESTS PASSED SUCCESSFULLY! (Exit code 0)")
    else:
        print(f"  TEST EXECUTION COMPLETED WITH EXIT CODE: {exit_code}")
    print("=" * 70)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
