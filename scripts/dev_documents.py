"""The developer documents of a project: 系统架构, 前端界面设计, 后端设计规范, 实现报告.

One standard (references/dev-documents.md), one validator and one HTML renderer for all four, so that every project's documents have the
same chapters, the same kinds of tables and figures, and name their sources. A document is a JSON spec::

    {"title": …, "conclusion": …, "sections": [{"title": …, "blocks": [block, …]}, …], "sources": [{"id", "url", "finding", "applies_to"}]}

Blocks: ``text``, ``sub`` (a sub heading), ``bullets``, ``table`` (caption, columns, rows, widths), ``figure`` (kind layers | steps |
sequence | grid, caption), ``image`` (file, alt, caption; not in the design document), ``prototype`` (file, title, kind phone | wide, library; an interactive
page built into the document as a frame, only in a front end tab), ``code``, ``note``. The page is typeset by Luz-Design (formal reading page).

The design document (前端界面设计) is 前端规范 + one tab per front end or device + 检查与差异. A front end tab is declared by the spec::

    {"title": "手机页", "layout": "frontend", "surface": "web-admin", "sections": [{"title": "手机页", "blocks": [{"type": "prototype", …}]}]}

``title`` is the name of the front end, ``surface`` the kind of use (a key of UI_SURFACES) it belongs to; the tab holds that one prototype and nothing
else (no screenshot, no caption, no table). Every path (prototype files, navigation, page list with routes) is in 前端规范 › 页面与路径.
"""
from __future__ import annotations

import base64
import html
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import baseline as bl
import dev_tabs
from project_paths import ProjectError, locate


def project_file(root: Path | str, rel: str) -> Path:
    """The absolute path of a project-relative file (docs/... in the project directory, the rest in the state root); a plain directory without
    project.json (the offline rehearsals) is read as one root."""
    try:
        return locate(root, rel)
    except ProjectError:
        return Path(root) / rel

# --- the standard ----------------------------------------------------------------------------------------------------

PATHS_TITLE = "页面与路径"          # the one sub tab of 前端规范 that is not a baseline category: every path of every front end is written here
SPEC_TAB, CHECK_TAB = "前端规范", "检查与差异"
# The kinds of use that have a screen -> (default tab name, prototype kind). A project needs a front end tab for each of them it has functions for.
UI_SURFACES = {"miniprogram": ("小程序", "phone"), "web-admin": ("管理后台", "wide"), "agent": ("智能体", "wide"), "website": ("官方网站", "wide"), "mobile-app": ("移动应用", "phone")}
LEGACY_TAB_SURFACE = {"小程序": "miniprogram", "管理后台": "web-admin"}       # the tab names of the older standard: a spec that does not write surface keeps working


def _std_tabs() -> dict[str, dict[str, Any]]:
    stack = [{"title": "技术栈总览", "figures": 1, "tables": 1}] + [{"title": name, "baseline": ("stack", lid)} for lid, name in bl.STACK_LAYERS.items()]
    frontend = [{"title": name, "baseline": ("frontend", cid)} for cid, name in bl.FRONTEND_CATEGORIES.items()]
    return {
        "architecture": {"tabs": [
            {"title": "技术栈", "layout": "subtabs", "sections": stack},
            {"title": "总体架构", "layout": "sections", "sections": [{"title": "系统上下文", "figures": 1, "tables": 1}, {"title": "分层与部署", "figures": 1, "tables": 1},
                                                                  {"title": "业务模块", "tables": 1}, {"title": "关键技术方案", "figures": 1}]},
            {"title": "功能与技术方案", "layout": "subtabs", "dynamic": "modules", "functions": True},
            {"title": "决策与质量", "layout": "sections", "sections": [{"title": "架构决策", "tables": 1}, {"title": "质量属性", "tables": 1}, {"title": "演进与扩展"}, {"title": "已知限制"}]},
        ], "min_figures": 3},
        "design": {"tabs": [
            {"title": "前端规范", "layout": "subtabs", "sections": frontend + [{"title": PATHS_TITLE, "paths": True}]},
            {"title": "前端名称", "frontend": True, "layout": "frontend"},       # the template of the front end tabs: expected_tabs() puts one tab per front end here
            {"title": "检查与差异", "layout": "sections", "no_screenshots": True, "sections": [{"title": "原型与真实系统的差异"}, {"title": "界面检查", "tables": 1}]},
        ]},
        "technical-plan": {"tabs": [
            {"title": "技术架构", "layout": "sections", "sections": [{"title": "工程结构与分层", "tables": 1}, {"title": "编码与数据约定", "tables": 2}]},
            {"title": "功能与业务逻辑", "layout": "subtabs", "dynamic": "modules", "module_tables": 2},
            {"title": "接口", "layout": "sections", "sections": [{"title": "接口规范", "tables": 3}, {"title": "接口清单", "tables": 5}]},
            {"title": "数据库", "layout": "sections", "sections": [{"title": "数据库设计", "figures": 1, "tables": 4}]},
            {"title": "安全与运维", "layout": "sections", "sections": [{"title": "安全与权限", "tables": 1}, {"title": "配置与部署", "tables": 1}, {"title": "日志与审计", "tables": 1}, {"title": "测试规范", "tables": 1}]},
            {"title": "底座对照与偏差", "layout": "sections", "sections": [{"title": "基础功能采用情况", "baseline": ("module", "")}, {"title": "规范偏差与待办", "tables": 1}]},
        ], "min_figures": 2},
    }


STANDARDS: dict[str, dict[str, Any]] = {
    **_std_tabs(),
    "implementation": {
        "sections": ["实现范围", "功能对照", "测试结果", "未完成与风险"],
        "tables": {"功能对照": 1, "测试结果": 1, "未完成与风险": 1},
        "min_figures": 0,
    },
}

PLACEHOLDER = re.compile(r"待补充|待填写|TODO|TBD|lorem ipsum|XXX|示例文字|（略）|占位文字|占位内容|此处占位", re.I)
BLOCKS = {"text", "sub", "bullets", "table", "figure", "image", "code", "note", "prototype", "baseline", "function"}
FIGURES = {"layers", "steps", "sequence", "grid"}


def has_standard(stage: str) -> bool:
    return stage in STANDARDS


def _blocks(section: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in section.get("blocks", []) if isinstance(b, dict)]


def frontend_surface(tab: dict[str, Any]) -> str:
    """The kind of use a front end tab belongs to: written in the spec (``surface``), else inferred from the two classic tab names."""
    return str(tab.get("surface") or LEGACY_TAB_SURFACE.get(str(tab.get("title", ""))) or "")


