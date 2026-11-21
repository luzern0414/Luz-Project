"""Approval by document: the user approves the files in ``docs/``, one at a time, in a fixed order.

The unit of user approval is a file in the project directory's ``docs/``. Everything else a stage produces (review pages, Crawl records and conclusions,
rule-card notes, check output) is an *internal record*: the user does not look at it, but the stage's steps (matrix ``steps``) must all be done and pass
before a file is shown to the user and before the stage counts as complete (flow_steps.py). What a record binds:

* ``scope: "document"`` records carry the file's SHA-256, the hashes of the sources it is built from (``source_hashes``), the hashes of every document
  that comes before it in the global order (``upstream``), the mode (``user`` or ``pre-authorized``), the approver, the note and the time.
  A record is *effective* only while all those hashes still hold and it has not been voided; changing an approved file therefore voids its
  approval and, through ``upstream``, the approval of every file after it.
* ``scope: "stage"`` (mode ``internal``) completes a stage that has no document; ``scope: "action"`` is the user's authorization of an act that is not a
  file (production release, final acceptance).
* ``pre-authorized`` records are what an old blanket authorization became: they keep the downstream files valid but count as *waiting for the user's
  review*, and while one exists nothing new may be generated unless ``approval_policy.mode`` is ``blanket`` (set by the user).

Projects of the older model (``approval_policy.model`` missing) keep their stage-level approvals (project_core.approve_stage); ``approvals-upgrade`` splits
them into document records.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import project_core as pc
from project_paths import ProjectError, locate

USER, PRE, INTERNAL = "user", "pre-authorized", "internal"
BLANKET_PREFIX = "用户整体预先授权"
NOTES_FILE = ("data", "review-notes.json")
STEPS_FILE = ("data", "steps.json")
STATE_LABELS = {"missing": "待生成", "ready": "待审", "notes": "有修改意见", "approved": "已通过", "pending-review": "待复核（预先授权）", "voided": "因变更作废"}


# --- policy ------------------------------------------------------------------------------------------------------

def policy(manifest: dict[str, Any]) -> dict[str, Any]:
    value = manifest.get("approval_policy")
    return value if isinstance(value, dict) else {}


def is_document_model(project: Path | str) -> bool:
    return policy(pc.load_project(project)).get("model") == "document"


def blanket(manifest: dict[str, Any]) -> bool:
    """``approval_policy.mode == "blanket"``: the user explicitly set that the files of a project are authorized in advance (never the default)."""
    return policy(manifest).get("mode") == "blanket"


def stage_order(project=None) -> list[str]:
    return [str(item["id"]) for item in pc.matrix_for(project)["stages"]]


def rel(path: str) -> str:
    return str(path).replace(chr(92), "/").strip()


# --- the documents of a stage ------------------------------------------------------------------------------------

def _client_document(root: Path) -> str | None:
    import client_data as cd

    return cd.requirements_client_document(cd.load(root, "client", "requirements.json"))


def documents(root: Path, stage: str, *, approvable: bool = True) -> list[dict[str, Any]]:
    """The files of ``docs/`` a stage hands over, in the order the user approves them (matrix ``documents``). ``approvable=False`` also lists the living
    file (the change ledger) and the client's own input (the filled-in form). The design stage lists its prototypes (named by data/stages/design.json)
    before the interface design document, which embeds them."""
    item = pc._stage_defs(root)[stage]
    out: list[dict[str, Any]] = []
    for d in item.get("documents", []):
        if d.get("dynamic") == "prototypes":
            for p in pc.stage_deliverables(root, item):
                if p.get("kind") == "prototype":
                    name = re.sub(r"^\d+-", "", Path(str(p["path"])).stem)
                    out.append({**{k: v for k, v in d.items() if k != "dynamic"}, "id": p["id"], "path": rel(p["path"]), "title": name, "stage": stage})
            continue
        if d.get("skip_when") == "client_document" and _client_document(root):
            continue
        if approvable and (d.get("living") or d.get("client_input")):
            continue
        out.append({**d, "path": rel(d["path"]), "stage": stage})
    return out


def all_documents(root: Path) -> list[dict[str, Any]]:
    """Every approvable file of the project in the global order: the stages in matrix order, inside a stage the order of its ``documents``."""
    out: list[dict[str, Any]] = []
    for stage in stage_order(root):
        out += documents(root, stage)
    return out


def find_document(root: Path, stage: str, doc: str) -> dict[str, Any]:
    wanted = rel(doc)
    docs = documents(root, stage, approvable=False)
    hit = [d for d in docs if d["path"] == wanted] or [d for d in docs if d["path"].endswith("/" + wanted.lstrip("/"))]
    if len(hit) != 1:
        names = "、".join(d["path"] for d in documents(root, stage)) or "（本阶段没有 docs 文件）"
        raise ProjectError(f"阶段 {stage} 没有这个文件: {doc}；本阶段的文件：{names}")
    found = hit[0]
    if found.get("living"):
        raise ProjectError(f"{found['path']} 是活文件，随变更台账变化，不单独审批：交接阶段以 03-需求变更台账-交付快照.xlsx 审批")
    if found.get("client_input"):
        raise ProjectError(f"{found['path']} 是客户的输入，不审批：导入后由内部门检查")
    return found


# --- records ---------------------------------------------------------------------------------------------------

class Ctx:
    """Everything a validity check needs, read once: manifest, ledger, artifact registry, file hashes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest = pc.load_project(root)
        self.ledger = pc._load_approvals(root)
        self.artifacts = pc._load_artifacts(root)
        self._hash: dict[str, str | None] = {}
        self.cache: dict[str, Any] = {}                       # results of expensive checks (flow_steps) for the life of this one operation
        self._docs: list[dict[str, Any]] | None = None
        self.notes = load_notes(root)["notes"]

    @property
    def docs(self) -> list[dict[str, Any]]:
        if self._docs is None:
            self._docs = all_documents(self.root)
        return self._docs

    def hash_of(self, path: str) -> str | None:
        key = rel(path)
        if key not in self._hash:
            section = "#" in key and not key.startswith("docs/")
            name = key.partition("#")[0] if section else key
            target = locate(self.root, name)
            if section:
                import client_data as cd

                self._hash[key] = cd.source_digest(self.root, key)
            else:
                self._hash[key] = pc.sha256_file(target) if target.is_file() else None
        return self._hash[key]

    def registered(self, stage: str, path: str) -> dict[str, Any] | None:
        return next((a for a in self.artifacts if a.get("stage") == stage and rel(a.get("path", "")) == rel(path)), None)

    def upstream_of(self, doc_path: str) -> dict[str, str]:
        """Hashes of all documents before ``doc_path`` in the global order (what an approval of it rests on)."""
        out: dict[str, str] = {}
        for d in self.docs:
            if d["path"] == rel(doc_path):
                break
            h = self.hash_of(d["path"])
            if h:
                out[d["path"]] = h
        return out

    def stage_upstream(self, stage: str) -> dict[str, str]:
        """Hashes of all documents of the stages before ``stage``."""
        order = stage_order(self.root)
        before = order[: order.index(stage)]
        return {d["path"]: h for d in self.docs if d["stage"] in before and (h := self.hash_of(d["path"]))}


