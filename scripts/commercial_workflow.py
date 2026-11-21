"""Commercial project stages, whole-package decisions and source/version checks."""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import project_core as pc
from project_paths import ProjectError

WORKFLOW = "commercial-v1"
ORIGINALS = "docs/01-原始资料"
CLIENT = "docs/02-对接资料"
DEVELOPMENT = "docs/03-开发资料"
FOLDERS = (ORIGINALS, CLIENT, DEVELOPMENT)
BATCHES = {
    "scope": ("需求与系统方案", "luz-system", ["luz-project", "luz-crawl", "luz-writing", "luz-design"], CLIENT,
              ["01-需求说明.pdf", "02-系统方案.pdf"]),
    "design": ("开发说明", "luz-system", ["luz-dev", "luz-design", "luz-ops"], DEVELOPMENT,
               ["01-功能说明.html", "02-技术方案.html", "03-前端开发说明.html", "04-后端开发说明.html"]),
    "demo": ("交互原型", "luz-design", ["luz-system", "luz-dev", "luz-ops"], DEVELOPMENT, ["05-交互原型.html"]),
    "baseline": ("对接资料定稿", "luz-system", ["luz-dev", "luz-design", "luz-writing", "luz-ops", "luz-project"], CLIENT,
                 ["03-架构图.pdf", "04-功能需求清单.xlsx", "05-业务规则确认表.xlsx", "06-项目实施计划表.xlsx"]),
}
LATE_NUMBERS = {"07": "07", "08": "08", "04": "09", "05": "10", "06": "11", "01": "12", "02": "13", "03": "14"}
CARDS = {"scope": [("luz-system", "business-discovery"), ("luz-system", "client-docs")],
         "design": [("luz-system", "function-list"), ("luz-design", "design-path"), ("luz-dev", "tech-plan"), ("luz-dev", "api-data")],
         "demo": [("luz-design", "prototype-reference"), ("luz-design", "interface-components"), ("luz-system", "interaction")],
         "baseline": [("luz-system", "client-docs"), ("luz-design", "showcase"), ("luz-design", "xlsx")]}


def active(root, stage=None):
    from project_paths import commercial_at
    return (stage is None or stage in BATCHES) and commercial_at(root)


def paths(batch):
    _, _, _, folder, names = BATCHES[batch]
    return [f"{folder}/{name}" for name in names]


@contextmanager
def write_lock(root):
    """Serialize package builds, decisions and reviews. The OS releases the lock when a writer exits."""
    directory = root / "data/commercial"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".writer.lock").open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ProjectError("本项目正在写入，当前操作尚未执行，请在前一操作结束后重试") from exc
        yield


def _batch_stage(batch, prev, following):
    title, owner, contributors, folder, names = BATCHES[batch]
    docs = [{"id": f"{batch}-{i}", "path": path, "kind": f"commercial-{batch}", "skill": owner,
             "title": Path(path).stem[3:], "format": Path(path).suffix[1:]} for i, path in enumerate(paths(batch), 1)]
    if batch == "design":
        for document, authors in zip(docs, [("luz-system",), ("luz-dev", "luz-system"), ("luz-dev", "luz-design"), ("luz-dev",)]):
            document.update(skill=authors[0], producers=list(authors))
    command = 'project.py build "<项目>" <阶段> --data "<事实.json>"'
    crawl = '--research search --task "<Crawl任务目录>"' if batch == "scope" else '--research local --reason "<实际依据>"'
    steps = [
        ("upstream", "upstream", "核对上游确认版本", "prepare", 'project.py context "<项目>" <阶段>'),
        ("rules", "step-record", "读取规则卡并记录采用的规则", "prepare", 'project.py step "<项目>" <阶段> rules --note "<采用的规则>"'),
        ("templates", "commercial-templates", "为本批选择真实模板和准确成品路径", "prepare", 'project.py templates "<项目>" <阶段>'),
        ("crawl", "crawl", "核对本阶段依据", "prepare", f'crawl_preflight.py run --caller {owner} --session "<状态根>" --stage {batch} --topic "<主题>" {crawl}'),
        ("specialist", "specialist", "记录专业技能产出与自检结论", "produce", 'project.py step "<项目>" <阶段> specialist --note "<参与技能、产出和自检结论>"'),
        ("build", "commercial-build", "生成并核对整组文件", "produce", command),
    ]
    if batch != "baseline":
        steps.append(("confirm", "record", "等待用户确认本批全部文件", "review",
                      'project.py approve "<项目>" <阶段> --approver "<用户>" --note "<确认原话>"'))
    return {"id": batch, "name": title, "owner": owner, "contributors": contributors, "docs_dir": folder,
            "rule_cards": [{"skill": skill, "card": card, "for": title} for skill, card in CARDS[batch]],
            "required_inputs": [prev] if prev else [], "next": following, "failure_route": prev or batch,
            "approval": "internal-baseline" if batch == "baseline" else "user-batch",
            "documents": docs, "deliverables": [{**d, "name": d["title"], "required": True} for d in docs],
            "outputs": paths(batch), "steps": [
                {"id": sid, "check": check, "gate": "user" if sid == "confirm" else "internal", "skill": owner,
                 "title": title, "phase": phase, "command": cmd, "proof": title,
                 **({"record": sid} if sid in ("rules", "specialist") else {})} for sid, check, title, phase, cmd in steps]}


