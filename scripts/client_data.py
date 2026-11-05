"""Canonical client-facing data for a Luz project: features, proposal, architecture, intake, changes, acceptance, manual.

Everything a client sees (PDF / XLSX) is rendered from the JSON files below ``data/``; the JSON is the source of truth,
the rendered files are derived and carry the SHA-256 of the sources they were built from (``data/client/build.json``)
so a later change to the sources is detected instead of silently shipping a stale document.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from project_core import ProjectError, _read_json, _write_json, locate, now_iso, relative_to_project, sha256_file

SURFACES = {
    "miniprogram": "微信小程序",
    "web-admin": "网页管理后台",
    "agent": "智能体平台",
    "website": "官方网站",
    "mobile-app": "移动应用",
    "api": "开放接口",
    "hardware": "现场硬件",
}
FEATURE_TIERS = ("基础", "可选")
FEATURE_STATUS = ("in-scope", "out-of-scope", "removed")
CHANGE_TYPES = ("新增", "修改", "删除", "补充")
CHANGE_CATEGORIES = ("需求", "规则", "界面", "流程", "技术", "范围", "其他")
CHANGE_SOURCES = ("客户", "内部", "测试发现", "政策法规")
CHANGE_STATUSES = ("待确认", "已确认", "已实施", "已驳回")
# What the client sees in 06-需求变更台账 (and the delivery snapshot): the client's own functional / rule / scope changes. Internal, technical and
# interface changes stay in data/changes.json only. An entry's explicit ``client_visible`` (true / false) wins over this default.
CLIENT_VISIBLE_SOURCES = ("客户",)
CLIENT_VISIBLE_CATEGORIES = ("需求", "规则", "范围")
# Numbers and file names that mean nothing to the client: approvals, artifacts, baseline items, the project's own client files.
INTERNAL_TOKENS = re.compile(r"\b(?:APPROVAL|ART|SRC|STK|FE|BF|CQ|ST|SE|MP)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
ACCEPTANCE_STATUSES = ("pending", "passed", "failed", "waived")
PLACEHOLDER = re.compile(r"待补充|TODO|TBD|占位符|占位文字|xxx|lorem ipsum", re.I)  # “占位图”等业务词不算占位

# The proposal says why, what and what is delivered; the feature list carries the functions and the price, the architecture
# book the architecture. One fact lives in one document and the others point to it by name.
PROPOSAL_SECTIONS = (
    ("background", "项目背景与需求分析"),
    ("solution", "解决方案"),
    ("deliverables", "交付内容"),
)
# The requirements document comes first: what the client's business is, what it needs, and how it will be accepted. A client who has no
# requirements document gets this one before any proposal is written; a client who has one registers it in requirements.json instead.
REQUIREMENT_SECTIONS = (
    ("background", "项目背景"),
    ("goals", "建设目标"),
    ("scope", "范围与使用者"),
    ("requirements", "需求清单"),
    ("rules", "业务规则与约束"),
    ("acceptance", "验收标准"),
    ("open", "需要客户确认的事项"),
)
WORD_BLOCKS = {"text", "p", "bullets", "checks", "callout", "sub", "table", "matrix"}
REQUIREMENT_WORD_BLOCKS = WORD_BLOCKS | {"auto"}      # the need list is taken from the feature list: it becomes sub headings and tables before typesetting
OTHER_FILES = re.compile(r"《(?:需求说明书|方案说明书|系统架构图册?|功能清单|报价清单|业务逻辑确认表|需求变更台账|使用说明书?|验收清单|客户信息收集表|业务规则收集表)》|配套文件|见功能清单|见系统架构图|见业务逻辑确认表")

# Feature tags that need a dedicated Luz-Ops check next to the generic surface checks.
TAG_CHECKS = {
    "排队": "queue_concurrency",
    "并发": "queue_concurrency",
    "定时任务": "scheduler",
    "风险预警": "alert_loop",
    "规则引擎": "rules_calc",
    "绩效核算": "rules_calc",
    "单据核算": "rules_calc",
    "知识库": "kb_quality",
    "流程编排": "workflow_debug",
}
SURFACE_CHECKS = {
    "miniprogram": ["miniprogram_automation", "e2e"],
    "web-admin": ["browser_automation", "e2e"],
    "website": ["browser_automation", "e2e"],
    "agent": ["agent_eval", "e2e"],
    "mobile-app": ["e2e"],
    "api": ["contract"],
    "hardware": ["integration"],
}


def data_path(root: Path, *parts: str) -> Path:
    return root.joinpath("data", *parts)


def load(root: Path, *parts: str, default: Any = None) -> Any:
    return _read_json(data_path(root, *parts), default)


def save(root: Path, payload: Any, *parts: str) -> Path:
    path = data_path(root, *parts)
    _write_json(path, payload)
    return path


def has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER.search(value))
    if isinstance(value, dict):
        return any(has_placeholder(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_placeholder(v) for v in value)
    return False


def empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


# --- documents config -------------------------------------------------------------------------------------------

def documents_config(root: Path) -> dict[str, Any]:
    return _read_json(root / "config" / "documents.json", {}) or {}


def amounts_enabled(root: Path) -> bool:
    """``config/documents.json`` ``"amounts": false`` keeps every price out of the client documents: no quote sheet in 04-功能清单 (``quote.json`` is not read),
    no amounts in the proposal, the architecture book, the change ledger or the review pages. The person-days (``hours``) stay. Default: true."""
    return documents_config(root).get("amounts", True) is not False


# What puts the quote in front of the client: the words of a quote, a price per person-day, a total with a sum of money. A rule that merely mentions money
# ("100 分抵 1 元", "订单金额满 200 元") is business logic and not matched; the feature list is held to the stricter pattern (any sum, 金额, a cell that starts with 合计 or 总计;
# a description that merely says "演示数量合计" is not a total).
PRICE = re.compile(r"报价|单价|小计|[¥￥]\s*\d|\d[\d,.]*\s*元\s*(?:每|/|／)\s*人天|(?:总价|合计|总计|基础功能|可选功能)[^。；\n]{0,10}\d[\d,.]*\s*(?:万)?元")
PRICE_STRICT = re.compile(PRICE.pattern + r"|金额|^\s*(?:合计|总计)|(?<![\d.])\d[\d,]*(?:\.\d+)?\s*(?:万)?元(?![素宵旦])")


def money_issues(text: str, strict: bool = False) -> list[str]:
    """Words and figures that put a price in front of the client (报价, 单价, 小计, 12,750 元每人天, ¥500); ``strict`` also takes 金额, 合计 and any sum in yuan."""
    return sorted({m.group(0).strip() for m in (PRICE_STRICT if strict else PRICE).finditer(text)})


def document_version(root: Path) -> str:
    """The version the client documents carry: ``config/documents.json`` ``version``, else the version on the proposal cover, else V1.0."""
    configured = documents_config(root).get("version")
    if configured:
        return str(configured)
    proposal = load(root, "client", "proposal.json", default={}) or {}
    for pair in ((proposal.get("hero") or {}).get("info") or []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] == "版本" and str(pair[1]).strip():
            return str(pair[1]).strip()
    return "V1.0"


def project_theme(root: Path, spec: dict[str, Any] | None = None) -> str:
    theme = (spec or {}).get("theme") or documents_config(root).get("theme")
    if not theme:
        raise ProjectError("尚未选定文档主题：先运行 project.py client theme <项目> <主题>（主题见 Luz-Design references/themes.json，按本项目行业和受众选择）")
    themes = json.loads((Path(__file__).resolve().parents[2] / "Luz-Design" / "references" / "themes.json").read_text(encoding="utf-8"))["themes"]
    if theme not in themes:
        raise ProjectError(f"未知主题: {theme}；可选: {', '.join(themes)}")
    return str(theme)


# --- features ---------------------------------------------------------------------------------------------------

def validate_features(spec: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["features.json 必须是对象"]
    modules = spec.get("modules")
    features = spec.get("features")
    if not isinstance(modules, list) or not modules:
        errors.append("features.modules 为空")
        modules = []
    if not isinstance(features, list) or not features:
        errors.append("features.features 为空")
        features = []
    module_ids: set[str] = set()
    for module in modules:
        if not isinstance(module, dict) or empty(module.get("id")) or empty(module.get("name")) or empty(module.get("summary")):
            errors.append("模块需含 id、name、summary")
            continue
        if module["id"] in module_ids:
            errors.append(f"模块 ID 重复: {module['id']}")
        module_ids.add(module["id"])
    seen: set[str] = set()
    for item in features:
        if not isinstance(item, dict):
            errors.append("功能必须是对象")
            continue
        fid = str(item.get("id", ""))
        if not re.fullmatch(r"FN-\d{3,}", fid):
            errors.append(f"功能 ID 须为 FN-001 形式: {fid or '(空)'}")
        if fid in seen:
            errors.append(f"功能 ID 重复: {fid}")
        seen.add(fid)
        for key in ("module", "name", "surface", "roles", "tier", "summary", "rules"):
            if empty(item.get(key)):
                errors.append(f"{fid} 缺少 {key}")
        if item.get("module") and item["module"] not in module_ids:
            errors.append(f"{fid} 引用不存在的模块 {item['module']}")
        if item.get("surface") and item["surface"] not in SURFACES:
            errors.append(f"{fid} 使用端无效: {item['surface']}（可选 {', '.join(SURFACES)}）")
        if item.get("tier") and item["tier"] not in FEATURE_TIERS:
            errors.append(f"{fid} tier 须为 基础 或 可选")
        if item.get("status", "in-scope") not in FEATURE_STATUS:
            errors.append(f"{fid} status 无效")
        if not isinstance(item.get("roles", []), list):
            errors.append(f"{fid} roles 须为数组")
        if has_placeholder(item):
            errors.append(f"{fid} 含占位文字，须写成真实内容")
    return errors


def load_quote(root: Path) -> dict[str, Any] | None:
    """``data/client/quote.json`` {"unit_price": 500}: the price of one person-day; the hours are on each feature (``hours``)."""
    return load(root, "client", "quote.json")


def validate_hours(features: dict[str, Any]) -> list[str]:
    """Every function in scope carries its estimate in person-days (``hours``): the feature list shows it with or without a price."""
    missing = [f["id"] for f in active_features(features) if not isinstance(f.get("hours"), (int, float)) or f["hours"] <= 0]
    return [f"这些功能没有工时（features.json 的 hours，人天）: {'、'.join(missing[:8])}"] if missing else []


def validate_quote(features: dict[str, Any], quote: Any) -> list[str]:
    if not isinstance(quote, dict) or not isinstance(quote.get("unit_price"), (int, float)) or quote["unit_price"] <= 0:
        return ["quote.json 需含大于 0 的 unit_price（元/人天）"]
    return validate_hours(features)


def quote_totals(features: dict[str, Any], quote: dict[str, Any]) -> dict[str, float]:
    items = active_features(features)
    price = float(quote["unit_price"])
    basic = sum(f["hours"] for f in items if f["tier"] == "基础")
    optional = sum(f["hours"] for f in items if f["tier"] != "基础")
    return {"unit_price": price, "basic_hours": basic, "optional_hours": optional, "basic_amount": basic * price, "optional_amount": optional * price}


def load_features(root: Path, *, validate: bool = True) -> dict[str, Any]:
    spec = load(root, "client", "features.json")
    if spec is None:
        raise ProjectError("缺少 data/client/features.json：功能清单是方案、确认表、验收清单和使用说明的共同来源")
    if validate:
        errors = validate_features(spec)
        if errors:
            raise ProjectError("功能清单无效: " + "; ".join(errors[:6]))
    return spec


def active_features(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in spec.get("features", []) if f.get("status", "in-scope") == "in-scope"]


# --- proposal / architecture -------------------------------------------------------------------------------------

def design_showcase():
    """Luz-Design's showcase library: the one place that knows how a client document is laid out and validated."""
    design = Path(__file__).resolve().parents[2] / "Luz-Design" / "scripts"
    if not design.is_dir():
        raise ProjectError(f"找不到 Luz-Design 脚本目录: {design}")
    import sys

    if str(design) not in sys.path:
        sys.path.insert(0, str(design))
    import showcase  # type: ignore

    return showcase


