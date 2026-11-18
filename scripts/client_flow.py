"""Client-facing workflow of a Luz project: proposal, intake form, change ledger, acceptance checklist, manual, trace.

Every function takes the project (its state root or its project directory). Canonical data is JSON under the state root's ``data/``;
the PDF/XLSX files in the project directory's ``docs/`` are rendered from it through Luz-Design (client_render.py), registered through
project_core and refused as approval evidence when their sources changed after they were built.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import client_data as cd
import client_render as cr
import estimate_policy as ep
from project_core import (
    ProjectError,
    client_document_files,
    UPLOADS_DIR,
    REVIEW_DIR,
    deliver_root,
    locate,
    state_name,
    _load_artifacts,
    _read_json,
    _stage_record,
    _write_json,
    load_project,
    now_iso,
    register_artifact,
    require_crawl,
    set_stage_status,
    sha256_file,
)

LIBRARY = Path(__file__).resolve().parents[1] / "references" / "intake-library.json"
PENDING_WORDS = {"待定", "待确认", "待客户确认", "不确定"}
NEEDS_EDIT = {"需修改", "需要修改"}              # the function rows offer 需要修改, the project questions 需修改: both mean the client wrote a new logic


def _target(root: Path, kind: str) -> Path:
    folder, name, _ = client_document_files()[kind]
    path = deliver_root(root) / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _publish(root: Path, kind: str, built: Path, sources: list[Path | str], key: str, stage: str | None, *, template: str | None = None) -> Path:
    """Copy a checked staging file into docs/, record what it was built from and register it for its stage."""
    target = _target(root, kind)
    shutil.copyfile(built, target)
    if stage:
        template = template or ("xlsx" if kind in {"intake-form", "change-ledger", "acceptance-checklist"} or kind.endswith("xlsx") else "showcase" if kind == "architecture-pdf" else "docx-paginated")
        cr.record_template_output(root, stage, target, template, generator=f"Luz-Project/scripts/client_flow.py:{kind}")
    cd.record_build(root, key, sources, [target])
    if stage:
        register_artifact(root, stage, target, kind)
    return target


def _fresh(root: Path, key: str, outputs: list[Path], force: bool) -> bool:
    if force or not all(p.is_file() for p in outputs) or cd.stale_sources(root, key):
        return False
    # Reusing bytes also needs the writer's valid post-binding. Otherwise a
    # manual edit or a lost template record could make repeated builds keep
    # returning the same unapprovable file forever.
    from project_template_gate import output_errors
    stage = {"intake-form": "client-intake", "manual": "handover"}.get(key, key)
    return not any(output_errors(root, stage, {"path": cd.relative_to_project(root, path)}) for path in outputs)


def _require_generation_gate(root: Path, stage: str) -> None:
    """Run the matrix's prepare/produce gate before a formal client file is built.

    Client documents historically called only ``require_crawl`` and therefore
    could be rendered after a Crawl record while the stage was still missing
    its upstream approvals, rules note, or specialist fact output.  New
    document-model projects use :mod:`flow_steps` as the single source of
    truth for that ordered gate.  Projects that still use the legacy
    stage-level approval model deliberately keep their old compatibility path;
    they do not have the per-step records required by ``flow_steps`` and must
    be migrated before the stricter contract applies.
    """
    manifest = load_project(root)
    if (manifest.get("approval_policy") or {}).get("model") != "document":
        return
    import flow_steps

    errors = flow_steps.generation_errors(root, stage)
    if errors:
        raise ProjectError(
            f"生成 {stage} 阶段正式文档前，内部步骤未全部通过：" + "；".join(errors[:8])
        )


def set_theme(root: Path, theme: str) -> dict[str, Any]:
    cd.project_theme(root, {"theme": theme})
    config = cd.documents_config(root)
    config["theme"] = theme
    _write_json(root / "config" / "documents.json", config)
    return config


def intake_choices(root: Path) -> dict[str, str]:
    return (cd.load(root, "client", "intake.json", default={}) or {}).get("feature_choices", {})


def effective_features(root: Path, spec: dict[str, Any]) -> list[dict[str, Any]]:
    """In scope after the client's choices: 基础 unless declined, 可选 only when chosen (before intake: all in-scope)."""
    choices = intake_choices(root)
    out = []
    for f in cd.active_features(spec):
        choice = choices.get(f["id"])
        if choice == "不需要":
            continue
        if choices and f["tier"] == "可选" and choice != "需要":
            continue
        out.append(f)
    return out


