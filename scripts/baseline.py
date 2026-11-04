"""The technical baseline (技术底座) of every Luz project, and what a project may do with it.

The baseline is three files in ``references/baseline/`` written once, in the skills' words, and reused by every project:

* ``stack.json``     the technology stack by layer (frontend miniapp, frontend admin, backend, database, cache and queue, storage,
                     deployment, observability, security, testing and release)
* ``frontend.json``  the frontend foundation by category (stack, logic, font, colour, card, icon, layout, motion, interaction, copy,
                     a11y, assets, principles)
* ``functions.json`` the basic functions (login, accounts and permissions, tenants, catalog, orders, payment, member cards, wallet,
                     coupons, notification, files, import and export, audit, legal, report, config) with frontend logic, backend
                     logic, database and technical solution for each

A project does not copy them. It states for every baseline item whether it keeps it (沿用), changes it (调整, with a reason), adds
something the baseline does not have (新增), or does not use it (不用, with a reason). ``project_baseline_errors`` checks that statement;
the developer documents render the baseline next to the project's value so a reader sees at a glance what is standard and what is
specific. See references/tech-baseline.md.

A layer or an item that belongs to one front end (the mini program) is only in the baseline of a project that has that front end:
``LAYER_SURFACE`` / ``FRONTEND_SURFACE`` say which, ``stack_items`` / ``frontend_items`` / ``mandatory_ids`` / ``project_baseline_errors`` take the
project's ``surfaces`` (the ids of ``data/client/features.json``; none known means everything applies), and a sentence that is true only
for one front end is written in the item's ``by_surface`` and read with ``text`` instead of sitting in the neutral text.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "references" / "baseline"
STATUSES = ("沿用", "调整", "新增", "不用")
NEEDS_REASON = ("调整", "不用")
PLACEHOLDER = re.compile(r"待补充|待填写|TODO|TBD|lorem ipsum|XXX|示例文字|（略）|占位文字|占位内容|此处占位", re.I)

STACK_LAYERS = {
    "frontend-miniapp": "小程序前端", "frontend-admin": "管理后台前端", "backend": "后端", "database": "数据库", "cache-queue": "缓存与队列",
    "storage": "文件存储", "deployment": "部署", "observability": "运维观测", "security": "安全", "testing-release": "测试与发布",
}
FRONTEND_CATEGORIES = {
    "principles": "设计原则", "stack": "前端技术栈", "logic": "前端逻辑", "font": "字体", "colour": "色彩", "card": "卡片与容器", "icon": "图标",
    "layout": "布局与响应式", "motion": "动效", "interaction": "交互与反馈", "copy": "文案与用词", "assets": "图片与素材", "a11y": "可访问性",
}
FUNCTION_FIELDS = ("frontend", "backend", "database", "tech")
# Front ends that only some projects have. The admin console stays in every project: it is also the web stack of a website or an agent console.
LAYER_SURFACE = {"frontend-miniapp": "miniprogram"}
FRONTEND_SURFACE = {"miniapp": "miniprogram"}
SURFACE_NAMES = {"miniprogram": "小程序"}
SURFACE_TEXT_FIELDS = ("baseline", "detail", "why", "replace_when")
SURFACE_ONLY_WORDS = re.compile(r"小程序|胶囊|订阅消息|wx\.")


def _load(name: str) -> dict[str, Any]:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def stack() -> dict[str, Any]:
    return _load("stack.json")


def frontend() -> dict[str, Any]:
    return _load("frontend.json")


def functions() -> dict[str, Any]:
    return _load("functions.json")


def has_surface(surfaces: Any, surface: str) -> bool:
    """Whether the project has this front end. No surfaces known (no function list yet, an offline rehearsal) means every one."""
    return not surfaces or surface in surfaces


def layer_applies(layer: str, surfaces: Any = None) -> bool:
    return layer not in LAYER_SURFACE or has_surface(surfaces, LAYER_SURFACE[layer])


def item_applies(item: dict[str, Any], surfaces: Any = None) -> bool:
    """A frontend item tagged for the mini program only is for projects that have one; ``both`` and ``admin`` items are in every project."""
    tags = set(item.get("surfaces") or ())
    if not tags or not tags <= set(FRONTEND_SURFACE):
        return True
    return all(has_surface(surfaces, FRONTEND_SURFACE[t]) for t in tags)


def stack_items(layer: str | None = None, surfaces: Any = None) -> list[dict[str, Any]]:
    return [i for l in stack()["layers"] if layer in (None, l["id"]) and layer_applies(l["id"], surfaces) for i in l["items"]]


def frontend_items(category: str | None = None, surfaces: Any = None) -> list[dict[str, Any]]:
    return [i for c in frontend()["categories"] if category in (None, c["id"]) for i in c["items"] if item_applies(i, surfaces)]


def text(item: dict[str, Any], field: str, surfaces: Any = None) -> str:
    """The text of an item's field for a project: the neutral text, then what ``by_surface`` adds for each front end the project has."""
    parts = [str(item.get(field) or "").strip()]
    parts += [str(extra[field]).strip() for surface, extra in (item.get("by_surface") or {}).items() if field in extra and has_surface(surfaces, surface)]
    return " ".join(p for p in parts if p)