def _scoped(ctx: Ctx, scope: str, **key: str) -> list[dict[str, Any]]:
    return [r for r in ctx.ledger["approvals"] if r.get("scope") == scope and all(r.get(k) == v for k, v in key.items())]


# Sources that only exist after the stage's files were approved, because they are the client's answer to them: the filled-in form (client-intake) and the signed checklist
# (handover). They bind the stage as a whole when it completes (approved_sources), not the approval of the files the client answers.
LATE_SOURCES = {"client-intake": {"data/client/intake.json"}, "handover": {"data/acceptance/checklist.json", "data/changes.json"}}


def source_hashes(ctx: Ctx, stage: str) -> dict[str, str]:
    """What a document of the stage is built from: the tracked data files of the stage (client_flow.TRACKED, without the client's late answers) and, for a stage whose documents
    are HTML pages rendered from its fact data, that data (data/stages/<stage>.json). The review pages of the other stages are internal records: their data does not bind the files."""
    import client_flow

    late = LATE_SOURCES.get(stage, set())
    out = {k: v for k, v in client_flow.tracked_hashes(ctx.root, stage).items() if k.partition("#")[0] not in late}
    if any(d.get("kind") in {"html", "prototype"} for d in pc._stage_defs(ctx.root)[stage].get("documents", [])):
        spec = f"data/stages/{stage}.json"
        if (h := ctx.hash_of(spec)):
            out[spec] = h
    return out


def record_problem(ctx: Ctx, record: dict[str, Any]) -> str | None:
    """None when an approval record is still effective; otherwise why not (``voided``, ``changed``, ``upstream``, ``source``, ``missing``)."""
    if record.get("status", "approved") != "approved":
        return "voided"
    if record.get("scope") == "action" and pc.commercial_at(ctx.root):
        stage, action = record.get("stage"), record.get("action")
        defs = pc._stage_defs(ctx.root)
        if not any(g["id"] == action for g in defs.get(stage, {}).get("action_gates", [])):
            return "source"
        bound = {d["path"]: ctx.hash_of(d["path"]) for d in documents(ctx.root, stage)}
        if action == "final-acceptance":
            bound["data/acceptance/checklist.json"] = ctx.hash_of("data/acceptance/checklist.json")
        if (not bound or None in bound.values() or record.get("source_hashes") != bound
                or record.get("upstream") != ctx.stage_upstream(stage) or record.get("mode") != USER
                or record.get("project_id") != ctx.manifest["project_id"] or not record.get("approver") or not record.get("note")):
            return "source"
    if record.get("scope") == "document":
        h = ctx.hash_of(record["document"])
        if h is None:
            return "missing"
        if h != record.get("hash"):
            return "changed"
    for path, digest in (record.get("upstream") or {}).items():
        if ctx.hash_of(path) != digest:
            return "upstream"
    for path, digest in (record.get("source_hashes") or {}).items():
        if ctx.hash_of(path) != digest:
            return "source"
    return None


def effective_record(ctx: Ctx, scope: str, **key: str) -> tuple[dict[str, Any] | None, str | None]:
    """The latest approved-status record of a target and whether it is still effective: (record, None) when it is, (None, reason) when it is not,
    (None, None) when the target never had one. Older records of the same target are history."""
    records = [r for r in _scoped(ctx, scope, **key) if r.get("status", "approved") == "approved"]
    if not records:
        voided = _scoped(ctx, scope, **key)
        return (None, "voided") if voided else (None, None)
    latest = records[-1]
    problem = record_problem(ctx, latest)
    return (latest, None) if problem is None else (None, problem)


def document_status(ctx: Ctx, doc: dict[str, Any]) -> dict[str, Any]:
    path = doc["path"]
    h = ctx.hash_of(path)
    notes = [n for n in ctx.notes if n.get("document") == path and n.get("status") == "open"]
    from commercial_workflow import BATCHES, WORKFLOW, batch_record
    batched = ctx.manifest.get("workflow") == WORKFLOW and doc["stage"] in BATCHES
    record, problem = batch_record(ctx, doc["stage"]) if batched else effective_record(ctx, "document", document=path)
    art = ctx.registered(doc["stage"], path)
    state, detail = "ready", ""
    if h is None:
        state, detail = "missing", "文件还没有生成"
    elif art is None:
        state, detail = "missing", "文件在，但没有登记为本阶段的产物（project.py artifact）"
    elif art.get("sha256") != h:
        state, detail = "missing", "文件与产物登记表的哈希不一致（重新登记或重新生成）"
    elif notes:
        state, detail = "notes", f"{len(notes)} 条修改意见待处理"
    elif record:
        state = "approved" if batched or record.get("mode") == USER else "pending-review"
        detail = ("基线已定稿" if doc["stage"] == "baseline" else "用户已确认整批文件") if batched else ("用户已逐个批准" if state == "approved" else "预先授权记录：等你逐个复核后才算数")
    elif problem in {"upstream", "source", "voided"}:
        state, detail = "voided", {"upstream": "前面的文件改过，这份文件的批准随之作废", "source": "来源数据变化，这份文件的批准作废", "voided": "变更使这份文件的批准作废"}[problem]
    elif problem == "changed":
        state, detail = "ready", "文件批准后又更新过，需要重新审阅"
    return {"document": path, "stage": doc["stage"], "title": doc.get("title") or Path(path).stem, "state": state, "label": STATE_LABELS[state], "detail": detail,
            "mode": (record or {}).get("mode"), "record": (record or {}).get("id"), "open_notes": [n["id"] for n in notes], "hash": h}