def frontend_tabs(ctx: dict[str, Any] | None, spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The front end tabs of a design document: those its spec declares (the tabs between 前端规范 and 检查与差异), and for a document that is
    only being started one per kind of use of the project (a mini program and a web admin when the project has no function list yet)."""
    tabs = spec.get("tabs") if isinstance(spec, dict) else None
    if isinstance(tabs, list) and len(tabs) > 2:
        return [{"title": str(t.get("title", "")), "layout": "frontend", "frontend": True, "surface": frontend_surface(t)} for t in tabs[1:-1] if isinstance(t, dict)]
    have = [s for s in UI_SURFACES if ctx and s in ctx["surfaces"]] or ["miniprogram", "web-admin"]
    return [{"title": UI_SURFACES[s][0], "layout": "frontend", "frontend": True, "surface": s} for s in have]


def project_context(root: Path | None) -> dict[str, Any] | None:
    """Modules, functions and surfaces of the project from its client function list (None when there is none: offline rehearsals)."""
    if root is None:
        return None
    path = Path(root) / "data" / "client" / "features.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    # A function the change ledger removed (status removed) keeps its number but is no longer part of the project: no card, no module of its own, no use of its surface.
    features = [f for f in data.get("features", []) if f.get("status", "in-scope") != "removed"]
    used = {str(f.get("module")) for f in features}
    modules = [m for m in data.get("modules", []) if not features or str(m.get("id")) in used]
    return {"modules": modules, "features": features, "surfaces": {f.get("surface") for f in features if f.get("surface")}}


def expected_tabs(stage: str, ctx: dict[str, Any] | None, spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The tabs a document of this stage must have: in the design document one tab per front end (the ones ``spec`` declares, see frontend_tabs),
    and in the stack tab only the layers of the front ends the project has (no 小程序前端 layer for a project without a mini program)."""
    tabs = [x for t in STANDARDS[stage]["tabs"] for x in (frontend_tabs(ctx, spec) if t.get("frontend") else [t])]
    if ctx is None or not ctx["surfaces"]:
        return tabs
    return [dict(t, sections=[s for s in t["sections"] if not (s.get("baseline") and s["baseline"][0] == "stack" and not bl.layer_applies(s["baseline"][1], ctx["surfaces"]))])
            if t.get("layout") == "subtabs" and "sections" in t else t for t in tabs]


def surfaces_of(root: Path | None) -> set[str] | None:
    """The front ends of the project from its function list; None when it has none yet (every baseline item then applies)."""
    ctx = project_context(root)
    return ctx["surfaces"] or None if ctx else None


def validate(stage: str, spec: dict[str, Any], root: Path | None = None) -> list[str]:
    """Every rule of references/dev-documents.md that a machine can check."""
    std = STANDARDS[stage]
    errors: list[str] = []
    if not str(spec.get("title", "")).strip():
        errors.append("缺少文档标题")
    if len(str(spec.get("conclusion", "")).strip()) < 30:
        errors.append("结论至少一两句话，说清这份文档的结论，不能只有标题")
    figures = 0
    if "tabs" in std:
        tab_errors, figures = _tab_errors(stage, std, spec, root)
        errors += tab_errors
    else:
        sections = spec.get("sections")
        if not isinstance(sections, list):
            return errors + ["缺少 sections"]
        titles = [str(s.get("title", "")) for s in sections if isinstance(s, dict)]
        if titles != std["sections"]:
            errors.append(f"章节必须依次是：{'、'.join(std['sections'])}；现在是：{'、'.join(titles) or '无'}")
        for section in sections:
            if isinstance(section, dict):
                req = {"tables": std.get("tables", {}).get(section.get("title"), 0), "figures": std.get("figures", {}).get(section.get("title"), 0)}
                e, n = _section_errors(section, req, root)
                errors += e
                figures += n
    if "tabs" in std:
        errors += _statement_errors(spec, root)
    if figures < std.get("min_figures", 0):
        errors.append(f"全文至少 {std['min_figures']} 张图，现在 {figures} 张")
    sources = spec.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        errors.append("来源与依据至少 2 条：每条来自 Luz-Crawl 前置检索，写明来源编号、网址、读到了什么、用在哪里或为什么没用")
    else:
        for s in sources:
            if not isinstance(s, dict) or any(not str(s.get(k, "")).strip() for k in ("id", "url", "finding", "applies_to")):
                errors.append("来源与依据每条都要有 id、url、finding、applies_to")
                break
    return list(dict.fromkeys(errors))


def _statement_errors(spec: dict[str, Any], root: Path | None) -> list[str]:
    """The project's own statement (data/baseline.json) is valid, and the baseline tables of the document say what it says."""
    path = Path(root) / "data" / "baseline.json" if root is not None else None
    if path is None or not path.is_file():
        return []
    statement = json.loads(path.read_text(encoding="utf-8-sig"))
    errors = [f"data/baseline.json：{e}" for e in bl.project_baseline_errors(statement, surfaces_of(root))]
    key = {"stack": "stack", "frontend": "frontend", "module": "modules"}
    for tab in spec.get("tabs", []):
        for section in tab.get("sections", []) if isinstance(tab, dict) else []:
            for b in _blocks(section) if isinstance(section, dict) else []:
                if b.get("type") != "baseline" or b.get("kind") not in key:
                    continue
                have = statement.get(key[b["kind"]], {})
                for r in b.get("rows", []):
                    iid = str(r.get("id", ""))
                    if iid.startswith("X-") or iid not in have:
                        continue
                    if have[iid].get("status") != r.get("status"):
                        errors.append(f"文档里 {iid} 的状态是{r.get('status')}，data/baseline.json 里是{have[iid].get('status')}，两处要一致")
    return errors


def _section_errors(section: dict[str, Any], req: dict[str, Any], root: Path | None) -> tuple[list[str], int]:
    """One section: its blocks are known and well formed, and it has the tables and figures the standard asks for. Returns the errors and its number of figures."""
    errors: list[str] = []
    name = str(section.get("title", ""))
    blocks = _blocks(section)
    if not blocks:
        errors.append(f"章节「{name}」没有内容")
    counts = {"table": 0, "figure": 0, "image": 0, "prototype": 0}
    for b in blocks:
        kind = b.get("type")
        if kind not in BLOCKS:
            errors.append(f"章节「{name}」有未知块类型: {kind}")
            continue
        if kind in counts:
            counts[kind] += 1
        if kind == "baseline":
            counts["table"] += 1
        errors.extend(_block_errors(name, b, root))
    for want, label in (("tables", "table"), ("figures", "figure")):
        if counts[label] < req.get(want, 0):
            errors.append(f"章节「{name}」至少要有 {req[want]} 个{ {'table': '表', 'figure': '图'}[label] }，现在只有 {counts[label]} 个")
    return errors, counts["figure"] + counts["image"]


def _baseline_scope(section: dict[str, Any], want: tuple[str, str]) -> list[str]:
    """The baseline blocks of a section must cover its scope: every mandatory item of the layer or category, or every baseline module."""
    kind, scope = want
    errors: list[str] = []
    blocks = [b for b in _blocks(section) if b.get("type") == "baseline" and b.get("kind") == kind]
    name = section.get("title")
    if not blocks:
        return [f"章节「{name}」要有一张底座对照表（kind={kind}）"]
    if kind != "module":
        covered = {r.get("id") for b in blocks for r in b.get("rows", []) if isinstance(r, dict)}
        if not any(str(b.get("scope", "")) == scope for b in blocks):
            errors.append(f"章节「{name}」的底座对照表 scope 必须是 {scope}")
        extra = {r.get("id") for b in blocks for r in b.get("rows", []) if isinstance(r, dict) and not str(r.get("id", "")).startswith("X-")} - covered
        errors += [f"章节「{name}」的底座对照表多出 {i}" for i in sorted(extra)]
    return errors


def _tab_errors(stage: str, std: dict[str, Any], spec: dict[str, Any], root: Path | None) -> tuple[list[str], int]:
    errors: list[str] = []
    ctx = project_context(root)
    tabs = spec.get("tabs")
    if not isinstance(tabs, list):
        return ["缺少 tabs（顶部标签页）"], 0
    if stage == "design":
        errors = _design_frame_errors(tabs, ctx)
        if errors:
            return errors, 0
    want_tabs = expected_tabs(stage, ctx, spec)
    got = [str(t.get("title", "")) for t in tabs if isinstance(t, dict)]
    if got != [t["title"] for t in want_tabs]:
        errors.append(f"标签页必须依次是：{'、'.join(t['title'] for t in want_tabs)}；现在是：{'、'.join(got) or '无'}")
        return errors, 0
    figures = 0
    frontends = [t for t in tabs[1:-1] if isinstance(t, dict)] if stage == "design" else []
    files_seen: dict[str, str] = {}
    for tab, want in zip(tabs, want_tabs):
        if tab.get("layout") != want["layout"]:
            errors.append(f"标签页「{want['title']}」的 layout 必须是 {want['layout']}")
        sections = tab.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append(f"标签页「{want['title']}」没有内容")
            continue
        titles = [str(s.get("title", "")) for s in sections if isinstance(s, dict)]
        if want.get("frontend"):
            errors += _frontend_tab_errors(tab, root, files_seen)
            continue
        if stage == "design":
            for kind, why in (("image", "有截图（image 块）：前端界面设计不放截图，界面以可交互原型为准"), ("prototype", "有原型：原型只放在各自的前端页签里")):
                if any(b.get("type") == kind for s in sections if isinstance(s, dict) for b in _blocks(s)):
                    errors.append(f"标签页「{want['title']}」里{why}")
        if want.get("dynamic") == "modules":
            if ctx is not None and ctx["modules"]:
                need = [str(m["name"]) for m in ctx["modules"]]
                if titles != need:
                    errors.append(f"标签页「{want['title']}」的子标签必须依次是 features.json 的模块：{'、'.join(need)}；现在是：{'、'.join(titles)}")
            for section in sections:
                req = {"tables": want.get("module_tables", 0)}
                e, n = _section_errors(section, req, root)
                errors += e
                figures += n
                if want.get("functions") and not any(b.get("type") == "function" for b in _blocks(section)):
                    errors.append(f"子标签「{section.get('title')}」至少要有一张功能卡")
            if want.get("functions"):
                errors += _function_coverage(tabs, want, ctx)
            continue
        if titles != [s["title"] for s in want["sections"]]:
            errors.append(f"标签页「{want['title']}」的章节必须依次是：{'、'.join(s['title'] for s in want['sections'])}；现在是：{'、'.join(titles)}")
            continue
        for section, sw in zip(sections, want["sections"]):
            req = {k: sw.get(k, 0) for k in ("tables", "figures")}
            e, n = _section_errors(section, req, root)
            errors += e
            figures += n
            if sw.get("baseline"):
                errors += _baseline_scope(section, sw["baseline"])
            if sw.get("paths"):
                errors += _paths_errors(section, frontends)
        if want.get("no_screenshots") and any("截图" in t for s in sections if isinstance(s, dict) for t in _texts(s)):
            errors.append(f"标签页「{want['title']}」里不再写截图：原型就是真实界面，差异只写原型与真实系统在数据、接口、行为上的不同")
    return errors, figures


# --- the front end tabs of the design document -------------------------------------------------------------------------

KIND_LABEL = {"image": "截图", "table": "表", "figure": "图", "text": "说明文字", "sub": "说明文字", "bullets": "说明文字", "note": "说明文字", "code": "说明文字",
              "baseline": "底座对照表", "function": "功能卡"}


def _texts(section: dict[str, Any]) -> list[str]:
    """Every string a reader sees in a section: text, items, table captions, headers and cells."""
    out: list[str] = []
    for b in _blocks(section):
        out += [str(b.get(k, "")) for k in ("text", "caption")]
        if isinstance(b.get("items"), list):
            out += [str(i) for i in b["items"]]
        if isinstance(b.get("columns"), list):
            out += [str(c) for c in b["columns"]]
        if isinstance(b.get("rows"), list):
            out += [str(c) for r in b["rows"] if isinstance(r, list) for c in r]
    return out


def _prototypes(tab: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for s in tab.get("sections", []) if isinstance(s, dict) for b in _blocks(s) if b.get("type") == "prototype"]


def _design_frame_errors(tabs: list[Any], ctx: dict[str, Any] | None) -> list[str]:
    """The frame of the design document: 前端规范, then one tab per front end or device, then 检查与差异; every kind of use of the project has a tab."""
    got = [str(t.get("title", "")) if isinstance(t, dict) else "" for t in tabs]
    if len(got) < 3 or got[0] != SPEC_TAB or got[-1] != CHECK_TAB:
        return [f"标签页必须依次是：{SPEC_TAB}、每个系统或设备端一个页签（页签名是前端名称，如手机页、管理后台、小程序）、{CHECK_TAB}；现在是：{'、'.join(got) or '无'}"]
    errors: list[str] = []
    if len(set(got)) != len(got) or "" in got:
        errors.append(f"页签名不能重复或为空：{'、'.join(got)}")
    labels = "、".join(UI_SURFACES)
    covered: set[str] = set()
    for tab in (t for t in tabs[1:-1] if isinstance(t, dict)):
        name, surface = str(tab.get("title", "")), frontend_surface(tab)
        if not surface:
            errors.append(f"前端页签「{name}」要写 surface：它属于功能清单里的哪种使用端（{labels}）；手机页和后台可以同为 web-admin")
        elif surface not in UI_SURFACES:
            errors.append(f"前端页签「{name}」的 surface 无效: {surface}（可选 {labels}）")
        elif ctx is not None and ctx["surfaces"] and surface not in ctx["surfaces"]:
            errors.append(f"前端页签「{name}」属于 {surface}，功能清单里没有这种使用端的功能，不出这个页签")
        covered.add(surface)
    if ctx is not None:
        for surface in UI_SURFACES:
            if surface in ctx["surfaces"] and surface not in covered:
                errors.append(f"功能清单有 {surface} 的功能，要有一个对应的前端页签（如“{UI_SURFACES[surface][0]}”，surface 写 {surface}）")
    return errors


def _frontend_tab_errors(tab: dict[str, Any], root: Path | None, files_seen: dict[str, str]) -> list[str]:
    """A front end tab holds one interactive prototype and nothing else: no screenshot, caption, source, page list or navigation table (those paths
    are in 前端规范 › 页面与路径)."""
    name = str(tab.get("title", ""))
    sections = [s for s in tab.get("sections", []) if isinstance(s, dict)]
    blocks = [b for s in sections for b in _blocks(s)]
    protos = [b for b in blocks if b.get("type") == "prototype"]
    errors: list[str] = []
    if len(sections) != 1:
        errors.append(f"前端页签「{name}」只有一个章节，章节里只放一个可交互原型")
    other = list(dict.fromkeys(KIND_LABEL.get(str(b.get("type")), str(b.get("type"))) for b in blocks if b.get("type") != "prototype"))
    if other:
        errors.append(f"前端页签「{name}」里只放一个可交互原型，不放{'、'.join(other)}：路径、导航结构和页面清单写进“{SPEC_TAB}”的“{PATHS_TITLE}”")
    if not protos:
        return errors + [f"前端页签「{name}」缺少可交互原型（prototype 块）"]
    if len(protos) > 1:
        errors.append(f"前端页签「{name}」有 {len(protos)} 个原型：一个页签只放一个，手机页、电脑页、小程序等不同设备端各开一个页签")
    for b in protos:
        for key in ("caption", "try", "source", "sources"):
            if key in b:
                errors.append(f"前端页签「{name}」的原型不写 {key}：页签里只显示原型本身，不放图题、操作说明和来源")
        if frontend_surface(tab) == "miniprogram" and b.get("kind") != "phone":
            errors.append(f"前端页签「{name}」是小程序，原型 kind 只能是 phone")
        file = str(b.get("file", ""))
        if file in files_seen:
            errors.append(f"前端页签「{name}」与「{files_seen[file]}」用了同一个原型文件 {file}：每个前端各有自己的原型")
        files_seen.setdefault(file, name)
    errors += _section_errors({"title": name, "blocks": protos}, {}, root)[0]
    return errors


def _paths_errors(section: dict[str, Any], frontends: list[dict[str, Any]]) -> list[str]:
    """前端规范 › 页面与路径: for each front end a part (a ``sub`` block with its name) with the path of its prototype file, a navigation table and
    a page list table that has a 路径 column."""
    blocks = _blocks(section)
    starts = {str(b.get("text", "")).strip(): i for i, b in enumerate(blocks) if b.get("type") == "sub"}
    marks = sorted(starts[t] for t in (str(f.get("title", "")) for f in frontends) if t in starts)
    errors: list[str] = []
    for tab in frontends:
        title = str(tab.get("title", ""))
        if title not in starts:
            errors.append(f"「{PATHS_TITLE}」要有一节「{title}」（sub 块，文字是前端名称），写它的原型文件路径、导航结构表和页面清单表")
            continue
        i = starts[title]
        part = {"blocks": blocks[i + 1:next((m for m in marks if m > i), len(blocks))]}
        tables = [b for b in part["blocks"] if b.get("type") == "table"]
        if len(tables) < 2:
            errors.append(f"「{PATHS_TITLE}」的「{title}」一节至少要有 2 张表：导航结构（菜单、入口、角色）和页面清单（路径、页面、作用），现在 {len(tables)} 张")
        elif not any("路径" in str(c) for t in tables if isinstance(t.get("columns"), list) for c in t["columns"]):
            errors.append(f"「{PATHS_TITLE}」的「{title}」一节的页面清单要有“路径”列（路由路径）")
        text = "\n".join(_texts(part))
        for proto in _prototypes(tab):
            if str(proto.get("file", "")) not in text:
                errors.append(f"「{PATHS_TITLE}」的「{title}」一节没有写原型文件路径：{proto.get('file')}")
    return errors


def _function_coverage(tabs: list[dict[str, Any]], want: dict[str, Any], ctx: dict[str, Any] | None) -> list[str]:
    """Every function of features.json has exactly one card, in the sub tab of its module."""
    if ctx is None or not ctx["features"]:
        return []
    errors: list[str] = []
    tab = next(t for t in tabs if t.get("title") == want["title"])
    modules = {str(m["id"]): str(m["name"]) for m in ctx["modules"]}
    seen: dict[str, str] = {}
    for section in tab.get("sections", []):
        for b in _blocks(section):
            if b.get("type") == "function":
                if b["id"] in seen:
                    errors.append(f"功能卡 {b['id']} 出现了两次")
                seen[b["id"]] = str(section.get("title"))
    for f in ctx["features"]:
        if f["id"] not in seen:
            errors.append(f"功能 {f['id']}（{f['name']}）没有功能卡")
        elif seen[f["id"]] != modules.get(str(f["module"])):
            errors.append(f"功能卡 {f['id']} 放在了子标签「{seen[f['id']]}」，它属于模块「{modules.get(str(f['module']))}」")
    errors += [f"功能卡 {i} 不在 features.json 里" for i in sorted(set(seen) - {f["id"] for f in ctx["features"]})]
    return errors


def _block_errors(section: str, b: dict[str, Any], root: Path | None) -> list[str]:
    where = f"章节「{section}」"
    kind = b["type"]
    out: list[str] = []
    texts: list[str] = []
    if kind in {"text", "sub", "note", "code"}:
        if not str(b.get("text", "")).strip():
            out.append(f"{where}有空的 {kind} 块")
        texts.append(str(b.get("text", "")))
    elif kind == "bullets":
        items = b.get("items")
        if not isinstance(items, list) or not items or any(not str(i).strip() for i in items):
            out.append(f"{where}的列表为空或有空项")
        else:
            texts.extend(map(str, items))
    elif kind == "table":
        cols, rows = b.get("columns"), b.get("rows")
        if not str(b.get("caption", "")).strip():
            out.append(f"{where}有没有表题的表")
        if not isinstance(cols, list) or not cols or not isinstance(rows, list) or not rows:
            out.append(f"{where}的表「{b.get('caption', '')}」缺表头或没有行")
        else:
            for r in rows:
                if not isinstance(r, list) or len(r) != len(cols):
                    out.append(f"{where}的表「{b.get('caption', '')}」有列数与表头不符的行")
                    break
                if any(str(c).strip() == "" for c in r):
                    out.append(f"{where}的表「{b.get('caption', '')}」有空单元格（没有内容写“—”）")
                    break
            texts.extend(str(c) for r in rows if isinstance(r, list) for c in r)
    elif kind == "figure":
        if not str(b.get("caption", "")).strip():
            out.append(f"{where}有没有图题的图")
        if b.get("kind") not in FIGURES:
            out.append(f"{where}的图类型无效: {b.get('kind')}")
        else:
            out.extend(_figure_errors(where, b))
    elif kind == "baseline":
        out.extend(dev_tabs.baseline_block_errors(where, b, surfaces_of(root)))
    elif kind == "function":
        out.extend(dev_tabs.function_block_errors(where, b))
    elif kind == "prototype":
        out.extend(_prototype_errors(where, b, root))
    elif kind == "image":
        if len(str(b.get("alt", "")).strip()) < 4 or not str(b.get("caption", "")).strip():
            out.append(f"{where}的截图要写替代文字（至少 4 个字）和图题")
        file = b.get("file")
        if not file or (root is not None and not project_file(root, str(file)).is_file()):
            out.append(f"{where}的截图文件不存在: {file}")
    for t in texts:
        if PLACEHOLDER.search(t):
            out.append(f"{where}含占位或待办字样：{t[:24]}")
            break
    return out


# What a prototype page must carry for the 前端界面设计 standard: a reduced-motion branch, dialogs with a role, a configuration panel. The checks
# read the built file, so a stub or a static mock-up does not pass.
PROTOTYPE_MARKERS = {
    "没有“减少动态效果”分支": ("prefers-reduced-motion",),
    "没有对话框（原生 dialog 或带 role=dialog 的容器）": ("showModal", "role: 'dialog'"),
    "没有场景配置面板": ("UI.demo(", "K.panel("),
}
PROTOTYPE_MIN_BYTES = 120_000
PROTOTYPE_MIN_COMPONENTS = 6          # different components of the chosen library that the built file names (references/component-libraries.json)
SURFACE_OF_KIND = {"phone": {"miniapp", "h5"}, "wide": {"admin", "website"}}


def component_libraries() -> dict[str, Any]:
    """The component library registry of Luz-Design: id -> name, stack, surfaces, class prefixes, theme mechanism, docs."""
    path = Path(__file__).resolve().parents[2] / "Luz-Design" / "references" / "component-libraries.json"
    return json.loads(path.read_text(encoding="utf-8"))["libraries"]


def library_components(text: str, prefixes: list[str]) -> set[str]:
    """The distinct components of a library that a built file names: class names (``el-button``) and custom elements (``<t-button>``) with
    the library's prefix, modifiers (``__``, ``--``) cut off."""
    found: set[str] = set()
    for prefix in prefixes:
        for m in re.finditer(r"(?<![\w-])(" + re.escape(prefix) + r"[a-z0-9]+(?:-[a-z0-9]+)*)", text):
            found.add(m.group(1))
    return found


def _prototype_errors(where: str, b: dict[str, Any], root: Path | None) -> list[str]:
    out: list[str] = []
    name = str(b.get("title", "")).strip() or "原型"
    if not str(b.get("title", "")).strip():
        out.append(f"{where}的原型要写标题（显示在原型框的顶栏）")
    if b.get("kind", "wide") not in {"phone", "wide"}:
        out.append(f"{where}的原型 kind 只能是 phone 或 wide")
    libs = component_libraries()
    lib = libs.get(str(b.get("library", "")))
    if lib is None and not str(b.get("library", "")).strip():
        out.append(f"{where}的原型「{name}」要写 library：所用组件库的编号（{'、'.join(libs)}）；控件一律来自这个库的真实组件，不手写自造控件")
    elif lib is None:
        out.append(f"{where}的原型「{name}」的 library「{b.get('library')}」不在组件库注册表里（{'、'.join(libs)}）：先在 Luz-Design 的 component-libraries.json 登记，再使用")
    elif not (set(lib["surfaces"]) & SURFACE_OF_KIND.get(b.get("kind", "wide"), set())):
        out.append(f"{where}的原型「{name}」是 {b.get('kind', 'wide')} 端，组件库 {lib['name']} 适用于 {'、'.join(lib['surfaces'])}，换一个适合这一端的库")
    file = b.get("file")
    if not file or not str(file).endswith(".html"):
        return out + [f"{where}的原型「{name}」缺少 html 文件"]
    if root is not None:
        path = project_file(root, str(file))
        if not path.is_file():
            return out + [f"{where}的原型文件不存在: {file}"]
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text.encode("utf-8")) < PROTOTYPE_MIN_BYTES:
            out.append(f"{where}的原型「{name}」只有框架没有内容（文件小于 {PROTOTYPE_MIN_BYTES // 1000} KB）")
        for why, options in PROTOTYPE_MARKERS.items():
            if not any(o in text for o in options):
                out.append(f"{where}的原型「{name}」{why}")
        if lib is not None:
            used = library_components(text, lib["prefix"])
            if len(used) < PROTOTYPE_MIN_COMPONENTS:
                out.append(f"{where}的原型「{name}」里只有 {len(used)} 种 {lib['name']} 的组件（至少 {PROTOTYPE_MIN_COMPONENTS} 种）：按钮、表单、表格、对话框等控件要用库的真实组件，"
                           "不能只引入样式再手写控件；构建后用 audit_rendered.py --library 在真实浏览器里逐页核对")
    return out