def _spec_errors(spec: Any, theme_default: str | None = None) -> list[str]:
    if not isinstance(spec, dict):
        return ["文档数据必须是对象"]
    probe = json.loads(json.dumps(spec, ensure_ascii=False))
    probe["theme"] = spec.get("theme") or theme_default or "b2b-graphite"
    if probe.get("format") == "word" or probe.get("cover") or probe.get("toc"):
        probe["style"] = "formal"          # a Word proposal is checked as a formal document: titled tables, no stat tiles
    for sec in probe.get("sections", []):  # {"type": "auto"} blocks are filled in from the feature list at build time
        sec["blocks"] = [{"type": "text", "text": "自动生成"} if b.get("type") == "auto" else b for b in sec.get("blocks", [])]
    return design_showcase().validate_spec(probe)


def _word_errors(spec: dict[str, Any], allowed: set[str] = WORD_BLOCKS) -> list[str]:
    """A proposal for a client is a Word document (cover, contents, text and tables, black and white): what the builder can write."""
    errors = []
    if not spec.get("cover") and not (spec.get("hero") or {}).get("info"):
        errors.append("方案需要封面信息：hero.info 写项目名称、版本、日期")
    if OTHER_FILES.search(json.dumps(spec, ensure_ascii=False)):
        errors.append("方案不提及其他文件（《方案说明书》《功能清单》等本项目文件名、配套文件、见某某表）：每份文件把自己的内容写完整；法规名称可以用书名号")
    if not spec.get("toc"):
        errors.append("方案需要目录：toc 写 true")
    for sec in spec.get("sections", []):
        where = f"第「{sec.get('title')}」节"
        if re.search(r"[（(）)]", str(sec.get("title", ""))):
            errors.append(f"{where}标题不写括号说明，说明放进正文")
        for b in sec.get("blocks", []):
            kind = b.get("type")
            if kind not in allowed:
                errors.append(f"{where}含 {kind} 块：方案用 Word 排版，只用文段、小标题、列点和表格")
            elif kind == "sub" and re.search(r"[（(）)]", str(b.get("text", ""))):
                errors.append(f"{where}小标题「{b.get('text')}」不写括号说明")
            elif kind in {"table", "matrix"} and not b.get("caption"):
                errors.append(f"{where}有表格没有表题（caption）")
    return errors