def stage_documents_state(ctx: Ctx, stage: str) -> list[dict[str, Any]]:
    return [{**document_status(ctx, d), "what": d.get("what", ""), "how": d.get("how", ""), "skill": d.get("skill", "")} for d in documents(ctx.root, stage)]


def stage_record_effective(ctx: Ctx, stage: str) -> bool:
    """A stage without documents is complete once its internal-gate record exists and is effective."""
    record, _ = effective_record(ctx, "stage", stage=stage)
    return record is not None


def action_effective(ctx: Ctx, stage: str, action: str) -> bool:
    record, _ = effective_record(ctx, "action", stage=stage, action=action)
    return record is not None


ACTION_PROBLEMS = {"voided": "授权已因变更作废", "changed": "授权所绑定的文件已变化", "upstream": "授权所依据的前面的文件已变化", "source": "授权所绑定的该阶段文件已变化（哈希与授权时不一致）",
                   "missing": "授权所绑定的文件现在不存在"}


def action_status(project: Path | str, stage: str, action: str) -> dict[str, Any]:
    """Read-only: has the user authorized this action gate (matrix ``action_gates``: release's production-release, handover's final-acceptance), and does the authorization still hold?

    ``granted`` is True only for an effective ``scope: "action"`` record of mode ``user`` whose bound files (the stage's documents at the time) still have the hashes it recorded and
    whose upstream files are unchanged. Otherwise ``reason`` says why: never authorized, voided by a change, a bound file changed (named), unknown stage or action, an older project
    that approves by stage. Nothing is written."""
    root = pc._project_root(project)
    out: dict[str, Any] = {"project": str(root), "stage": stage, "action": action, "granted": False, "reason": "", "approver": None, "time": None, "note": None, "record": None, "bound_files": {}}
    defs = pc._stage_defs(root)
    if stage not in defs:
        out["reason"] = f"未知阶段: {stage}"
        return out
    gates = defs[stage].get("action_gates", [])
    if not any(g["id"] == action for g in gates):
        out["reason"] = f"阶段 {stage} 没有动作门 {action}；有的是：{'、'.join(g['id'] for g in gates) or '无'}"
        return out
    if not is_document_model(root):
        out["reason"] = "这个项目还按阶段审批（旧模型），动作门的授权记在阶段审批里：先 project.py approvals-upgrade <项目>"
        return out
    ctx = Ctx(root)
    record, problem = effective_record(ctx, "action", stage=stage, action=action)
    if record is not None and pc.commercial_at(root):
        problems = hold_errors(ctx, stage)
        if action == "final-acceptance":
            import client_flow
            problems += client_flow.stage_checks(root, stage, phase="complete")
        if problems:
            out["reason"] = "；".join(problems[:3])
            return out
    if record is not None:
        out.update({"granted": True, "approver": record.get("approver"), "time": record.get("time") or record.get("approved_at"), "note": record.get("note"), "record": record.get("id"),
                    "bound_files": dict(record.get("source_hashes") or {}), "mode": record.get("mode")})
        return out
    if problem is None:
        out["reason"] = f"用户还没有授权：{next(g['title'] for g in gates if g['id'] == action)}（project.py action <项目> {stage} {action} --note <用户原话> --approver <用户>）"
        return out
    old = [r for r in _scoped(ctx, "action", stage=stage, action=action) if r.get("status", "approved") == "approved"]
    changed = [p for p, h in ((old[-1].get("source_hashes") or {}) if old else {}).items() if ctx.hash_of(p) != h]
    out["reason"] = ACTION_PROBLEMS.get(problem, problem) + (f"：{'、'.join(changed[:4])}" if changed else "") + "；文件改过之后要用户重新审阅，再重新授权"
    return out


def action_granted(state_root: Path | str, stage: str, action: str) -> tuple[bool, str]:
    """``(True, "")`` when the user has authorized the action gate and the authorization still holds, else ``(False, reason)``. For the other skills (Luz-Ops' release commands):
    ``sys.path.append(r"D:\\Codes\\Luz-Project\\scripts"); import approval_docs`` (append, so the caller's own modules win on a name clash). A project that cannot be read is ``(False, reason)``."""
    try:
        status = action_status(state_root, stage, action)
    except ProjectError as exc:
        return False, str(exc)
    return (True, "") if status["granted"] else (False, status["reason"])


def stage_docs_done(ctx: Ctx, stage: str, *, allow_pre: bool = True) -> bool:
    docs = documents(ctx.root, stage)
    if not docs:
        return stage_record_effective(ctx, stage)
    states = {document_status(ctx, d)["state"] for d in docs}
    return states <= ({"approved", "pending-review"} if allow_pre else {"approved"})


def completion_open(ctx: Ctx, stage: str) -> list[str]:
    """What is left after the documents of a stage are approved: the client's input (intake import, acceptance sign-off) and the user's action gates."""
    import client_flow

    item = pc._stage_defs(ctx.root)[stage]
    out: list[str] = []
    if stage in {"client-intake", "handover"}:
        try:
            out = list(client_flow.stage_checks(ctx.root, stage, phase="complete"))
        except ProjectError as exc:
            out = [str(exc)]
    for action in item.get("action_gates", []):
        if not action_effective(ctx, stage, action["id"]):
            out.append(f"动作门未授权：{action['title']}（project.py action <项目> {stage} {action['id']}）")
    return out