def _figure_errors(where: str, b: dict[str, Any]) -> list[str]:
    kind = b["kind"]
    if kind == "layers":
        rows = b.get("rows")
        if not isinstance(rows, list) or len(rows) < 2 or any(not r.get("nodes") for r in rows):
            return [f"{where}的分层图至少两层，每层至少一个节点"]
    elif kind == "steps":
        if not isinstance(b.get("steps"), list) or len(b["steps"]) < 2:
            return [f"{where}的步骤图至少两步"]
    elif kind == "sequence":
        actors, msgs = b.get("actors"), b.get("messages")
        if not isinstance(actors, list) or len(actors) < 2 or not isinstance(msgs, list) or not msgs:
            return [f"{where}的时序图要有至少两个角色和一条消息"]
        for m in msgs:
            if not (0 <= m.get("from", -1) < len(actors) and 0 <= m.get("to", -1) < len(actors)) or not str(m.get("label", "")).strip():
                return [f"{where}的时序图消息引用了不存在的角色或没有文字"]
    elif kind == "grid":
        ids = {n.get("id") for n in b.get("nodes", [])}
        if len(ids) < 2 or any(l.get("from") not in ids or l.get("to") not in ids or not str(l.get("label", "")).strip() for l in b.get("links", [])):
            return [f"{where}的关系图要有至少两个节点，每条线引用存在的节点并写明关系"]
    return []


