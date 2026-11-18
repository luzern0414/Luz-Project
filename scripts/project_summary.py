"""The summary page of a project: ``<输出根>\\NNN-项目名\\NNN-项目名.html``, the overview of the Luz-Project session.

Three tables the reader needs (the results with their place in the project directory, the stages with their approvals, the sessions of the other
skills) and one for the files the tools keep. The frame is make_summary.py's, the same page every Luz skill writes.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import project_core as pc

SUMMARY_STAGE = "internal-summary"
PURPOSE = {
    "project.json": "项目状态、阶段与路径（以它为准）",
    "MANIFEST.json": "project.json 的副本",
    "APPROVALS.json": "审批记录（逐文件，含预先授权待复核的、内部完成的、动作门的）",
    "backup": "升级审批模型和迁移前的备份",
    "data": "台账与事实 JSON：客户文档数据、阶段文档数据、变更台账、验收清单、运维结果；steps.json 是内部步骤记录，review-notes.json 是你的修改意见",
    "config": "Luz 工具配置：文档主题、目录对应、密钥引用清单",
    "00-crawl": "各阶段的前置检索记录与结论页",
    "00-design": "实际模板选择、源快照、最终文件校验值与同字节迁移凭据",
    "reviews": "评审页（内部记录，无需审阅）",
    "uploads": "客户给的原始资料",
    "client-docs": "客户文档的 Word 源文件、构建中间件与页面总览图",
}


def _backslash(rel: str) -> str:
    return rel.replace("/", "\\")


def sessions(root: Path) -> list[dict[str, Any]]:
    value = pc._read_json(root.joinpath("data", "sessions.json"), {}) or {}
    return [dict(item) for item in (value.get("sessions") if isinstance(value, dict) else None) or [] if isinstance(item, dict)]


def register_session(project: Path | str, skill: str, path: Path | str, stage: str = "", note: str = "") -> dict[str, Any]:
    """Record a session of another skill that belongs to this project (the summary page lists it). The same path is recorded once."""
    root = pc._project_root(project)
    if not str(skill).strip() or not str(path).strip():
        raise pc.ProjectError("会话要写明技能和会话目录")
    if stage and stage not in {str(s.get("id")) for s in pc.load_project(root).get("stages", [])}:
        raise pc.ProjectError(f"未知阶段: {stage}")
    entries = sessions(root)
    entry = {"skill": str(skill).strip(), "path": str(Path(path)), "stage": stage, "note": str(note).strip()}
    entries = [e for e in entries if e.get("path") != entry["path"]] + [entry]
    pc._write_json(root.joinpath("data", "sessions.json"), {"schema_version": "1.0", "sessions": entries})
    return entry


def _session_label(path: str) -> str:
    parts = Path(path).parts
    return "\\".join(parts[-2:]) if len(parts) >= 2 else path


def summary_spec(root: Path) -> dict[str, Any]:
    manifest = pc.load_project(root)
    deliver = pc.deliver_root(root)
    artifacts = pc._load_artifacts(root)
    stages = manifest.get("stages", [])
    stage_name = {str(s.get("id")): str(s.get("name", s.get("id"))) for s in stages}
    by_path = {str(a.get("path", "")).replace("\\", "/"): a for a in artifacts}
    spec_sections: list[dict[str, Any]] = []

    results: list[list[str]] = []
    for folder in pc.DOC_FOLDERS:
        base = deliver / folder
        for file in sorted(base.iterdir()) if base.is_dir() else []:
            if file.is_file() and not file.name.startswith("."):
                rel = f"{folder}/{file.name}"
                art = by_path.get(rel)
                results.append([file.stem, stage_name.get(str(art.get("stage")), "—") if art else "—", _backslash(rel)])
    if results:
        spec_sections.append({"title": "成果", "text": "成果只放在项目目录的 docs 下，位置是项目内的相对路径。",
                              "table": {"caption": "表 1　成果清单", "columns": ["名称", "所属阶段", "位置"], "rows": results}})

    approvals = {str(a.get("id")): a for a in pc._load_approvals(root).get("approvals", [])}
    rows = []
    for stage in stages:
        approval = approvals.get(str(stage.get("approval_id")))
        rows.append([str(stage.get("name", stage.get("id"))), str(stage.get("owner", "—")), pc.STATUS_LABELS.get(str(stage.get("status")), str(stage.get("status"))),
                     str(approval.get("approver")) if approval else "—", str(approval.get("approved_at", "—")).replace("T", " ").replace("Z", "") if approval else "—"])
    current = stage_name.get(str(manifest.get("current_stage")), str(manifest.get("current_stage")))
    spec_sections.append({"title": "阶段与审批", "text": f"项目状态：{pc.STATUS_LABELS.get(str(manifest.get('status')), manifest.get('status'))}；当前阶段：{current}。",
                          "table": {"caption": f"表 {2 if results else 1}　阶段状态与审批", "columns": ["阶段", "负责人", "状态", "审批人", "审批时间"], "rows": rows, "align": ["left", "left", "center", "center", "center"]}})

    listed = [[e.get("skill", "—"), _session_label(str(e.get("path", ""))), stage_name.get(str(e.get("stage")), "—") if e.get("stage") else "—", e.get("note") or "—"] for e in sessions(root)]
    task = (manifest.get("crawl") or {}).get("task_root")
    if task and not any(str(r[1]) == _session_label(str(task)) for r in listed):
        listed.append(["Luz-Crawl", _session_label(str(task)), "各阶段前置检索", "项目复用的检索任务，爬取的原始内容在该任务里"])
    if listed:
        spec_sections.append({"title": "技能会话", "table": {"caption": f"表 {len(spec_sections) + 1}　各技能为本项目产出的会话", "columns": ["技能", "会话", "阶段", "用途"], "rows": listed}})

    files = [[_backslash(f"raw/{name}"), purpose] for name, purpose in PURPOSE.items() if (root / name).exists()]
    if files:
        spec_sections.append({"title": "过程文件", "table": {"caption": f"表 {len(spec_sections) + 1}　raw 下的主要文件和用途", "columns": ["位置", "用途"], "rows": files}})
    return {"title": f"{manifest['name']}项目总览", "sections": spec_sections}


def design_library():
    """Load the real Design template contract without a same-name module leak."""
    design = Path(os.environ.get("LUZ_DESIGN_ROOT") or pc.ROOT.parent / "Luz-Design")
    source = design / "scripts/template_library.py"
    spec = importlib.util.spec_from_file_location("_luz_project_summary_design_library", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_page(root: Path, library) -> str:
    """Render the structured state tables with the selected Design generator."""
    source = library.ROOT / "scripts/make_summary.py"
    spec = importlib.util.spec_from_file_location("_luz_project_summary_reading_template", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render(summary_spec(root))


def render_summary(root: Path) -> Path | None:
    """Write the summary page of a project with its own session; None for a project of the old layout (it has no session until ``migrate``).
    A project approved by document gets the user's page (user_page): the one file waiting for review, the files in order with their state, and the process
    records folded at the end; a project of the older model keeps the stage table."""
    page = pc.summary_path(root)
    if page is None:
        return None
    import approval_docs

    # This index renders existing machine state, not a new business proposal.
    # Initialisation and internal status updates must not recursively open a
    # research stage. The separate docs writers/presentation gates still check
    # the business stage's Crawl record and the exact deliverable's receipt.
    session = pc.session_dir(root)
    try:
        library = design_library()
        library.select(session, "luz-project", SUMMARY_STAGE, "reading-html", str(page.resolve()))
        library.require_selected(session, "luz-project", SUMMARY_STAGE, page, "reading-html")
        content = user_page(root) if approval_docs.is_document_model(root) else _legacy_page(root, library)
        page.parent.mkdir(parents=True, exist_ok=True)
        temporary = page.with_suffix(page.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(page)
        library.record_output(session, "luz-project", SUMMARY_STAGE, page, "reading-html",
                              generator="Luz-Project/scripts/project_summary.py:render_summary")
        library.require_selected(session, "luz-project", SUMMARY_STAGE, page, "reading-html", phase="post")
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise pc.ProjectError(f"项目状态总览模板未通过：{exc}") from exc
    return page


EXTRA_CSS = """details { margin: 0 0 24px; border-top: 1px solid var(--line); padding-top: 12px; }
summary { cursor: pointer; font-size: var(--md-h2); line-height: 1.3; font-weight: 700; padding-bottom: 12px; }
tr.current td { background: var(--tint); }
td.nowrap, th.nowrap { white-space: nowrap; }"""


def _table(caption: str, columns: list[str], rows: list[list[str]], align: list[str] | None = None, current: int | None = None, nowrap: tuple[int, ...] = ()) -> str:
    from make_summary import esc

    align = list(align or []) + ["left"] * len(columns)
    head = "".join(f'<th scope="col">{esc(c)}</th>' for c in columns)
    body = ""
    for i, row in enumerate(rows):
        mark = ' class="current"' if current == i else ""
        body += f"<tr{mark}>" + "".join(f'<td class="{align[j]}{" nowrap" if j in nowrap else ""}">{esc(v)}</td>' for j, v in enumerate(row)) + "</tr>"
    wrap = ' class="nowrap"'
    head = "".join(f'<th scope="col"{wrap if i in nowrap else ""}>{esc(c)}</th>' for i, c in enumerate(columns))
    return f'<div class="table-wrap"><table><caption>{esc(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


MODE_LABELS = {"user": "用户逐个通过", "pre-authorized": "待用户复核（预先授权）", "internal": "内部门通过（无 docs 文件）"}


def _win(path: str) -> str:
    return path.replace("/", chr(92))


def user_page(root: Path) -> str:
    """The summary page as the user reads it. At the top only what needs the user: the single file waiting for their review (path, what it is, how to look at it) and the
    files in the order they are reviewed, each with its state. Everything the user does not review (internal checks, review pages, Crawl records, sessions,
    approval records) is folded at the end under 过程记录（无需审阅）."""
    import approval_docs as ad
    import flow_steps
    import make_summary
    from make_summary import esc

    manifest = pc.load_project(root)
    ctx = ad.Ctx(root)
    report = flow_steps.next_report(root)
    counter = [0]

    def cap(text: str) -> str:
        counter[0] += 1
        return f"表 {counter[0]}　{text}"

    parts = [f"<h1>{esc(manifest['name'])}项目总览</h1>"]
    if report.get("user_todos"):
        parts.append("<section><h2>需要你先做</h2>" + _table(cap("别人替不了的事"), ["事项"], [[t] for t in report["user_todos"]]) + "</section>")
    kind = report.get("kind")
    if kind == "present":
        doc = report["document"]
        parts.append("<section><h2>当前待审文件</h2>" + _table(cap("现在只需要你看这一个文件"), ["文件", "是什么", "怎么看"], [[_win(doc["path"]), doc["what"], doc["how"]]]) + "</section>")
    elif kind == "revise":
        doc = report["document"]
        parts.append("<section><h2>当前待审文件</h2>" + _table(cap("你提过修改意见，处理后再请你审"), ["文件", "你的意见"], [[_win(doc["path"]), "；".join(n["text"] for n in report["open_notes"])]]) + "</section>")
    elif kind == "done":
        parts.append("<section><h2>当前待审文件</h2><p>没有待审文件：所有文件都已通过，动作门都已授权。</p></section>")
    else:
        target = report.get("document")
        text = "现在没有可以请你审的文件：" + ("下一个要审的 " + _win(target["path"]) + " 还要先做完内部步骤（" + "、".join((report.get("current_step") or {}).get("id", "").split()) + "），" if target else "") + "做完后会请你审，这些内部步骤不需要你看"
        if kind == "waiting":
            text = "文件都已通过，还差：" + "；".join(report.get("waiting_for") or [])
        parts.append(f"<section><h2>当前待审文件</h2><p>{esc(text)}。</p></section>")

    files = []
    current_index = None
    for i, d in enumerate(ctx.docs):
        st = ad.document_status(ctx, d)
        files.append([str(i + 1), _win(d["path"]), str(pc._stage_record(manifest, d["stage"]).get("name", d["stage"])), flow_steps.label_of(ctx, d, st)])
        if report.get("document") and report["document"]["path"] == d["path"]:
            current_index = i
    for sid in ad.stage_order():
        for d in ad.documents(root, sid, approvable=False):
            if d.get("living"):
                files.append(["—", _win(d["path"]), str(pc._stage_record(manifest, sid).get("name", sid)), "不单独审批（随变更台账，交接时审快照）"])
            elif d.get("client_input"):
                files.append(["—", _win(d["path"]), str(pc._stage_record(manifest, sid).get("name", sid)), "客户填写，不审批"])
    parts.append("<section><h2>文件清单与状态</h2>" + _table(cap("按审批顺序的 docs 文件，一次只审一个"), ["序号", "文件", "阶段", "状态"], files, ["center", "left", "center", "center"], current_index, nowrap=(0, 2)) + "</section>")

    folded = []
    gates = []
    for entry in manifest.get("stages", []):
        sched = flow_steps.checklist(root, entry["id"], ctx=ctx)
        internal = [r for r in sched["steps"] if r["gate"] != "user"]
        done = sum(1 for r in internal if r["status"] == "done")
        gates.append([str(entry.get("name", entry["id"])), f"{done} / {len(internal)}", "；".join(r["id"] for r in internal if r["status"] != "done") or "全部通过"])
    folded.append("<h3>各阶段的内部检查</h3>" + _table(cap("内部步骤的完成情况（用户不需要操作）"), ["阶段", "已通过 / 共", "未通过的步骤"], gates, ["left", "center", "left"]))
    records = [[str(r.get("document") or r.get("stage")), MODE_LABELS.get(str(r.get("mode")), str(r.get("mode"))), str(r.get("approver", "—")), str(r.get("id"))]
               for r in ctx.ledger["approvals"] if r.get("scope") in {"document", "stage", "action"} and r.get("status", "approved") == "approved"]
    if records:
        folded.append("<h3>审批记录</h3>" + _table(cap("现行有效的审批记录"), ["文件或阶段", "方式", "审批人", "记录"], records, ["left", "center", "center", "center"]))
    stage_name = {str(s.get("id")): str(s.get("name", s.get("id"))) for s in manifest.get("stages", [])}
    listed = [[e.get("skill", "—"), _session_label(str(e.get("path", ""))), stage_name.get(str(e.get("stage")), "—") if e.get("stage") else "—", e.get("note") or "—"] for e in sessions(root)]
    task = (manifest.get("crawl") or {}).get("task_root")
    if task and not any(str(r[1]) == _session_label(str(task)) for r in listed):
        listed.append(["Luz-Crawl", _session_label(str(task)), "各阶段前置检索", "项目复用的检索任务，爬取的原始内容在该任务里"])
    if listed:
        folded.append("<h3>技能会话</h3>" + _table(cap("各技能为本项目产出的会话"), ["技能", "会话", "阶段", "用途"], listed))
    files_rows = [[_backslash(f"raw/{name}"), purpose] for name, purpose in PURPOSE.items() if (root / name).exists()]
    if files_rows:
        folded.append("<h3>过程文件</h3>" + _table(cap("raw 下的主要文件和用途"), ["位置", "用途"], files_rows))
    parts.append("<details><summary>过程记录（无需审阅）</summary>" + "".join(folded) + "</details>")

    title = f"{manifest['name']}项目总览"
    page = design_library().render_reading(title, "\n".join(parts[1:]))
    return page.replace("</style>", EXTRA_CSS + "\n</style>", 1)