def stage_complete(ctx: Ctx, stage: str, *, allow_pre: bool = True) -> bool:
    return stage_docs_done(ctx, stage, allow_pre=allow_pre) and not completion_open(ctx, stage)


def crawl_expiry_status(project: Path | str, stage: str, *, ctx: Ctx | None = None) -> tuple[bool, str]:
    """Is the seven-day limit of the stage's Crawl record waived? It is once the stage is complete: every file approved by the user, the client's input and the action gates through.
    The record must then only exist, be valid (task marker, log hashes) and be concluded; the age counts for the stage being worked on, and again for a stage a change reopened
    (its approvals are void, so it is not complete). An older project (approval by stage) waives it for a stage whose status is approved or completed."""
    root = pc._project_root(project)
    manifest = pc.load_project(root)
    if stage not in {str(s.get("id")) for s in manifest.get("stages", [])}:
        return False, f"未知阶段: {stage}"
    if not is_document_model(root):
        done = pc._stage_record(manifest, stage).get("status") in {"approved", "completed"}
        return done, "阶段已批准（按阶段审批的旧模型）：检索记录只核对存在、有效、已 conclude" if done else "阶段还没有批准：检索记录超过七天要重新检索"
    ctx = ctx or Ctx(root)
    if stage_complete(ctx, stage):
        return True, "阶段已完成（文件都由用户批准，客户输入和动作门都已通过）：检索记录只核对存在、有效、已 conclude，超过七天不挡"
    pending = [s["document"] for s in stage_documents_state(ctx, stage) if s["state"] != "approved"] or completion_open(ctx, stage)
    if not pending and not documents(root, stage):
        pending = [f"没有 docs 文件的阶段，内部步骤全部通过后才算完成（project.py approve <项目> {stage}）"]
    return False, "阶段还在进行（或被变更重开）：检索记录超过七天要重新检索。还差：" + "；".join(str(p) for p in pending[:3])


def crawl_expiry_waived(project: Path | str, stage: str, *, ctx: Ctx | None = None) -> bool:
    """True when the stage is complete and its Crawl record is not held to the seven days (see ``crawl_expiry_status``). The one judgement every Luz skill's crawl gate uses in
    project mode: ``errors = [e for e in errors if "检索记录超过七天" not in e]`` when it is True. For the other skills: ``sys.path.append(r"D:\\Codes\\Luz-Project\\scripts"); import approval_docs``."""
    return crawl_expiry_status(project, stage, ctx=ctx)[0]


# --- ordering / holds -------------------------------------------------------------------------------------------

def hold_errors(ctx: Ctx, stage: str, *, before_doc: str | None = None) -> list[str]:
    """Why work on ``stage`` (or approval of ``before_doc``) may not start: a file before it is not approved by the user (``pre-authorized`` records wait for the
    user's review; ``blanket`` mode lets them stand), a stage before it is not complete."""
    errors: list[str] = []
    allow_pre = blanket(ctx.manifest)
    order = stage_order(ctx.root)
    for earlier in order[: order.index(stage)]:
        for d in documents(ctx.root, earlier):
            st = document_status(ctx, d)
            if st["state"] == "approved" or (st["state"] == "pending-review" and allow_pre):
                continue
            if st["state"] == "pending-review":
                errors.append(f"待用户复核：{d['path']}（预先授权记录，还没有你逐个通过；project.py approve <项目> {earlier} --doc {d['path']} …）")
            else:
                errors.append(f"前置审批未完成：{d['path']}（{st['label']}）")
        if not documents(ctx.root, earlier) and not stage_record_effective(ctx, earlier):
            errors.append(f"前置审批未完成：阶段 {earlier} 没有 docs 文件，内部步骤还没有全部通过并自动完成（project.py approve <项目> {earlier}）")
        for text in completion_open(ctx, earlier) if stage_docs_done(ctx, earlier) else []:
            errors.append(f"前置审批未完成：阶段 {earlier}：{text}")
        # the user's approval of a stage's files does not stand in for its internal steps: a stage whose Crawl conclusion, review page or checks went missing holds back everything after it
        if stage_docs_done(ctx, earlier):
            import flow_steps

            errors += [f"前置阶段 {earlier} 的内部步骤未通过（即使文件已批准，下游也不放行）：{e}" for e in flow_steps.internal_errors(ctx.root, earlier, ctx=ctx, skip=("upstream",), light=True)]
    if before_doc is not None:
        for d in documents(ctx.root, stage):
            if d["path"] == rel(before_doc):
                break
            st = document_status(ctx, d)
            if st["state"] == "approved" or (st["state"] == "pending-review" and allow_pre):
                continue
            errors.append(f"顺序在前的文件还没通过：{d['path']}（{st['label']}）；一次只审一个文件，先让它通过")
    return list(dict.fromkeys(errors))


# --- writing records --------------------------------------------------------------------------------------------

def _new_record(ctx: Ctx, **fields: Any) -> dict[str, Any]:
    ledger = ctx.ledger
    record = {"id": pc._next_id(ledger["approvals"], "APPROVAL"), "project_id": ctx.manifest["project_id"], "status": "approved", **fields}
    record["time"] = record["approved_at"] = pc.now_iso()
    ledger["approvals"].append(record)
    pc._write_json(ctx.root / "APPROVALS.json", ledger)
    return record


