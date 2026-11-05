#!/usr/bin/env python3
"""Command line interface for the Luz project control plane.

A project is given as its project directory (``D:\\Codes\\NNN-项目名``) or as its state root (the ``raw`` of its session in the output root); every
command except ``init`` takes either."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project_core import (
    ProjectError,
    approve_stage,
    create_project,
    deliver_root,
    is_legacy,
    load_matrix,
    load_project,
    output_root,
    resolve_state_root,
    project_status,
    register_artifact,
    render_project,
    stage_route,
    set_stage_status,
    validate_project,
    gate_stage,
    stage_context,
)


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _path(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Luz 完整项目生命周期控制台")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="创建项目：会话（状态根与汇总页）在输出根，项目目录只有成果")
    init.add_argument("name")
    init.add_argument("--project-dir", required=True, help="项目目录 D:/Codes/NNN-项目名（不存在则创建）；会话目录与它同名")
    init.add_argument("--output-root", help="Luz-Project 的输出根（默认 D:/Codes/skill输出/Luz-Project，或环境变量 LUZ_PROJECT_OUTPUT）")
    init.add_argument("--repository")

    status = sub.add_parser("status", help="查看项目状态")
    status.add_argument("project")

    route = sub.add_parser("route", help="查看当前或指定阶段的路由")
    route.add_argument("project")
    route.add_argument("stage", nargs="?")

    stage = sub.add_parser("stage", help="更新阶段状态")
    stage.add_argument("project")
    stage.add_argument("stage")
    stage.add_argument("status", nargs="?", choices=["pending", "pending-review", "in-progress", "approved", "blocked", "rejected", "superseded", "completed"])
    stage.add_argument("--status", dest="status_flag", choices=["pending", "pending-review", "in-progress", "approved", "blocked", "rejected", "superseded", "completed"])

    artifact = sub.add_parser("artifact", help="登记阶段产物")
    artifact.add_argument("project")
    artifact.add_argument("stage")
    artifact.add_argument("path", nargs="?")
    artifact.add_argument("--path", dest="path_flag")
    artifact.add_argument("--kind", default="html")
    artifact.add_argument("--source-id", action="append", default=[])

    approve = sub.add_parser("approve", help="记录用户阶段审批")
    approve.add_argument("project")
    approve.add_argument("stage")
    approve.add_argument("--note", required=True)
    approve.add_argument("--approver", required=True)

    render = sub.add_parser("render", help="重新生成会话的汇总页")
    render.add_argument("project")

    check = sub.add_parser("check", help="检查状态根、项目目录（只放成果）、会话和产物")
    check.add_argument("project")
    check.add_argument("--strict", action="store_true")

    matrix = sub.add_parser("matrix", help="输出完整开发矩阵")
    matrix.add_argument("--json", action="store_true", dest="as_json")
    gate = sub.add_parser("gate", help="检查当前阶段的前置审批和检索证据")
    gate.add_argument("project")
    gate.add_argument("stage")
    context = sub.add_parser("context", help="输出已批准的具体交接文件与项目上下文")
    context.add_argument("project")
    context.add_argument("stage")
    context.add_argument("--skill")
    document = sub.add_parser("document", help="根据真实阶段数据生成评审 HTML（架构为三个 Tab）")
    document.add_argument("project")
    document.add_argument("stage")
    document.add_argument("--file", required=True)

    adopt = sub.add_parser("adopt", help="把既有仓库就地接入为 Luz 项目（仓库做项目目录，不改代码目录；文档按 --move 迁移）")
    adopt.add_argument("project")
    adopt.add_argument("--output-root", help="Luz-Project 的输出根")
    adopt.add_argument("--name")
    adopt.add_argument("--move", action="append", default=[], metavar="旧=新", help="相对项目根的路径迁移，可重复；已跟踪文件用 git mv")
    adopt.add_argument("--alias", action="append", default=[], metavar="标准目录=实际目录", help="例如 test=tests、infra=config、raw/logs=logs")
    relink = sub.add_parser("relink", help="按接入时记录的迁移（或 --move 旧=新）修复 Markdown 链接和文档路径提及")
    relink.add_argument("project")
    relink.add_argument("--move", action="append", default=[], metavar="旧=新")
    migrate = sub.add_parser("migrate", help="把旧项目迁到新布局并升级到当前矩阵；默认只预演，加 --apply 才执行")
    migrate.add_argument("project")
    migrate.add_argument("--apply", action="store_true", help="执行迁移（默认只列出会搬什么、会改什么）")
    migrate.add_argument("--output-root", help="Luz-Project 的输出根（旧项目的新会话建在这里）")
    session = sub.add_parser("session", help="登记或列出其他技能为本项目产出的会话（汇总页的会话索引）")
    session.add_argument("project")
    session.add_argument("action", choices=["add", "list"])
    session.add_argument("--skill")
    session.add_argument("--path")
    session.add_argument("--stage", default="")
    session.add_argument("--note", default="")
    trace = sub.add_parser("trace", help="功能 → 架构 → 使用说明 → 验收项 → 变更 的追溯与缺口")
    trace.add_argument("project")

    link = sub.add_parser("link", help="登记功能在架构/设计/开发中的落点（供 trace 使用）")
    link.add_argument("project")
    link.add_argument("feature")
    link.add_argument("--arch", default="")
    link.add_argument("--design", default="")
    link.add_argument("--dev", default="")

    client = sub.add_parser("client", help="客户文档：方案 PDF、业务逻辑确认表、验收清单、使用说明（经 Luz-Design 版式与检查）")
    client.add_argument("project")
    client.add_argument("action", choices=["theme", "requirements-draft", "requirements", "proposal-draft", "proposal", "intake-form", "intake-import", "intake-status", "intake-defer", "acceptance-plan", "acceptance", "acceptance-import", "acceptance-waive", "manual-draft", "manual"])
    client.add_argument("value", nargs="?", help="theme 名、导入的 xlsx 路径、defer/waive 的键或编号")
    client.add_argument("--force", action="store_true", help="来源未变化时也重新生成")
    client.add_argument("--all-questions", action="store_true", help="确认表包含问题库的全部问题")
    client.add_argument("--owner")
    client.add_argument("--due")
    client.add_argument("--by")
    client.add_argument("--note")

    change = sub.add_parser("change", help="全局需求变更台账（客户新增需求/修改规则/补充细节都先登记）")
    change.add_argument("project")
    change.add_argument("action", choices=["add", "update", "list", "render", "snapshot"])
    change.add_argument("id", nargs="?")
    change.add_argument("--type", choices=["新增", "修改", "删除", "补充"])
    change.add_argument("--category", default="需求", choices=["需求", "规则", "界面", "流程", "技术", "范围", "其他"])
    change.add_argument("--title")
    change.add_argument("--detail", help="变更后的逻辑或补充的细节，必须具体")
    change.add_argument("--source", default="客户", choices=["客户", "内部", "测试发现", "政策法规"])
    change.add_argument("--requester", default="")
    change.add_argument("--refs", default="", help="关联功能/需求 ID，逗号分隔")
    change.add_argument("--affects", default="", help="影响的阶段 ID，逗号分隔；update 时替换原有的，已确认的变更会重开新补进的已批准阶段（--no-reopen 只记录）")
    change.add_argument("--impact", default="")
    change.add_argument("--status", choices=["待确认", "已确认", "已实施", "已驳回"])
    change.add_argument("--confirmed-by")
    change.add_argument("--feature-ops", help="JSON 文件：[{op:add|update|remove, feature:{...}}]，确认时应用到功能清单")
    change.add_argument("--no-reopen", action="store_true", help="确认变更时不重开已批准阶段（仅限不影响已批准内容）")
    change.add_argument("--all-confirmed", action="store_true", help="update：把所有已确认变更标为已实施")
    change.add_argument("--note", help="过程记录（审批编号、阶段名、出处等），写进 note 字段，不进客户台账；detail 只写客户看得懂的逻辑")
    change.add_argument("--client-visible", choices=["是", "否", "默认"], help="是否进入交给客户的台账与交付快照；默认：来源为客户且分类为需求、规则、范围的可见，其余（内部、技术、界面等）不可见；add/update 都可设置，“默认”清除显式设置")
    return parser


def run_client(args: argparse.Namespace) -> object:
    import client_flow as cf

    root = resolve_state_root(_path(args.project))
    act = args.action
    if act == "theme":
        return cf.set_theme(root, args.value or "")
    if act == "requirements-draft":
        return [str(p) for p in cf.requirements_draft(root)]
    if act == "requirements":
        return [str(p) for p in cf.build_requirements(root, force=args.force)]
    if act == "proposal-draft":
        return [str(p) for p in cf.proposal_draft(root)]
    if act == "proposal":
        return [str(p) for p in cf.build_proposal(root, force=args.force)]
    if act == "intake-form":
        return str(cf.build_intake_form(root, force=args.force, include_all=args.all_questions))
    if act == "intake-import":
        return cf.import_intake(root, _path(args.value))
    if act == "intake-status":
        return cf.intake_status(root)
    if act == "intake-defer":
        cf.defer_intake(root, args.value, args.owner or "", args.due or "", args.note or "")
        return cf.intake_status(root)
    if act == "acceptance-plan":
        cf.generate_acceptance(root)
        return cf.acceptance_status(root)
    if act == "acceptance":
        cf.generate_acceptance(root)
        return {"checklist": str(cf.build_acceptance_xlsx(root)), "status": cf.acceptance_status(root)}
    if act == "acceptance-import":
        return cf.import_acceptance(root, _path(args.value))
    if act == "acceptance-waive":
        cf.waive_acceptance(root, args.value, args.by or "", args.note or "")
        return cf.acceptance_status(root)
    if act == "manual-draft":
        return str(cf.manual_draft(root))
    return str(cf.build_manual(root, force=args.force))


def run_change(args: argparse.Namespace) -> object:
    import client_flow as cf

    root = resolve_state_root(_path(args.project))
    split = lambda value: [x.strip() for x in value.split(",") if x.strip()]
    visible_flag = lambda value: {"是": True, "否": False, "默认": "default" if args.action == "update" else None}.get(value)
    if args.action == "add":
        ops = json.loads(_path(args.feature_ops).read_text(encoding="utf-8-sig")) if args.feature_ops else None
        if not (args.type and args.title and args.detail):
            raise ProjectError("change add 需要 --type --title --detail")
        return cf.add_change(root, type=args.type, category=args.category, title=args.title, detail=args.detail, source=args.source, requester=args.requester,
                             refs=split(args.refs), affects=split(args.affects), impact=args.impact, status=args.status or "待确认", feature_ops=ops,
                             reopen=not args.no_reopen, confirmed_by=args.confirmed_by, client_visible=visible_flag(args.client_visible), note=args.note or "")
    if args.action == "update":
        if args.all_confirmed:
            return [cf.update_change(root, c["id"], status="已实施", note=args.note or "") ["id"] for c in cf._ledger(root)["changes"] if c["status"] == "已确认"]
        if not args.id:
            raise ProjectError("change update 需要 变更编号，以及 --status 或 --client-visible / --detail / --impact / --confirmed-by / --affects / --note 之一")
        return cf.update_change(root, args.id, status=args.status, confirmed_by=args.confirmed_by, note=args.note or "", reopen=not args.no_reopen,
                                client_visible=visible_flag(args.client_visible), detail=args.detail, impact=args.impact if args.impact else None,
                                affects=split(args.affects) or None)
    if args.action == "render":
        path = cf.render_ledger(root)
        if not path:
            return "台账为空或未选定主题，未生成"
        ledger = cf._ledger(root)["changes"]
        return {"path": str(path), "client_visible": sum(1 for c in ledger if cf.is_client_visible(c)), "internal_only": sum(1 for c in ledger if not cf.is_client_visible(c)), "warnings": cf.ledger_warnings(root)}
    if args.action == "snapshot":
        return str(cf.snapshot_ledger(root))
    return cf._ledger(root)["changes"]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            state = create_project(args.name, _path(args.project_dir), _path(args.output_root) if args.output_root else output_root(), args.repository)
            _print({"project": str(deliver_root(state)), "state_root": str(state), "session": str(state.parent), "summary": str(state.parent / f"{state.parent.name}.html")})
        elif args.command == "status":
            _print(project_status(_path(args.project)))
        elif args.command == "route":
            _print(stage_route(_path(args.project), args.stage))
        elif args.command == "gate":
            errors = gate_stage(_path(args.project), args.stage)
            _print({"ok": not errors, "errors": errors})
            return 1 if errors else 0
        elif args.command == "context":
            _print(stage_context(_path(args.project), args.stage, args.skill))
        elif args.command == "document":
            from stage_documents import write_document
            payload = json.loads(_path(args.file).read_text(encoding="utf-8-sig"))
            _print({"path": str(write_document(_path(args.project), args.stage, payload))})
        elif args.command == "stage":
            status = args.status or args.status_flag
            if not status:
                raise ProjectError("stage 需要 status 或 --status")
            _print(set_stage_status(_path(args.project), args.stage, status))
        elif args.command == "artifact":
            path = args.path or args.path_flag
            if not path:
                raise ProjectError("artifact 需要 path 或 --path")
            _print(register_artifact(_path(args.project), args.stage, _path(path), args.kind, args.source_id))
        elif args.command == "approve":
            _print(approve_stage(_path(args.project), args.stage, args.note, args.approver))
        elif args.command == "render":
            _print({"rendered": [str(path) for path in render_project(_path(args.project))]})
        elif args.command == "check":
            errors = validate_project(_path(args.project), args.strict)
            notes = ["项目是旧布局（状态与过程文件还在项目目录里）：运行 project.py migrate <项目> 预演迁移，确认后加 --apply"] if not errors and is_legacy(_path(args.project)) else []
            _print({"ok": not errors, "errors": errors, **({"notes": notes} if notes else {})})
            return 1 if errors else 0
        elif args.command == "adopt":
            from project_core import adopt_project
            pair = lambda v: tuple(x.strip() for x in v.split("=", 1))
            _print(adopt_project(_path(args.project), args.name, moves=[pair(v) for v in args.move], aliases=dict(pair(v) for v in args.alias),
                                 output=_path(args.output_root) if args.output_root else None))
        elif args.command == "relink":
            from project_core import load_project, relink_after_moves
            pairs = [tuple(x.strip() for x in v.split("=", 1)) for v in args.move] or [tuple(x) for x in load_project(_path(args.project)).get("adopted", {}).get("pairs", [])]
            _print(relink_after_moves(_path(args.project), pairs))
        elif args.command == "migrate":
            from project_core import migrate_project
            _print(migrate_project(_path(args.project), apply=args.apply, output=_path(args.output_root) if args.output_root else None))
        elif args.command == "session":
            import project_summary
            if args.action == "add":
                _print(project_summary.register_session(_path(args.project), args.skill or "", args.path or "", args.stage, args.note))
            else:
                _print(project_summary.sessions(resolve_state_root(_path(args.project))))
        elif args.command == "trace":
            import client_flow
            result = client_flow.trace(resolve_state_root(_path(args.project)))
            _print(result)
            return 1 if result["gaps"] else 0
        elif args.command == "link":
            import client_flow
            split = lambda v: [x.strip() for x in v.split(",") if x.strip()]
            _print(client_flow.link_feature(resolve_state_root(_path(args.project)), args.feature, arch=split(args.arch), design=split(args.design), dev=split(args.dev)))
        elif args.command == "client":
            _print(run_client(args))
        elif args.command == "change":
            _print(run_change(args))
        elif args.command == "matrix":
            matrix_value = load_matrix()
            if args.as_json:
                _print(matrix_value)
            else:
                for stage in matrix_value.get("stages", []):
                    print(f'{stage["id"]}\t{stage.get("name", "")}\towner={stage.get("owner", "")}\tnext={stage.get("next") or "-"}')
        return 0
    except (ProjectError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

