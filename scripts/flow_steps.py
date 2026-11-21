"""The ordered path of a stage (matrix ``steps``), checked against the live state: what is done, what is next, what blocks it.

Every step has a *gate*: ``internal`` (the agent does it, a check proves it; the user is not asked to look), ``user`` (the user decides about one file),
``client`` (the client's own input) or ``action`` (an act that is not a file). A stage may show a file to the user, and the user's approval of it may be
recorded, only when all steps of the phases ``prepare`` and ``produce`` pass: upstream files approved, rule cards read and noted, Luz-Crawl preflight
concluded, specialist output present, the files built and fresh, the internal records written, trace without gaps. Nothing here relaxes with the number of
files a user wants to see: internal steps are not skippable, they are only not shown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import approval_docs as ad
import estimate_policy as ep
import project_core as pc
from project_paths import ProjectError, command_project, locate

PREPARE, PRODUCE, REVIEW, COMPLETE = "prepare", "produce", "review", "complete"
INTERNAL_PHASES = (PREPARE, PRODUCE)
GATE_LABELS = {"internal": "内部门", "user": "用户门", "client": "客户输入", "action": "动作门"}
MIN_NOTE = 8


# --- which steps apply -----------------------------------------------------------------------------------------

def steps_of(root: Path, stage: str) -> list[dict[str, Any]]:
    """The steps of a stage that apply to this project: the ones marked ``only_if: documents`` only when the stage has files for the user, ``no-documents`` only when it has none."""
    item = pc._stage_defs(root)[stage]
    has_docs = bool(ad.documents(root, stage))
    out = []
    for step in item.get("steps", []):
        cond = step.get("only_if")
        if cond == "documents" and not has_docs:
            continue
        if cond == "no-documents" and has_docs:
            continue
        out.append(step)
    return out


def _fmt(command: str, project: str, stage: str) -> str:
    return command.replace("<项目>", project).replace("<阶段>", stage)


# --- the checks ---------------------------------------------------------------------------------------------------

def _ops_errors(root: Path, stage: str) -> list[str]:
    if stage not in {"verification", "release", "operations"}:
        return []
    import sys

    sys.path.insert(0, str(pc.ROOT.parent / "Luz-Ops" / "scripts"))
    try:
        from ops_core import validate_ops  # type: ignore[import-not-found]
    except ImportError as exc:                                 # Luz-Ops missing is a failed check, not a skipped one
        return [f"Luz-Ops 的校验器读不到: {exc}"]
    return validate_ops(root, stage, check_project=False)


def _c_upstream(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    return ad.hold_errors(ctx, stage)


def _c_record(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    rec = ad.step_record(ctx.root, stage, step["record"])
    if not rec or len(str(rec.get("note", "")).strip()) < MIN_NOTE:
        return [f"data/steps.json 里没有 {stage} 的 {step['record']} 记录（project.py step <项目> {stage} {step['record']} --note \"…\"）"]
    return []


def _c_crawl(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    from project_crawl_gate import crawl_errors

    cache = ctx.cache.setdefault("crawl", {})              # one Ctx is one operation: the Crawl records of a stage are validated once, not once per stage after it
    if stage not in cache:
        # The seven days count for the stage being worked on. Once all its files are approved (and its client input and action gates are through) the record only has to be
        # there, valid and concluded: a project that takes longer than a week does not redo the research of stages the user already approved. A change that reopens the stage
        # voids those approvals, so the age counts again from then on.
        cache[stage] = crawl_errors(ctx.root, stage, caller=pc._stage_record(ctx.manifest, stage)["owner"], waive_expiry=ad.crawl_expiry_waived(ctx.root, stage, ctx=ctx))
    if stage == "scope" and pc.commercial_at(ctx.root):
        from commercial_workflow import scope_evidence_errors
        return list(cache[stage]) + scope_evidence_errors(ctx.root)
    return list(cache[stage])


def _specialist_files(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    errors: list[str] = []
    for rel_path in step.get("files", []):
        if not locate(ctx.root, rel_path).is_file():
            errors.append(f"专家技能的事实文件还不存在: {rel_path}")
    any_of = step.get("files_any", [])
    if any_of:
        deliver = pc.deliver_root(ctx.root)
        if not any((deliver / folder).is_dir() and any(p.is_file() for p in (deliver / folder).rglob("*")) for folder in any_of):
            errors.append("项目目录的 " + "、".join(any_of) + " 里还没有任何文件（代码和测试写进项目目录）")
    if stage == "proposal" and not light:
        errors += _estimate_errors(ctx.root)
    return errors + ([] if light else _ops_errors(ctx.root, stage))


def _estimate_errors(root: Path) -> list[str]:
    """The estimate switches of a project (person-days and quote are off unless a person asked, with the evidence) and, with workdays on, the hours and their basis on every function."""
    import client_data as cd

    state = cd.estimate_state(root)
    errors = [f"估算开关无效: {e}" for e in state.errors]
    if state.workdays:
        try:
            errors += ep.hours_errors(cd.load_features(root, validate=False))
        except ProjectError:
            pass                                                   # no function list yet: the files check says so
    return errors


def _c_specialist(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    return _c_record(ctx, stage, step) + _specialist_files(ctx, stage, step, light)


def _c_build(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    errors = []
    if stage == "proposal" and ep.read_state(ctx.root).waiting_for_quote:             # the three files are built by one command and it will not run without a person's number
        errors.append(ep.quote_wait_message())
    for d in ad.documents(ctx.root, stage):
        st = ad.document_status(ctx, d)
        if st["state"] == "missing":
            errors.append(f"{d['path']}：{st['detail']}")
        else:
            from project_template_gate import output_errors
            errors += output_errors(ctx.root, stage, d)
    if errors:
        return errors
    if pc.schema_at_least(ctx.manifest, "1.1"):
        import client_flow

        errors += client_flow.stage_checks(ctx.root, stage, phase="build")
    import dev_documents

    if dev_documents.has_standard(stage):
        spec = pc._read_json(ctx.root / "data" / "stages" / f"{stage}.json", {})
        problems = dev_documents.validate(stage, spec, ctx.root) + dev_documents.source_binding_errors(stage, spec, ctx.root)
        if problems:
            errors.append("开发文档没有通过 references/dev-documents.md 的标准: " + "; ".join(problems[:4]))
    return errors


def _c_records(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    errors = []
    item = pc._stage_defs(ctx.root)[stage]
    for rec in item.get("internal_records", []):
        kind = rec["kind"]
        if kind == "crawl-record":
            from project_crawl_gate import stage_record, uses_local_evidence

            record = stage_record(ctx.root, ctx.manifest, stage)
            if not record.is_file():
                errors.append(f"缺少 Crawl 前置记录: {record}")
            elif not uses_local_evidence(record) and not record.with_suffix(".html").is_file():
                errors.append(f"缺少 Crawl 联网结论页: {record.with_suffix('.html')}")
        elif kind == "frontend-spec-bundle":
            import client_flow

            errors += client_flow.architecture_frontend_errors(ctx.root)
        else:
            path = pc.state_name(ctx.root, rec["path"].partition("/")[0]) + "/" + rec["path"].partition("/")[2] if rec["path"].startswith(pc.REVIEW_DIR + "/") else rec["path"]
            art = ctx.registered(stage, path) or ctx.registered(stage, rec["path"])
            if not locate(ctx.root, path).is_file():
                errors.append(f"缺少{rec['title']}: {path}（{step['command'].split('；')[0]}）")
            elif art is None:
                errors.append(f"{rec['title']} {path} 没有登记为本阶段的产物")
            elif art.get("sha256") != ctx.hash_of(path):
                errors.append(f"{rec['title']} {path} 与产物登记表的哈希不一致")
    return errors


def cd_features(root: Path) -> list[dict[str, Any]]:
    import client_data as cd

    try:
        return cd.load_features(root, validate=False).get("features", [])
    except ProjectError:
        return []


def _c_trace(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    import client_flow

    try:
        gaps = client_flow.trace(ctx.root)["gaps"]
    except ProjectError as exc:
        return [str(exc)]
    if stage == "architecture":
        gaps = [g for g in gaps if "架构" in g]
        spec = pc._read_json(ctx.root / "data" / "stages" / "architecture.json", {}) or {}
        if not client_flow.architecture_cards(spec) and any(f.get("status", "in-scope") == "in-scope" for f in cd_features(ctx.root)):
            gaps.append("系统架构里还没有功能卡，无法对账（先 project.py document <项目> architecture）")
    return gaps[:6]


def _c_complete_client(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    import client_flow

    return client_flow.stage_checks(ctx.root, stage, phase="complete")


def _c_action(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    return [] if ad.action_effective(ctx, stage, step["action"]) else [f"用户还没有授权：{step['title']}"]


def _c_auto(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    return [] if ad.stage_record_effective(ctx, stage) else ["内部完成记录还没有写（内部步骤全部通过后 project.py approve <项目> " + stage + "）"]


def _c_user(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    docs = ad.documents(ctx.root, stage)
    todo = [ad.document_status(ctx, d) for d in docs]
    todo = [s for s in todo if s["state"] != "approved"]
    return [f"{s['document']}（{s['label']}）" for s in todo]


from commercial_workflow import build_errors as commercial_build_errors, template_errors as commercial_template_errors

CHECKS = {"commercial-build": commercial_build_errors, "commercial-templates": commercial_template_errors, "upstream": _c_upstream, "step-record": _c_record, "crawl": _c_crawl, "specialist": _c_specialist, "build": _c_build, "records": _c_records, "trace": _c_trace,
          "client-intake-imported": _c_complete_client, "handover-signed": _c_complete_client, "action": _c_action, "auto-complete": _c_auto,
          "present": _c_user, "decide": _c_user, "record": _c_user}


def check_step(ctx: ad.Ctx, stage: str, step: dict[str, Any], light: bool = False) -> list[str]:
    """The reasons a step is not done (empty when it is). ``light`` leaves out the evidence validation of Luz-Ops (done for the stage itself only)."""
    check = CHECKS.get(step["check"])
    if check is None:
        return [f"矩阵里的步骤 {step['id']} 用了未知的检查 {step['check']}"]
    cache = ctx.cache.setdefault("steps", {})                    # one Ctx is one operation: a step is checked once however many stages ask for it
    key = (stage, step["id"], light)
    if key not in cache:
        try:
            cache[key] = check(ctx, stage, step, light)
        except ProjectError as exc:                              # data the step needs is missing: the step is not done, the message says what
            cache[key] = [str(exc)]
    return list(cache[key])


def _short(title: str) -> str:
    """A step's title without its explanation: up to the first colon, semicolon or bracket, at most 16 characters."""
    import re

    return re.split(r"[：；（(]", title, maxsplit=1)[0][:16]