def approve_document(project: Path | str, stage: str, doc: str, note: str, approver: str, *, mode: str = USER) -> dict[str, Any]:
    """The user approves one file. Refused unless: the model is by document; the file belongs to the stage; every file before it is approved by the user;
    no modification note is open; the internal steps of the stage (flow_steps: upstream, rules, Crawl, specialist output, build, records, trace) are done and pass;
    the file is registered and unchanged since. The record binds the file's hash, its sources and the files before it."""
    root = pc._project_root(project)
    from commercial_workflow import active
    if active(root, stage):
        raise ProjectError("商业项目前三批文件须整批确认，不能逐件批准；基线由 build 定稿")
    if not is_document_model(root):
        raise ProjectError("这个项目还是按阶段审批的旧模型：先 project.py approvals-upgrade <项目> 预演，确认后 --apply；或用 project.py approve <项目> <阶段> --note … 按阶段批准")
    if not str(note).strip() or not str(approver).strip():
        raise ProjectError("审批说明和审批人不能为空（说明写用户的原话）")
    if mode not in {USER, PRE}:
        raise ProjectError(f"审批模式只有 {USER}、{PRE}")
    ctx = Ctx(root)
    if mode == PRE:
        if not blanket(ctx.manifest):
            raise ProjectError("预先授权记录只在 project.json 的 approval_policy.mode 是用户显式设置的 blanket 时才能写；默认每个文件由用户逐个审批")
        if not str(note).strip().startswith(BLANKET_PREFIX):
            raise ProjectError(f"整体预先授权的备注要如实以“{BLANKET_PREFIX}”开头，写明用户的原话和未逐件审阅")
    elif str(note).strip().startswith(BLANKET_PREFIX) or any(w in str(approver) for w in ("代为记录", "预先授权")):
        raise ProjectError("备注或审批人写的是整体预先授权/代为记录，不能记成用户逐个批准（mode user）；等用户逐个通过后再记")
    found = find_document(root, stage, doc)
    holds = hold_errors(ctx, stage, before_doc=found["path"])
    if holds:
        raise ProjectError("不能批准这个文件，前面还有没通过的：" + "；".join(holds[:4]))
    state = document_status(ctx, found)
    if state["open_notes"]:
        raise ProjectError(f"{found['path']} 还有 {len(state['open_notes'])} 条未处理的修改意见（{'、'.join(state['open_notes'])}）：改完 project.py review <项目> done --id … 并重新生成后再审批")
    import flow_steps

    problems = flow_steps.internal_errors(root, stage)
    if problems:
        raise ProjectError("内部步骤没有全部完成，不能出示或批准这个文件（缺哪一步见 project.py checklist <项目> " + stage + "）: " + "；".join(problems[:5]))
    pc._register_evidence(root, stage)
    ctx = Ctx(root)
    found_state = document_status(ctx, found)
    if found_state["state"] == "missing":
        raise ProjectError(f"{found['path']} {found_state['detail']}")
    art = ctx.registered(stage, found["path"])
    record = _new_record(ctx, scope="document", stage=stage, document=found["path"], hash=found_state["hash"], source_hashes=source_hashes(ctx, stage),
                         upstream=ctx.upstream_of(found["path"]), mode=mode, approver=str(approver).strip(), note=str(note).strip(),
                         artifact_hashes={art["id"]: found_state["hash"]} if art else {})
    refresh(root)
    return record


def approve_stage_level(project: Path | str, stage: str, note: str = "", approver: str = "") -> dict[str, Any]:
    """``approve <项目> <阶段>`` in the document model: a stage with documents is approved file by file; a stage without any completes by itself once its internal steps pass."""
    root = pc._project_root(project)
    pc._stage_record(pc.load_project(root), stage)
    from commercial_workflow import active, confirm
    if active(root, stage):
        return confirm(root, stage, note, approver)
    docs = documents(root, stage)
    if docs:
        raise ProjectError(f"阶段 {stage} 有 docs 文件，由用户逐个审批：{'、'.join(d['path'] for d in docs)}。用 project.py approve <项目> {stage} --doc <路径> --note <用户原话> --approver <用户>；"
                           "当前该审哪一个见 project.py next <项目>")
    ctx = Ctx(root)
    import flow_steps

    problems = flow_steps.internal_errors(root, stage)
    if problems:
        raise ProjectError(f"阶段 {stage} 没有 docs 文件，内部步骤全部通过后自动完成；现在没通过的：" + "；".join(problems[:5]))
    import client_flow

    checks = client_flow.stage_checks(root, stage, phase="all")
    if checks:
        raise ProjectError("客户文档/变更门禁未通过: " + "; ".join(checks))
    pc._register_evidence(root, stage)
    ctx = Ctx(root)
    record = _new_record(ctx, scope="stage", stage=stage, mode=INTERNAL, approver=str(approver).strip() or "internal-gates",
                         note=str(note).strip() or "本阶段没有 docs 文件，内部步骤全部通过，自动完成", source_hashes=source_hashes(ctx, stage), upstream=ctx.stage_upstream(stage),
                         artifact_hashes={a["id"]: a["sha256"] for a in ctx.artifacts if a.get("stage") == stage})
    refresh(root)
    return record