# --- rendering -------------------------------------------------------------------------------------------------------

E = html.escape
CSS = """<style>
.tcap{margin:20px 0 6px;color:var(--ink)}
figure.fig,figure.shot{margin:18px 0}
figure.fig svg{width:100%;height:auto;display:block}
figure.shot img{display:block;max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px}
figure.shots{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}
figure.shots figure.shot{margin:0}
figure.shot.phone{width:300px;max-width:100%}
figure.shot.wide{width:100%}
pre.code{white-space:pre-wrap;overflow-wrap:anywhere}
.fg-node{fill:var(--tint1);stroke:var(--line);stroke-width:1.5}
.fg-band{fill:none;stroke:var(--line);stroke-width:1}
.fg-text{fill:var(--ink)}
.fg-line{stroke:var(--ink);stroke-width:1.5;fill:none}
.fg-dash{stroke:var(--line);stroke-width:1.5;stroke-dasharray:4 4;fill:none}
.fg-arrow{fill:var(--ink)}
.fg-bg{fill:var(--bg,#fff)}
div.proto{margin:0 0 18px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}
.proto-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--tint1)}
.proto-bar strong{font-weight:600}
.proto-act{display:flex;gap:8px}
.proto-act a,.proto-act button{display:inline-flex;align-items:center;min-height:36px;padding:0 14px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font:inherit;font-size:var(--md-table);text-decoration:none;cursor:pointer}
.proto-act a:hover,.proto-act button:hover{background:var(--tint1)}
div.proto iframe{display:block;width:100%;border:0;background:#f5f6f8}
@media(max-width:700px){.twrap{overflow-x:auto}.twrap table.tbl{table-layout:auto}.twrap .tbl th,.twrap .tbl td{min-width:4.5em;overflow-wrap:normal;word-break:normal}}
</style>"""
FS, FS_NAME = 14, 16


