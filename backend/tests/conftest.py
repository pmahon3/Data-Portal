# backend/tests/conftest.py
"""Pytest configuration for smoke tests."""
import pytest


def pytest_configure(config):
    """Configure pytest for cleaner smoke test output."""
    # Disable pytest warnings
    config.option.disable_warnings = True


def pytest_runtest_logreport(report):
    """Custom test result logging for cleaner output."""
    if report.when == "call":
        test_name = report.nodeid.split("::")[-1]
        if report.passed:
            # Use simple checkmark for passed tests
            print(f"  ✓ {test_name}", flush=True)
        elif report.failed:
            print(f"  ✗ {test_name}", flush=True)
            if hasattr(report, "longrepr"):
                print(f"    {report.longrepr}", flush=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Suppress verbose output during test execution."""
    outcome = yield
    report = outcome.get_result()

    # Suppress chatty output from successful tests
    if report.when == "call" and report.passed:
        report.sections = []