def validate_proposal(spec: Any, theme_default: str | None = None) -> list[str]:
    """The proposal is a showcase spec; on top of Design's checks every required chapter must exist (by ``key``), the document is
    the formal style (text and tables, no icons before titles) and it opens with a contents list."""
    errors = _spec_errors(spec, theme_default)
    if isinstance(spec, dict) and spec.get("format", "word") == "word":
        errors += _word_errors(spec)
    if isinstance(spec, dict) and isinstance(spec.get("sections"), list):
        keys = {sec.get("key") for sec in spec["sections"]}
        for key, label in PROPOSAL_SECTIONS:
            if key not in keys:
                errors.append(f"方案缺少章节「{label}」（section.key = {key}）")
    return errors


def validate_requirements(spec: Any, theme_default: str | None = None) -> list[str]:
    """The requirements document is a Word document for the client: every chapter present, the need list a titled table (or filled in from
    the feature list), and no placeholder left."""
    errors = _spec_errors(spec, theme_default)
    if isinstance(spec, dict) and spec.get("format", "word") == "word":
        errors += _word_errors(spec, REQUIREMENT_WORD_BLOCKS)
    if isinstance(spec, dict) and isinstance(spec.get("sections"), list):
        by_key = {sec.get("key"): sec for sec in spec["sections"]}
        for key, label in REQUIREMENT_SECTIONS:
            if key not in by_key:
                errors.append(f"需求说明书缺少章节「{label}」（section.key = {key}）")
        need = by_key.get("requirements")
        if need and not any(b.get("type") in {"table", "matrix"} or (b.get("type") == "auto" and b.get("what") == "requirement_list") for b in need.get("blocks", [])):
            errors.append("需求清单要有带表题的表，或用 {\"type\": \"auto\", \"what\": \"requirement_list\"} 由功能清单生成")
        background = by_key.get("background")
        if background and not any(b.get("type") == "table" for b in background.get("blocks", [])):
            errors.append("项目背景要有一张按使用方写的现状问题表（现状问题、具体表现、带来的后果）")
    return errors