def internal_errors(root: Path, stage: str, *, ctx: ad.Ctx | None = None, phases: tuple[str, ...] = INTERNAL_PHASES, skip: tuple[str, ...] = (), light: bool = False) -> list[str]:
    """The internal steps (``prepare`` and ``produce``) of a stage that do not pass: one line each. A file is shown to the user and its approval recorded only when none is left.
    ``skip`` and ``light`` serve the check of the stages in front of this one (ad.hold_errors): their ``upstream`` step is not asked again and Luz-Ops' evidence is not re-validated."""
    ctx = ctx or ad.Ctx(root)
    errors = []
    for step in steps_of(root, stage):
        if step["phase"] not in phases or step["id"] in skip:
            continue
        problems = check_step(ctx, stage, step, light)
        if problems:
            errors.append(f"{step['id']}（{_short(step['title'])}）: " + " / ".join(problems[:2]))
    return errors


def preparation_errors(root: Path, stage: str, *, ctx: ad.Ctx | None = None) -> list[str]:
    """Prerequisites for preparing specialist data, before those data exist.

    Draft helpers only write process JSON containing explicit placeholders.
    They still require upstream approvals, adopted rules and this stage's
    concluded Crawl evidence, but cannot require their own future output.
    """
    return internal_errors(root, stage, ctx=ctx, phases=(PREPARE,))


