"""Smoke test: HyperFrames invoke path stays pinned."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import compose  # noqa: E402


def test_hyperframes_pin_is_versioned():
    assert compose.HYPERFRAMES_VERSION.count(".") >= 1
    assert compose.HYPERFRAMES_PKG == f"hyperframes@{compose.HYPERFRAMES_VERSION}"
    for script in compose.PACKAGE_JSON["scripts"].values():
        assert compose.HYPERFRAMES_PKG in script
        assert "npx --yes hyperframes " not in script  # unpinned form