def requirements_client_document(spec: Any) -> str | None:
    """The path of the client's own requirements document when requirements.json registers one instead of a document written by us."""
    if isinstance(spec, dict) and isinstance(spec.get("client_document"), dict):
        return str(spec["client_document"].get("file") or "") or None
    return None


ARCHITECTURE_SECTIONS = (
    ("layers", "总体架构"),
    ("modules", "功能模块与逻辑"),
    ("dependencies", "模块依赖关系"),
    ("dataflow", "数据链路与流转"),
)


def _without_parentheses(sections: list[dict[str, Any]]) -> list[str]:
    return [f"标题「{s.get('title')}」不写括号说明" for s in sections if re.search(r"[（(）)]", str(s.get("title", "")))]


def validate_architecture(spec: Any, theme_default: str | None = None) -> list[str]:
    """The architecture book is the formal style without a contents list; it must show the whole architecture, what each module
    does, how modules depend on each other and how data moves."""
    errors = _spec_errors(spec, theme_default)
    if isinstance(spec, dict) and spec.get("style") not in ("formal", "atlas"):
        errors.append("架构图册必须是正式版：style 写 atlas（柔和配色、轻字重）或 formal")
    if isinstance(spec, dict) and spec.get("toc"):
        errors.append("架构图册不需要目录：去掉 toc")
    if isinstance(spec, dict):
        errors += _without_parentheses(spec.get("sections", []))
    if isinstance(spec, dict):
        keys = {sec.get("key") for sec in spec.get("sections", [])}
        for key, label in ARCHITECTURE_SECTIONS:
            if key not in keys:
                errors.append(f"架构图册缺少章节「{label}」（section.key = {key}）")
    if isinstance(spec, dict):
        figures = [b.get("figure") for sec in spec.get("sections", []) for b in sec.get("blocks", []) if b.get("type") == "figure"]
        if "arch_layers" not in figures:
            errors.append("系统架构图册至少需要一张分层总体架构图（figure: arch_layers）")
        # The atlas is figures and tables: no paragraphs, bullet lists, callouts or card text.
        for sec in spec.get("sections", []):
            if sec.get("lead"):
                errors.append(f"架构图册第「{sec.get('title')}」节不写导语句：用图和表表达")
            for b in sec.get("blocks", []):
                if b.get("type") not in {"figure", "table", "matrix", "gantt", "auto"}:
                    errors.append(f"架构图册第「{sec.get('title')}」节含 {b.get('type')} 块：只允许图（泳道、分层、部署）、表和矩阵，不用段落文字")
    return errors