def matrix(legacy):
    # Keep the same post-development document, review, evidence and action contracts as the existing specialist tools.
    later = [s for s in legacy["stages"] if s["id"] in {"implementation", "verification", "release", "operations", "handover"}]
    text = json.dumps(later, ensure_ascii=False).replace("docs/02-产品开发", DEVELOPMENT).replace("docs/03-验收交付", CLIENT)
    for stage in later:
        for item in stage.get("deliverables", []):
            if item["path"].startswith("docs/03-验收交付/"):
                name = Path(item["path"]).name
                text = text.replace(name, LATE_NUMBERS[name[:2]] + name[2:])
    tail = json.loads(text)
    tail[0].update(required_inputs=["baseline"], failure_route="baseline")
    order = list(BATCHES) + ["implementation"]
    early = [_batch_stage(batch, order[i-1] if i else None, order[i+1]) for i, batch in enumerate(BATCHES)]
    return {"workflow": WORKFLOW, "stages": early + tail, "approval_unit": "batch-then-document",
            "directory_contract": {ORIGINALS: "客户提供的原件", CLIENT: "对接资料、正式交付与签收文件", DEVELOPMENT: "开发资料、可操作原型与实施验证记录"}}


def _has_real_search(record):
    return (isinstance(record, dict) and record.get("research_mode") in {"search", "deep"}
            and any(isinstance(step, dict) and step.get("command") == "search" and step.get("search_performed") is True
                    for step in (record.get("steps") or [])))


def scope_evidence_errors(root):
    from project_crawl_gate import stage_record
    manifest = pc.load_project(root)
    if pc._stage_record(manifest, "scope").get("owner") != BATCHES["scope"][1]:
        return ["范围与系统方案的检索调用者必须是 luz-system"]
    record = pc._read_json(stage_record(root, manifest, "scope"), {}) or {}
    if not _has_real_search(record):
        return ["需求与方案需要 Luz-System 的本阶段真实检索记录（search/deep），并读正文、归档和 conclude"]
    return []


def design_evidence_errors(ctx):
    from project_crawl_gate import stage_record

    # An unchanged approved batch keeps the evidence admitted at its review.
    if batch_record(ctx, "design", check_templates=False)[0]:
        return []
    record_path = stage_record(ctx.root, ctx.manifest, "design")
    if not _has_real_search(pc._read_json(record_path, {})):
        return ["功能与技术设计需由 System 和 Dev 在本阶段真实搜索（search/deep），核对目标版本的技术、组件及恢复方案，再 conclude"]
    return []


def receipt_path(stage):
    return f"data/commercial/receipts/{stage}.json"


def scope_research_change(root, stage):
    """A newly confirmed change to an approved scope can open its own research task once."""
    if stage != "scope" or not active(root, stage):
        return None
    import client_flow
    decisions = [r for r in pc._load_approvals(root)["approvals"] if r.get("scope") == "batch" and r.get("stage") == stage]
    if not decisions or decisions[-1].get("status") != "voided":
        return None
    receipt = pc._read_json(root / receipt_path(stage), {}) or {}
    used = {c.get("id") for c in receipt.get("changes", [])}
    used.update(row.get("change") for row in pc.load_project(root)["crawl"].get("task_history", []))
    return next((change for change in reversed(client_flow._ledger(root)["changes"])
                 if change.get("status") in {"已确认", "已实施"} and change.get("category") == "范围"
                 and change.get("confirmed_by") and stage in change.get("reopened", []) and change["id"] not in used), None)