def record_action(project: Path | str, stage: str, action: str, note: str, approver: str) -> dict[str, Any]:
    """The user's authorization of an act that is not a file (matrix ``action_gates``: production release, final acceptance). Needs the stage's files approved
    by the user and its internal steps done; binds the hashes of those files, so changing one voids the authorization. Never recordable as pre-authorized."""
    root = pc._project_root(project)
    if pc.commercial_at(root):
        from commercial_workflow import require_decision
        require_decision(note, approver)
    if not is_document_model(root):
        raise ProjectError("动作门属于逐文件审批模型；旧项目的发布和验收授权仍记在阶段审批里")
    item = pc._stage_defs(root)[stage]
    gate = next((a for a in item.get("action_gates", []) if a["id"] == action), None)
    if gate is None:
        raise ProjectError(f"阶段 {stage} 没有动作门 {action}；有的是：{'、'.join(a['id'] for a in item.get('action_gates', [])) or '无'}")
    if not str(note).strip() or not str(approver).strip():
        raise ProjectError("动作门的授权说明和授权人不能为空（写用户的原话）")
    if str(note).strip().startswith(BLANKET_PREFIX) or any(w in str(approver) for w in ("代为记录", "预先授权")):
        raise ProjectError("动作门不能由整体预先授权或代记录：真实对外动作要用户明确授权")
    ctx = Ctx(root)
    holds = hold_errors(ctx, stage)
    if holds:
        raise ProjectError("前面还有没通过的文件，不能授权：" + "；".join(holds[:3]))
    if not stage_docs_done(ctx, stage, allow_pre=False):
        raise ProjectError(f"阶段 {stage} 的 docs 文件还没有全部由用户通过，先逐个审批完再授权“{gate['title']}”")
    import flow_steps

    problems = [p for p in flow_steps.internal_errors(root, stage)]
    if problems:
        raise ProjectError("内部步骤没有全部完成: " + "；".join(problems[:4]))
    if action == "final-acceptance" and pc.commercial_at(root):
        import client_flow
        problems = client_flow.stage_checks(root, stage, phase="complete")
        if problems:
            raise ProjectError("客户签收未完成：" + "；".join(problems))
    docs = documents(root, stage)
    bound = {d["path"]: ctx.hash_of(d["path"]) for d in docs if ctx.hash_of(d["path"])}
    if pc.commercial_at(root) and action == "final-acceptance":
        bound["data/acceptance/checklist.json"] = ctx.hash_of("data/acceptance/checklist.json")
    record = _new_record(ctx, scope="action", stage=stage, action=action, mode=USER, approver=str(approver).strip(), note=str(note).strip(),
                         source_hashes=bound, upstream=ctx.stage_upstream(stage))
    refresh(root)
    return record


# --- voiding and the stage status cache -----------------------------------------------------------------------

def void_from(root: Path, stage: str, reason: str) -> int:
    """A change reopens ``stage``: every approval record of that stage and all after it is voided (kept as history with the reason)."""
    ledger = pc._load_approvals(root)
    order = stage_order(root)
    affected = set(order[order.index(stage):])
    count = 0
    for record in ledger["approvals"]:
        if record.get("scope") in {"document", "stage", "action", "batch"} and record.get("stage") in affected and record.get("status", "approved") == "approved":
            record["status"] = "voided"
            record["voided_at"] = pc.now_iso()
            record["voided_reason"] = reason
            count += 1
    if count:
        pc._write_json(root / "APPROVALS.json", ledger)
    return count


def refresh(root: Path, manifest: dict[str, Any] | None = None, *, save: bool = True) -> dict[str, Any]:
    """Bring the stages' cached status in project.json in line with the records: a stage whose files are all effective and whose steps pass is ``approved``
    (``completed`` for the last), one whose approvals no longer hold goes back. The cache only serves the older readers; the truth is the records."""
    manifest = manifest if manifest is not None else pc.load_project(root)
    if not policy(manifest).get("model") == "document":
        return manifest
    import client_flow
    import flow_steps

    ctx = Ctx(root)
    ctx.manifest = manifest
    order = stage_order(root)
    previous_done = True
    for sid in order:
        record = pc._stage_record(manifest, sid)
        # Approval records are history.  A deleted Crawl conclusion, missing
        # template post-binding or changed source package must also reopen a
        # previously completed stage, not only prevent its first promotion.
        done = previous_done and stage_complete(ctx, sid) and not flow_steps.internal_errors(root, sid, ctx=ctx)
        if done and record.get("status") not in {"approved", "completed"}:
            last = next((r for r in reversed(ctx.ledger["approvals"]) if r.get("stage") == sid and r.get("scope") in {"document", "stage", "action", "batch"} and r.get("status") == "approved"), None)
            record["status"] = "approved"
            record["approval_id"] = (last or {}).get("id")
            record["approved_hashes"] = {a["id"]: a["sha256"] for a in ctx.artifacts if a.get("stage") == sid}
            record["approved_sources"] = client_flow.tracked_hashes(root, sid) if pc.schema_at_least(manifest, "1.1") else {}
            record["updated_at"] = pc.now_iso()
        elif not done and record.get("status") in {"approved", "completed"}:
            record["status"] = "pending-review" if record.get("artifact_ids") else "pending"
            record["approval_id"], record["approved_hashes"], record["approved_sources"] = None, {}, {}
            record["updated_at"] = pc.now_iso()
        elif not done and record.get("status") == "pending" and previous_done and record.get("artifact_ids"):
            record["status"] = "pending-review"
        previous_done = done and record.get("status") in {"approved", "completed"}
    complete = [pc._stage_record(manifest, s).get("status") in {"approved", "completed"} for s in order]
    first_open = next((s for s, ok in zip(order, complete) if not ok), None)
    if first_open is None:
        manifest["current_stage"] = order[-1]
        manifest["status"] = "completed"
        pc._stage_record(manifest, order[-1])["status"] = "completed"
    else:
        manifest["current_stage"] = first_open
        manifest["status"] = "active" if manifest.get("status") in {"completed", "draft"} or complete[0] or any(complete) else manifest.get("status", "draft")
        target = pc._stage_record(manifest, first_open)
        if target.get("status") in {"pending", "superseded"}:
            target["status"] = "in-progress"
    if save:
        pc._save_manifest(root, manifest)
    return manifest


# --- modification notes -------------------------------------------------------------------------------------------

def load_notes(root: Path) -> dict[str, Any]:
    value = pc._read_json(root.joinpath(*NOTES_FILE), None)
    if value is None:
        return {"schema_version": "1.0", "notes": []}
    if not isinstance(value, dict) or not isinstance(value.get("notes"), list):
        raise ProjectError("data/review-notes.json 格式无效")
    return value


