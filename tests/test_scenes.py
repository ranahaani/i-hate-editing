"""Scene spec validation, composition registration and overlay merge."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scenes  # noqa: E402


def test_overlapping_scenes_are_rejected():
    plan = [{"id": "one", "start": 1.0, "duration": 2.0},
            {"id": "two", "start": 2.5, "duration": 1.0}]
    with pytest.raises(SystemExit):
        scenes.validate(plan, 30, 10.0)


def test_scene_past_the_cut_is_rejected():
    with pytest.raises(SystemExit):
        scenes.validate([{"id": "late", "start": 9.0, "duration": 2.0}],
                        30, 10.0)


def test_long_scene_warns_but_passes():
    warnings = scenes.validate(
        [{"id": "held", "start": 0.0, "duration": 6.0}], 30, 10.0)
    assert any("held" in w for w in warnings)


def test_frames_come_from_the_cut_fps():
    s = scenes.spec([{"id": "pop", "start": 1.0, "duration": 2.0}],
                    1080, 1920, 30)
    assert s["scenes"][0]["durationInFrames"] == 60
    assert s["scenes"][0]["component"] == "Pop"


def test_root_registers_every_scene_independently():
    s = scenes.spec([{"id": "token-waste", "start": 0.0, "duration": 1.0},
                     {"id": "payoff", "start": 2.0, "duration": 1.0}],
                    1080, 1920, 30)
    root = scenes.root_tsx(s)
    assert root.count("<Composition") == 2
    assert 'id="token-waste"' in root
    assert "TokenWaste" in root and "Payoff" in root


def test_merge_keeps_broll_and_replaces_scene_entries(tmp_path):
    studio = tmp_path
    (studio / "broll.json").write_text(json.dumps({"overlays": [
        {"file": "assets/broll/a.mp4", "start": 0.0, "end": 3.0},
        {"id": "payoff", "source": "scene", "file": "old.mp4",
         "start": 5.0, "end": 6.0},
    ]}))
    scenes.merge_overlays(studio, {"payoff": {
        "id": "payoff", "source": "scene",
        "file": "assets/scenes/payoff.mp4", "start": 5.0, "end": 7.0,
        "full": True}})
    overlays = json.loads((studio / "broll.json").read_text())["overlays"]
    assert len(overlays) == 2
    assert overlays[0]["file"] == "assets/broll/a.mp4"
    assert overlays[1]["file"] == "assets/scenes/payoff.mp4"
    assert overlays[1]["end"] == 7.0