def _source_hashes(ctx, stage, *, recorded_sources=None):
    from project_crawl_gate import stage_record
    evidence = stage_record(ctx.root, ctx.manifest, stage)
    sources = [f"data/commercial/{stage}.json", evidence.relative_to(ctx.root).as_posix()]
    if evidence.with_suffix(".html").is_file():
        sources.append(evidence.with_suffix(".html").relative_to(ctx.root).as_posix())
    if stage == "demo":
        from commercial_documents import DEMO_WALKTHROUGH
        if recorded_sources is None or DEMO_WALKTHROUGH in recorded_sources:
            sources.append(DEMO_WALKTHROUGH)
    if stage == "scope":
        if recorded_sources is None:
            deliver = pc.deliver_root(ctx.root)
            sources.extend(p.relative_to(deliver).as_posix() for p in sorted((deliver / ORIGINALS).rglob("*")) if p.is_file())
        else:
            # A later sign-off form or production sample is a new input, not an edit to this approved scope.
            sources.extend(p for p in recorded_sources if p.startswith(ORIGINALS + "/"))
    if stage == "baseline":
        import client_data
        from client_flow import ESTIMATE_SOURCE, QUOTE_SOURCE
        sources.extend(["data/client/features.json", "data/client/trace-links.json#arch", "data/client/architecture.json",
                        "data/stages/architecture.json", ESTIMATE_SOURCE])
        estimate = client_data.estimate_state(ctx.root)
        if estimate.quote:
            sources.append(QUOTE_SOURCE)
            quote_file = (estimate.quote_data or {}).get("evidence_file")
            if quote_file:
                sources.append(quote_file)
    return {p: ctx.hash_of(p) for p in sources}


def predecessors(ctx, stage):
    previous = {}
    for batch in BATCHES:
        if batch == stage:
            break
        record = next((r for r in reversed(ctx.ledger["approvals"]) if r.get("stage") == batch and r.get("scope") == "batch"), None)
        previous[batch] = record["id"] if record and record.get("status") == "approved" else None
    return previous


def relevant_changes(ctx, stage):
    from client_flow import _ledger
    keys = ("id", "title", "detail", "impact", "refs", "feature_ops", "confirmed_by")
    return [{k: change.get(k) for k in keys} for change in _ledger(ctx.root)["changes"]
            if stage in change.get("affects", []) and change.get("status") in {"已确认", "已实施"}]


def version_errors(ctx, stage):
    """Check content, source, change and registry bindings without invoking the template library."""
    rec = pc._read_json(ctx.root / receipt_path(stage), {}) or {}
    if not rec:
        return [f"缺少本批构建记录。运行 project.py build <项目> {stage} --data <事实.json>"]
    sources = _source_hashes(ctx, stage, recorded_sources=rec.get("sources", {}))
    files = {p: ctx.hash_of(p) for p in paths(stage)}
    if (rec.get("files") != files or rec.get("sources") != sources or None in files.values() or None in sources.values()
            or rec.get("approvals") != predecessors(ctx, stage) or rec.get("changes") != relevant_changes(ctx, stage)):
        return [f"{stage} 的文件、来源或上游确认版本已变化，须重新构建"]
    if any(not ctx.registered(stage, p) or ctx.registered(stage, p)["sha256"] != digest for p, digest in files.items()):
        return [f"{stage} 尚未完整登记当前整组文件"]
    if stage == "demo":
        # Approved work retains its original rule edition. New decisions require today's rules.
        last = next((r for r in reversed(ctx.ledger["approvals"]) if r.get("stage") == stage
                     and r.get("scope") == "batch"), {})
        stamp = {receipt_path(stage): ctx.hash_of(receipt_path(stage))}
        if last.get("status") != "approved" or last.get("source_hashes") != stamp:
            return _pending_demo_errors(ctx, sources, files[paths(stage)[0]])
    return []


def _pending_demo_errors(ctx, sources, html_hash):
    from commercial_documents import DEMO_WALKTHROUGH, UI_STATE_RULES
    records = pc._read_json(ctx.root / DEMO_WALKTHROUGH, [])
    facts = pc._read_json(ctx.root / "data/commercial/demo.json", {})
    journeys = facts.get("journeys") or []
    problem = ["Demo 需要按当前 Design 成品规则重新构建并逐步走查"]
    if (DEMO_WALKTHROUGH not in sources or not journeys or not isinstance(records, list)
            or len(records) != len(journeys)):
        return problem
    rule_hash = hashlib.sha256(UI_STATE_RULES.read_bytes()).hexdigest()
    for record, journey in zip(records, journeys):
        if (not isinstance(record, dict) or record.get("name") != journey.get("name")
                or record.get("width") != journey.get("width", 1280) or record.get("html_sha256") != html_hash
                or record.get("design_rules_sha256") != rule_hash
                or len(record.get("ui_states") or []) != len(journey.get("steps") or []) + 2):
            return problem
    return []


