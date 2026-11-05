"""The summary page of a project: ``<输出根>\\NNN-项目名\\NNN-项目名.html``, the overview of the Luz-Project session.

Three tables the reader needs (the results with their place in the project directory, the stages with their approvals, the sessions of the other
skills) and one for the files the tools keep. The frame is make_summary.py's, the same page every Luz skill writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import project_core as pc

SESSIONS_FILE = ("data", "sessions.json")
PURPOSE = {
    "project.json": "项目状态、阶段与路径（以它为准）",
    "MANIFEST.json": "project.json 的副本",
    "APPROVALS.json": "各阶段的审批记录",
    "data": "台账与事实 JSON：客户文档数据、阶段文档数据、变更台账、验收清单、运维结果",
    "config": "Luz 工具配置：文档主题、目录对应、密钥引用清单",
    "00-crawl": "各阶段的前置检索记录与结论页",
    "reviews": "给你审批、给开发看的评审页",
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


def render_summary(root: Path) -> Path | None:
    """Write the summary page of a project with its own session; None for a project of the old layout (it has no session until ``migrate``)."""
    page = pc.summary_path(root)
    if page is None:
        return None
    import make_summary

    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(make_summary.render(summary_spec(root)), encoding="utf-8")
    return page