def generation_errors(root: Path, stage: str) -> list[str]:
    """What must be done before any file of ``stage`` is generated.

    A specialist output is a produce-phase prerequisite for every formal
    document.  Keeping it out of this gate used to let callers write a
    plausible-looking PDF/HTML after only recording rules and Crawl evidence.
    The build/records steps remain downstream because they depend on the file
    this function protects.
    """
    ctx = ad.Ctx(root)
    errors = preparation_errors(root, stage, ctx=ctx)
    specialist = next((step for step in steps_of(root, stage) if step.get("check") == "specialist"), None)
    if specialist is not None:
        problems = check_step(ctx, stage, specialist)
        if problems:
            errors.append(f"specialist（{_short(specialist['title'])}）: " + " / ".join(problems[:2]))
    return errors


# --- recording the two steps no tool can see ------------------------------------------------------------------

def record_step(project: Path | str, stage: str, step_id: str, note: str, by: str = "") -> dict[str, Any]:
    """``rules`` (the context and rule cards were read, which rules are adopted) and ``specialist`` (the specialist skills produced the data, their own checks passed)
    are noted by whoever did them. A step cannot be noted before the steps in front of it are done."""
    root = pc._project_root(project)
    if not ad.is_document_model(root):
        raise ProjectError("step 记录属于逐文件审批模型；旧项目先 project.py approvals-upgrade <项目>")
    pc._stage_record(pc.load_project(root), stage)
    ctx = ad.Ctx(root)
    steps = steps_of(root, stage)
    target = next((s for s in steps if s.get("record") == step_id), None)
    if target is None:
        raise ProjectError(f"阶段 {stage} 没有可记录的步骤 {step_id}；可记录的有：{'、'.join(str(s['record']) for s in steps if s.get('record'))}")
    if len(str(note).strip()) < MIN_NOTE:
        raise ProjectError(f"说明太短：写清读了哪些规则卡、采用了哪些规则（rules），或哪个技能产出了什么、它自带的检查结论（specialist），至少 {MIN_NOTE} 个字")
    for earlier in steps:
        if earlier is target:
            break
        if earlier["phase"] in INTERNAL_PHASES and earlier["check"] not in {"build", "records", "trace", "specialist"}:
            problems = check_step(ctx, stage, earlier)
            if problems:
                raise ProjectError(f"先完成前面的步骤「{earlier['id']}」再记 {step_id}: " + " / ".join(problems[:2]))
    if step_id == "specialist":
        problems = _specialist_files(ctx, stage, target)
        if problems:
            raise ProjectError("专家技能的产出还不齐，不能记 specialist: " + " / ".join(problems[:3]))
    steps_file = ad.load_steps(root)
    steps_file["records"].setdefault(stage, {})[step_id] = {"note": str(note).strip(), "by": str(by).strip(), "at": pc.now_iso(), "backfilled": False}
    pc._write_json(root.joinpath(*ad.STEPS_FILE), steps_file)
    return {"stage": stage, "step": step_id, **steps_file["records"][stage][step_id]}