def template_errors(ctx, stage, *_):
    from commercial_documents import TEMPLATES, WRITER, _design
    library = _design()
    confirmed, _ = batch_record(ctx, stage, check_templates=False)
    errors = []
    for path in paths(stage):
        try:
            library.require_selected(ctx.root, WRITER, stage, pc.locate(ctx.root, path), TEMPLATES[stage][Path(path).suffix],
                                     phase="post" if confirmed else "pre")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(f"{path}：{exc}")
    return errors


def build_errors(ctx, stage, *_):
    errors = version_errors(ctx, stage)
    if errors:
        return errors
    import client_flow
    import commercial_documents
    return list(commercial_documents.output_errors(pc.deliver_root(ctx.root), ctx.root, stage)) + client_flow.stage_checks(ctx.root, stage, phase="build")


def batch_record(ctx, stage, *, check_templates=True):
    """A batch decision binds the exact complete package, never a subset or an arbitrary single-file record."""
    import approval_docs as ad
    target = ad._scoped(ctx, "batch", stage=stage)
    record = target[-1] if target else None
    problem = ad.record_problem(ctx, record) if record else None
    if problem:
        return None, problem
    if record:
        expected_mode = ad.INTERNAL if stage == "baseline" else ad.USER
        files = {p: ctx.hash_of(p) for p in paths(stage)}
        receipt = receipt_path(stage)
        if (record.get("mode") != expected_mode or record.get("project_id") != ctx.manifest["project_id"]
                or not record.get("id") or not record.get("approved_at") or not record.get("approver") or not record.get("note")
                or record.get("files") != files or None in files.values()
                or record.get("source_hashes") != {receipt: ctx.hash_of(receipt)} or not ctx.hash_of(receipt)
                or record.get("upstream") != ctx.stage_upstream(stage)):
            return None, "source"
        if stage == "baseline" and record.get("approver") != "internal-gates":
            return None, "source"
        if stage != "baseline":
            try:
                require_decision(record["note"], record["approver"])
            except ProjectError:
                return None, "source"
        cache = ctx.cache.setdefault("commercial_build_valid", {})
        key = stage, check_templates
        if key not in cache:
            cache[key] = not (build_errors(ctx, stage) if check_templates else version_errors(ctx, stage))
        if not cache[key]:
            return None, "source"
    return record, problem


def _decision(ctx, stage, note, approver):
    import approval_docs as ad
    receipt = receipt_path(stage)
    result = ad._new_record(ctx, scope="batch", stage=stage, mode=ad.INTERNAL if stage == "baseline" else ad.USER,
                            note=note, approver=approver, files={p: ctx.hash_of(p) for p in paths(stage)},
                            source_hashes={receipt: ctx.hash_of(receipt)}, upstream=ctx.stage_upstream(stage))
    ad.refresh(ctx.root)
    return result


def require_decision(note, approver):
    invalid = r"默认通过|自动通过|预先授权|代为|未确认|未通过|未同意|不同意|不通过|待确认|请确认|待回复|未回复|未审|不批准|不确认|未授权|暂缓|不要发布|不得上线|do not|not approved|not yet"
    decision = r"确认|同意|通过|批准|授权|认可|没问题|无异议|没.{0,1}异议|可以|定稿|继续|允许|进入下一|\bok\b|\byes\b|\bapproved?\b|\bconfirmed?\b|go ahead"
    if (not approver.strip() or re.fullmatch(r"[<〈].*[>〉]", approver.strip()) or re.fullmatch(r"[<〈].*[>〉]", note.strip())
            or re.fullmatch(r"agent|assistant|codex|internal-gates|系统自动", approver.strip(), re.I)
            or not re.search(decision, note, re.I) or re.search(invalid, note + approver, re.I)):
        raise ProjectError("请记录用户的明确决定和实际确认人")