def review_add(project: Path | str, doc: str, text: str, by: str = "") -> dict[str, Any]:
    """Log the user's modification opinion on the file in front of them (verbatim). The file now counts as ``有修改意见`` and cannot be approved until the note is done."""
    root = pc._project_root(project)
    if not str(text).strip():
        raise ProjectError("修改意见不能为空（写用户的原话）")
    ctx = Ctx(root)
    wanted = rel(doc)
    found = next((d for d in ctx.docs if d["path"] == wanted or d["path"].endswith("/" + wanted)), None)
    if found is None:
        raise ProjectError(f"不是需要审批的 docs 文件: {doc}")
    st = document_status(ctx, found)
    from commercial_workflow import active
    if active(root, found["stage"]):
        if found["stage"] == "baseline" or hold_errors(ctx, found["stage"]):
            raise ProjectError("本批尚不在用户确认阶段")
    if st["state"] == "missing":
        raise ProjectError(f"{found['path']} {st['detail']}：没有可审的文件，不能登记修改意见")
    if st["state"] == "approved":
        raise ProjectError(f"{found['path']} 已经由用户通过：已批准的文件要改，先登记变更台账（project.py change add …），该文件的批准作废、顺序在它之后的文件随之作废，再重新生成和审批")
    notes = load_notes(root)
    note = {"id": pc._next_id([{"id": n["id"]} for n in notes["notes"]], "RN"), "document": found["path"], "stage": found["stage"], "text": str(text).strip(), "status": "open",
            "by": str(by).strip(), "created_at": pc.now_iso(), "hash_at_creation": st["hash"], "resolution": None, "done_at": None}
    notes["notes"].append(note)
    pc._write_json(root.joinpath(*NOTES_FILE), notes)
    return note


def review_done(project: Path | str, note_id: str, resolution: str = "", *, unchanged: bool = False) -> dict[str, Any]:
    """Mark an opinion handled. The file must have been changed since the opinion was logged (regenerated or re-rendered), otherwise ``unchanged`` with the
    reason (for instance the user withdrew the opinion) is required."""
    root = pc._project_root(project)
    notes = load_notes(root)
    note = next((n for n in notes["notes"] if n["id"] == note_id), None)
    if note is None:
        raise ProjectError(f"没有这条修改意见: {note_id}")
    if note["status"] == "done":
        raise ProjectError(f"{note_id} 已经处理过")
    h = Ctx(root).hash_of(note["document"])
    if h == note.get("hash_at_creation") and not unchanged:
        raise ProjectError(f"{note['document']} 自登记这条意见后没有变化：先按意见修改并重新生成；意见撤回或无需修改时加 --unchanged 并在 --resolution 写明原因")
    if unchanged and not str(resolution).strip():
        raise ProjectError("--unchanged 需要在 --resolution 写明为什么不用改")
    note.update({"status": "done", "resolution": str(resolution).strip() or "已按意见修改并重新生成", "done_at": pc.now_iso(), "hash_at_done": h})
    pc._write_json(root.joinpath(*NOTES_FILE), notes)
    return note


def review_list(project: Path | str, doc: str | None = None) -> list[dict[str, Any]]:
    root = pc._project_root(project)
    items = load_notes(root)["notes"]
    return [n for n in items if not doc or n["document"] == rel(doc) or n["document"].endswith("/" + rel(doc))]


# --- recorded steps (rules read, specialist output) ---------------------------------------------------------------

def load_steps(root: Path) -> dict[str, Any]:
    value = pc._read_json(root.joinpath(*STEPS_FILE), None)
    if value is None:
        return {"schema_version": "1.0", "records": {}}
    if not isinstance(value, dict) or not isinstance(value.get("records"), dict):
        raise ProjectError("data/steps.json 格式无效")
    return value


def step_record(root: Path, stage: str, step: str) -> dict[str, Any] | None:
    return (load_steps(root)["records"].get(stage) or {}).get(step)


# --- upgrade of stage-level approvals -----------------------------------------------------------------------------