# --- checklist ------------------------------------------------------------------------------------------------

def checklist(root: Path, stage: str, *, ctx: ad.Ctx | None = None, project: str = "<项目>") -> dict[str, Any]:
    """Every step of a stage with its live status: ``done``, ``todo`` (the first one not done is ``current``) or ``waiting``; what blocks it and the command to run."""
    ctx = ctx or ad.Ctx(root)
    steps = steps_of(root, stage)
    rows: list[dict[str, Any]] = []
    current_seen = False
    docs = ad.stage_documents_state(ctx, stage)
    current_doc = next((d for d in docs if d["state"] != "approved"), None)
    for step in steps:
        problems = check_step(ctx, stage, step)
        done = not problems
        backfilled = bool(step.get("record") and (ad.step_record(root, stage, step["record"]) or {}).get("backfilled"))
        row = {"id": step["id"], "title": step["title"], "gate": step["gate"], "gate_label": GATE_LABELS[step["gate"]], "skill": step["skill"], "phase": step["phase"],
               "status": "done" if done else "todo", "blocked_by": problems, "proof": step["proof"], "command": _fmt(step["command"], project, stage), "backfilled": backfilled}
        if step.get("per") == "document":
            row["document"] = (current_doc or {}).get("document")
        if step.get("record") == "rules" and pc._stage_defs(root)[stage].get("rule_files"):
            row["rule_files"] = [f["path"] + ("" if f["exists"] else "（找不到）") for f in pc.rule_files(stage, root)]
        if not done and not current_seen:
            row["status"], row["current"] = "todo", True
            current_seen = True
        elif not done:
            row["status"] = "waiting"
        rows.append(row)
    return {"stage": stage, "name": pc._stage_record(ctx.manifest, stage).get("name", stage), "steps": rows,
            "done": sum(1 for r in rows if r["status"] == "done"), "total": len(rows), "user_todos": ep.user_todos(root, f'"{project}"')}