def _w(text: str, size: int) -> float:
    return sum(size if ord(c) > 0x2E80 else size * 0.56 for c in text)


def _wrap(text: str, px: float, size: int = FS) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if _w(cur + ch, size) > px and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def _t(x: float, y: float, s: str, size: int = FS, anchor: str = "middle", cls: str = "fg-text") -> str:
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}">{E(s)}</text>'


def _arrow_head(x: float, y: float, direction: str) -> str:
    pts = {"down": f"{x-5:.1f},{y-9:.1f} {x+5:.1f},{y-9:.1f} {x:.1f},{y:.1f}", "right": f"{x-9:.1f},{y-5:.1f} {x-9:.1f},{y+5:.1f} {x:.1f},{y:.1f}",
           "left": f"{x+9:.1f},{y-5:.1f} {x+9:.1f},{y+5:.1f} {x:.1f},{y:.1f}"}[direction]
    return f'<polygon class="fg-arrow" points="{pts}"/>'


def _box(x: float, y: float, w: float, h: float, name: str, note: str = "") -> str:
    out = [f'<rect class="fg-node" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8"/>']
    note_lines = _wrap(note, w - 16) if note else []
    block = FS_NAME + 6 + len(note_lines) * (FS + 4)
    top = y + (h - block) / 2 + FS_NAME
    out.append(_t(x + w / 2, top, name, FS_NAME))
    for i, line in enumerate(note_lines):
        out.append(_t(x + w / 2, top + 8 + (i + 1) * (FS + 4) - 4, line))
    return "".join(out)


