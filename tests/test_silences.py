"""Smoke tests for silence-gap quality labels — no media required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from silences import CLEAN, USABLE  # noqa: E402


def quality(duration):
    """Mirror the classification in silences.detect without calling ffmpeg."""
    if duration >= CLEAN:
        return "clean"
    if duration >= USABLE:
        return "usable"
    return "unsafe"


def test_thresholds_are_ordered():
    assert CLEAN > USABLE > 0


def test_quality_labels():
    assert quality(0.50) == "clean"
    assert quality(CLEAN) == "clean"
    assert quality(0.20) == "usable"
    assert quality(USABLE) == "usable"
    assert quality(0.05) == "unsafe"