# --- next ---------------------------------------------------------------------------------------------------------

FEATURE_LIST = "feature-list-xlsx"


def draft_mark(root: Path, doc: dict[str, Any], state: str) -> str:
    """The function list that carries person-days says so until the user has approved it: what it shows is an estimate (basis: hours_basis in features.json), not a promise."""
    if doc.get("kind") == FEATURE_LIST and state != "approved" and ep.read_state(root).workdays:
        return "工时（人天）是拟定值，估算依据在 features.json 每个功能的 hours_basis，你批准之后才作数"
    return ""


def quote_source(root: Path, doc: dict[str, Any]) -> str:
    state = ep.read_state(root)
    if doc.get("kind") == FEATURE_LIST and state.quote and state.quote_data and not state.quote_errors:
        return f"报价清单里的单价来自{state.quote_data.get('provided_by')}提供的报价（出处：{state.quote_data.get('evidence')}），不是我们估的"
    return ""


def label_of(ctx: ad.Ctx, doc: dict[str, Any], st: dict[str, Any]) -> str:
    return st["label"] + ("（工时拟定）" if draft_mark(ctx.root, doc, st["state"]) else "")


def _queue(ctx: ad.Ctx, after: str | None) -> list[dict[str, Any]]:
    """All approvable files after ``after`` in the global order (all of them when None) that are not approved yet."""
    out, seen = [], after is None
    for d in ctx.docs:
        if not seen:
            seen = d["path"] == after
            continue
        st = ad.document_status(ctx, d)
        out.append({"document": d["path"], "title": st["title"], "stage": d["stage"], "state": st["state"], "label": label_of(ctx, d, st)})
    return out


