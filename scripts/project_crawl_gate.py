"""Load the shared Crawl evidence gate without creating a project."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path

from project_paths import ProjectError, resolve_state_root


def evidence_session(project) -> Path:
    """What Crawl takes as the session of a project: its state root. Crawl keeps the preflight records in the folder project.json's
    ``crawl.evidence_index`` names (``00-crawl``; ``raw/00-crawl`` in a project that still has the old layout)."""
    try:
        return resolve_state_root(project)
    except ProjectError:
        return Path(project)


# Luz-Crawl's validator ends every record older than seven days with this sentence. The age matters for the stage that is being worked on (research that old has to be
# looked at again); for a stage whose files the user has already approved it does not: the record only has to be there, valid, concluded (references/runbook.md).
EXPIRY_MARK = "检索记录超过七天"


def _preflight(name: str):
    """Luz-Crawl's validator loaded by path under ``name``, with the path it was looked for; the module is None when it is missing."""
    source = Path(os.environ.get("LUZ_CRAWL_ROOT") or Path(__file__).resolve().parents[2] / "Luz-Crawl") / "scripts" / "crawl_preflight.py"
    if not source.is_file():
        return None, source
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, source


def crawl_errors(project, stage=None, caller=None, *, waive_expiry=False):
    """Luz-Crawl's check of the preflight record of ``stage``. ``waive_expiry`` drops the one finding that is about age (the stage is approved): the record must still exist,
    carry the task marker and log hashes, and be concluded."""
    module, source = _preflight("_luz_crawl_preflight")
    if module is None:
        return [f"Crawl 前置检索校验器不存在: {source}"]
    caller = caller or Path(__file__).resolve().parents[1].name.lower()
    errors = module.validate_preflight(evidence_session(project), caller, stage)
    return [e for e in errors if EXPIRY_MARK not in e] if waive_expiry else errors


def stage_record(root: Path, manifest: dict, stage: str) -> Path:
    from project_core import _stage_record, evidence_dir, locate

    caller = _stage_record(manifest, stage)["owner"]
    return locate(root, f"{evidence_dir(root, manifest)}/{caller}-{stage}.json")


def uses_local_evidence(record_path: Path) -> bool:
    """Identify the declared mode for display and layout. Crawl validates the record."""
    from project_core import _read_json

    record = _read_json(record_path, {})
    return isinstance(record, dict) and record.get("research_mode") == "local"


def bind_document_sources(project, stage, sources, *, require_hash=False):
    """Bind citations to the stage's checked body archives without trusting user-supplied URLs or hashes.

    This checks content identity. Freshness is checked by the stage's Crawl gate,
    whose expiry policy also covers already approved documents.
    """
    from project_core import load_project, _stage_record

    root = evidence_session(project)
    caller = _stage_record(load_project(root), stage)["owner"]
    module, source = _preflight("_luz_document_source_preflight")
    if module is None:
        raise ProjectError(f"来源无法核对：Crawl 前置检索校验器不存在：{source}")
    errors = [e for e in module.validate_preflight(root, caller, stage) if EXPIRY_MARK not in e]
    if errors:
        raise ProjectError("来源归档未通过 Crawl 校验：" + "; ".join(errors))
    record = module.read(module.record_path(root, caller, stage))
    if not isinstance(sources, list):
        raise ProjectError("文档来源必须是数组")
    if record.get("research_mode") == "local":
        if sources:
            raise ProjectError("本地阶段没有联网来源，请在正文注明实际采用的本地依据")
        return []
    actual = {entry["id"]: entry for entry in record["sources"]}
    findings = record.get("findings") if isinstance(record, dict) else None
    adopted = [f for f in findings or [] if isinstance(f, dict) and f.get("adopted") is True]
    if not isinstance(findings, list) or not adopted:
        raise ProjectError("本阶段 Crawl 结论缺少可采用的 findings；不能把模型自写的 finding 当作依据")
    by_source = {}
    for finding in adopted:
        by_source.setdefault(finding.get("source_id"), []).append(finding)
    bound, seen = [], set()
    for entry in sources:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ProjectError("文档来源缺少有效 id")
        identifier = entry["id"]
        descriptor = actual.get(identifier)
        if descriptor is None:
            raise ProjectError(f"来源 {identifier} 未出现在本阶段已核验的 Crawl 归档中")
        if identifier in seen:
            raise ProjectError(f"文档来源重复：{identifier}")
        seen.add(identifier)
        if entry.get("url") != descriptor["url"]:
            raise ProjectError(f"来源 {identifier} 的网址与实际归档正文不符")
        supplied_hash = entry.get("manifest_sha256")
        if (require_hash and not supplied_hash) or ("manifest_sha256" in entry and supplied_hash != descriptor["manifest_sha256"]):
            raise ProjectError(f"来源 {identifier} 的归档清单哈希缺失或与已核验记录不符")
        candidates = by_source.get(identifier, [])
        if not candidates:
            raise ProjectError(f"来源 {identifier} 没有对应的已采用 Crawl finding")
        finding_text = str(entry.get("finding") or "").strip()
        finding_id = entry.get("finding_id")
        if "finding_id" in entry:
            if not isinstance(finding_id, str) or not finding_id.strip():
                raise ProjectError(f"来源 {identifier} 的 finding_id 必须是非空的已采用结论编号")
            candidates = [f for f in candidates if f.get("id") == finding_id]
        if not candidates:
            raise ProjectError(f"来源 {identifier} 的 finding_id 未指向已采用结论")
        # A real ID identifies the finding; it does not authorize new prose or
        # a new application scope. New decisions must first be recorded as
        # adopted Crawl findings of kind decision with their actual evidence.
        candidates = [f for f in candidates if finding_text and finding_text in {
            str(f.get("summary") or "").strip(), str(f.get("quote") or "").strip()}]
        if not candidates:
            raise ProjectError(f"来源 {identifier} 的 finding 没有出现在已采用 Crawl 结论中")
        applies = str(entry.get("applies_to") or "").strip()
        covered = {str(f.get("applies_to") or "").strip() for f in candidates}
        candidate_ids = {str(f["id"]) for f in candidates}
        covered.update(str(row.get("applies_to") or "").strip() for row in (record.get("coverage") or [])
                       if isinstance(row, dict) and candidate_ids.intersection(str(i) for i in row.get("finding_ids", [])))
        if not applies or applies not in covered:
            raise ProjectError(f"来源 {identifier} 的 applies_to 没有对应 Crawl coverage")
        bound.append({**entry, "manifest_sha256": descriptor["manifest_sha256"]})
    return bound