def _svg(width: float, height: float, body: str, label: str) -> str:
    return f'<svg role="img" aria-label="{E(label, quote=True)}" viewBox="0 0 {width:.0f} {height:.0f}" xmlns="http://www.w3.org/2000/svg"><title>{E(label)}</title>{body}</svg>'


def figure_layers(b: dict[str, Any]) -> str:
    rows, W, label_w, pad = b["rows"], 1000.0, 120.0, 12.0
    area_x, area_w = label_w + 20, W - label_w - 20 - 4
    cap = 320.0
    widths = [min((area_w - pad * (len(r["nodes"]) - 1)) / len(r["nodes"]), cap) for r in rows]
    lines_max = max([len(_wrap(str(n.get("note", "")), w - 16)) for r, w in zip(rows, widths) for n in r["nodes"]] + [1])
    node_h = max(60.0, FS_NAME + 6 + lines_max * (FS + 4) + 22)
    gap = 54.0
    links = {int(l["after"]): str(l.get("label", "")) for l in b.get("links", [])}
    body, y = [], 4.0
    for i, r in enumerate(rows):
        n = len(r["nodes"])
        w = widths[i]
        total = n * w + (n - 1) * pad
        x0 = area_x + (area_w - total) / 2
        body.append(f'<rect class="fg-band" x="2" y="{y:.1f}" width="{W-6:.0f}" height="{node_h:.1f}" rx="8"/>')
        for k, line in enumerate(_wrap(str(r["label"]), label_w - 12, FS_NAME)):
            body.append(_t(14, y + node_h / 2 + (k - (len(_wrap(str(r['label']), label_w - 12, FS_NAME)) - 1) / 2) * (FS_NAME + 4) + 5, line, FS_NAME, "start"))
        for j, node in enumerate(r["nodes"]):
            body.append(_box(x0 + j * (w + pad), y + 6, w, node_h - 12, str(node["name"]), str(node.get("note", ""))))
        y += node_h
        if i < len(rows) - 1:
            cx = area_x + area_w / 2
            body.append(f'<line class="fg-line" x1="{cx:.1f}" y1="{y:.1f}" x2="{cx:.1f}" y2="{y+gap-9:.1f}"/>{_arrow_head(cx, y+gap, "down")}')
            if links.get(i):
                body.append(_t(cx + 12, y + gap / 2 + 5, links[i], FS, "start"))
            y += gap
    return _svg(W, y + 6, "".join(body), b["caption"])