def approvals_upgrade(project: Path | str, apply: bool = False) -> dict[str, Any]:
    """Split the stage-level approvals of an older project into one record per file (preview by default).

    A stage's live approval (``approval_id``) gives each of its documents the hash it was approved with; that must equal the file now, otherwise the file gets no
    record and is simply "待审". A note that starts with “用户整体预先授权” makes the records ``pre-authorized`` (waiting for the user's review, downstream files stay
    valid); any other approval keeps mode ``user`` (the user approved the stage; ``granularity: stage`` says so). A stage without documents gets an ``internal``
    completion record. The steps ``rules`` and ``specialist`` that the old protocol did not record are backfilled for approved stages and marked as such.
    Before writing, APPROVALS.json and project.json are copied to ``backup/approvals-upgrade-<time>/`` in the state root. Running it again changes nothing."""
    root = pc._project_root(project)
    manifest = pc.load_project(root)
    if is_document_model(root):
        return {"applied": False, "already_upgraded": True, "message": "已经是逐文件审批模型，没有需要升级的内容"}
    if not manifest.get("deliver_root"):
        raise ProjectError("旧布局项目先 project.py migrate <项目>（预演，确认后 --apply）迁到当前布局，再升级审批")
    manifest = dict(manifest)
    manifest["approval_policy"] = {"model": "document", "mode": "user", "upgraded_from": "stage", "upgraded_at": pc.now_iso()}
    ctx = Ctx(root)
    ctx.manifest = manifest
    ledger = ctx.ledger
    by_id = {a["id"]: a for a in ledger["approvals"]}
    plan: list[dict[str, Any]] = []
    unmapped: list[str] = []
    new_records: list[dict[str, Any]] = []
    backfill: list[str] = []
    probe = [dict(r) for r in ledger["approvals"]]
    for sid in stage_order(root):
        stage = pc._stage_record(manifest, sid)
        legacy = by_id.get(str(stage.get("approval_id")))
        docs = documents(root, sid)
        if stage.get("status") not in {"approved", "completed"} or not legacy:
            for d in docs:
                plan.append({"stage": sid, "document": d["path"], "result": "没有批准记录", "mode": None, "source": None})
            continue
        backfill.append(sid)
        mode = PRE if str(legacy.get("note", "")).startswith(BLANKET_PREFIX) else USER
        if not docs:
            new_records.append({"scope": "stage", "stage": sid, "mode": INTERNAL, "approver": "internal-gates", "migrated_from": legacy["id"],
                                "note": f"由阶段级批准 {legacy['id']} 升级：本阶段没有 docs 文件，不设用户审批，内部门通过即完成"})
            plan.append({"stage": sid, "document": None, "result": "无 docs 文件：记内部完成", "mode": INTERNAL, "source": legacy["id"]})
            continue
        for d in docs:
            art = ctx.registered(sid, d["path"])
            h = ctx.hash_of(d["path"])
            approved = (legacy.get("artifact_hashes") or {}).get((art or {}).get("id"))
            if art is None or h is None or approved != h or art.get("sha256") != h:
                unmapped.append(d["path"])
                plan.append({"stage": sid, "document": d["path"], "result": "批准时的哈希与现在的文件对不上，不转成记录，需要用户重新审", "mode": None, "source": legacy["id"]})
                continue
            new_records.append({"scope": "document", "stage": sid, "document": d["path"], "hash": h, "mode": mode, "approver": legacy.get("approver", ""), "note": legacy.get("note", ""),
                                "migrated_from": legacy["id"], "granularity": "stage", "artifact_hashes": {art["id"]: h}, "approved_time": legacy.get("approved_at")})
            plan.append({"stage": sid, "document": d["path"], "result": "待用户复核（预先授权）" if mode == PRE else "已通过（沿用阶段级批准）", "mode": mode, "source": legacy["id"]})
    result: dict[str, Any] = {"applied": False, "plan": plan, "unmapped": unmapped, "backfilled_steps": backfill,
                              "policy": manifest["approval_policy"], "pre_authorized": [p["document"] for p in plan if p.get("mode") == PRE],
                              "message": "预演：没有写任何文件。确认后加 --apply；写之前自动备份 APPROVALS.json 与 project.json 到状态根 backup/。"}
    if not apply:
        return result
    stamp = pc.now_iso().replace(":", "").replace("-", "")
    folder = root / "backup" / f"approvals-upgrade-{stamp}"
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("APPROVALS.json", "project.json", "MANIFEST.json"):
        if (root / name).is_file():
            shutil.copyfile(root / name, folder / name)
    # records get their upstream/source hashes from the files as they are now (they were verified equal to the approved hashes above)
    manifest_now = manifest
    ctx.manifest = manifest_now
    for fields in new_records:
        sid = fields["stage"]
        if fields["scope"] == "document":
            fields["upstream"] = ctx.upstream_of(fields["document"])
            fields["source_hashes"] = source_hashes(ctx, sid)
        else:
            fields["upstream"] = ctx.stage_upstream(sid)
            fields["source_hashes"] = {}
        record = {"id": pc._next_id(ledger["approvals"], "APPROVAL"), "project_id": manifest["project_id"], "status": "approved", **fields}
        record["time"] = record["approved_at"] = fields.pop("approved_time", None) or pc.now_iso()
        record.pop("approved_time", None)
        ledger["approvals"].append(record)
    pc._write_json(root / "APPROVALS.json", ledger)
    steps = load_steps(root)
    for sid in backfill:
        entry = steps["records"].setdefault(sid, {})
        for name in ("rules", "specialist"):
            entry.setdefault(name, {"note": "升级审批模型时按既有批准记录补记：旧流程没有单独记录这一步，规则卡采用情况以当时的 BRIEF 为准", "by": "approvals-upgrade", "at": pc.now_iso(), "backfilled": True})
    if backfill:
        pc._write_json(root.joinpath(*STEPS_FILE), steps)
    pc._save_manifest(root, manifest)
    refresh(root)
    result.update({"applied": True, "backup": str(folder), "message": "已升级。待复核的预先授权文件请逐个出示给用户（project.py next <项目>）；备份在 backup/。"})
    return result


# --- validation (called by project_core.validate_project) ----------------------------------------------------------

def validation_errors(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy(manifest).get("model") != "document":
        return errors
    ctx = Ctx(root)
    ctx.manifest = manifest
    for record in ctx.ledger["approvals"]:
        if record.get("scope") not in {"document", "stage", "action", "batch"}:
            continue
        mode, note, approver = record.get("mode"), str(record.get("note", "")), str(record.get("approver", ""))
        from commercial_workflow import active, BATCHES
        if active(root) and record.get("stage") in BATCHES and record.get("scope") != "batch":
            errors.append(f"商业批次 {record['stage']} 不能用 {record['scope']} 记录代替整组确认")
        if mode == USER and (note.startswith(BLANKET_PREFIX) or any(w in approver for w in ("代为记录", "预先授权"))):
            errors.append(f"审批记录 {record.get('id')} 标了用户逐个批准，但备注或审批人写的是整体预先授权/代为记录：应标 pre-authorized")
        if mode == PRE and not note.startswith(BLANKET_PREFIX):
            errors.append(f"预先授权记录 {record.get('id')} 的备注没有如实以“{BLANKET_PREFIX}”开头")
        if mode not in {USER, PRE, INTERNAL}:
            errors.append(f"审批记录 {record.get('id')} 的模式无效: {mode}")
        if record.get("scope") == "action" and mode != USER:
            errors.append(f"动作门记录 {record.get('id')} 必须是用户授权（mode user）")
    order = stage_order(root)
    for sid in order:
        stage = pc._stage_record(manifest, sid)
        if stage.get("status") not in {"approved", "completed"}:
            continue
        for d in documents(root, sid):
            st = document_status(ctx, d)
            if st["state"] not in {"approved", "pending-review"}:
                errors.append(f"已批准阶段 {sid} 的文件没有有效的批准记录：{d['path']}（{st['label']}：{st['detail']}）")
        if not documents(root, sid) and not stage_record_effective(ctx, sid):
            errors.append(f"已批准阶段 {sid} 没有 docs 文件，也没有内部完成记录")
    for note in ctx.notes:
        if note.get("status") not in {"open", "done"}:
            errors.append(f"修改意见 {note.get('id')} 的状态无效")
    return errors
