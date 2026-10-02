"""Mobile-emulation rules for proof capture. Browser tests skip without playwright."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture.py"
PAGE = "data:text/html,<title>t</title><h1>hello</h1>"


def run(tmp_path, *args):
    return subprocess.run([sys.executable, str(SCRIPT), PAGE, "--studio", str(tmp_path),
                           "--name", "p", "--wait", "0.2", *args],
                          capture_output=True, text=True)


def sidecar(tmp_path):
    return json.loads((tmp_path / "assets" / "proof" / "p.json").read_text())


def test_wide_width_without_desktop_is_refused(tmp_path):
    r = run(tmp_path, "--width", "1280")
    assert r.returncode != 0
    assert "mobile" in r.stderr
    assert not (tmp_path / "assets").exists()


def test_desktop_flag_warns_about_proof_rule(tmp_path):
    pytest.importorskip("playwright")
    r = run(tmp_path, "--desktop", "--width", "1280")
    assert "violates rules/proof.md" in r.stderr


def test_default_capture_is_mobile(tmp_path):
    pytest.importorskip("playwright")
    r = run(tmp_path)
    assert r.returncode == 0, r.stderr
    meta = sidecar(tmp_path)
    assert meta["mobile"] is True
    assert "Mobile" in meta["user_agent"] and "iPhone" in meta["user_agent"]
    assert meta["viewport"] == [390, 844] and meta["dpr"] == 3
    assert "mobile=True" in r.stdout


def test_desktop_sidecar_records_not_mobile(tmp_path):
    pytest.importorskip("playwright")
    r = run(tmp_path, "--desktop", "--width", "1280", "--height", "800")
    assert r.returncode == 0, r.stderr
    meta = sidecar(tmp_path)
    assert meta["mobile"] is False
    assert "Mobile" not in meta["user_agent"]