def function_items() -> list[dict[str, Any]]:
    return [f for m in functions()["modules"] for f in m["functions"]]


def item(item_id: str) -> dict[str, Any] | None:
    """Any baseline item (stack, frontend or function) by its id."""
    for source in (stack_items(), frontend_items(), function_items()):
        for i in source:
            if i["id"] == item_id:
                return i
    return None


def _text_errors(where: str, value: Any, minimum: int = 8) -> list[str]:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        return [f"{where} 太短或为空（至少 {minimum} 个字）"]
    if PLACEHOLDER.search(value):
        return [f"{where} 含占位字样"]
    return []


def _check_id(errors: list[str], ids: set[str], i: dict[str, Any], prefix: str, where: str) -> None:
    iid = str(i.get("id", ""))
    if not re.fullmatch(prefix + r"-[A-Z0-9]+-\d{2}", iid):
        errors.append(f"{where} 的编号不合格式 {prefix}-XX-NN: {iid}")
    if iid in ids:
        errors.append(f"{where} 的编号重复: {iid}")
    ids.add(iid)


def stack_errors() -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    s = stack()
    got = [l["id"] for l in s["layers"]]
    if got != list(STACK_LAYERS):
        errors.append(f"stack.json 的层必须依次是 {list(STACK_LAYERS)}，现在是 {got}")
    for l in s["layers"]:
        if len(l["items"]) < 3:
            errors.append(f"stack.json 的层 {l['id']} 至少 3 项")
        for i in l["items"]:
            w = f"stack.json {i.get('id')}"
            _check_id(errors, ids, i, "STK", w)
            for k in ("name", "baseline", "why", "source"):
                errors += _text_errors(f"{w}.{k}", i.get(k), 2 if k == "name" else 4)
            errors += _text_errors(f"{w}.detail", i.get("detail"), 20)
            if not isinstance(i.get("mandatory"), bool):
                errors.append(f"{w}.mandatory 必须是 true 或 false")
            if i.get("mandatory") is False:
                errors += _text_errors(f"{w}.replace_when", i.get("replace_when"), 8)
            errors += _by_surface_errors(w, i, in_surface_layer=l["id"] in LAYER_SURFACE)
    return list(dict.fromkeys(errors))


def _by_surface_errors(where: str, i: dict[str, Any], in_surface_layer: bool) -> list[str]:
    """``by_surface`` holds what is true for one front end only; the neutral text of an item outside that front end's layer must not name it."""
    extras = i.get("by_surface")
    out: list[str] = []
    if extras is not None:
        if in_surface_layer:
            out.append(f"{where} 在只属于一端的层里，不写 by_surface")
        if not isinstance(extras, dict) or not extras:
            return out + [f"{where}.by_surface 要是 {{端: {{字段: 文字}}}}"]
        for surface, fields in extras.items():
            if surface not in SURFACE_NAMES or not isinstance(fields, dict) or not fields:
                out.append(f"{where}.by_surface 的端只能是 {'、'.join(SURFACE_NAMES)}，并写出字段")
                continue
            for field, value in fields.items():
                if field not in SURFACE_TEXT_FIELDS or not str(i.get(field) or "").strip():
                    out.append(f"{where}.by_surface.{surface} 的字段 {field} 要是 {'、'.join(SURFACE_TEXT_FIELDS)} 之一，且正文里有这个字段")
                else:
                    out += _text_errors(f"{where}.by_surface.{surface}.{field}", value, 8)
    if not in_surface_layer:
        for field in ("name",) + SURFACE_TEXT_FIELDS:
            hit = SURFACE_ONLY_WORDS.search(str(i.get(field) or ""))
            if hit:
                out.append(f"{where}.{field} 正文写了“{hit.group(0)}”：只对小程序成立的话放进 by_surface.miniprogram，正文保持不分端")
    return out


def frontend_errors() -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    f = frontend()
    got = [c["id"] for c in f["categories"]]
    if got != list(FRONTEND_CATEGORIES):
        errors.append(f"frontend.json 的分类必须依次是 {list(FRONTEND_CATEGORIES)}，现在是 {got}")
    for c in f["categories"]:
        if len(c["items"]) < 2:
            errors.append(f"frontend.json 的分类 {c['id']} 至少 2 项")
        for i in c["items"]:
            w = f"frontend.json {i.get('id')}"
            _check_id(errors, ids, i, "FE", w)
            for k in ("name", "baseline", "source"):
                errors += _text_errors(f"{w}.{k}", i.get(k), 2 if k == "name" else 4)
            errors += _text_errors(f"{w}.detail", i.get("detail"), 20)
            if i.get("surfaces") and not set(i["surfaces"]) <= {"miniapp", "admin", "both"}:
                errors.append(f"{w}.surfaces 只能是 miniapp、admin、both")
            if not isinstance(i.get("mandatory", True), bool):
                errors.append(f"{w}.mandatory 必须是 true 或 false")
    return list(dict.fromkeys(errors))