def figure_steps(b: dict[str, Any]) -> str:
    steps, W = b["steps"], 1000.0
    per = int(b.get("per_row", 4))
    n_rows = math.ceil(len(steps) / per)
    gap_x, w = 44.0, (W - 8 - 44.0 * (per - 1)) / per
    lines = [len(_wrap(str(s.get("note", "")), w - 16)) for s in steps]
    h = max(86.0, FS_NAME + 10 + max(lines + [1]) * (FS + 4) + 30)
    gap_y, body = 52.0, []
    for i, s in enumerate(steps):
        r, c = divmod(i, per)
        x, y = 4 + c * (w + gap_x), 4 + r * (h + gap_y)
        body.append(_box(x, y, w, h, f"{i + 1}　{s['name']}", str(s.get("note", ""))))
        if i < len(steps) - 1:
            if c < per - 1:
                body.append(f'<line class="fg-line" x1="{x+w:.1f}" y1="{y+h/2:.1f}" x2="{x+w+gap_x-9:.1f}" y2="{y+h/2:.1f}"/>{_arrow_head(x+w+gap_x, y+h/2, "right")}')
            else:
                nx, ny = 4 + w / 2, 4 + (r + 1) * (h + gap_y)
                mid = y + h + gap_y / 2
                body.append(f'<polyline class="fg-line" points="{x+w/2:.1f},{y+h:.1f} {x+w/2:.1f},{mid:.1f} {nx:.1f},{mid:.1f} {nx:.1f},{ny-9:.1f}"/>{_arrow_head(nx, ny, "down")}')
    return _svg(W, 8 + n_rows * h + (n_rows - 1) * gap_y, "".join(body), b["caption"])


def figure_sequence(b: dict[str, Any]) -> str:
    actors, msgs, W = b["actors"], b["messages"], 1000.0
    n = len(actors)
    col = (W - 8) / n
    xs = [4 + col * (i + 0.5) for i in range(n)]
    head_h, row_h = 44.0, 50.0
    height = head_h + 24 + len(msgs) * row_h + 10
    body = []
    for i, a in enumerate(actors):
        w = min(col - 14, 180.0)
        body.append(_box(xs[i] - w / 2, 2, w, head_h - 4, str(a)))
        body.append(f'<line class="fg-dash" x1="{xs[i]:.1f}" y1="{head_h:.1f}" x2="{xs[i]:.1f}" y2="{height-4:.1f}"/>')
    for k, m in enumerate(msgs):
        y = head_h + 24 + k * row_h + row_h / 2
        a, c = xs[m["from"]], xs[m["to"]]
        if a == c:
            body.append(f'<polyline class="fg-line" points="{a:.1f},{y-10:.1f} {a+46:.1f},{y-10:.1f} {a+46:.1f},{y+8:.1f} {a+9:.1f},{y+8:.1f}"/>{_arrow_head(a, y+8, "left")}')
            body.append(_t(a + 54, y - 2, f"{k + 1}　{m['label']}", FS, "start"))
            continue
        d = 1 if c > a else -1
        body.append(f'<line class="fg-line" x1="{a:.1f}" y1="{y:.1f}" x2="{c-d*9:.1f}" y2="{y:.1f}"/>{_arrow_head(c, y, "right" if d > 0 else "left")}')
        label = f"{k + 1}　{m['label']}"
        body.append(_t((a + c) / 2, y - 8, label, FS))
    return _svg(W, height, "".join(body), b["caption"])


def figure_grid(b: dict[str, Any]) -> str:
    nodes, W = b["nodes"], 1000.0
    cols = max(n["col"] for n in nodes) + 1
    rows = max(n["row"] for n in nodes) + 1
    cell_w, cell_h = (W - 8) / cols, 112.0
    w, h = min(cell_w - 70, 190.0), 64.0
    pos = {n["id"]: (4 + n["col"] * cell_w + cell_w / 2, 4 + n["row"] * cell_h + cell_h / 2) for n in nodes}
    body = []
    for l in b.get("links", []):
        (x1, y1), (x2, y2) = pos[l["from"]], pos[l["to"]]
        dx, dy = x2 - x1, y2 - y1
        t = min((w / 2) / abs(dx) if dx else 9e9, (h / 2) / abs(dy) if dy else 9e9)
        sx, sy, ex, ey = x1 + dx * t, y1 + dy * t, x2 - dx * t, y2 - dy * t
        L = math.hypot(ex - sx, ey - sy) or 1
        ux, uy = (ex - sx) / L, (ey - sy) / L
        px, py = ex - ux * 9, ey - uy * 9
        body.append(f'<line class="fg-line" x1="{sx:.1f}" y1="{sy:.1f}" x2="{px:.1f}" y2="{py:.1f}"/>')
        ang = math.atan2(uy, ux)
        pts = " ".join(f"{ex - 10 * math.cos(ang + d):.1f},{ey - 10 * math.sin(ang + d):.1f}" for d in (0.4, -0.4))
        body.append(f'<polygon class="fg-arrow" points="{ex:.1f},{ey:.1f} {pts}"/>')
        lw = _w(str(l["label"]), FS) + 10
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        body.append(f'<rect class="fg-bg" x="{mx-lw/2:.1f}" y="{my-11:.1f}" width="{lw:.1f}" height="22"/>' + _t(mx, my + 5, str(l["label"])))
    for n in nodes:
        x, y = pos[n["id"]]
        body.append(_box(x - w / 2, y - h / 2, w, h, str(n["name"]), str(n.get("note", ""))))
    return _svg(W, 8 + rows * cell_h, "".join(body), b["caption"])


FIGURE_FUNCS = {"layers": figure_layers, "steps": figure_steps, "sequence": figure_sequence, "grid": figure_grid}