def next_report(project: Path | str) -> dict[str, Any]:
    """The one source for what to tell the user: the single file waiting for their review (why it is first, which internal checks it already passed, the queue after it),
    or, when no file can be shown yet, the next internal step with its command."""
    root = pc._project_root(project)
    manifest = pc.load_project(root)
    name = str(command_project(root))
    if not ad.is_document_model(root):
        return {"model": "stage", "kind": "legacy", "message": "这个项目还按阶段审批（旧模型）：当前阶段 " + str(manifest.get("current_stage")) + "。先 project.py approvals-upgrade <项目> 预演升级为逐文件审批。",
                "current_stage": manifest.get("current_stage")}
    ctx = ad.Ctx(root)
    estimate = ep.read_state(root)
    todos = ep.user_todos(root, f'"{name}"')
    focus: tuple[str, str, Any] | None = None
    for sid in ad.stage_order(root):
        from commercial_workflow import active, next_batch
        if active(root, sid):
            if not ad.stage_complete(ctx, sid) or internal_errors(root, sid, ctx=ctx):
                return next_batch(ctx, sid, checklist(root, sid, ctx=ctx, project=name))
            continue
        docs = ad.documents(root, sid)
        if not docs:
            if not ad.stage_record_effective(ctx, sid) or internal_errors(root, sid, ctx=ctx):
                focus = ("auto", sid, None)
                break
            continue
        states = [ad.document_status(ctx, d) for d in docs]
        pending = [s for s in states if s["state"] != "approved"]
        if pending:
            focus = ("document", sid, pending[0])
            break
        # A historical user approval does not replace the evidence and
        # output checks.  Revisit the stage before skipping to later files or
        # declaring the whole project done.
        problems = internal_errors(root, sid, ctx=ctx)
        if problems:
            focus = ("internal", sid, problems)
            break
        open_items = ad.completion_open(ctx, sid)
        if open_items:
            focus = ("waiting", sid, open_items)
            break
    if focus is None:
        return {"model": "document", "kind": "done", "message": "所有阶段的文件都已由用户通过，动作门都已授权；项目完成。", "queue": [], "user_todos": todos}
    kind, sid, payload = focus
    sched = checklist(root, sid, ctx=ctx, project=name)
    passed = [r for r in sched["steps"] if r["gate"] != "user" and r["status"] == "done" and r["phase"] in INTERNAL_PHASES]
    internal_open = [r for r in sched["steps"] if r["gate"] != "user" and r["status"] != "done" and r["phase"] in INTERNAL_PHASES]
    base = {"model": "document", "stage": sid, "stage_name": pc._stage_record(ctx.manifest, sid).get("name", sid), "user_todos": todos,
            "internal": {"passed": [r["id"] for r in passed], "open": [r["id"] for r in internal_open], "summary": f"内部检查 {len(passed)}/{len(passed) + len(internal_open)} 已通过"}}
    if kind == "auto":
        step = next((r for r in sched["steps"] if r.get("current")), None)
        return {**base, "kind": "internal", "message": f"阶段 {sid} 没有 docs 文件，不设用户审批；内部步骤做完后自动完成。", "current_step": step, "queue": _queue_from_stage(ctx, sid),
                "command": (step or {}).get("command")}
    if kind == "internal":
        step = next((r for r in sched["steps"] if r.get("current")), None)
        return {**base, "kind": "internal", "message": "本阶段已批准文件的内部依据未通过检查；先修复：" + "；".join(payload),
                "current_step": step, "queue": _queue_from_stage(ctx, sid), "command": (step or {}).get("command")}
    if kind == "waiting":
        step = next((r for r in sched["steps"] if r.get("current")), None)
        return {**base, "kind": "waiting", "message": "本阶段的文件都已通过；还差：" + "；".join(payload), "waiting_for": payload, "current_step": step, "queue": _queue_from_stage(ctx, sid),
                "command": (step or {}).get("command")}
    doc = payload
    meta = next(d for d in ctx.docs if d["path"] == doc["document"])
    queue = _queue(ctx, doc["document"])
    why = {"pending-review": "这是预先授权记录：你还没有逐个复核过它，只有你逐个通过后才算数；它在队列最前，之后的文件要等它通过才能生成。",
           "voided": doc["detail"] + "，需要重新审阅。", "notes": f"你提过修改意见，处理完（改完、标记 done、重新生成）后再请你审：{doc['detail']}。",
           "ready": "前面的文件都已通过，它是顺序里的下一个。", "missing": "前面的文件都已通过，下一个要生成它（见内部步骤）。"}[doc["state"]]
    first_ever = ctx.docs and ctx.docs[0]["path"] == doc["document"]
    if doc["state"] == "ready" and first_ever:
        why = "它是整个项目的第一个文件。"
    open_notes = [n for n in ctx.notes if n["document"] == doc["document"] and n["status"] == "open"]
    internal_ok = not internal_open
    current_step = next((r for r in sched["steps"] if r.get("current")), None)
    drafted = [x for x in (draft_mark(root, meta, doc["state"]), quote_source(root, meta)) if x]
    what_text = meta.get("what", "") + ("；" + "；".join(drafted) if drafted else "")
    result = {**base, "document": {"path": doc["document"], "title": doc["title"], "what": what_text, "how": meta.get("how", ""), "state": doc["state"], "label": label_of(ctx, meta, doc),
                                   "skill": meta.get("skill", ""), "mode": doc.get("mode")},
              "why": why, "open_notes": [{"id": n["id"], "text": n["text"]} for n in open_notes], "queue": queue}
    if sid == "proposal" and estimate.waiting_for_quote:
        step = next((r for r in sched["steps"] if r.get("current")), None)
        return {**result, "kind": "waiting", "message": "功能清单要写报价，还在等人工报价，方案阶段的文件先不生成、不出示。", "waiting_for": todos, "current_step": step, "command": (step or {}).get("command")}
    if doc["state"] == "missing" or not internal_ok:
        step = next((r for r in sched["steps"] if r.get("current")), None)
        return {**result, "kind": "internal", "message": "这个文件还不能出示给用户：内部步骤没有全部完成（用户不需要看这些，做完即可）。", "current_step": step, "command": (step or {}).get("command")}
    if doc["state"] == "notes":
        return {**result, "kind": "revise", "message": "用户对它提过修改意见：按意见修改并重新生成，再标记 done，然后重新出示。",
                "command": f'{CLI} review "{name}" done --id {open_notes[0]["id"]}' if open_notes else None, "current_step": current_step}
    report = [f"文件：{doc['document']}", f"是什么：{what_text or doc['title']}", f"怎么看：{meta.get('how', '')}。请回复“通过”或提修改意见。"]
    return {**result, "kind": "present", "message": "可以向用户出示这一个文件（只出示它，别的文件通过前不生成、不出示）。", "report": report,
            "command": f'{CLI} approve "{name}" {sid} --doc {doc["document"]} --note "<用户原话>" --approver "<用户>"', "current_step": current_step}


