"""형식에 들어가는 글 · 그라데이션을 DesignCraft 재료로 만든다"""
from __future__ import annotations


class Page:
    def __init__(self):
        self.st, self.sw = [], {}

    def add(self, cid, p):
        self.st.append({"id": cid, "params": p})
        return len(self.st) - 1

    def swatch(self, c):
        if c not in self.sw:
            self.sw[c] = f"c{c[1:]}"
            self.add("swatch.create", {"name": self.sw[c], "color": c})
        return self.sw[c]

    def style(self, name, font, fstyle, size, color="#2b2118", leading=None, **para):
        ch = {"fontFamily": font, "fontStyle": fstyle, "size": size, "fill": self.swatch(color)}
        if leading:
            ch["leading"] = {"kind": "points", "value": leading}
        self.add("style.paragraph.create", {"name": name, "para": {"hyphenate": False, **para}, "chars": ch})

    def text(self, rect, text, style):
        n = self.add("frame.create", {"rect": rect, "content": "text", "text": text})
        self.add("object.textFrameOptions", {"inset": 0, "verticalJustification": "top", "ids": [f"${n}.id"]})
        self.add("text.select", {"story": f"${n}.story", "anchor": 0, "focus": 1 << 20})
        self.add("style.paragraph.apply", {"name": style})
        return n


def page(mid, w, h, m) -> dict:
    p = Page()
    p.style("머리", m.get("font", "Song Myung"), "Regular", 92, align="center")
    p.style("본문", m.get("font", "Song Myung"), "Regular", 44, leading=74, align="leftJustified")
    p.text([300, 130, w - 300, 260], m.get("title", ""), "머리")
    p.text([300, 300, w - 300, 900], m.get("body", ""), "본문")
    return {"id": mid, "type": "craft", "app": "designcraft", "show": False, "new": {"width": w, "height": h, "units": "points", "margins": 0}, "steps": p.st, "export": {"format": "png", "size": [w, h]}}


def gradient(mid, w, h, stops) -> dict:
    p = Page()
    n = p.add("frame.create", {"rect": [0, 0, w, h], "content": "unassigned"})
    p.add("object.gradient", {"kind": "linear", "angle": 270, "stops": [{"location": a, "color": c} for a, c in stops], "ids": [f"${n}.id"]})
    return {"id": mid, "type": "craft", "app": "designcraft", "show": False, "new": {"width": w, "height": h, "units": "points", "margins": 0}, "steps": p.st, "export": {"format": "png", "size": [w, h]}}
