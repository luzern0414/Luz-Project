"""只读核对旧模板产物的原批准；不生成、续批或改写任何项目记录。

Design 已核对准确目标、原模板快照和原生成回执。本模块只接受现有
逐文件审批模型的真实账本类型，并重新核对成品、来源、上游及产物登记。
阶段缓存中的 approved 字样和普通 record_output 都不是历史批准。
"""
from __future__ import annotations

from pathlib import Path

import approval_docs as ad
import project_core as pc
from project_paths import locate, relative_to_project
from project_template_gate import output_contract


def _latest(ctx, scope, **keys):
    records = [r for r in ctx.ledger.get("approvals", []) if r.get("scope") == scope
               and all(r.get(k) == v for k, v in keys.items())]
    if not records:
        raise ValueError("缺少准确目标的原批准记录")
    # A revocation is the latest decision; never revive an older approval.
    record = records[-1]
    if (record.get("status") != "approved" or record.get("project_id") != ctx.manifest["project_id"]
            or not record.get("id") or not record.get("approved_at")
            or not str(record.get("approver") or "").strip()):
        raise ValueError("原批准已撤销、缺失或不属于本项目")
    if ad.record_problem(ctx, record):
        raise ValueError("原批准所绑定的成品、来源或上游已变化")
    return record


def _bound_artifact(ctx, record, stage, path):
    art = ctx.registered(stage, path)
    digest = ctx.hash_of(path)
    if (not art or not digest or art.get("sha256") != digest
            or (record.get("artifact_hashes") or {}).get(art.get("id")) != digest):
        raise ValueError("原批准没有绑定本阶段准确产物及其当前 SHA-256")


def _approved_document(ctx, doc, checked):
    path, stage = doc["path"], doc["stage"]
    if path in checked:
        return
    record = _latest(ctx, "document", document=path)
    if (record.get("stage") != stage or record.get("mode") != ad.USER
            or record.get("source_hashes") != ad.source_hashes(ctx, stage)
            or record.get("upstream") != ctx.upstream_of(path)):
        raise ValueError("用户文件批准的类型、阶段、完整来源或上游绑定不符")
    if ad.document_status(ctx, doc)["state"] != "approved":
        raise ValueError("文件当前没有有效用户批准或仍有未处理修改意见")
    _bound_artifact(ctx, record, stage, path)
    for previous in ctx.docs:
        if previous["path"] == path:
            break
        _approved_document(ctx, previous, checked)
    checked.add(path)


def _approved_internal_stage(ctx, stage, path):
    if ad.documents(ctx.root, stage):
        raise ValueError("有用户文件的阶段不能用内部阶段批准替代文件批准")
    record = _latest(ctx, "stage", stage=stage)
    if (record.get("mode") != ad.INTERNAL
            or record.get("source_hashes") != ad.source_hashes(ctx, stage)
            or record.get("upstream") != ctx.stage_upstream(stage)):
        raise ValueError("内部步骤批准的类型、完整来源或上游绑定不符")
    _bound_artifact(ctx, record, stage, path)
    # Internal stages bind their source spec and evidence as artifacts too.
    # Checking only the final page would miss a changed research source spec.
    artifacts = {a["id"]: a for a in ctx.artifacts if a.get("stage") == stage}
    for identifier, digest in record["artifact_hashes"].items():
        art = artifacts.get(identifier)
        if not art or art.get("sha256") != digest or ctx.hash_of(art["path"]) != digest:
            raise ValueError("内部步骤原批准绑定的来源或产物已变化")
    earlier = ad.stage_order()[:ad.stage_order().index(stage)]
    checked = set()
    for doc in ctx.docs:
        if doc["stage"] in earlier:
            _approved_document(ctx, doc, checked)


def _contract(ctx, stage, path):
    """Only known Project writers can prove historical Project output."""

    for kind, (folder, name, owner_stage) in pc.client_document_files().items():
        if path == f"{folder}/{name}" and stage == owner_stage:
            caller, identifier = output_contract(ctx.root, stage, {"path": path})
            return caller, identifier, f"Luz-Project/scripts/client_flow.py:{kind}"
    if path == pc.stage_document_path(stage, ctx.root).replace(chr(92), "/"):
        return "luz-project", "showcase", "Luz-Project/scripts/stage_documents.py"
    owner = pc._stage_record(ctx.manifest, stage)["owner"]
    report = f"{pc.evidence_dir(ctx.root, ctx.manifest)}/{owner}-{stage}.html"
    if path == report:
        return owner, "reading-html", "Luz-Crawl/scripts/crawl_preflight.py:render_report"
    raise ValueError("目标不属于可核验原生成器的历史项目文档或内部结论")


def require_approved_output(session, caller, stage, target, selection):
    root, target = Path(session).resolve(), Path(target).resolve()
    if not (root / "project.json").is_file():
        raise ValueError("历史模板产物必须绑定真实项目状态根")
    ctx = ad.Ctx(root)
    if ad.policy(ctx.manifest).get("model") != "document":
        raise ValueError("历史模板核验要求逐文件审批模型的原始批准账本")
    if stage not in pc._stage_defs():
        raise ValueError("历史模板阶段不存在")
    path = relative_to_project(root, target)
    if locate(root, path).resolve() != target:
        raise ValueError("历史模板目标位置与项目契约不符")
    expected = _contract(ctx, stage, path)
    output = selection.get("output") or {}
    if ((caller, selection.get("id"), output.get("generator")) != expected
            or Path(str(output.get("path") or "")).resolve() != target
            or output.get("sha256") != ctx.hash_of(path)):
        raise ValueError("原生成回执未绑定准确调用者、模板、实际生成器与成品 SHA-256")
    doc = next((d for d in ad.documents(root, stage) if d["path"] == path), None)
    if doc:
        _approved_document(ctx, doc, set())
    else:
        _approved_internal_stage(ctx, stage, path)
