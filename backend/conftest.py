"""
conftest.py – pytest configuration for the backend test suite.

Ensures the backend/ directory is on sys.path so that `from app.*` imports
resolve correctly regardless of how pytest discovers the files, and clears
any stale __pycache__ entries that could cause "(unknown location)" errors.
"""
import os
import sys

import pytest

# Put the backend/ directory (this file's directory) first on sys.path so that
# `from app.xxx` always resolves to the real source tree, not a stale .pyc.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Point at the SQLite dev database that the test files use by default.
_TEST_DB = os.path.join(_HERE, "edusense_test.db").replace("\\", "/")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])
os.environ.setdefault("PYTHONUTF8", "1")


@pytest.fixture(autouse=True)
def reset_vector_store_collection():
    yield
    from app.services.vector_store import init_collection

    init_collection()