def _inline(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", E(str(text)))


def _image_uri(root: Path, file: str) -> str:
    path = project_file(root, file)
    mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[path.suffix.lower()]
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def render_body(spec: dict[str, Any], root: Path, doc_dir: Path | None = None) -> str:
    """The HTML body of a developer document; the page wrapper adds the h1 and the theme. A tabbed document is one page: the sections of
    every tab are in the page, shown one tab at a time."""
    import sys

    design = Path(__file__).resolve().parents[2] / "Luz-Design" / "scripts"
    if str(design) not in sys.path:
        sys.path.insert(0, str(design))
    import showcase  # type: ignore

    counters = {"table": 0, "figure": 0, "proto": 0}
    surfaces = surfaces_of(root)
    parts = [CSS, dev_tabs.TAB_CSS, f"<h2>结论</h2><p>{_inline(spec['conclusion'])}</p>"]
    uid = [0]

    def prototype_html(b: dict[str, Any]) -> str:
        """The prototype as a frame: the real interface, with a bar that has the title and two buttons (reload, open in a new window). Nothing else."""
        counters["proto"] += 1
        base = Path(doc_dir) if doc_dir else project_file(root, "docs/02-产品开发")
        src = os.path.relpath(project_file(root, b["file"]), base).replace(os.sep, "/")
        height = int(b.get("height", 900 if b.get("kind") == "phone" else 860))
        fid = f"proto-{counters['proto']}"
        return (f'<div class="proto" role="group" aria-label="{E(b["title"], quote=True)}"><div class="proto-bar"><strong>{E(b["title"])}</strong><span class="proto-act">'
                f'<button type="button" data-reload="{fid}">重新载入</button>'
                f'<a href="{E(src, quote=True)}" target="_blank" rel="noopener">在新窗口打开</a></span></div>'
                f'<iframe id="{fid}" data-src="{E(src, quote=True)}" title="{E(b["title"], quote=True)}" height="{height}">'
                f'当前浏览器不能内嵌页面，请用“在新窗口打开”。</iframe></div>')

    def blocks_html(section: dict[str, Any], sub_level: int) -> str:
        out: list[str] = []
        pending: list[str] = []

        def flush() -> None:
            if pending:
                out.append('<figure class="shots">' + "".join(pending) + "</figure>")
                pending.clear()

        for b in _blocks(section):
            kind = b["type"]
            if kind == "image":
                counters["figure"] += 1
                size = "phone" if b.get("size", "wide") == "phone" else "wide"
                pending.append(f'<figure class="shot {size}"><img src="{_image_uri(root, b["file"])}" alt="{E(b["alt"], quote=True)}">'
                               f'<figcaption>图 {counters["figure"]}　{E(b["caption"])}</figcaption></figure>')
                continue
            flush()
            if kind == "prototype":
                out.append(prototype_html(b))
            elif kind == "text":
                out.append(f"<p>{_inline(b['text'])}</p>")
            elif kind == "note":
                out.append(f'<p class="notice">{_inline(b["text"])}</p>')
            elif kind == "sub":
                out.append(f"<h{sub_level}>{_inline(b['text'])}</h{sub_level}>")
            elif kind == "bullets":
                out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in b["items"]) + "</ul>")
            elif kind == "code":
                out.append(f'<pre class="code">{E(b["text"])}</pre>')
            elif kind == "table":
                counters["table"] += 1
                cells = [["\n".join(map(str, c)) if isinstance(c, (list, tuple)) else str(c) for c in row] for row in b["rows"]]
                out.append(f'<div class="tcap">表 {counters["table"]}　{E(b["caption"])}</div>'
                           + showcase.table_html([str(c) for c in b["columns"]], cells, widths=b.get("widths"), first_key=b.get("first_key", False), formal=True))
            elif kind == "baseline":
                counters["table"] += 1
                out.append(dev_tabs.render_baseline(b, counters["table"], surfaces))
            elif kind == "function":
                out.append(dev_tabs.render_function(b))
            elif kind == "figure":
                counters["figure"] += 1
                out.append(f'<figure class="fig">{FIGURE_FUNCS[b["kind"]](b)}<figcaption>图 {counters["figure"]}　{E(b["caption"])}</figcaption></figure>')
        flush()
        return "".join(out)

    if "tabs" in spec:
        uid[0] += 1
        top = f"d{uid[0]}"
        panels = []
        for i, tab in enumerate(spec["tabs"]):
            if tab["layout"] == "frontend":
                inner = "".join(prototype_html(b) for s in tab["sections"] for b in _blocks(s) if b.get("type") == "prototype")
            elif tab["layout"] == "subtabs":
                sub = f"{top}s{i}"
                nav = dev_tabs.tab_nav([s["title"] for s in tab["sections"]], sub, sub=True)
                inner = nav + "".join(dev_tabs.tab_panel(sub, j, f'<h3 class="sec">{E(s["title"])}</h3>' + blocks_html(s, 4)) for j, s in enumerate(tab["sections"]))
            else:
                inner = "".join(f"<h2>{E(s['title'])}</h2>" + blocks_html(s, 3) for s in tab["sections"])
            panels.append(dev_tabs.tab_panel(top, i, inner))
        parts.append(dev_tabs.tab_nav([t["title"] for t in spec["tabs"]], top) + "".join(panels))
    else:
        for section in spec["sections"]:
            parts.append(f"<h2>{E(section['title'])}</h2>" + blocks_html(section, 3))
    has_tabs = "tabs" in spec
    if any(b.get("type") == "prototype" for s in _all_sections(spec) for b in _blocks(s)):
        parts.append("<script>document.addEventListener('click',function(e){var b=e.target.closest('[data-reload]');if(!b)return;var f=document.getElementById(b.getAttribute('data-reload'));if(!f)return;var s=f.getAttribute('src')||f.dataset.src;if(s){f.removeAttribute('data-src');f.src=s;}});</script>")
    if has_tabs:
        parts.append(dev_tabs.TAB_JS)
    parts.append("<h2>来源与依据</h2>")
    counters["table"] += 1
    rows = [[str(s["id"]), str(s["url"]), str(s["finding"]), str(s["applies_to"])] for s in spec["sources"]]
    parts.append(f'<div class="tcap">表 {counters["table"]}　检索来源与采用位置</div>'
                 + showcase.table_html(["来源", "网址", "读到的内容", "采用位置"], rows, widths=[1.3, 3.2, 4, 3], first_key=False, formal=True))
    return "".join(parts)


def _all_sections(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for t in spec["tabs"] for s in t["sections"]] if "tabs" in spec else list(spec.get("sections", []))
