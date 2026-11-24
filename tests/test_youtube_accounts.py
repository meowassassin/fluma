"""YouTube 채널 여러 개 — 예전 한 계정 파일(~/.shortsforge/youtube.json)을 새 모양으로 옮기는 규칙(서버 youtube.mjs · 업로드 스크립트 둘 다).
진짜 파일은 건드리지 않는다: 임시 경로만 쓴다."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine" / "publish"))
import upload_youtube as up  # noqa: E402

OLD = {"client_id": "cid.apps.googleusercontent.com", "client_secret": "sec", "refresh_token": "rt-old",
       "channel": {"id": "UCold", "title": "옛 채널", "thumb": "https://x/a.jpg"}, "connected_at": "2026-11-01T00:00:00Z"}


def test_py_migrates_old_single_account():
    d = up.normalize(OLD)
    assert d["accounts"] == [{"id": "UCold", "refresh_token": "rt-old", "channel": OLD["channel"], "connected_at": OLD["connected_at"]}]
    assert d["default"] == "UCold"
    assert "refresh_token" not in d and "channel" not in d
    assert d["client_id"] == OLD["client_id"]


def test_py_new_shape_kept_and_default_repaired():
    new = {"client_id": "c", "client_secret": "s", "accounts": [{"id": "UCa", "refresh_token": "a"}, {"id": "UCb", "refresh_token": "b"}], "default": "UCgone"}
    d = up.normalize(new)
    assert [a["id"] for a in d["accounts"]] == ["UCa", "UCb"] and d["default"] == "UCa"
    assert up.pick_account(d, "UCb")["refresh_token"] == "b"
    assert up.pick_account(d, None)["id"] == "UCa"
    with pytest.raises(SystemExit):
        up.pick_account(d, "UCnope")
    assert up.normalize({}) == {"accounts": [], "default": None}


def test_py_duplicate_guard_is_per_account(tmp_path, monkeypatch):
    pub = tmp_path / "_published.jsonl"
    pub.write_text("\n".join(json.dumps(r) for r in [
        {"id": "v1", "url": "u1", "account": "UCa"},
        {"id": "v2", "url": "u2"},                     # 예전 줄(채널 기록 없음) — 어느 채널로도 다시 올리지 않는다
    ]) + "\n", "utf-8")
    monkeypatch.setattr(up, "PUBLISHED", pub)
    assert up.already_published("v1", "UCa")["url"] == "u1"
    assert up.already_published("v1", "UCb") is None
    assert up.already_published("v1", None)["url"] == "u1"
    assert up.already_published("v2", "UCb")["url"] == "u2"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_node_migrates_file_and_hides_tokens(tmp_path):
    f = tmp_path / "youtube.json"
    f.write_text(json.dumps(OLD), "utf-8")
    js = """
import { createYoutube, normalize } from %s;
const yt = createYoutube({ file: process.argv[1] });
const st = yt.status();
console.log(JSON.stringify({ st, n: normalize({ refresh_token: "r" }) }));
""" % json.dumps((ROOT / "studio" / "youtube.mjs").as_uri())
    r = subprocess.run(["node", "--input-type=module", "-e", js, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    st = out["st"]
    assert st["connected"] and st["default"] == "UCold" and st["configured"]
    assert [a["id"] for a in st["accounts"]] == ["UCold"] and st["accounts"][0]["title"] == "옛 채널"
    assert st["accounts"][0]["thumb"].startswith("/api/youtube/avatar?id=UCold")
    assert "rt-old" not in r.stdout and "sec" not in json.dumps(st)          # 토큰 · 비밀은 화면으로 안 나간다
    assert out["n"]["accounts"][0]["id"] == "legacy" and out["n"]["default"] == "legacy"
    saved = json.loads(f.read_text("utf-8"))                                  # 읽을 때 새 모양으로 고쳐 썼다
    assert "refresh_token" not in saved and saved["accounts"][0]["refresh_token"] == "rt-old" and saved["default"] == "UCold"
    if os.name == "posix":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
