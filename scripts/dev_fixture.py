"""Minimal valid developer documents for the offline rehearsals: just enough to satisfy references/dev-documents.md (never real content)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import dev_documents as dd

SOURCES = [
    {"id": "SRC-001", "url": "https://example.org/a", "finding": "离线演练中的一条来源内容", "applies_to": "演练文档的结论"},
    {"id": "SRC-002", "url": "https://example.org/b", "finding": "离线演练中的另一条来源内容", "applies_to": "演练文档的表"},
]


def figure(caption: str) -> dict[str, Any]:
    return {"type": "figure", "kind": "layers", "caption": caption, "rows": [{"label": "使用端", "nodes": [{"name": "小程序", "note": "员工"}]}, {"label": "服务端", "nodes": [{"name": "后端", "note": "业务规则"}]}],
            "links": [{"after": 0, "label": "接口调用"}]}


def table(caption: str) -> dict[str, Any]:
    return {"type": "table", "caption": caption, "columns": ["项", "内容"], "rows": [["甲", "乙"]]}


def prototype(root: Path, title: str, name: str, kind: str = "phone") -> dict[str, Any]:
    """A prototype page that carries every marker the standard looks for (never a real prototype). ``kind`` phone names Vant, wide names Element Plus."""
    path = Path(root) / "raw" / "fixtures" / f"{name}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    marks = "@media (prefers-reduced-motion: reduce) {} dlg.showModal(); UI.demo({});"
    parts = ["button", "input", "table", "dialog", "tag", "card", "tabs", "switch"]
    classes = " ".join(f"{'van' if kind == 'phone' else 'el'}-{c}" for c in parts)     # the rehearsal names eight components of the library it declares
    path.write_text("<!doctype html><title>演练原型</title><script>" + marks + "</script><div class='" + classes + "'></div><!--" + "x" * 130_000 + "-->", encoding="utf-8")
    return {"type": "prototype", "file": f"raw/fixtures/{name}.html", "title": title, "kind": kind, "library": "vant" if kind == "phone" else "element-plus"}


def paths_blocks(prototypes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """前端规范 › 页面与路径 for the rehearsal: for each front end its prototype file, a navigation table and a page list with a 路径 column."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": "页面与路径的演练内容，只验证文档标准与门禁。"}]
    for title, proto in prototypes.items():
        blocks += [{"type": "sub", "text": title}, {"type": "text", "text": f"原型文件：`{proto['file']}`"},
                   {"type": "table", "caption": f"{title}的导航结构", "columns": ["菜单", "入口", "角色"], "rows": [["首页", "底部标签", "全部"]]},
                   {"type": "table", "caption": f"{title}的页面清单", "columns": ["路径", "页面", "作用"], "rows": [["/home", "首页", "演练页面"]]}]
    return blocks


def baseline_block(kind: str, scope: str, surfaces: Any = None) -> dict[str, Any]:
    """A baseline table that keeps every item (the rehearsal does not care what a project really chooses)."""
    import baseline as bl

    if kind == "module":
        ids = [m["id"] for m in bl.functions()["modules"]]
    else:
        ids = bl.mandatory_ids(kind, scope, surfaces)
    return {"type": "baseline", "kind": kind, "scope": scope, "caption": f"底座对照 {scope or '基础功能'}", "rows": [{"id": i, "status": "沿用"} for i in ids]}


def function_card(fid: str, module: str, name: str) -> dict[str, Any]:
    import baseline as bl

    text = "演练内容，只验证文档标准与门禁：写到页面、接口、表和数字才是真实的功能卡。" * 2
    return {"type": "function", "id": fid, "name": name, "system": "小程序", "module": module, "summary": "演练功能卡，验证标准", "frontend": text, "backend": text, "database": text, "tech": text,
            "rules": ["演练规则一条，条件与结果"], "exceptions": ["演练异常一条，界面提示"], "tests": ["演练测试一条"], "code": ["src/演练.java"], "deviation": [],
            "inherits": bl.function_items()[0]["id"], "status": "沿用"}


def sample_spec(stage: str, root: Path, frontends: list[tuple[str, str, str]] | None = None) -> dict[str, Any]:
    """``frontends`` (title, surface, prototype kind) overrides the front end tabs of a design document (default: one per surface of the project)."""
    import dev_documents as dd

    std = dd.STANDARDS[stage]
    ctx = dd.project_context(Path(root))

    def blocks_for(title: str, req: dict[str, Any]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [{"type": "text", "text": f"{title}的演练内容，只验证文档标准与门禁。"}]
        if req.get("baseline"):
            blocks.append(baseline_block(*req["baseline"], surfaces=ctx["surfaces"] if ctx else None))
        for n in range(req.get("tables", 0)):
            blocks.append(table(f"{title}表{n + 1}"))
        for n in range(req.get("figures", 0)):
            blocks.append(figure(f"{title}图{n + 1}"))
        return blocks

    if "tabs" in std:
        tabs = []
        want = dd.expected_tabs(stage, ctx)
        if frontends:
            mids = [{"title": n, "layout": "frontend", "frontend": True, "surface": sf, "kind": k} for n, sf, k in frontends]
            want = [x for t in want for x in (mids if t.get("frontend") else [t])]
        prototypes = {t["title"]: prototype(Path(root), f"{t['title']}原型", f"proto{n}", t.get("kind") or dd.UI_SURFACES[t["surface"]][1]) for n, t in enumerate((t for t in want if t.get("frontend")), 1)}
        for tab in want:
            if tab.get("frontend"):
                tabs.append({"title": tab["title"], "layout": tab["layout"], "surface": tab["surface"], "sections": [{"title": tab["title"], "blocks": [prototypes[tab["title"]]]}]})
                continue
            if tab.get("dynamic") == "modules":
                mods = [(str(m["id"]), str(m["name"])) for m in ctx["modules"]] if ctx and ctx["modules"] else [("M01", "模块甲"), ("M02", "模块乙")]
                sections = []
                for mid, mname in mods:
                    blocks = blocks_for(mname, {"tables": tab.get("module_tables", 0)})
                    if tab.get("functions"):
                        feats = [f for f in ctx["features"] if str(f["module"]) == mid] if ctx and ctx["features"] else [{"id": f"FN-{len(sections) + 1:03d}", "name": "演练功能"}]
                        blocks += [function_card(f["id"], mname, f["name"]) for f in feats]
                    sections.append({"title": mname, "blocks": blocks})
            else:
                sections = [{"title": s["title"], "blocks": paths_blocks(prototypes) if s.get("paths") else blocks_for(s["title"], s)} for s in tab["sections"]]
            tabs.append({"title": tab["title"], "layout": tab["layout"], "sections": sections})
        spec: dict[str, Any] = {"title": f"{stage} 离线演练", "conclusion": "只验证路由、门禁和文档标准，不构成真实的开发文档，也不是产品验收。", "tabs": tabs, "sources": SOURCES}
        have = sum(1 for t in tabs for sec in t["sections"] for b in sec["blocks"] if b["type"] in ("figure", "image"))
        for n in range(max(0, std.get("min_figures", 0) - have)):
            tabs[0]["sections"][0]["blocks"].append(figure(f"补充图{n + 1}"))
        return spec
    sections = []
    for title in std["sections"]:
        sections.append({"title": title, "blocks": blocks_for(title, {"tables": std.get("tables", {}).get(title, 0), "figures": std.get("figures", {}).get(title, 0)})})
    return {"title": f"{stage} 离线演练", "conclusion": "只验证路由、门禁和文档标准，不构成真实的开发文档，也不是产品验收。", "sections": sections, "sources": SOURCES}