def _queue_from_stage(ctx: ad.Ctx, sid: str) -> list[dict[str, Any]]:
    docs = [d for d in ctx.docs if d["stage"] in ad.stage_order(ctx.root)[ad.stage_order(ctx.root).index(sid):]]
    out = []
    for d in docs:
        st = ad.document_status(ctx, d)
        out.append({"document": d["path"], "title": st["title"], "stage": d["stage"], "state": st["state"], "label": label_of(ctx, d, st)})
    return out


CLI = r"py -X utf8 D:\Codes\Luz-Project\scripts\project.py"


def format_todos(todos: list[str]) -> list[str]:
    return ["需要你先做（别人替不了）：", *[f"  - {t}" for t in todos], ""] if todos else []


def format_next(report: dict[str, Any]) -> str:
    kind = report.get("kind")
    if report.get("model") == "batch":
        details = [report["stage_name"], report["message"], *format_todos(report.get("user_todos") or [])]
        if kind in {"present", "revise"}:
            details.extend(report["documents"])
        details.extend(n["text"] for n in report["open_notes"])
        details.extend((report.get("current_step") or {}).get("blocked_by", []))
        if report.get("command"):
            details.append(report["command"])
        return "\n".join(details)
    lines: list[str] = format_todos(report.get("user_todos") or [])
    if kind in {"legacy", "done"}:
        return "\n".join(lines) + report["message"]
    if kind == "present":
        doc = report["document"]
        lines += [f"当前待审文件：{doc['path']}　〔{doc['label']}〕", f"阶段：{report['stage_name']}", f"是什么：{doc['what']}", f"怎么看：{doc['how']}", f"为什么是它：{report['why']}",
                  f"{report['internal']['summary']}（无需你看）"]
        lines += ["", "给用户的汇报（三行以内，只报这一个文件）：", *[f"  {r}" for r in report["report"]]]
    elif kind == "revise":
        doc = report["document"]
        lines += [f"待处理：{doc['path']}　〔{doc['label']}〕", "用户的修改意见："] + [f"  {n['id']}　{n['text']}" for n in report["open_notes"]] + [report["message"]]
    else:
        doc = report.get("document")
        lines += [f"阶段：{report['stage_name']}", report["message"]]
        if doc:
            lines.append(f"目标文件：{doc['path']}　〔{doc['label']}〕")
        step = report.get("current_step")
        if step:
            lines += [f"现在该做：{step['id']}　{step['title']}（{step['gate_label']}，负责：{step['skill']}）", f"没通过的原因：{'；'.join(step['blocked_by'][:3]) or '—'}", f"命令：{step['command']}"]
    if report.get("command") and kind in {"present", "revise"}:
        lines.append(f"用户通过后记录：{report['command']}" if kind == "present" else f"处理后：{report['command']}")
    queue = report.get("queue") or []
    if queue:
        lines += ["", "之后的队列（按顺序，当前文件通过前都不生成、不出示）："]
        lines += [f"  {i}. {q['document']}　〔{q['label']}〕" for i, q in enumerate(queue, 1)]
    return "\n".join(lines)


def format_checklist(data: dict[str, Any]) -> str:
    marks = {"done": "[x]", "todo": "[ ]", "waiting": "[ ]"}
    lines = format_todos(data.get("user_todos") or []) + [f"阶段 {data['stage']}（{data['name']}）：{data['done']}/{data['total']} 步已完成"]
    for r in data["steps"]:
        tail = "　← 现在该做这一步" if r.get("current") else ""
        lines.append(f"{marks[r['status']]} {r['id']}　{r['title']}　〔{r['gate_label']}·{r['skill']}〕{'（升级时补记）' if r['backfilled'] else ''}{tail}")
        if r["status"] != "done" and r["blocked_by"]:
            lines.append(f"      没通过：{'；'.join(r['blocked_by'][:3])}")
        if r.get("current") and r.get("rule_files"):
            lines.append("      要读的文件：" + "；".join(r["rule_files"]))
        if r.get("current"):
            lines.append(f"      判据：{r['proof']}")
            lines.append(f"      命令：{r['command']}")
    return "\n".join(lines)