def confirm(root, stage, note, approver):
    import approval_docs as ad
    import flow_steps as flow
    if stage == "baseline":
        raise ProjectError("基线由第三次确认后的 build 定稿，无需另行批准")
    require_decision(note, approver)
    ctx = ad.Ctx(root)
    problems = flow.internal_errors(root, stage, ctx=ctx)
    if any(n["stage"] == stage and n["status"] == "open" for n in ctx.notes):
        problems.append("本批仍有未处理的修改意见")
    if problems:
        raise ProjectError("整组文件尚未就绪：" + "；".join(problems))
    existing, _ = batch_record(ctx, stage)
    return existing or _decision(ctx, stage, note.strip(), approver.strip())


def require_batch_sources(ctx, data_path, stage):
    from project_crawl_gate import stage_record
    from urllib.parse import urldefrag
    evidence = pc._read_json(stage_record(ctx.root, ctx.manifest, stage))
    findings = {f.get("source_id") for f in evidence.get("findings", []) if f.get("adopted") is True}
    urls = {urldefrag(s["url"])[0] for s in evidence.get("sources", []) if s.get("url") and s.get("id") in findings}
    facts = json.loads(Path(data_path).read_text(encoding="utf-8-sig"))
    if not isinstance(facts, dict) or not isinstance(facts.get("sources"), list):
        raise ProjectError("本批事实文件需提供 sources 列表")
    cited = {urldefrag(s["reference"])[0] for s in facts["sources"] if isinstance(s, dict)
             and isinstance(s.get("reference"), str) and s["reference"].startswith(("http://", "https://"))}
    if not urls.intersection(cited):
        raise ProjectError("本批 sources[].reference 应引用已采用的本阶段 Crawl 正文网址")
    if cited - urls:
        raise ProjectError("本批外部来源须逐项对应已采用的原文：" + "、".join(sorted(cited - urls)))


def build(root, stage, data_path):
    import approval_docs as ad
    import flow_steps as flow
    if not active(root, stage):
        raise ProjectError("build 只用于商业流程的四组文件")
    problems = flow.generation_errors(root, stage)
    if problems:
        raise ProjectError("构建前的内部步骤未通过：" + "；".join(problems))
    ctx = ad.Ctx(root)
    if batch_record(ctx, stage)[0] and not build_errors(ctx, stage):
        raise ProjectError("本批已经定稿。修改已确认版本请先登记变更")
    if stage in {"scope", "design"}:
        require_batch_sources(ctx, data_path, stage)
    from commercial_documents import build as generate, output_errors
    deliver = pc.deliver_root(root)
    pc._register_evidence(root, stage)
    generate(deliver, root, stage, data_path)
    errors = output_errors(deliver, root, stage)
    if errors:
        raise ProjectError("模板最终检查未通过：" + "；".join(errors))
    ctx = ad.Ctx(root)
    sources = _source_hashes(ctx, stage)
    files = {p: ctx.hash_of(p) for p in paths(stage)}
    if None in sources.values() or None in files.values():
        raise ProjectError("本批缺少必需的成品、事实文件或下游交接数据")
    for path in files:
        pc.register_artifact(root, stage, path, f"commercial-{stage}")
    rec = {"batch": stage, "files": files, "sources": sources, "approvals": predecessors(ctx, stage),
           "changes": relevant_changes(ctx, stage), "built_at": pc.now_iso()}
    pc._write_json(root / receipt_path(stage), rec)
    if stage == "baseline":
        ctx = ad.Ctx(root)
        errors = build_errors(ctx, stage)
        if errors:
            raise ProjectError("基线定稿未通过：" + "；".join(errors))
        _decision(ctx, stage, "三批已确认，基线构建与数据交接已核验", "internal-gates")
    return rec


def next_batch(ctx, stage, sched):
    rows = sched["steps"]
    current = next((r for r in rows if r.get("current")), None)
    notes = [n for n in ctx.notes if n["stage"] == stage and n["status"] == "open"]
    kind = "revise" if notes else "present" if current and current["id"] == "confirm" else "internal"
    if stage == "baseline" and sched["user_todos"] and current and current["id"] == "build":
        kind = "waiting"
    return {"model": "batch", "stage": stage, "stage_name": sched["name"], "kind": kind, "documents": paths(stage),
            "user_todos": sched["user_todos"] if stage == "baseline" else [],
            "current_step": current, "command": (current or {}).get("command"), "open_notes": notes,
            "message": {"revise": "按意见更新本批文件，处理完再请用户整组确认。", "present": "请一起审阅本批文件，回复确认或修改意见。",
                        "waiting": "请补齐功能需求清单的估算依据，再生成定稿文件。", "internal": "完成当前步骤后再交接本批文件。"}[kind]}
