"""에이전트 허용 목록 — 깨지면 비대화 실행이 승인 대기 없이 멈춘다(2026-11-06: 구조 정리가 'scripts/*' 를 'engine/…' 로 망가뜨림)"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
SRC = (ROOT / "studio" / "agent.mjs").read_text("utf-8")


def _list(name: str) -> str:
    a = SRC.index(f"const {name} = [")
    return SRC[a:SRC.index("\n", a) if name == "WRITABLE" else SRC.index("// 키·인증", a)]


def test_bash_patterns_are_real_wildcards():
    pats = re.findall(r'"(Bash\([^"]*\))"', _list("TOOLS"))
    assert pats and any("engine/*" in p for p in pats)
    for p in pats:
        assert p.isascii(), f"ASCII 가 아닌 글자: {p}"
        assert p.endswith("*)"), f"와일드카드가 없다: {p}"


def test_no_secret_reading_shell_is_allowed():
    pats = re.findall(r'"(Bash[^"]*)"', _list("TOOLS"))
    assert "Bash" not in pats
    assert not any(re.match(r"Bash\((cat|curl|wget|sh|bash|env|grep|find|head|tail)\b", p) for p in pats)


def test_writable_paths_exist_in_this_layout():
    for p in re.findall(r'"([^"]+)"', _list("WRITABLE")):
        q = ROOT / p
        if p.startswith("data/"):
            assert p.split("/")[1] in {"storyboards", "shotplans", "compositions", "characters", "workspace", "research", "briefs"}, p
        else:
            assert q.exists(), p
