"""Minimal pkg_resources shim for Python 3.13+.

Several audio/ML libraries (webrtcvad, resemblyzer/librosa) import
``pkg_resources`` at the top level.  In Python 3.13 that module was
removed from the stdlib and requires ``setuptools`` to be installed.

This module injects a lightweight stub into ``sys.modules`` when the
real ``pkg_resources`` is unavailable, providing just enough surface
area for those libraries to import successfully.

Call ``ensure_pkg_resources()`` **before** importing any affected library.
"""

from __future__ import annotations

import sys
import types


class _FakeDistribution:
    """Minimal stand-in for ``pkg_resources.Distribution``."""

    def __init__(self, version: str = "0.0.0") -> None:
        self.version = version
        self.project_name = "unknown"

    def __str__(self) -> str:
        return f"{self.project_name} {self.version}"


def _get_distribution(name: str) -> _FakeDistribution:
    """Return a fake distribution so version lookups don't crash."""
    dist = _FakeDistribution()
    dist.project_name = name
    return dist


def _require(*_args, **_kwargs):
    """No-op replacement for ``pkg_resources.require``."""
    return []


def ensure_pkg_resources() -> None:
    """Guarantee that ``import pkg_resources`` will succeed.

    If the real ``setuptools``-provided module is available it is left
    untouched.  Otherwise a tiny stub is registered in ``sys.modules``.
    """
    if "pkg_resources" in sys.modules:
        return

    try:
        import pkg_resources  # noqa: F401
    except ModuleNotFoundError:
        mod = types.ModuleType("pkg_resources")
        mod.get_distribution = _get_distribution  # type: ignore[attr-defined]
        mod.require = _require  # type: ignore[attr-defined]
        mod.DistributionNotFound = Exception  # type: ignore[attr-defined]
        mod.VersionConflict = Exception  # type: ignore[attr-defined]
        mod.__version__ = "0.0.0"  # type: ignore[attr-defined]
        sys.modules["pkg_resources"] = mod
