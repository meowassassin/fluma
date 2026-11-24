"""lint 가 허용하는 형태 화풍이 엔진 화풍 목록과 같다(새 화풍이 L39 에 막히지 않게)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _const(path, name):
    for n in ast.parse(path.read_text("utf-8")).body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets):
            return ast.literal_eval(n.value)
    raise AssertionError(f"{name} not in {path}")


def test_lint_form_styles_match_engine():
    assert _const(ROOT / "engine/checks/lint.py", "FORM_STYLES") == _const(ROOT / "engine/craft/form/__init__.py", "STYLES")