# --- manual -----------------------------------------------------------------------------------------------------

def validate_manual(spec: Any, features: dict[str, Any]) -> list[str]:
    if not isinstance(spec, dict) or not isinstance(spec.get("chapters"), list) or not spec["chapters"]:
        return ["manual.json 需含 title 与 chapters"]
    errors, covered = [], set()
    if empty(spec.get("title")):
        errors.append("使用说明缺少 title")
    for chapter in spec["chapters"]:
        name = chapter.get("heading") or chapter.get("id") or "(无标题章节)"
        for key in ("id", "heading", "features", "entry", "steps", "rules"):
            if empty(chapter.get(key)):
                errors.append(f"章节「{name}」缺少 {key}")
        covered.update(chapter.get("features", []))
    wanted = {f["id"] for f in active_features(features)}
    missing = sorted(wanted - covered)
    if missing:
        errors.append("使用说明未覆盖功能: " + "、".join(missing[:10]) + ("…" if len(missing) > 10 else ""))
    unknown = sorted(covered - {f["id"] for f in features.get("features", [])})
    if unknown:
        errors.append("使用说明引用了不存在的功能: " + "、".join(unknown))
    if has_placeholder(spec):
        errors.append("使用说明含占位文字（待补充/TODO 等）")
    return errors


# --- build ledger (staleness) -----------------------------------------------------------------------------------

def source_digest(root: Path, rel: str) -> str | None:
    """Hash of a source file. ``file#a,b`` is the hash of only sections a and b of a JSON file (the other sections may change without making a
    document built from the file stale); a plain path is the hash of the whole file. None when the file is not there or has no such sections."""
    name, _, sections = rel.partition("#")
    path = locate(root, name)
    if not path.is_file():
        return None
    if not sections:
        return sha256_file(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    payload = {key: data.get(key) for key in sections.split(",")}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def record_build(root: Path, key: str, sources: list[Path | str], outputs: list[Path]) -> None:
    """``sources`` are files, or ``relative/path.json#section,section`` strings for a document that depends on only part of a file."""
    ledger = load(root, "client", "build.json", default={}) or {}
    rels = [p if isinstance(p, str) else relative_to_project(root, p) for p in sources]
    ledger[key] = {
        "built_at": now_iso(),
        "sources": {rel: digest for rel in rels if (digest := source_digest(root, rel)) is not None},
        "outputs": {relative_to_project(root, p): sha256_file(p) for p in outputs if p.is_file()},
    }
    save(root, ledger, "client", "build.json")


def stale_sources(root: Path, key: str) -> list[str]:
    ledger = (load(root, "client", "build.json", default={}) or {}).get(key)
    if not ledger:
        return [f"{key} 尚未生成"]
    stale = []
    for rel, digest in ledger.get("sources", {}).items():
        if not locate(root, rel.partition("#")[0]).is_file():
            stale.append(f"来源已不存在: {rel}")
        elif source_digest(root, rel) != digest:
            stale.append(f"来源已变化: {rel}")
    for rel, digest in ledger.get("outputs", {}).items():
        path = locate(root, rel)
        if not path.is_file():
            stale.append(f"成品已不存在: {rel}")
    return stale