def _scoped(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    return {**spec, "features": effective_features(root, spec)}


# --- requirements document ---------------------------------------------------------------------------------------

def draft_requirements(root: Path) -> dict[str, Any]:
    """A requirements document says what the business of the client is and what it needs, before any solution: background and pain points,
    goals, scope and users, the needs, the rules and limits, how it is accepted, and what only the client can decide."""
    name = load_project(root)["name"]

    def text_block(label: str) -> dict[str, Any]:
        return {"type": "text", "text": f"待补充：{label}"}

    need = ({"type": "auto", "what": "requirement_list"} if cd.data_path(root, "client", "features.json").is_file() else
            {"type": "table", "columns": ["编号", "需求", "具体要求", "业务规则", "类型"], "widths": [1.9, 2.2, 4, 4, 1.2], "caption": "需求清单", "rows": [["待补充"] * 5]})
    sections = [
        {"key": "background", "title": "项目背景", "blocks": [{"type": "sub", "text": "业务现状"}, text_block("客户是做什么的、现在怎么做、规模多大"), {"type": "sub", "text": "问题与痛点"},
                                                            {"type": "table", "columns": ["使用方", "现状问题", "具体表现", "带来的后果"], "caption": "按使用方的现状问题", "rows": [["待补充"] * 4]}]},
        {"key": "goals", "title": "建设目标", "blocks": [text_block("三到四个可检验的目标，各写衡量方法")]},
        {"key": "scope", "title": "范围与使用者", "blocks": [{"type": "sub", "text": "本期范围"}, text_block("本期要做的"), {"type": "sub", "text": "不在本期范围"}, text_block("明确不做的"),
                                                          {"type": "table", "columns": ["使用者", "使用端", "主要做什么"], "caption": "使用者与使用端", "rows": [["待补充"] * 3]}]},
        {"key": "requirements", "title": "需求清单", "blocks": [need]},
        {"key": "rules", "title": "业务规则与约束", "blocks": [text_block("业务规则、时间与金额口径、数据范围、合规与平台约束")]},
        {"key": "acceptance", "title": "验收标准", "blocks": [text_block("怎样算做好了：可观察的结果与验收方式")]},
        {"key": "open", "title": "需要客户确认的事项", "blocks": [{"type": "table", "columns": ["事项", "为什么需要确认", "建议的做法"], "caption": "需要客户确认的事项", "rows": [["待补充"] * 3]}]},
    ]
    return {"title": f"{name}需求说明书", "format": "word", "toc": True,
            "hero": {"info": [["项目名称", name], ["版本", "V1.0"], ["日期", date.today().isoformat()]]}, "sections": sections}


def requirements_draft(root: Path) -> list[Path]:
    """Write a draft of requirements.json when missing. The draft contains 待补充 and cannot be built."""
    require_crawl(root, "requirements", for_draft=True)
    if cd.load(root, "client", "requirements.json") is not None:
        return []
    return [cd.save(root, draft_requirements(root), "client", "requirements.json")]


def requirements_errors(root: Path) -> list[str]:
    """What stops the requirements stage and every stage after it: no requirements document, a draft, or a stale PDF.
    The own document of the client counts when requirements.json registers it (under uploads/ of the state root); otherwise we write one."""
    spec = cd.load(root, "client", "requirements.json")
    if spec is None:
        return ["没有需求文档：客户没有需求文档时先写 data/client/requirements.json 并生成 01-需求说明书.pdf（project.py client requirements-draft，填写后 project.py client requirements）；客户有自己的需求文档时在 requirements.json 的 client_document 里登记它"]
    own = cd.requirements_client_document(spec)
    if own:
        if not own.replace(chr(92), "/").startswith((f"{UPLOADS_DIR}/", f"raw/{UPLOADS_DIR}/")):
            return [f"客户自己的需求文档放在状态根的 {UPLOADS_DIR}/，现在登记的是 {own}"]
        if not locate(root, own).is_file():
            return [f"requirements.json 登记的客户需求文档不存在: {own}"]
        return []
    errors = cd.validate_requirements(spec, cd.documents_config(root).get("theme"))
    if not _registered(root, "requirements", "requirements-pdf"):
        errors.append("缺少 01-需求说明书.pdf（project.py client requirements）")
    errors += [f"需求说明书已过期: {s}（重新运行 project.py client requirements）" for s in cd.stale_sources(root, "requirements")]
    return errors


def build_requirements(root: Path, *, force: bool = False) -> list[Path]:
    """01-需求说明书.pdf: typeset as a Word document under the formal client-document standard of Luz-Design and delivered as the exported PDF."""
    require_crawl(root, "requirements")
    spec = cd.load(root, "client", "requirements.json")
    if spec is None:
        raise ProjectError("先写需求资料：project.py client requirements-draft，填写 data/client/requirements.json")
    if cd.requirements_client_document(spec):
        raise ProjectError("requirements.json 登记了客户自己的需求文档，不用再生成需求说明书；要由我们写一份，先去掉 client_document")
    theme = cd.project_theme(root, spec)
    errors = cd.validate_requirements(spec, theme)
    if errors:
        raise ProjectError("需求资料未通过: " + "; ".join(errors[:8]))
    _require_generation_gate(root, "requirements")
    sources: list[Path | str] = [cd.data_path(root, "client", "requirements.json")]
    features: dict[str, Any] = {"modules": [], "features": []}
    if any(b.get("type") == "auto" for sec in spec["sections"] for b in sec["blocks"]):
        features = _scoped(root, cd.load_features(root))             # the needs the client still wants: what was declined in the confirmation form is not a need
        sources += [cd.data_path(root, "client", "features.json"), "data/client/intake.json#feature_choices"]
    target = _target(root, "requirements-pdf")
    if _fresh(root, "requirements", [target], force):
        return [target]
    expanded = cr.expand_auto({**spec, "orientation": "portrait"}, features, theme)
    if spec.get("format", "word") == "word":
        _word, pdf = cr.build_docx(root, "requirements", expanded)
    else:
        pdf, _display = cr.build_showcase(root, "requirements", expanded)
    return [_publish(root, "requirements-pdf", pdf, sources, "requirements", "requirements", template="docx-paginated" if spec.get("format", "word") == "word" else "showcase")]


# --- proposal ---------------------------------------------------------------------------------------------------

def derive_architecture(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """A first draft of the architecture atlas from the feature list (one layered figure); edit and extend it before building."""
    features = cd.active_features(spec)
    surfaces = []
    for f in features:
        if f["surface"] not in surfaces:
            surfaces.append(f["surface"])
    front = [{"id": f"U{i}", "name": cd.SURFACES[s_], "role": "使用者在这里完成日常操作", "icon": {"miniprogram": "phone", "web-admin": "monitor", "agent": "bolt", "website": "globe"}.get(s_, "grid")} for i, s_ in enumerate(surfaces, 1)]
    modules = [{"id": f"S{i}", "name": m["name"], "role": m["summary"]} for i, m in enumerate(spec["modules"][:6], 1)]
    base = [{"id": "B1", "name": "账号与权限", "role": "登录与数据范围", "icon": "shield"}, {"id": "B2", "name": "数据存储", "role": "业务数据与备份", "icon": "database"},
            {"id": "B3", "name": "日志监控", "role": "运行状态与告警", "icon": "chart-line"}]
    flows = [{"from": front[min(i, len(front) - 1)]["id"], "to": modules[i]["id"], "n": i + 1} for i in range(min(len(front), len(modules)))]
    def table(columns: list[str], rows: list[list[str]], caption: str) -> dict[str, Any]:
        return {"type": "table", "columns": columns, "rows": rows, "caption": caption}

    return {"title": "系统架构图册", "icon": "layers", "orientation": "landscape", "style": "atlas", "sections": [
        {"key": "layers", "title": "总体架构", "blocks": [{"type": "figure", "figure": "arch_layers", "caption": "系统总体架构",
                                                           "data": {"layers": [{"name": "使用端", "icon": "phone", "nodes": front}, {"name": "业务模块", "icon": "layers", "nodes": modules}, {"name": "基础保障", "icon": "server", "nodes": base}], "flows": flows}}]},
        {"key": "modules", "title": "功能模块与逻辑", "blocks": [table(["模块", "输入", "处理逻辑", "输出", "数据保存在"], [[m["name"], "待补充", "待补充", "待补充", "待补充"] for m in spec["modules"]], "业务模块的输入、处理与输出")]},
        {"key": "dependencies", "title": "模块依赖关系", "blocks": [table(["被依赖的对象", "被谁使用", "它不可用时的影响"], [[m["name"], "待补充", "待补充"] for m in spec["modules"][:6]], "被依赖对象与影响")]},
        {"key": "dataflow", "title": "数据链路与流转", "blocks": [table(["数据", "产生于", "经过", "保存在", "被谁使用"], [["待补充", "待补充", "待补充", "待补充", "待补充"]], "主要数据的来源、去向与保存位置")]}]}


def draft_proposal(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """A proposal analyses the client's need and gives the solution: background and needs, goals, the solution (systems, roles, flow, functions and
    their logic, rules) and what is delivered."""
    def text_block(label: str) -> dict[str, Any]:
        return {"type": "text", "text": f"待补充：{label}"}

    sections = [
        {"key": "background", "title": "项目背景与需求分析", "blocks": [{"type": "sub", "text": "业务现状"}, text_block("客户现状与痛点"), {"type": "sub", "text": "需求分析"},
                                                                  {"type": "table", "columns": ["使用方", "现状与痛点", "核心需求", "解决方式"], "caption": "按使用方的需求分析", "rows": [["待补充", "待补充", "待补充", "待补充"]]}]},
        {"key": "goals", "title": "建设目标", "blocks": [text_block("三到四个可检验的目标")]},
        {"key": "solution", "title": "解决方案", "blocks": [text_block("总体思路"), {"type": "sub", "text": "系统构成"}, {"type": "table", "columns": ["系统", "使用者", "解决什么问题", "主要功能模块"], "caption": "系统构成", "rows": [["待补充", "待补充", "待补充", "待补充"]]},
                                                          {"type": "sub", "text": "角色与权限"}, {"type": "sub", "text": "业务流程"}, {"type": "sub", "text": "各系统功能与业务逻辑"}, {"type": "sub", "text": "统一业务规则"}]},
        {"key": "deliverables", "title": "交付内容", "blocks": [text_block("交付物、工期与费用约定")]}]
    return {"title": "待补充", "subtitle": "建设方案", "format": "word", "toc": True,
            "hero": {"info": [["项目名称", "待补充"], ["版本", "V1.0"], ["日期", "待补充"]]}, "sections": sections}


def proposal_draft(root: Path) -> list[Path]:
    """Write drafts of proposal.json / architecture.json when missing. Drafts contain 待补充 and cannot be built."""
    require_crawl(root, "proposal", for_draft=True)
    spec = cd.load_features(root)
    written = []
    if cd.load(root, "client", "proposal.json") is None:
        written.append(cd.save(root, draft_proposal(root, spec), "client", "proposal.json"))
    if cd.load(root, "client", "architecture.json") is None:
        written.append(cd.save(root, derive_architecture(root, spec), "client", "architecture.json"))
    return written


def build_proposal(root: Path, *, force: bool = False) -> list[Path]:
    """Two client PDFs (proposal, architecture atlas) and the feature list as one Excel sheet."""
    require_crawl(root, "proposal")
    missing = requirements_errors(root)
    if missing:
        raise ProjectError("方案之前要先有需求文档: " + "; ".join(missing[:3]))
    _require_generation_gate(root, "proposal")
    features = cd.load_features(root)
    theme = cd.project_theme(root, cd.load(root, "client", "proposal.json") or {})
    proposal = cd.load(root, "client", "proposal.json")
    architecture = cd.load(root, "client", "architecture.json")
    errors = cd.validate_proposal(proposal, theme) + cd.validate_architecture(architecture, theme)
    if errors:
        raise ProjectError("方案资料未通过: " + "; ".join(errors[:8]))
    sources: list[Path | str] = [cd.data_path(root, "client", n) for n in ("features.json", "proposal.json", "architecture.json")]
    sources.append(ESTIMATE_SOURCE)                           # the switches (with their evidence) the function list is written under: turning one on or off makes the files stale
    estimate = cd.estimate_state(root)
    blocked = estimate_build_errors(root, estimate, features)
    if blocked:
        raise ProjectError("；".join(blocked))
    quote = estimate.quote_data if estimate.quote else None                    # a quote.json that was not asked for is not read
    if quote:
        sources.append(cd.data_path(root, "client", "quote.json"))
    word = proposal.get("format", "word") == "word"            # the proposal is typeset as a Word document and delivered as the PDF exported from it
    kinds = ["proposal-pdf", "architecture-pdf", "feature-list-xlsx"]
    outputs = [_target(root, k) for k in kinds]
    if _fresh(root, "proposal", outputs, force):
        return outputs
    project_name = load_project(root)["name"]
    proposal_spec = cr.expand_auto({**proposal, "orientation": "portrait"}, features, theme)
    built: dict[str, Path] = {}
    if word:
        _word, built["proposal-pdf"] = cr.build_docx(root, "proposal", proposal_spec)
    else:
        built["proposal-pdf"], _display = cr.build_showcase(root, "proposal", proposal_spec)
    built["architecture-pdf"], _display = cr.build_showcase(root, "architecture", cr.expand_auto({**architecture, "orientation": "landscape"}, features, theme))
    built["feature-list-xlsx"] = cr.build_xlsx(root, "feature-list", cr.feature_list_xlsx_spec(features, project_name, theme, quote, version=cd.document_version(root), day=today_cn(),
                                                                                              estimate=estimate.render_block()))
    paths = []
    for kind in kinds:
        target = _target(root, kind)
        shutil.copyfile(built[kind], target)
        template = "xlsx" if kind == "feature-list-xlsx" else "showcase" if kind == "architecture-pdf" or not word else "docx-paginated"
        cr.record_template_output(root, "proposal", target, template, generator=f"Luz-Project/scripts/client_flow.py:{kind}")
        paths.append(target)
    cd.record_build(root, "proposal", sources, paths)
    for path, kind in zip(paths, kinds):
        register_artifact(root, "proposal", path, kind)
    from project_core import unregister_artifacts
    unregister_artifacts(root, {"feature-list-pdf", "proposal-showcase", "architecture-showcase", "feature-list-showcase", "proposal-docx"})
    return paths


# --- intake form ------------------------------------------------------------------------------------------------

def _qkey(category: str, item: str) -> str:
    return f"{category}/{item}"


IMPACT = {
    "企业与主体信息": "全程", "品牌与视觉素材": "界面设计", "经营信息与规则": "业务规则", "会员、积分与营销规则": "业务规则",
    "预约与服务规则": "业务规则", "微信小程序账号与上线资料": "小程序上线", "支付与结算": "支付上线", "消息通知": "消息模板",
    "管理后台与人员权限": "权限设计", "智能体与自动化": "智能体配置", "规则、核算与定时任务": "规则配置", "域名、服务器与第三方": "部署",
    "现场硬件": "硬件选型", "验收与运维": "验收上线",
}


def _normalize_question(q: dict[str, Any], *, default_priority: str | None = None) -> dict[str, Any]:
    """One shape for library, project-specific and feature questions: priority, default, impact and basis travel with the question."""
    kind = q.get("kind") or ("logic" if q.get("feature_id") else "info")
    priority = q.get("priority") or ("必须" if q.get("required", True) else "建议") if default_priority is None else q.get("priority", default_priority)
    return {
        "category": q["category"], "item": q["item"], "example": q.get("example") or q.get("hint", ""), "method": q.get("method") or ("单选" if kind == "logic" else "文本"), "kind": kind,
        "options": list(q.get("options", [])) or (["确认", "需修改"] if kind == "logic" else []),
        "priority": priority, "required": priority == "必须", "default": "" if kind == "logic" or str(q.get("default", "")).strip() in {"无", "—", "-"} else q.get("default", ""), "impact": q.get("impact") or IMPACT.get(q["category"], "全程"),
        "why": q.get("why", ""), "basis": q.get("basis", ""), "features": list(q.get("features", [])), **({"feature_id": q["feature_id"]} if q.get("feature_id") else {}), **({"sheet": q["sheet"]} if q.get("sheet") else {}),
    }


SEP = " · "
SHEET_BUSINESS, SHEET_SETUP = "业务逻辑确认", "需要提供的资料"


def sheet_of(q: dict[str, Any]) -> str:
    """A logic question (a proposed business logic the client confirms or changes) goes to the first sheet; what only the client can provide, to the second."""
    return q.get("sheet") or (SHEET_BUSINESS if q["kind"] == "logic" else SHEET_SETUP)


def split_category(category: str) -> tuple[str, str]:
    """Internal category 'main · sub' -> the two sheet columns; a category without a sub-category shows 通用."""
    main, _, sub = category.partition(SEP)
    return main, sub or "通用"


def join_category(main: str, sub: str) -> str:
    return main if sub in ("", "通用") else f"{main}{SEP}{sub}"


def intake_questions(root: Path, features: dict[str, Any], *, include_all: bool = False) -> list[dict[str, Any]]:
    lib = json.loads(LIBRARY.read_text(encoding="utf-8"))
    active = cd.active_features(features)
    surfaces = {f["surface"] for f in active}
    tags = {t for f in active for t in f.get("tags", [])}
    extra_raw = cd.load(root, "client", "intake-extra.json", default=[]) or []
    extra = extra_raw.get("questions", []) if isinstance(extra_raw, dict) else extra_raw
    excluded = set(extra_raw.get("exclude", [])) if isinstance(extra_raw, dict) else set()
    # intake-extra.json {"library": "tagged" (default) | "all" | "none" | ["分类/信息项", …]} decides how much of the generic bank is used
    mode = extra_raw.get("library", "none") if isinstance(extra_raw, dict) else "none"      # the generic bank asks what every project asks: only on request
    out = []
    for q in lib["questions"]:
        key = _qkey(q["category"], q["item"])
        s_ok = q["surfaces"] is None or bool(surfaces & set(q["surfaces"]))
        t_ok = q["tags"] is None or bool(tags & set(q["tags"]))
        if isinstance(mode, list):
            wanted = key in mode
        elif mode == "none":
            wanted = False
        else:
            wanted = include_all or mode == "all" or (s_ok and t_ok)
        if wanted and key not in excluded:
            out.append(_normalize_question(q))
    out += [_normalize_question(q) for q in extra]
    module_names = {m["id"]: m["name"] for m in features["modules"]}
    for f in cr.ordered_features(features):          # one row per function: its concrete rules, written out for the client to confirm
        lines = [x.strip() for x in re.split(r"[；;。]", f["rules"]) if x.strip()]
        rules = "\n".join(f"{k}. {line}" for k, line in enumerate(lines, 1))
        options = ["确认", "需要修改", "不需要此功能"] if f["tier"] == "基础" else ["需要", "不需要", "待定"]
        out.append(_normalize_question({"category": f"{'、'.join(f['roles'])}{SEP}{module_names.get(f['module'], f['module'])}", "item": f["name"], "example": rules,
                                       "why": f["summary"], "kind": "logic", "method": "单选", "options": options, "priority": "必须", "default": "确认" if f["tier"] == "基础" else "",
                                       "basis": f["id"], "features": [f["id"]], "feature_id": f["id"]}))
    for q in out:
        if not q.get("feature_id") and not q.get("why"):
            raise ProjectError(f"确认表问题缺少说明与理由（why）: {q['category']}/{q['item']}")
    seen = set()
    for q in out:
        key = _qkey(q["category"], q["item"])
        if key in seen:
            raise ProjectError(f"确认表问题重复: {key}")
        seen.add(key)
    return _ordered(out, lib["categories"], {q["category"] for q in extra})


def _ordered(questions: list[dict[str, Any]], lib_categories: list[str], extra_categories: set[str]) -> list[dict[str, Any]]:
    """Business-logic questions first, then account and deployment questions; inside each sheet a category is one consecutive block."""
    return _order_one([q for q in questions if sheet_of(q) == SHEET_BUSINESS], lib_categories, extra_categories) + \
        _order_one([q for q in questions if sheet_of(q) == SHEET_SETUP], lib_categories, extra_categories)


def _order_one(questions: list[dict[str, Any]], lib_categories: list[str], extra_categories: set[str]) -> list[dict[str, Any]]:
    """Reading order inside one sheet: the rules of each function / 主体信息 → generic bank → project blocks → 验收与运维; big category before sub-category."""
    def rank(q: dict[str, Any]) -> tuple[int, int]:
        main = split_category(q["category"])[0]
        if main == "企业与主体信息":
            return (0, 1)
        if q.get("feature_id"):
            return (0, 0)
        if main == "验收与运维":
            return (4, 0)
        if main in lib_categories and main not in {split_category(c)[0] for c in extra_categories}:
            return (1, lib_categories.index(main))
        return (2, 0)

    ordered = sorted(questions, key=rank)  # stable: project blocks keep the order they were written in
    first_seen: dict[str, int] = {}
    for q in ordered:
        first_seen.setdefault(q["category"], len(first_seen))
    main_seen: dict[str, int] = {}
    for q in ordered:
        main_seen.setdefault(split_category(q["category"])[0], len(main_seen))
    # big group first (same main category stays together), then its sub-categories in the order written
    return sorted(ordered, key=lambda q: (main_seen[split_category(q["category"])[0]], first_seen[q["category"]]))


def _list_formula(options: list[str]) -> bool:
    return bool(options) and len('"' + ",".join(options) + '"') <= 255 and not any("," in o for o in options)


def build_intake_form(root: Path, *, force: bool = False, include_all: bool = False) -> Path:
    require_crawl(root, "client-intake")
    _require_generation_gate(root, "client-intake")
    features = cd.load_features(root)
    theme = cd.project_theme(root)
    project = load_project(root)
    out = _target(root, "intake-form")
    sources = [cd.data_path(root, "client", "features.json")]
    extra = cd.data_path(root, "client", "intake-extra.json")
    if extra.is_file():
        sources.append(extra)
    if _fresh(root, "intake-form", [out], force):
        return out
    questions = intake_questions(root, features, include_all=include_all)
    sheets, lists = [], {}
    title = f"{project['name']} 业务逻辑确认表"
    for name, heading in ((SHEET_BUSINESS, "一、业务逻辑确认"), (SHEET_SETUP, "二、需要提供的资料")):
        logic = name == SHEET_BUSINESS
        rows, per_sheet = [], {}
        for q in (x for x in questions if sheet_of(x) == name):
            shown = q["example"] or " / ".join(q["options"]) or "—"
            main, sub = split_category(q["category"])
            if q["options"] and q["method"] == "单选" and _list_formula(q["options"]):
                per_sheet[len(rows)] = q["options"]
            if logic:
                rows.append([main, sub, q["item"], shown, q.get("why") or "—", q["default"], ""])
            else:
                rows.append([main, sub, q["item"], shown, q.get("why") or "—", q["default"], "必填" if q["required"] else "选填"])
        if rows:
            lists[name] = per_sheet
            groups = [{"name": "分类", "merge": True}, {"name": "子类", "merge": True}]
            columns = groups + ([{"name": "业务逻辑"}, {"name": "拟定逻辑", "type": "longtext"}, {"name": "说明与理由", "type": "longtext"}, {"name": "审核结果"}, {"name": "修改后的逻辑", "type": "longtext"}] if logic else
                                [{"name": "需要提供的内容"}, {"name": "示例", "type": "longtext"}, {"name": "为什么需要", "type": "longtext"}, {"name": "客户填写", "type": "longtext"}, {"name": "必填"}])
            sheets.append({"sheet": name, "title": f"{project['name']} {'业务逻辑确认表' if logic else '需要提供的资料'}", "columns": columns, "rows": rows})
    spec = {"title": title, "theme": theme, "sheets": sheets}
    built = cr.build_xlsx(root, "intake-form", spec, pick_column=["审核结果", "修改后的逻辑", "客户填写"], row_lists=lists)
    published = _publish(root, "intake-form", built, sources, "intake-form", "client-intake")
    cd.save(root, {"built_at": now_iso(), "questions": questions, "answers": {}, "feature_choices": {}, "deferred": {}, "imported_at": None}, "client", "intake.json")
    return published


def import_intake(root: Path, xlsx: Path) -> dict[str, Any]:
    """Read the client's filled form back into data/client/intake.json: the verdict on each proposed logic (and the logic they wrote instead)
    and the information they provided, keyed by 分类/业务逻辑 or 分类/需要提供的内容."""
    from openpyxl import load_workbook

    intake = cd.load(root, "client", "intake.json")
    if not intake:
        raise ProjectError("尚未生成确认表（project.py client intake-form）")
    answers: dict[str, str] = {}
    edits: dict[str, str] = {}
    found = False
    for ws in load_workbook(xlsx, data_only=True).worksheets:
        header_row = next((r for r in range(1, 8) if any(c.value in ("业务逻辑", "需要提供的内容") for c in ws[r])), None)
        if header_row is None:
            continue
        found = True
        index = {c.value: c.column for c in ws[header_row]}
        item_col = index.get("业务逻辑") or index["需要提供的内容"]
        answer_col = index.get("审核结果") or index.get("客户填写")
        if "分类" not in index or not answer_col:
            raise ProjectError(f"回填表「{ws.title}」缺少列（分类、业务逻辑或需要提供的内容、审核结果或客户填写）")
        main, sub = None, None
        for r in range(header_row + 1, ws.max_row + 1):
            main = ws.cell(r, index["分类"]).value or main
            sub = (ws.cell(r, index["子类"]).value if "子类" in index else None) or sub
            item = ws.cell(r, item_col).value
            if not item or not main:
                continue
            key = _qkey(join_category(str(main), str(sub or "通用")), str(item))
            value = ws.cell(r, answer_col).value
            if value is not None and str(value).strip():
                answers[key] = str(value).strip()
            if "修改后的逻辑" in index:
                changed = ws.cell(r, index["修改后的逻辑"]).value
                if changed is not None and str(changed).strip():
                    edits[key] = str(changed).strip()
    if not found:
        raise ProjectError("回填表缺少“业务逻辑”或“需要提供的内容”表头，不是本系统生成的确认表")
    keys = {_qkey(q["category"], q["item"]) for q in intake["questions"]}
    unknown = sorted(set(answers) - keys)
    if unknown:
        raise ProjectError("回填表含确认表里没有的问题（表格被改动？）: " + "；".join(unknown[:4]))
    choices = {}
    for q in intake["questions"]:
        if not q.get("feature_id"):
            continue
        key = _qkey(q["category"], q["item"])
        answer = answers.get(key, "")
        if answer in ("确认", "需要"):
            choices[q["feature_id"]] = "需要"
        elif answer.startswith("不需要"):
            choices[q["feature_id"]] = "不需要"
        elif answer in PENDING_WORDS:
            choices[q["feature_id"]] = "待定"
        elif answer in NEEDS_EDIT:                       # the function stays; the logic the client wrote is a pending change
            choices[q["feature_id"]] = "需要"
    intake.update({"answers": answers, "logic_edits": edits, "feature_choices": choices, "imported_at": now_iso(), "response_sha256": sha256_file(xlsx)})
    target = _target(root, "intake-response")
    shutil.copyfile(xlsx, target)
    cd.save(root, intake, "client", "intake.json")
    register_artifact(root, "client-intake", target, "intake-response")
    log_choice_changes(root, intake)
    log_rule_edits(root, intake)
    log_extra_scope(root, intake)
    return intake_status(root)


def log_choice_changes(root: Path, intake: dict[str, Any]) -> None:
    """Choices that differ from the proposal baseline (declined 基础, chosen 可选) are written to the change ledger once."""
    features = cd.load_features(root)
    module_names = {m["id"]: m["name"] for m in features.get("modules", [])}
    ledger = _ledger(root)
    logged = {(c.get("refs", [None])[0], c["title"]) for c in ledger["changes"] if c.get("auto") == "intake"}
    for f in cd.active_features(features):
        choice = intake.get("feature_choices", {}).get(f["id"])
        if f["tier"] == "基础" and choice == "不需要":
            kind, title, older = "删除", f"客户放弃基础功能：{f['name']}", f"客户在业务逻辑确认表中放弃基础功能：{f['name']}"
        elif f["tier"] == "可选" and choice == "需要":
            kind, title, older = "新增", f"客户选择可选功能：{f['name']}", None
        else:
            continue
        if (f["id"], title) in logged or (f["id"], older) in logged:      # the older wording named a client file; projects that already logged it keep their entry
            continue
        module = module_names.get(f["module"], f["module"])
        add_change(root, type=kind, category="范围", title=title, detail=f"客户在确认业务逻辑时{'放弃了' if kind == '删除' else '选择了'}该功能（所属模块：{module}）；功能规则：{f['rules']}", source="客户", requester="客户", refs=[f["id"]], affects=["architecture"],
                   status="已确认", auto="intake", reopen=False, note="来自业务逻辑确认表的功能勾选")


def log_rule_edits(root: Path, intake: dict[str, Any]) -> None:
    """A business logic the client changed (审核结果“需修改” plus the logic they wrote) is a pending change: cost and schedule are confirmed before it is built."""
    ledger = _ledger(root)
    logged = {c["title"] for c in ledger["changes"] if c.get("auto") == "intake-rule"}
    for q in intake.get("questions", []):
        key = _qkey(q["category"], q["item"])
        text = intake.get("logic_edits", {}).get(key)
        if intake.get("answers", {}).get(key) not in NEEDS_EDIT or not text:
            continue
        title = f"客户要求修改业务逻辑：{q['item']}"
        if title not in logged:
            add_change(root, type="修改", category="规则", title=title, detail=f"拟定逻辑：{q['example']}；客户修改为：{text}", source="客户", requester="客户",
                       refs=q.get("features", []), affects=["proposal"], status="待确认", auto="intake-rule", reopen=False, note="来自业务逻辑确认表的回填")


def log_extra_scope(root: Path, intake: dict[str, Any]) -> None:
    """An answer that picks an option marked 超出范围 is a pending change: it needs the client's confirmation of cost and schedule."""
    ledger = _ledger(root)
    logged = {c["title"] for c in ledger["changes"] if c.get("auto") == "intake-scope"}
    for q in intake.get("questions", []):
        answer = intake.get("answers", {}).get(_qkey(q["category"], q["item"]), "")
        if "超出范围" in answer or "超出 MVP" in answer:
            title = f"客户选择超出范围的方案：{q['item']}"
            if title not in logged:
                add_change(root, type="修改", category="范围", title=title, detail=f"客户在确认业务逻辑时选择：{answer}。需评估费用与工期后确认。", source="客户", requester="客户", refs=q.get("features", []), affects=["proposal"], status="待确认", auto="intake-scope", reopen=False, note="来自业务逻辑确认表的回填")


def intake_status(root: Path) -> dict[str, Any]:
    intake = cd.load(root, "client", "intake.json") or {}
    answers, deferred = intake.get("answers", {}), intake.get("deferred", {})
    missing, pending = [], []
    for q in intake.get("questions", []):
        key = _qkey(q["category"], q["item"])
        value = answers.get(key, "")
        if value in NEEDS_EDIT and not intake.get("logic_edits", {}).get(key):
            value = ""                                   # asked for a change but did not write the new logic
        if not value or value in PENDING_WORDS:
            if key in deferred:
                continue
            (missing if q["required"] else pending).append(key)
    return {"total": len(intake.get("questions", [])), "answered": len(answers), "missing_required": missing, "unanswered_optional": len(pending), "deferred": list(deferred), "imported_at": intake.get("imported_at")}


def defer_intake(root: Path, key: str, owner: str, due: str, note: str) -> None:
    intake = cd.load(root, "client", "intake.json")
    if not intake or key not in {_qkey(q["category"], q["item"]) for q in intake["questions"]}:
        raise ProjectError(f"确认表里没有这个问题: {key}（格式：分类/信息项）")
    intake.setdefault("deferred", {})[key] = {"owner": owner, "due": due, "note": note, "at": now_iso()}
    cd.save(root, intake, "client", "intake.json")


INTAKE_DEVELOPMENT_STAGES = ["architecture", "design", "technical-plan", "implementation"]


def _deferral_change_digest(change: dict[str, Any]) -> str:
    fields = ("id", "type", "category", "title", "detail", "source", "requester", "affects", "confirmed_by", "confirmed_at")
    return hashlib.sha256(json.dumps({k: change.get(k) for k in fields}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def intake_deferral_state(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """A transparent, project-bound development exception, never client answers."""
    record = cd.load(root, "client", "intake-deferral.json")
    if record is None:
        return None, []
    errors = []
    if not isinstance(record, dict):
        return None, ["暂缓回填授权记录格式无效"]
    if record.get("schema") != "luz-intake-deferral/v1" or record.get("mode") != "deferred-development":
        errors.append("暂缓回填授权类型无效")
    if record.get("project_id") != load_project(root)["project_id"] or record.get("allowed_stages") != INTAKE_DEVELOPMENT_STAGES:
        errors.append("暂缓回填授权的项目或阶段范围不一致")
    by, note = record.get("authorized_by"), record.get("user_statement")
    if not isinstance(by, str) or not by.strip() or not isinstance(note, str) or not note.strip() or not record.get("authorized_at"):
        errors.append("暂缓回填授权缺少用户及原话")
    change = next((c for c in _ledger(root)["changes"] if c.get("id") == record.get("change_id")), None)
    if not change or change.get("status") not in {"已确认", "已实施"} or change.get("source") != "客户" or change.get("confirmed_by") != by:
        errors.append("暂缓回填授权没有对应的有效用户变更")
    elif _deferral_change_digest(change) != record.get("change_sha256") or not isinstance(note, str) or not note or note not in change.get("note", ""):
        errors.append("暂缓回填授权与用户变更依据不一致")
    form = _registered(root, "client-intake", "intake-form")
    path = locate(root, form["path"]) if form else None
    if not path or not path.is_file() or sha256_file(path) != record.get("form_sha256") or form.get("sha256") != record.get("form_sha256"):
        errors.append("暂缓回填授权绑定的确认表已变化")
    return record, errors


def authorize_intake_deferral(root: Path, change_id: str, by: str, note: str) -> dict[str, Any]:
    """Record an explicitly confirmed human instruction; do not import a workbook."""
    if not by.strip() or not note.strip():
        raise ProjectError("暂缓回填必须提供用户及其明确原话")
    change = next((c for c in _ledger(root)["changes"] if c.get("id") == change_id), None)
    if not change or change.get("status") not in {"已确认", "已实施"} or change.get("source") != "客户" or change.get("confirmed_by") != by or note not in change.get("note", "") or "client-intake" not in change.get("affects", []):
        raise ProjectError("请先登记相同用户已确认、影响 client-intake 的变更及授权原话")
    form = _registered(root, "client-intake", "intake-form")
    path = locate(root, form["path"]) if form else None
    if not path or not path.is_file() or form["sha256"] != sha256_file(path):
        raise ProjectError("暂缓回填需要已登记且哈希一致的确认表")
    old, errors = intake_deferral_state(root)
    if old and not errors and old.get("change_id") == change_id and old.get("user_statement") == note:
        return old
    record = {
        "schema": "luz-intake-deferral/v1", "mode": "deferred-development",
        "project_id": load_project(root)["project_id"], "change_id": change_id,
        "change_sha256": _deferral_change_digest(change), "form_sha256": sha256_file(path),
        "authorized_by": by, "authorized_at": now_iso(), "user_statement": note,
        "allowed_stages": list(INTAKE_DEVELOPMENT_STAGES),
        "recheck_before": "真实业务数据联调及验收；未提供资料仍为未确认，不生成客户答案",
        "unanswered_at_authorization": intake_status(root)["missing_required"],
    }
    cd.save(root, record, "client", "intake-deferral.json")
    return record


def _real_intake_ready(root: Path) -> bool:
    intake = cd.load(root, "client", "intake.json") or {}
    response = _registered(root, "client-intake", "intake-response")
    if not intake.get("imported_at") or not response or not locate(root, response["path"]).is_file():
        return False
    for q in intake.get("questions", []):
        if not q.get("required"):
            continue
        key = _qkey(q["category"], q["item"])
        value = intake.get("answers", {}).get(key, "")
        if not value or value in PENDING_WORDS or (value in NEEDS_EDIT and not intake.get("logic_edits", {}).get(key)):
            return False
    return True


# --- change ledger ----------------------------------------------------------------------------------------------

def _ledger(root: Path) -> dict[str, Any]:
    ledger = cd.load(root, "changes.json", default=None)
    if ledger is None:
        ledger = {"schema_version": "1.0", "changes": []}
    return ledger


def _next_change_id(ledger: dict[str, Any]) -> str:
    nums = [int(m.group(1)) for c in ledger["changes"] if (m := re.search(r"(\d+)$", c["id"]))]
    return f"CHG-{max(nums, default=0) + 1:03d}"


NL = chr(10)
FN_ID = re.compile(r"FN-\d+")                          # the function ids stay in the data files; the client reads the function names
CN_TZ = timezone(timedelta(hours=8))                    # the ledger's dates are Beijing dates; confirmed_at is stored in UTC
LEGACY_LOG_LINE = re.compile(r"^\[\d{4}-\d{2}-\d{2}\]\s")   # older versions appended "[date] note" lines to detail; they are process logs, not client text


def today_cn() -> str:
    return datetime.now(CN_TZ).date().isoformat()


def cn_date(iso: str | None) -> date | None:
    """The Beijing calendar date of a stored UTC timestamp (2026-11-03T23:15:54Z -> 2026-11-04)."""
    if not iso:
        return None
    moment = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(CN_TZ).date()


def is_client_visible(entry: dict[str, Any]) -> bool:
    """Explicit ``client_visible`` wins; otherwise the client's own functional / rule / scope changes are visible and everything else is internal."""
    explicit = entry.get("client_visible")
    if isinstance(explicit, bool):
        return explicit
    return entry.get("source") in cd.CLIENT_VISIBLE_SOURCES and entry.get("category") in cd.CLIENT_VISIBLE_CATEGORIES


# Entries the intake logged before 2026-11 quoted the client file and the module number in the text the client reads; they are shown without them.
LEGACY_AUTO_PREFIX = re.compile(r"^来自业务逻辑确认表的功能勾选（[^）]*）；")
LEGACY_AUTO_TITLE = "客户在业务逻辑确认表中放弃基础功能："


def client_detail(entry: dict[str, Any]) -> str:
    """detail as the client reads it: without the process-log lines older versions appended (logs belong in ``note``)."""
    lines = [line for line in str(entry.get("detail", "")).split(NL) if not LEGACY_LOG_LINE.match(line)]
    text = NL.join(lines).strip()
    if entry.get("auto") == "intake":
        text = LEGACY_AUTO_PREFIX.sub("客户在确认业务逻辑时" + ("放弃了" if entry.get("type") == "删除" else "选择了") + "该功能；", text)
    return text


def client_title(entry: dict[str, Any]) -> str:
    title = str(entry.get("title", ""))
    return "客户放弃基础功能：" + title[len(LEGACY_AUTO_TITLE):] if entry.get("auto") == "intake" and title.startswith(LEGACY_AUTO_TITLE) else title


def client_requester(entry: dict[str, Any]) -> str:
    requester = str(entry.get("requester", ""))
    return "客户" if entry.get("auto", "") and requester == "客户（业务逻辑确认表）" else requester


def client_text_issues(entry: dict[str, Any], root: Path | None = None) -> list[str]:
    """What must not reach the client in a visible entry: internal numbers (approvals, baseline items), the names of other client files and, unless the project
    asked for them (config/documents.json ``estimate``), person-days and prices."""
    text = NL.join([client_title(entry), client_detail(entry), entry.get("impact", "") or "", client_requester(entry)])
    problems = []
    if cd.INTERNAL_TOKENS.search(text):
        problems.append("内部编号 " + "、".join(sorted(set(cd.INTERNAL_TOKENS.findall(text)))[:4]))
    if cd.OTHER_FILES.search(text):
        problems.append("其他文件的名称（《…》）")
    if root is not None:
        state = cd.estimate_state(root)
        allowed = ep.project_allowed_terms(root)
        if not state.quote and cd.money_issues(text, allow=allowed):
            problems.append("金额：" + "、".join(cd.money_issues(text, allow=allowed)[:4]) + "（本项目没有人工报价，客户文件不出现金额）")
        if not state.workdays and ep.workday_issues(text, allowed):
            problems.append("人天：" + "、".join(ep.workday_issues(text, allowed)[:4]) + "（本项目没有要求写人日，客户文件不出现人天和工时）")
    return problems


def _require_client_text(entry: dict[str, Any], root: Path | None = None) -> None:
    if is_client_visible(entry):
        problems = client_text_issues(entry, root)
        if problems:
            raise ProjectError(f"{entry['id']} 会出现在交给客户的台账里，不能含{'；'.join(problems)}：改写成客户的话，过程与出处写进 --note，或标 --client-visible 否（内部变更不进客户台账）")


def _append_note(entry: dict[str, Any], text: str) -> None:
    if text:
        entry["note"] = (entry["note"] + NL if entry.get("note") else "") + f"[{today_cn()}] {text}"


def add_change(root: Path, *, type: str, category: str, title: str, detail: str, source: str, requester: str, refs: list[str] | None = None,
               affects: list[str] | None = None, impact: str = "", status: str = "待确认", feature_ops: list[dict[str, Any]] | None = None,
               auto: str | None = None, reopen: bool = True, confirmed_by: str | None = None, client_visible: bool | None = None, note: str = "") -> dict[str, Any]:
    from project_core import _stage_defs

    if type not in cd.CHANGE_TYPES or category not in cd.CHANGE_CATEGORIES or source not in cd.CHANGE_SOURCES or status not in cd.CHANGE_STATUSES:
        raise ProjectError(f"变更字段无效。类型{cd.CHANGE_TYPES} 分类{cd.CHANGE_CATEGORIES} 来源{cd.CHANGE_SOURCES} 状态{cd.CHANGE_STATUSES}")
    if not title.strip() or not detail.strip():
        raise ProjectError("变更必须写清标题和逻辑/细节（detail），不能只写“修改规则”")
    stages = _stage_defs()
    if feature_ops and not affects:
        affects = ["proposal"]  # a feature-list change always reopens the approved proposal
    for s in affects or []:
        if s not in stages:
            raise ProjectError(f"未知阶段: {s}")
    if status == "已确认" and not (confirmed_by or auto):
        raise ProjectError("已确认的变更需要 --confirmed-by（谁确认的）")
    ledger = _ledger(root)
    entry = {"id": _next_change_id(ledger), "date": today_cn(), "type": type, "category": category, "title": title.strip(), "detail": detail.strip(), "source": source, "requester": requester, "refs": refs or [], "affects": affects or [], "impact": impact, "status": status, "confirmed_by": confirmed_by, "confirmed_at": now_iso() if status == "已确认" else None, "feature_ops": feature_ops or [], "reopened": [], "auto": auto}
    if client_visible is not None:
        entry["client_visible"] = bool(client_visible)
    _append_note(entry, note.strip())
    if not auto:                                              # auto entries quote what the client wrote in the form; hand-written ones are checked
        _require_client_text(entry, root)
    ledger["changes"].append(entry)
    if status == "已确认":
        _apply_confirmed(root, entry, reopen)
    cd.save(root, ledger, "changes.json")
    return {**entry, "ledger_render": _refresh_ledger(root)}


def _approved_files(root: Path, stage: str) -> bool:
    """A stage approved by document is touched by a change as soon as one of its files (or its internal completion, or an action) has an effective approval, not only when the whole stage is approved."""
    import approval_docs

    if not approval_docs.is_document_model(root):
        return False
    ctx = approval_docs.Ctx(root)
    return any(approval_docs.effective_record(ctx, "document", document=d["path"])[0] for d in approval_docs.documents(root, stage)) or approval_docs.stage_record_effective(ctx, stage)


def _apply_confirmed(root: Path, entry: dict[str, Any], reopen: bool) -> None:
    if entry.get("feature_ops"):
        apply_feature_ops(root, entry)
    if not reopen:
        return
    manifest = load_project(root)
    order = [s["id"] for s in manifest["stages"]]
    hit = [s for s in entry["affects"] if _stage_record(manifest, s).get("status") in {"approved", "completed"} or _stage_record(manifest, s).get("approval_id") or _approved_files(root, s)]
    if hit:
        first = min(hit, key=order.index)
        set_stage_status(root, first, "pending-review")
        entry["reopened"] = [s for s in order[order.index(first):] if s in entry["affects"] or s == first]


def _reopen_added(root: Path, entry: dict[str, Any], added: list[str]) -> None:
    """A confirmed change that later names one more stage reopens that stage too, when it is approved (the earliest of them; the hash chain voids what follows)."""
    manifest = load_project(root)
    order = [s["id"] for s in manifest["stages"]]
    hit = [s for s in added if _stage_record(manifest, s).get("status") in {"approved", "completed"} or _stage_record(manifest, s).get("approval_id") or _approved_files(root, s)]
    if not hit:
        return
    first = min(hit, key=order.index)
    set_stage_status(root, first, "pending-review")
    entry["reopened"] = list(dict.fromkeys(entry.get("reopened", []) + [s for s in order[order.index(first):] if s in entry["affects"] or s == first]))


def apply_feature_ops(root: Path, entry: dict[str, Any]) -> None:
    spec = cd.load_features(root, validate=False)
    by_id = {f["id"]: f for f in spec["features"]}
    for op in entry["feature_ops"]:
        kind, feature = op.get("op"), op.get("feature", {})
        fid = feature.get("id")
        if kind == "add":
            if fid in by_id:
                raise ProjectError(f"功能已存在: {fid}")
            spec["features"].append({**feature, "status": "in-scope", "version": 1, "history": [entry["id"]]})
        elif kind in {"update", "remove"}:
            if fid not in by_id:
                raise ProjectError(f"功能不存在: {fid}")
            target = by_id[fid]
            target.update(feature if kind == "update" else {"status": "removed"})
            target["version"] = int(target.get("version", 1)) + 1
            target.setdefault("history", []).append(entry["id"])
        else:
            raise ProjectError(f"未知 feature_ops.op: {kind}")
    errors = cd.validate_features(spec)
    if errors:
        raise ProjectError("应用变更后功能清单无效: " + "; ".join(errors[:5]))
    cd.save(root, spec, "client", "features.json")


def update_change(root: Path, change_id: str, *, status: str | None = None, confirmed_by: str | None = None, note: str = "", reopen: bool = True,
                  client_visible: bool | str | None = None, detail: str | None = None, impact: str | None = None, affects: list[str] | None = None) -> dict[str, Any]:
    """Move a change to a new status and/or edit it. ``note`` is the process log (never shown to the client); ``client_visible`` True/False
    sets the flag, "default" clears it; ``detail`` replaces the client-facing logic (the old text is kept in the note); ``affects`` replaces the
    list of stages the change touches (a confirmed change reopens the approved stages it newly names, unless ``reopen`` is False)."""
    ledger = _ledger(root)
    entry = next((c for c in ledger["changes"] if c["id"] == change_id), None)
    if not entry:
        raise ProjectError(f"没有这条变更: {change_id}")
    if status is not None and status not in cd.CHANGE_STATUSES:
        raise ProjectError(f"状态无效: {status}")
    if status == "已确认" and entry["status"] != "已确认" and not confirmed_by:
        raise ProjectError("确认变更需要 --confirmed-by")
    if status is None and not any(v not in (None, "", []) for v in (note, client_visible, detail, impact, confirmed_by, affects)):
        raise ProjectError("change update 需要 --status，或 --client-visible / --detail / --impact / --confirmed-by / --affects / --note 之一")
    added_stages: list[str] = []
    if affects:
        from project_core import _stage_defs
        known = _stage_defs()
        for stage_id in affects:
            if stage_id not in known:
                raise ProjectError(f"未知阶段: {stage_id}")
        affects = list(dict.fromkeys(affects))
        added_stages = [stage_id for stage_id in affects if stage_id not in entry["affects"]]
        if affects != entry["affects"]:
            _append_note(entry, "影响阶段由 " + ("、".join(entry["affects"]) or "无") + " 改为 " + "、".join(affects))
            entry["affects"] = affects
    if detail is not None:
        if not detail.strip():
            raise ProjectError("--detail 不能为空")
        if detail.strip() != entry["detail"].strip():
            _append_note(entry, "逻辑与细节改写，原文：" + entry["detail"].strip().replace("\n", " "))
            entry["detail"] = detail.strip()
    if impact is not None:
        entry["impact"] = impact.strip()
    if client_visible == "default":
        entry.pop("client_visible", None)
    elif client_visible is not None:
        entry["client_visible"] = bool(client_visible)
    if detail is not None or impact is not None or client_visible is True:
        _require_client_text(entry, root)
    was = entry["status"]
    if status is not None:
        entry["status"] = status
    _append_note(entry, note.strip())
    if status == "已确认" and was != "已确认":
        entry.update({"confirmed_by": confirmed_by, "confirmed_at": now_iso()})
        _apply_confirmed(root, entry, reopen)
    else:
        if confirmed_by and entry["status"] in {"已确认", "已实施"} and not entry.get("confirmed_by"):
            entry["confirmed_by"] = confirmed_by              # fill in who confirmed an entry that was recorded without it
        if added_stages and reopen and entry["status"] == "已确认":
            _reopen_added(root, entry, added_stages)
    cd.save(root, ledger, "changes.json")
    return {**entry, "ledger_render": _refresh_ledger(root)}


def ledger_rows(root: Path) -> list[list[Any]]:
    """The rows of the client-facing ledger: only visible entries, detail without process logs, Beijing dates in both date columns."""
    from project_core import _stage_defs

    project_stage_names = {k: v.get("name", k) for k, v in _stage_defs().items()}
    feature_file = cd.data_path(root, "client", "features.json")
    names = {x["id"]: x["name"] for x in (cd.load(root, "client", "features.json", default={}) or {}).get("features", [])} if feature_file.is_file() else {}
    rows = []
    for c in _ledger(root)["changes"]:
        if not is_client_visible(c):
            continue
        confirmed = cn_date(c.get("confirmed_at"))
        rows.append([c["id"], date.fromisoformat(c["date"]), c["type"], c["category"], client_title(c), client_detail(c), c["source"], client_requester(c),
                     "、".join(names.get(r, r) for r in c["refs"] if r in names or not FN_ID.fullmatch(r)) or "—", "、".join(project_stage_names.get(a, a) for a in c["affects"]) or "—",
                     c["impact"] or "—", c["status"], c.get("confirmed_by") or "—", confirmed or "—"])
    return rows


def ledger_warnings(root: Path) -> list[str]:
    """Visible entries whose text would still show the client internal numbers or other files' names (existing data is reported, never rewritten)."""
    out = []
    for c in _ledger(root)["changes"]:
        if is_client_visible(c):
            out += [f"{c['id']} 含{p}" for p in client_text_issues(c, root)]
    return out


REVIEW_PAGES = ("03-方案评审.html", "04-业务逻辑确认评审.html")        # in the state root's reviews folder


def _sheet_words(sheet: Path, allow: tuple[str, ...] = ()) -> tuple[list[str], set[str], set[str]]:
    """The sheet names of a workbook, and the money words and the person-day words in its text cells."""
    from openpyxl import load_workbook

    money: set[str] = set()
    days: set[str] = set()
    try:
        book = load_workbook(sheet, data_only=True)
    except Exception:                                                    # not a workbook at all (a placeholder in a rehearsal): there are no cells to read; the build's own check judges the file
        return [], money, days
    for ws in book.worksheets:
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, str):
                    money |= set(cd.money_issues(cell, strict=True, allow=allow))
                    days |= set(ep.workday_issues(cell, allow))
    return [ws.title for ws in book.worksheets], money, days


def estimate_errors(root: Path) -> list[str]:
    """The 预算、人日与报价政策 as a check (config/documents.json ``estimate``; both switches are off unless a person asked, with the evidence): what the client reads
    carries person-days only when ``workdays`` is on and money only when ``quote`` is on with a quote that a person gave.

    Covered: the switches themselves (evidence, quote needs workdays) and quote.json when it is in use; the client data files, the visible ledger entries, 04-功能清单
    (sheets, words, the evidence the workbook carries) and the review pages of the client stages. A leftover quote.json while the quote switch is off is not read and not checked."""
    state = cd.estimate_state(root)
    errors: list[str] = list(state.errors)
    if state.quote and state.quote_errors:
        errors += [f"报价单（data/client/quote.json）不合格: {e}" for e in state.quote_errors]
    for name in ("requirements.json", "proposal.json", "architecture.json", "intake-extra.json", "manual.json"):
        data = cd.load(root, "client", name)
        if not data:
            continue
        allowed = ep.project_allowed_terms(root)
        text = json.dumps(data, ensure_ascii=False)
        found = [] if state.quote else cd.money_issues(text, allow=allowed)
        days = [] if state.workdays else ep.workday_issues(text, allowed)
        if found:
            errors.append(f"data/client/{name} 出现金额（没有人工报价，客户文件不出现金额）: {'、'.join(found[:4])}")
        if days:
            errors.append(f"data/client/{name} 出现人天或工时（没有要求写人日，客户文件不出现）: {'、'.join(days[:4])}")
    errors += [f"变更台账（客户可见）{w}" for w in ledger_warnings(root) if w.split("含", 1)[-1].startswith(("金额", "人天"))]
    folder, name, _ = client_document_files()["feature-list-xlsx"]
    sheet = deliver_root(root) / folder / name
    names, money, days = _sheet_words(sheet, ep.project_allowed_terms(root)) if sheet.is_file() else ([], set(), set())
    if names:
        if state.workdays:
            money -= {"小计", "合计", "总计"}                      # under the person-days the summary rows add up days, not money (the quote sheet is what carries the money)
        label = name
        if not state.workdays and (days or "报价清单" in names):
            errors.append(f"{label} 不应有人天、工时（{'、'.join(sorted(days)[:4]) or '多个工作表'}）：没有要求写人日，功能清单只列功能")
        if not state.quote and (money or "报价清单" in names or len(names) > 1):
            errors.append(f"{label} 不应有报价页或金额字样（{'、'.join(sorted(money)[:4]) or '多个工作表'}）：没有人工报价，功能清单不出现金额")
        if state.quote and "报价清单" not in names and not state.waiting_for_quote:
            errors.append(f"{label} 缺少报价清单工作表：已开启报价，重新生成（project.py client <项目> proposal）")
    stages = {s["id"]: s.get("status") for s in load_project(root).get("stages", [])}
    for name, stage in zip(REVIEW_PAGES, ("proposal", "client-intake")):
        rel = f"{state_name(root, REVIEW_DIR)}/{name}"
        page = locate(root, rel)
        if page.is_file() and stages.get(stage) != "superseded" and not state.quote:         # a page of a stage that is being redone is replaced, not held to the new rule
            found = cd.money_issues(re.sub(r"<[^>]+>", " ", page.read_text(encoding="utf-8", errors="replace")))
            if found:
                errors.append(f"{rel} 出现金额: {'、'.join(found[:4])}")
    return errors


def _ledger_workbook_spec(root: Path) -> dict[str, Any] | None:
    """Read the confirmed ledger data without touching either formal file."""
    ledger = _ledger(root)
    try:
        theme = cd.project_theme(root)
    except ProjectError:
        return None
    if not ledger["changes"]:
        return None
    project = load_project(root)
    spec = {"title": f"{project['name']} 需求变更台账", "theme": theme, "sheet": "变更台账",
            "columns": [{"name": "变更编号"}, {"name": "提出日期", "type": "date"}, {"name": "变更类型"}, {"name": "分类"}, {"name": "变更标题", "type": "longtext"}, {"name": "逻辑与补充细节", "type": "longtext"}, {"name": "来源"}, {"name": "提出人"}, {"name": "关联功能", "type": "longtext"}, {"name": "涉及阶段", "type": "longtext"}, {"name": "影响说明", "type": "longtext"}, {"name": "状态"}, {"name": "确认人"}, {"name": "确认日期", "type": "date"}],
            "rows": ledger_rows(root)}
    return spec


def _ledger_stage(root: Path) -> str:
    manifest = load_project(root)
    stage = manifest.get("current_stage")
    _stage_record(manifest, stage)
    return stage


def _ledger_render_record(root: Path, status: str, *, path: Path | None = None, reason: str = "") -> dict[str, Any]:
    result = {"status": status, "stage": _ledger_stage(root), "at": now_iso(),
              "changes_sha256": sha256_file(cd.data_path(root, "changes.json")),
              "path": str(path) if path else None, "reason": reason}
    cd.save(root, result, "client", "ledger-render.json")
    return result


def _refresh_ledger(root: Path) -> dict[str, Any]:
    """Persist a change immediately; defer its formal workbook when gated.

    A requirement can be recorded before a stage has completed its research or
    specialist data. That process record must not be lost, and the command
    must report the workbook as pending instead of failing after saving it.
    An explicit ``change render`` still raises the original gate/check error.
    """
    try:
        path = render_ledger(root)
    except ProjectError as exc:
        return _ledger_render_record(root, "deferred", reason=str(exc))
    return _ledger_render_record(root, "rendered" if path else "skipped", path=path,
                                 reason="" if path else "台账为空或未选定主题")


def render_ledger(root: Path) -> Path | None:
    """Build the live workbook using the active stage's evidence and template."""
    spec = _ledger_workbook_spec(root)
    if spec is None:
        return None
    stage = _ledger_stage(root)
    require_crawl(root, stage)
    _require_generation_gate(root, stage)
    built = cr.build_xlsx(root, "change-ledger", spec, stage=stage)
    target = _target(root, "change-ledger")
    shutil.copyfile(built, target)
    cr.record_template_output(root, stage, target, "xlsx", generator="Luz-Project/scripts/client_flow.py:change-ledger")
    _ledger_render_record(root, "rendered", path=target)
    return target


def snapshot_ledger(root: Path) -> Path:
    # Check handover first and build from the fact ledger directly. A refused
    # snapshot must never rewrite the live client workbook as a side effect.
    require_crawl(root, "handover")
    _require_generation_gate(root, "handover")
    spec = _ledger_workbook_spec(root)
    if spec is None:
        raise ProjectError("变更台账为空或未选定主题，无法生成交付快照")
    built = cr.build_xlsx(root, "change-ledger-snapshot", spec, stage="handover")
    target = _target(root, "change-ledger-snapshot")
    shutil.copyfile(built, target)
    cr.record_template_output(root, "handover", target, "xlsx", generator="Luz-Project/scripts/client_flow.py:change-ledger-snapshot")
    register_artifact(root, "handover", target, "change-ledger")
    cd.save(root, {"changes_sha256": sha256_file(cd.data_path(root, "changes.json")), "at": now_iso()}, "client", "ledger-snapshot.json")
    return target


# --- acceptance checklist ---------------------------------------------------------------------------------------

def _evidence_checks(f: dict[str, Any]) -> list[str]:
    checks = list(cd.SURFACE_CHECKS.get(f["surface"], ["e2e"]))
    for tag in f.get("tags", []):
        extra = cd.TAG_CHECKS.get(tag)
        if extra and extra not in checks:
            checks.append(extra)
    return checks


def generate_acceptance(root: Path) -> dict[str, Any]:
    """Create/refresh data/acceptance/checklist.json from the effective features; keeps results of items that persist."""
    features = cd.load_features(root)
    current = cd.load(root, "acceptance", "checklist.json", default={"items": []}) or {"items": []}
    old = {(i["feature_id"], i.get("case", 1)): i for i in current["items"]}
    scoped = {f["id"] for f in effective_features(root, features)}
    items, number = [], 0
    for f in features["features"]:
        cases = f.get("acceptance") or [{"steps": f"按《使用说明》中「{f['name']}」一节逐步操作", "expected": f["rules"]}]
        for case_no, case in enumerate(cases, 1):
            prior = old.get((f["id"], case_no))
            number = max(number, int(prior["id"].split("-")[1])) if prior else number
            items.append({"prior": prior, "feature": f, "case_no": case_no, "case": case})
    next_no = max([int(i["id"].split("-")[1]) for i in current["items"]] + [0]) + 1
    out = []
    for entry in items:
        f, prior = entry["feature"], entry["prior"]
        in_scope = f["id"] in scoped
        item = prior or {"id": f"ACC-{next_no:03d}", "status": "pending", "signed_by": None, "signed_at": None, "note": None}
        if not prior:
            next_no += 1
        item.update({"feature_id": f["id"], "module": f["module"], "feature_name": f["name"], "surface": f["surface"], "case": entry["case_no"], "steps": entry["case"]["steps"], "expected": entry["case"]["expected"], "evidence_checks": entry["case"].get("evidence_checks") or _evidence_checks(f)})
        if not in_scope and item["status"] != "waived":
            item.update({"status": "waived", "note": "功能不在最终范围内（客户未选择或已移除），见变更台账"})
        elif in_scope and item["status"] == "waived" and (item.get("note") or "").startswith("功能不在最终范围"):
            item.update({"status": "pending", "note": None})
        out.append(item)
    payload = {"schema_version": "1.0", "generated_at": now_iso(), "items": out}
    cd.save(root, payload, "acceptance", "checklist.json")
    return payload


def _ops_status(root: Path) -> dict[str, str]:
    data = cd.load(root, "ops", "checks.json", default=[]) or []
    if isinstance(data, dict):
        data = [{"id": k, **(v if isinstance(v, dict) else {"status": v})} for k, v in data.items()]
    return {str(r.get("id")): str(r.get("status")) for r in data if isinstance(r, dict)}


def _ops_names() -> dict[str, str]:
    """Check id -> the Chinese name Luz-Ops gives it; ids that Ops does not know stay unnamed."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Luz-Ops" / "scripts"))
        from ops_core import operations_matrix
        return {c["id"]: c["name"] for c in operations_matrix()["checks"]}
    except Exception:
        return {}


def evidence_summary(item: dict[str, Any], ops: dict[str, str], names: dict[str, str] | None = None) -> str:
    names = names if names is not None else _ops_names()
    parts = []
    for check in item["evidence_checks"]:
        state = ops.get(check)
        parts.append(f"{names.get(check, '测试项')}：{'通过' if state == 'passed' else '未通过' if state in {'failed', 'blocked'} else '已豁免' if state == 'waived' else '未记录'}")
    return "；".join(parts)


def build_acceptance_xlsx(root: Path) -> Path:
    require_crawl(root, "handover")
    _require_generation_gate(root, "handover")
    checklist = cd.load(root, "acceptance", "checklist.json")
    if not checklist:
        checklist = generate_acceptance(root)
    features = cd.load_features(root)
    modules = {m["id"]: m["name"] for m in features["modules"]}
    ops = _ops_status(root)
    names = _ops_names()
    project = load_project(root)
    label = {"pending": "待验收", "passed": "通过", "failed": "不通过", "waived": "不适用"}
    surface_rank = {name: k for k, name in enumerate(cd.SURFACES)}
    module_rank = {m["id"]: k for k, m in enumerate(features["modules"])}
    ordered = sorted(checklist["items"], key=lambda i: (surface_rank.get(i["surface"], 99), module_rank.get(i["module"], 99), i["id"]))   # big group first
    rows = [[cd.SURFACES.get(i["surface"], i["surface"]), modules.get(i["module"], i["module"]), i["id"], f"{i['feature_id']} {i['feature_name']}", i["steps"], i["expected"],
             evidence_summary(i, ops, names), label[i["status"]], i.get("signed_by") or "", i.get("signed_at") or "", i.get("note") or ""] for i in ordered]
    spec = {"title": f"{project['name']} 验收清单", "theme": cd.project_theme(root), "sheet": "验收清单",
            "columns": [{"name": "使用端", "merge": True}, {"name": "功能模块", "merge": True}, {"name": "验收项编号"}, {"name": "功能"}, {"name": "验收步骤", "type": "longtext"}, {"name": "预期结果", "type": "longtext"},
                        {"name": "测试证据", "type": "longtext"}, {"name": "验收结果"}, {"name": "客户签字"}, {"name": "签字日期"}, {"name": "备注", "type": "longtext"}],
            "rows": rows}
    lists = {i: ["通过", "不通过", "待验收"] for i in range(len(rows))}
    built = cr.build_xlsx(root, "acceptance-checklist", spec, pick_column="验收结果", row_lists=lists)
    target = _target(root, "acceptance-checklist")
    shutil.copyfile(built, target)
    # ``build_xlsx`` validates the selected template for its staging file;
    # bind the final client deliverable as well.  Without this post-build
    # record the template selection remains an unbound claim and the next
    # stage cannot verify the bytes that were actually delivered.
    cr.record_template_output(root, "handover", target, "xlsx", generator="Luz-Project/scripts/client_flow.py:acceptance-checklist")
    register_artifact(root, "handover", target, "acceptance-checklist")
    return target


def import_acceptance(root: Path, xlsx: Path) -> dict[str, Any]:
    """Human sign-off only: results, signer and date come from the client's sheet; nothing here signs on anyone's behalf."""
    from openpyxl import load_workbook

    checklist = cd.load(root, "acceptance", "checklist.json")
    ws = load_workbook(xlsx, data_only=True).active
    header_row = next((r for r in range(1, 8) if any(c.value == "验收项编号" for c in ws[r])), None)
    if header_row is None:
        raise ProjectError("不是本系统生成的验收清单（缺少「验收项编号」）")
    idx = {c.value: c.column for c in ws[header_row]}
    by_id = {i["id"]: i for i in checklist["items"]}
    code = {"通过": "passed", "不通过": "failed", "待验收": "pending", "待定": "pending"}
    for r in range(header_row + 1, ws.max_row + 1):
        item = by_id.get(str(ws.cell(r, idx["验收项编号"]).value or ""))
        if not item or item["status"] == "waived":
            continue
        result = str(ws.cell(r, idx["验收结果"]).value or "待验收").strip()
        if result not in code:
            raise ProjectError(f"{item['id']} 验收结果无效: {result}")
        signer = str(ws.cell(r, idx["客户签字"]).value or "").strip() or None
        signed_at = ws.cell(r, idx["签字日期"]).value
        signed_at = signed_at.date().isoformat() if hasattr(signed_at, "date") else (str(signed_at).strip() or None if signed_at else None)
        note = str(ws.cell(r, idx["备注"]).value or "").strip() or None
        if code[result] == "passed" and not (signer and signed_at):
            raise ProjectError(f"{item['id']} 标为通过但缺少客户签字或日期")
        item.update({"status": code[result], "signed_by": signer if code[result] != "pending" else None, "signed_at": signed_at if code[result] != "pending" else None, "note": note})
    cd.save(root, checklist, "acceptance", "checklist.json")
    return acceptance_status(root)


def waive_acceptance(root: Path, item_id: str, by: str, note: str) -> None:
    checklist = cd.load(root, "acceptance", "checklist.json")
    item = next((i for i in checklist["items"] if i["id"] == item_id), None)
    if not item or not by.strip() or not note.strip():
        raise ProjectError("需要存在的验收项编号、豁免确认人和理由")
    item.update({"status": "waived", "signed_by": by, "signed_at": date.today().isoformat(), "note": note})
    cd.save(root, checklist, "acceptance", "checklist.json")


def acceptance_status(root: Path) -> dict[str, Any]:
    checklist = cd.load(root, "acceptance", "checklist.json", default={"items": []}) or {"items": []}
    count: dict[str, int] = {}
    for i in checklist["items"]:
        count[i["status"]] = count.get(i["status"], 0) + 1
    return {"total": len(checklist["items"]), **count}


# --- manual -----------------------------------------------------------------------------------------------------

def manual_draft(root: Path) -> Path:
    require_crawl(root, "handover", for_draft=True)
    features = cd.load_features(root)
    path = cd.data_path(root, "client", "manual.json")
    if path.is_file():
        raise ProjectError("manual.json 已存在，不覆盖")
    chapters = []
    for m in features["modules"]:
        ids = [f["id"] for f in effective_features(root, features) if f["module"] == m["id"]]
        if ids:
            chapters.append({"id": f"CH-{m['id']}", "heading": m["name"], "features": ids, "entry": "待补充", "steps": ["待补充"], "rules": ["待补充"]})
    return cd.save(root, {"title": f"{load_project(root)['name']}使用说明", "intro": {"paragraphs": ["待补充"]}, "roles": [], "chapters": chapters}, "client", "manual.json")


def build_manual(root: Path, *, force: bool = False) -> Path:
    require_crawl(root, "handover")
    _require_generation_gate(root, "handover")
    features = cd.load_features(root)
    spec = cd.load(root, "client", "manual.json")
    errors = cd.validate_manual(spec, _scoped(root, features))
    if errors:
        raise ProjectError("使用说明未通过: " + "; ".join(errors[:8]))
    out = _target(root, "user-manual-pdf")
    sources = [cd.data_path(root, "client", "manual.json"), cd.data_path(root, "client", "features.json")]
    if _fresh(root, "manual", [out], force):
        return out
    theme = cd.project_theme(root, spec)
    _word, pdf = cr.build_docx(root, "user-manual", cr.manual_spec(features, spec, theme))      # typeset as Word, delivered as the PDF exported from it
    result = _publish(root, "user-manual-pdf", pdf, sources, "manual", "handover")
    from project_core import unregister_artifacts
    unregister_artifacts(root, {"user-manual-showcase", "user-manual-docx"})
    return result


# --- trace ------------------------------------------------------------------------------------------------------

def architecture_cards(arch: dict[str, Any]) -> dict[str, str]:
    """FN id -> module name, read from the function cards (``function`` blocks) of a tabs-structured architecture spec.

    A card names its module in ``module``; the sub tab it sits in (the section title) is the fallback.
    """
    cards: dict[str, str] = {}

    def visit(node: Any, section: str = "") -> None:
        if isinstance(node, dict):
            if node.get("type") == "function" and node.get("id"):
                cards[str(node["id"])] = str(node.get("module") or section)
                return
            title = str(node.get("title") or section) if "blocks" in node else section
            for value in node.values():
                visit(value, title)
        elif isinstance(node, list):
            for value in node:
                visit(value, section)

    visit(arch.get("tabs", []))
    return cards


def trace(root: Path) -> dict[str, Any]:
    features = cd.load_features(root, validate=False)
    manual = cd.load(root, "client", "manual.json", default={}) or {}
    checklist = cd.load(root, "acceptance", "checklist.json", default={"items": []}) or {"items": []}
    ledger = _ledger(root)
    arch = _read_json(root / "data" / "stages" / "architecture.json", {}) or {}
    cards = architecture_cards(arch)                                              # current spec: tabs with function cards
    arch_modules = {m.get("id") for m in arch.get("logic", {}).get("modules", [])}   # older spec: logic.modules
    id_by_name = {m["name"]: m["id"] for m in features.get("modules", []) if m.get("name")}
    known_modules = set(cards.values()) | {id_by_name[n] for n in cards.values() if n in id_by_name}
    scoped = {f["id"] for f in effective_features(root, features)}
    links = cd.load(root, "client", "trace-links.json", default={}) or {}
    rows, gaps = [], []
    for f in features.get("features", []):
        fid = f["id"]
        in_scope = fid in scoped
        chapters = [c["id"] for c in manual.get("chapters", []) if fid in c.get("features", [])]
        acc = [i["id"] for i in checklist["items"] if i["feature_id"] == fid]
        chg = [c["id"] for c in ledger["changes"] if fid in c.get("refs", [])]
        link = links.get(fid, {})
        arch_refs = link.get("arch", [])
        rows.append({"feature": fid, "name": f["name"], "in_scope": in_scope, "architecture": arch_refs, "design": link.get("design", []), "dev": link.get("dev", []), "manual": chapters, "acceptance": acc, "changes": chg})
        if in_scope:
            if cards:
                card = cards.get(fid)
                if card is None:
                    gaps.append(f"{fid} 在系统架构里没有功能卡")
                if not arch_refs:
                    gaps.append(f"{fid} 未关联架构模块（project.py link {fid} --arch <模块ID>）")
                for ref in arch_refs:
                    if ref not in known_modules:
                        gaps.append(f"{fid} 引用了不存在的架构模块 {ref}")
                if card is not None and arch_refs and not {card, id_by_name.get(card)} & set(arch_refs):
                    gaps.append(f"{fid} 登记的架构模块 {'、'.join(arch_refs)} 与功能卡所属模块 {card}{'（' + id_by_name[card] + '）' if card in id_by_name else ''} 不一致")
            elif arch_modules:
                if not arch_refs:
                    gaps.append(f"{fid} 未关联架构模块（project.py link {fid} --arch <模块ID>）")
                for ref in arch_refs:
                    if ref not in arch_modules:
                        gaps.append(f"{fid} 引用了不存在的架构模块 {ref}")
            if manual and not chapters:
                gaps.append(f"{fid} 使用说明未覆盖")
            if checklist["items"] and not acc:
                gaps.append(f"{fid} 没有验收项")
    return {"rows": rows, "gaps": gaps}


# --- estimate: what stops the function list ----------------------------------------------------------------------------

def estimate_build_errors(root: Path, estimate: Any, features: dict[str, Any]) -> list[str]:
    """What stops 04-功能清单 from being written under the current switches (empty when nothing does): malformed switches or switches without their evidence, the hours and
    their basis when workdays is on, the quote nobody has given yet (the project waits for a person) or one that is not acceptable."""
    errors = ["估算开关无效: " + e for e in estimate.errors]
    if estimate.workdays:
        errors += ep.hours_errors(features)
    if estimate.quote and estimate.quote_missing:
        errors.append(ep.quote_wait_message())
    elif estimate.quote and estimate.quote_errors:
        errors += ["报价单不合格: " + e for e in estimate.quote_errors]
    return errors


# --- gates ------------------------------------------------------------------------------------------------------

BASELINE_FILE = "data/baseline.json"
BASELINE_SECTIONS = {"architecture": ("stack", "modules")}      # the architecture stage owns the stack and the basic function modules; the frontend section belongs to design
ESTIMATE_SOURCE = "config/documents.json#estimate"          # the estimate section of the documents config: the switches and the evidence they rest on (client_data.source_digest reads it normalised)
TRACKED = {
    "requirements": ["data/client/requirements.json"],
    "proposal": ["data/client/features.json", "data/client/proposal.json", "data/client/architecture.json", ESTIMATE_SOURCE],
    "client-intake": ["data/client/intake.json", "data/client/intake-deferral.json"],
    "architecture": [f"{BASELINE_FILE}#{','.join(BASELINE_SECTIONS['architecture'])}"],
    "handover": ["data/client/manual.json", "data/acceptance/checklist.json", "data/changes.json"],
}
QUOTE_SOURCE = "data/client/quote.json"


def tracked_sources(root: Path, stage: str) -> list[str]:
    """The tracked sources of a stage. The quote that a person gave belongs to the proposal while the quote switch is on (a quote left behind while it is off is not a source)."""
    out = list(TRACKED.get(stage, []))
    if stage == "proposal" and cd.estimate_state(root).quote:
        out.append(QUOTE_SOURCE)
    if stage == "architecture":
        # Bind only the new registered contract, without changing historical
        # source-locked approvals that used the older frontend-spec format.
        out.extend(str(a["path"]) for a in _architecture_ui_requirements(root, _load_artifacts(root)))
        out = list(dict.fromkeys(out))
    return out


def tracked_digest(root: Path, rel: str) -> str | None:
    """Hash of a tracked source. ``file#a,b`` is the hash of only sections a and b of a JSON file (the others may change without disturbing the approval);
    a plain path is the hash of the whole file. None when the file (or a section holder) is not there."""
    return cd.source_digest(root, rel)


def tracked_hashes(root: Path, stage: str) -> dict[str, str]:
    return {rel: digest for rel in tracked_sources(root, stage) if (digest := tracked_digest(root, rel)) is not None}


def open_changes(root: Path, stage: str | None = None) -> list[dict[str, Any]]:
    out = []
    for c in _ledger(root)["changes"]:
        if c["status"] == "待确认" and (stage is None or stage in c["affects"] or not c["affects"]):
            out.append(c)
    return out


def _registered(root: Path, stage: str, kind: str) -> dict[str, Any] | None:
    return next((a for a in _load_artifacts(root) if a["stage"] == stage and a["kind"] == kind), None)


#: What the architecture stage hands to the front end design of a project that has screens (references/dev-documents.md, "随附产物"): the interface
#: function description (page and data), and the entrance tables. Registered as artifacts of the stage, so their hashes are bound by the approval.
ARCHITECTURE_FRONTEND_KINDS = (
    ("frontend-spec", "界面功能说明的数据（frontend-spec.json）"),
    ("frontend-spec-page", "界面功能说明（人读的 HTML）"),
    ("entrances", "入口表（entrances*.json，每个使用端或角色一份）"),
)


def _architecture_ui_requirements(root: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find new contracts by their registered kind or real file schema."""
    out = []
    for art in artifacts:
        if art.get("stage") != "architecture":
            continue
        if art.get("kind") == "ui-requirements":
            out.append(art)                    # malformed declared contracts must still be checked
            continue
        try:
            data = json.loads(locate(root, str(art["path"])).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("schema") in ("luz-ui-requirements/1", "luz-ui-requirements/2"):
            out.append(art)
    return out


def _check_ui_requirements(path: Path) -> None:
    """Use System's pure structural checker; approval binding happens later."""
    source = Path(__file__).resolve().parents[2] / "Luz-System" / "scripts" / "ui_requirements.py"
    spec = importlib.util.spec_from_file_location("_project_system_ui_requirements", source)
    if spec is None or spec.loader is None:
        raise ProjectError(f"找不到 System UI requirements 校验器: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check(path)


def architecture_frontend_errors(root: Path) -> list[str]:
    """A project with screens must hand the front end design its 界面功能说明 and entrance tables from the architecture stage: registered as artifacts of the
    stage (so the approval binds their hashes), readable, and the entrance tables together answer for every function that is still part of the project
    (a row with its ``fn``, or a ``no_entrance`` line that says why it has none)."""
    import dev_documents

    manifest = load_project(root)
    component_mode = manifest.get("ui_mode") == "component-reuse"
    require_ownership = component_mode and manifest.get("ui_requirements_version") == 2
    arts = [a for a in _load_artifacts(root) if a.get("stage") == "architecture"]
    contracts = _architecture_ui_requirements(root, arts)
    try:
        features = cd.load_features(root)
    except ProjectError as exc:
        return [str(exc)] if component_mode or contracts else []        # preserve old offline rehearsals only
    active = effective_features(root, features) if component_mode or contracts else cd.active_features(features)
    errors: list[str] = []
    for art in contracts:
        path = locate(root, str(art["path"]))
        try:
            _check_ui_requirements(path)
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if require_ownership and data.get("schema") != "luz-ui-requirements/2":
                errors.append(f"{art['path']} 的新项目界面合同须使用 luz-ui-requirements/2，声明动作归属")
            wanted = {f["id"] for f in active}
            actual = {f["id"] for f in data["features"]}
            if wanted != actual:
                errors.append(f"{art['path']} 的 UI requirements 与有效功能范围不一致: missing={sorted(wanted - actual)}; extra={sorted(actual - wanted)}")
        except (OSError, ValueError, TypeError, KeyError, ImportError, ProjectError) as exc:
            errors.append(f"{art['path']} UI requirements 无效: {exc}")
    if not any(f.get("surface") in dev_documents.UI_SURFACES for f in active):
        return errors
    if component_mode and not contracts:
        version = "2" if require_ownership else "1 或 /2"
        errors.append(f"component-reuse 项目的架构阶段必须登记 luz-ui-requirements/{version} 合同（--kind ui-requirements 或 frontend-spec）")
    errors += [f"有界面的项目，架构阶段要交{label}并登记（project.py artifact <项目> architecture <文件> --kind {kind}），见 references/dev-documents.md"
               for kind, label in ARCHITECTURE_FRONTEND_KINDS
               if not any(a.get("kind") == kind for a in arts) and not (kind == "frontend-spec" and contracts)]
    answered: set[str] = set()
    for art in (a for a in arts if a.get("kind") in {"frontend-spec", "entrances"}):
        path = locate(root, str(art["path"]))
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            errors.append(f"{art['path']} 读不出来（要是 JSON 文件）")
            continue
        if art["kind"] == "entrances":
            rows = (data.get("entrances") if isinstance(data, dict) else None) or []
            gaps = (data.get("no_entrance") if isinstance(data, dict) else None) or []
            answered |= {str(r.get("fn")) for r in rows + gaps if isinstance(r, dict)}
    if any(a.get("kind") == "entrances" for a in arts):
        missing = [f["id"] for f in active if f["id"] not in answered]
        if missing:
            errors.append("入口表没有覆盖这些功能（每个功能要有一行入口，或在 no_entrance 里写明为什么没有）: " + "、".join(missing[:8]))
    return errors


def stage_checks(root: Path, stage: str, phase: str = "all") -> list[str]:
    """Stage-specific approval conditions for the client-facing stages (and the change-ledger rule for every stage).

    ``phase`` splits them for the by-document model (flow_steps.py): ``build`` is what must hold before the stage's files are shown to the user (documents built, fresh, the
    data valid, no pending change), ``complete`` is what only the client can supply afterwards (the filled-in form, the signed checklist); ``all`` is both, as the
    stage-level approval of the older model asks for it."""
    errors: list[str] = []
    build = phase in {"all", "build"}
    done = phase in {"all", "complete"}
    deferral, deferral_errors = intake_deferral_state(root)
    if stage in {"verification", "release", "operations", "handover"} and deferral and not _real_intake_ready(root):
        return ["用户授权的暂缓回填只适用于设计开发；真实业务验收与交付前须补齐真实客户资料"] + deferral_errors
    pending = open_changes(root, stage)
    if pending:
        errors.append("仍有待确认的变更影响本阶段: " + "、".join(c["id"] for c in pending[:6]))
    if stage == "architecture" and build:
        errors += architecture_frontend_errors(root)
    if stage == "requirements" and build:
        errors += requirements_errors(root)
    if stage == "proposal" and build:
        errors += ["方案之前要先有需求文档: " + e for e in requirements_errors(root)]
        try:
            features = cd.load_features(root)
        except ProjectError as exc:
            return errors + [str(exc)]
        errors += cd.validate_proposal(cd.load(root, "client", "proposal.json"), cd.documents_config(root).get("theme")) + cd.validate_architecture(cd.load(root, "client", "architecture.json"), cd.documents_config(root).get("theme"))
        proposal_spec = cd.load(root, "client", "proposal.json") or {}
        for kind in ("proposal-pdf", "architecture-pdf", "feature-list-xlsx"):
            art = _registered(root, stage, kind)
            folder, filename, _ = client_document_files()[kind]
            if not art:
                errors.append(f"缺少客户文档 {filename}（project.py client proposal）")
            elif not art["path"].startswith(folder + "/"):
                errors.append(f"{filename} 必须位于 {folder}")
        errors += [f"方案文档已过期: {s}（重新运行 project.py client proposal）" for s in cd.stale_sources(root, "proposal")]
        if not any(f["tier"] == "基础" for f in features["features"]):
            errors.append("功能清单没有基础功能")
        errors += estimate_build_errors(root, cd.estimate_state(root), features) + estimate_errors(root)
    elif stage == "client-intake":
        if build:
            if not _registered(root, stage, "intake-form"):
                errors.append(f"缺少 {client_document_files()['intake-form'][1]}")
            errors += [f"确认表已过期: {s}" for s in cd.stale_sources(root, "intake-form")]
        if done:
            if deferral is not None:
                errors += deferral_errors
                if not deferral_errors:
                    return errors
            if not _registered(root, stage, "intake-response"):
                errors.append(f"缺少 {client_document_files()['intake-response'][1]}")
            status = intake_status(root)
            if not status["imported_at"]:
                errors.append("尚未导入客户回填表（project.py client intake-import）")
            if status["missing_required"]:
                errors.append(f"客户尚有 {len(status['missing_required'])} 项必填信息未答（可用 client intake-defer 记录责任人与期限）: " + "；".join(status["missing_required"][:4]))
    elif stage == "handover":
        features = cd.load_features(root)
        checklist = cd.load(root, "acceptance", "checklist.json")
        if build:
            errors += cd.validate_manual(cd.load(root, "client", "manual.json"), _scoped(root, features))
            errors += [f"使用说明已过期: {s}" for s in cd.stale_sources(root, "manual")]
            for kind in ("user-manual-pdf", "acceptance-checklist", "change-ledger"):
                if not _registered(root, stage, kind):
                    errors.append(f"缺少交付文件 {client_document_files()[kind if kind != 'change-ledger' else 'change-ledger-snapshot'][1]}")
            if not checklist or not checklist["items"]:
                errors.append("验收清单为空（project.py client acceptance）")
            else:
                covered = {i["feature_id"] for i in checklist["items"]}
                errors += [f"功能 {f['id']} 没有验收项" for f in effective_features(root, features) if f["id"] not in covered]
            snap = cd.load(root, "client", "ledger-snapshot.json")
            ledger_file = cd.data_path(root, "changes.json")
            if not snap or (ledger_file.is_file() and snap["changes_sha256"] != sha256_file(ledger_file)):
                errors.append("变更台账交付快照缺失或已过期（project.py change snapshot）")
            unfinished = [c["id"] for c in _ledger(root)["changes"] if c["status"] in {"待确认", "已确认"}]
            if unfinished:
                errors.append("变更台账仍有未实施的条目: " + "、".join(unfinished[:6]))
        if done and checklist and checklist["items"]:
            for i in checklist["items"]:
                if i["status"] == "passed" and not (i.get("signed_by") and i.get("signed_at")):
                    errors.append(f"{i['id']} 缺少客户签字")
                elif i["status"] == "waived" and not i.get("note"):
                    errors.append(f"{i['id']} 豁免缺少理由")
                elif i["status"] in {"pending", "failed"}:
                    errors.append(f"{i['id']} 验收未完成（{i['status']}）")
    return errors


def tracked_drift(root: Path, manifest: dict[str, Any]) -> list[str]:
    """After approval the tracked sources must not change silently: record a change (which reopens the stage) instead."""
    errors = []
    for stage in manifest.get("stages", []):
        if stage.get("status") in {"approved", "completed"} and stage.get("approved_sources"):
            for rel, digest in stage["approved_sources"].items():
                if tracked_digest(root, rel) != digest:
                    name, _, sections = rel.partition("#")
                    what = f"{name} 的 {'、'.join(sections.split(','))} 两段" if sections else rel
                    errors.append(f"阶段 {stage['id']} 批准后 {what}已变化：先登记变更（project.py change add）并重新批准" if sections else f"阶段 {stage['id']} 批准后 {what} 已变化：先登记变更（project.py change add）并重新批准")
    return errors


def deliverable_context(root: Path, stage_record: dict[str, Any]) -> list[dict[str, Any]]:
    from project_core import _stage_defs

    from project_core import stage_deliverables

    defs = _stage_defs().get(stage_record["id"], {})
    arts = _load_artifacts(root)
    out = []
    for d in stage_deliverables(root, defs):
        path = locate(root, d["path"])
        out.append({**d, "absolute_path": str(path), "exists": path.is_file(), "registered": any(a["stage"] == stage_record["id"] and a["path"] == d["path"] for a in arts)})
    return out


SKILL_CARDS = {
    "requirements": [
        ("luz-writing", r"py -X utf8 D:\Codes\Luz-Writing\scripts\06-context.py client-document", "需求说明书正文：先写业务现状与问题，再写需求；用客户的词，不写方案、技术细节和价格，不提及其他文件"),
        ("luz-system", r"py -X utf8 D:\Codes\Luz-System\scripts\context.py function-list", "需求清单的粒度与写法；功能清单已有时用 auto 块 requirement_list 生成，需求与功能清单不会不一致"),
        ("luz-design", r"py -X utf8 D:\Codes\Luz-Design\scripts\context.py docx", "需求说明书版式（客户正式文档：封面、可点击目录、表题与续表、黑白）；构建由 project.py client requirements 调用 make_docx_paginated"),
    ],
    "proposal": [
        ("luz-system", r"py -X utf8 D:\Codes\Luz-System\scripts\context.py function-list", "客户功能清单：功能粒度、基础/可选、业务逻辑的写法；人日与报价默认不写，用户明确要求并打开 estimate 开关才写，开了人日每个功能要有 hours 与 hours_basis"),
        ("luz-system", r"py -X utf8 D:\Codes\Luz-System\scripts\features_check.py <状态根>\data\client --documents-config <状态根>\config\documents.json", "检查 features.json、intake-extra.json、quote.json 的内容规则（逻辑要有数字或边界、不用技术词、不问通用信息；按 estimate 开关：未开启不得出现人日与金额，开启人日要有 hours 与 hours_basis，开启报价要有人工证据）"),
        ("luz-system", r"py -X utf8 D:\Codes\Luz-System\scripts\context.py client-docs", "方案说明书的内容来源与系统架构图册的画法"),
        ("luz-writing", r"py -X utf8 D:\Codes\Luz-Writing\scripts\06-context.py client-document", "方案说明书正文（先分析需求再给方案，用客户的词，不讲技术细节、不写人日和价格、不提及其他文件）"),
        ("luz-writing", r"py -X utf8 D:\Codes\Luz-Writing\scripts\09-text_check.py <文本或 proposal.json> --project-config <状态根>\config\documents.json", "标点、数字、占位、他文件指引、价格与人日（按 estimate 开关）、技术词、标题括号的自查"),
        ("luz-design", r"py -X utf8 D:\Codes\Luz-Design\scripts\context.py docx", "方案说明书版式（客户正式文档：封面、可点击目录、表题与续表、黑白）；构建由 project.py client proposal 调用 make_docx_paginated"),
        ("luz-design", r"py -X utf8 D:\Codes\Luz-Design\scripts\context.py showcase", "系统架构图册版式（atlas 样式）；构建由 project.py client proposal 调用 make_showcase"),
    ],
    "client-intake": [
        ("luz-system", r"py -X utf8 D:\Codes\Luz-System\scripts\context.py function-list", "每个功能拟定的业务逻辑怎么写；只问客户才有的资料"),
        ("luz-design", r"py -X utf8 D:\Codes\Luz-Design\scripts\context.py xlsx", "确认表版式；构建由 project.py client intake-form 调用 make_xlsx"),
    ],
    "handover": [
        ("luz-writing", r"py -X utf8 D:\Codes\Luz-Writing\scripts\06-context.py client-document", "使用说明正文：步骤、规则、状态、常见问题"),
        ("luz-ops", r"python -X utf8 D:\Codes\Luz-Ops\scripts\ops.py check <项目> delivery", "验收证据与交付检查；验收清单读取 data/acceptance/checklist.json"),
        ("luz-design", r"py -X utf8 D:\Codes\Luz-Design\scripts\context.py docx", "使用说明版式（客户正式文档）；验收清单 XLSX 用 context.py xlsx"),
    ],
}


def client_context(root: Path, stage: str) -> dict[str, Any]:
    manifest = load_project(root)
    record = _stage_record(manifest, stage)
    files = {k: str(cd.data_path(root, *p)) for k, p in {"features": ("client", "features.json"), "requirements": ("client", "requirements.json"), "proposal": ("client", "proposal.json"), "architecture": ("client", "architecture.json"), "intake": ("client", "intake.json"), "manual": ("client", "manual.json"), "changes": ("changes.json",), "acceptance": ("acceptance", "checklist.json")}.items() if cd.data_path(root, *p).is_file()}
    return {
        "data_files": files,
        "deliverables": deliverable_context(root, record),
        "estimate": {"workdays": cd.estimate_state(root).workdays, "quote": cd.estimate_state(root).quote, "waiting_for_quote": cd.estimate_state(root).waiting_for_quote,
                     "user_todos": ep.user_todos(root), "rule": "默认不写人日、预算和报价；用户明确要求才开（project.py client <项目> estimate），报价的数字只来自人工提供的报价单，agent 不得自拟"},
        "open_changes": [{"id": c["id"], "title": c["title"], "affects": c["affects"]} for c in open_changes(root)],
        "recent_changes": [{"id": c["id"], "type": c["type"], "title": c["title"], "status": c["status"]} for c in _ledger(root)["changes"][-8:]],
        "skill_cards": [{"skill": s, "run": cmd, "for": why} for s, cmd, why in SKILL_CARDS.get(stage, [])],
        "directory_contract": __import__("project_core").load_matrix().get("directory_contract", {}),
    }


def review_extras(root: Path, stage: str) -> list[dict[str, str]]:
    """Sections the dev-facing review HTML of the three client stages always carries (derived, never hand-written)."""
    out: list[dict[str, str]] = []
    if stage == "proposal":
        spec = cd.load_features(root, validate=False) if cd.data_path(root, "client", "features.json").is_file() else None
        if spec:
            rows = [f"{f['id']} {f['name']}（{f['tier']}，{cd.SURFACES.get(f['surface'], f['surface'])}，v{f.get('version', 1)}）" for f in spec["features"] if f.get("status", "in-scope") == "in-scope"]
            out.append({"title": "稳定功能 ID", "content": rows})
        stale = cd.stale_sources(root, "proposal")
        out.append({"title": "客户文档状态", "content": stale or ["方案、架构图与功能清单文件和当前数据一致"]})
        state = cd.estimate_state(root)
        if state.workdays or state.quote:
            line = [f"估算开关：人日已开启，{'价格已开启，单价由' + str((state.quote_data or {}).get('provided_by', '（尚无）')) + '提供' if state.quote else '价格未开启'}",
                    f"要求人：{state.request['requested_by']}（{state.request['requested_at']}）"]
        else:
            line = ["估算开关：人日未开启，价格未开启（默认只给功能清单）"]
        out.append({"title": "估算开关", "content": line + (["价格还在等人工提供的数字"] if state.waiting_for_quote else [])})
    elif stage == "client-intake":
        st = intake_status(root)
        out.append({"title": "客户回填状态", "content": [f"问题 {st['total']} 项，已答 {st['answered']} 项", f"必填未答 {len(st['missing_required'])} 项", f"已记录延期 {len(st['deferred'])} 项"]})
    elif stage == "handover":
        ac = acceptance_status(root)
        out.append({"title": "验收进度", "content": [f"{k}：{v}" for k, v in ac.items()]})
        tr = trace(root)
        out.append({"title": "追溯缺口", "content": tr["gaps"] or ["无"]})
    pending = open_changes(root)
    if pending:
        out.append({"title": "待确认变更", "content": [f"{c['id']} {c['title']}（影响 {'、'.join(c['affects']) or '未标注'}）" for c in pending]})
    return out


def link_feature(root: Path, feature_id: str, *, arch: list[str], design: list[str], dev: list[str]) -> dict[str, Any]:
    """Owners record where a feature lives downstream (kept apart from features.json so approvals are not disturbed)."""
    ids = {f["id"] for f in cd.load_features(root)["features"]}
    if feature_id not in ids:
        raise ProjectError(f"功能不存在: {feature_id}")
    links = cd.load(root, "client", "trace-links.json", default={}) or {}
    entry = links.setdefault(feature_id, {})
    for key, values in (("arch", arch), ("design", design), ("dev", dev)):
        if values:
            entry[key] = sorted(set(entry.get(key, [])) | set(values))
    cd.save(root, links, "client", "trace-links.json")
    return entry
