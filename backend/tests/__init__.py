"""Test package bootstrap.

Environment configuration happens here because `config.py` reads the
environment at import time, and the application modules are imported by the
test modules below this package.

The suite is written against `unittest`, so it runs with either
`python -m unittest discover -s tests` (no third-party dependency) or `pytest`.
Tests that need a native tree-sitter build or FastAPI skip themselves when
those are absent, so the same suite is meaningful in a minimal environment and
complete in a full one.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="conformance-tests-")
os.environ.setdefault("WORKSPACE_DIR", _TMP)
os.environ.setdefault("SECRET_KEY", "test-only-secret-not-for-deployment")
os.environ.setdefault("LLM_MODE", "offline")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("MAX_ANALYSES_PER_HOUR", "10000")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