def function_errors() -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    fn = functions()
    if len(fn["modules"]) < 10:
        errors.append("functions.json 至少 10 个基础模块")
    for m in fn["modules"]:
        for k in ("id", "name", "summary"):
            errors += _text_errors(f"functions.json 模块 {m.get('id')}.{k}", m.get(k), 2)
        if not m.get("functions"):
            errors.append(f"functions.json 模块 {m.get('id')} 没有功能")
        for x in m.get("functions", []):
            w = f"functions.json {x.get('id')}"
            _check_id(errors, ids, x, "BF", w)
            errors += _text_errors(f"{w}.name", x.get("name"), 2)
            errors += _text_errors(f"{w}.summary", x.get("summary"), 10)
            for k in FUNCTION_FIELDS:
                errors += _text_errors(f"{w}.{k}", x.get(k), 30)
            for k in ("rules", "exceptions", "tests"):
                v = x.get(k)
                if not isinstance(v, list) or not v or any(len(str(t).strip()) < 6 for t in v):
                    errors.append(f"{w}.{k} 至少一条，每条至少 6 个字")
                elif any(PLACEHOLDER.search(str(t)) for t in v):
                    errors.append(f"{w}.{k} 含占位字样")
            if x.get("kind") not in ("基础", "可选"):
                errors.append(f"{w}.kind 只能是 基础 或 可选")
            if not x.get("surfaces") or not set(x["surfaces"]) <= {"miniapp", "admin", "backend", "agent", "website"}:
                errors.append(f"{w}.surfaces 不合格")
    return list(dict.fromkeys(errors))


def baseline_errors() -> list[str]:
    """The baseline files themselves: structure, unique ids, no empty or placeholder text, every layer and category present."""
    return stack_errors() + frontend_errors() + function_errors()


def mandatory_ids(kind: str, scope: str, surfaces: Any = None) -> list[str]:
    """The baseline items a project must account for: kind ``stack`` / ``frontend``, scope = layer or category id."""
    items = stack_items(scope, surfaces) if kind == "stack" else frontend_items(scope, surfaces)
    return [i["id"] for i in items if i.get("mandatory", True)]


def project_baseline_errors(statement: dict[str, Any], surfaces: Any = None) -> list[str]:
    """A project's statement ``{"stack": {id: {status, value, reason}}, "frontend": {…}, "modules": {module id: {…}}}`` against the
    baseline: every mandatory item and every basic-function module accounted for, a valid status, a reason for every change or omission,
    nothing invented under a baseline id, and nothing about a front end the project does not have."""
    errors: list[str] = []
    for kind, getter in (("stack", stack_items), ("frontend", frontend_items)):
        have = statement.get(kind, {})
        known = {i["id"]: i for i in getter(surfaces=surfaces)}
        absent = {i["id"] for i in getter()} - set(known)
        for iid, row in have.items():
            if iid.startswith("X-"):
                if row.get("status") != "新增":
                    errors.append(f"{iid}: 底座没有的项状态只能是 新增")
                continue
            if iid in absent:
                errors.append(f"{iid}: 本项目没有这一端（功能清单里没有{'、'.join(SURFACE_NAMES.values())}功能），不写这一项")
                continue
            if iid not in known:
                errors.append(f"{iid}: 不在底座里（项目自己加的项编号用 X-开头）")
                continue
            errors += _row_errors(iid, row)
        for iid, i in known.items():
            if i.get("mandatory", True) and iid not in have:
                errors.append(f"{iid}（{i['name']}）是底座必有项，项目没有说明沿用、调整还是不用")
    have_modules = statement.get("modules", {})
    modules = {m["id"]: m for m in functions()["modules"]}
    for iid, row in have_modules.items():
        if iid not in modules:
            errors.append(f"{iid}: 不是底座的基础功能模块")
        else:
            errors += _row_errors(iid, row)
    for iid, m in modules.items():
        if iid not in have_modules:
            errors.append(f"{iid}（{m['name']}）是底座的基础功能模块，项目没有说明沿用、调整还是不用")
    return errors


def _row_errors(iid: str, row: dict[str, Any]) -> list[str]:
    status = row.get("status")
    if status not in STATUSES:
        return [f"{iid}: 状态必须是 {'、'.join(STATUSES)}"]
    out: list[str] = []
    if status in NEEDS_REASON:
        out += _text_errors(f"{iid} 的理由", row.get("reason"), 8)
    if status in ("调整", "新增"):
        out += _text_errors(f"{iid} 的本项目取值", row.get("value"), 2)
    if PLACEHOLDER.search(" ".join(str(v) for v in row.values())):
        out.append(f"{iid} 含占位字样")
    return out


if __name__ == "__main__":
    problems = baseline_errors()
    print("baseline: ok" if not problems else "\n".join(problems))
    raise SystemExit(1 if problems else 0)
