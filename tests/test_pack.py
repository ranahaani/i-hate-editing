"""Smoke tests for phrase packing — no ffmpeg required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pack import phrases  # noqa: E402


def test_word_phrases_split_on_long_gap():
    words = [
        {"start": 0.0, "end": 0.2, "text": "Hello"},
        {"start": 0.25, "end": 0.4, "text": "world"},
        {"start": 1.2, "end": 1.4, "text": "Again"},
    ]
    out = phrases(words, "word")
    assert len(out) == 2
    assert out[0]["text"] == "Hello world"
    assert out[1]["text"] == "Again"
    assert out[0]["start"] == 0.0
    assert out[1]["end"] == 1.4


def test_word_phrases_keep_punctuation_glued():
    words = [
        {"start": 0.0, "end": 0.2, "text": "Wait"},
        {"start": 0.21, "end": 0.22, "text": ","},
        {"start": 0.25, "end": 0.4, "text": "what"},
        {"start": 0.41, "end": 0.42, "text": "?"},
    ]
    out = phrases(words, "word")
    assert len(out) == 1
    assert out[0]["text"] == "Wait, what?"


def test_segment_granularity_passthrough():
    words = [
        {"start": 0.0, "end": 1.0, "text": "Already a phrase"},
        {"start": 1.5, "end": 2.5, "text": "And another"},
    ]
    out = phrases(words, "segment")
    assert out == words
