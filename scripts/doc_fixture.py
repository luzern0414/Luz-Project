"""Offline rehearsal of the by-document approval model (tests only; never a real project, never a real approval).

``drive`` does for a stage what an agent does before the user is asked about a file (the matrix steps): note the rules read, run the Crawl preflight fixture, produce the specialists'
data, build the files, write the internal records; ``approve_all`` then records the user's approval file by file in the global order. The approvals written here say TEST ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Ops" / "scripts"))

import approval_docs as ad
import client_data as cd
import client_fixture
import client_flow as cf
import dev_documents
import dev_fixture
import flow_steps
import project_core as pc
from project_crawl_gate import evidence_session
from project_paths import locate
from stage_documents import write_document
from test_crawl_preflight import complete_fixture

TEST_NOTE = "TEST ONLY: synthetic user approval in an isolated fixture"
OPS = ("verification", "release", "operations")


def baseline_statement(root: Path) -> None:
    """A project statement against the baseline that uses every item (dev_documents.validate compares the documents with it)."""
    import baseline as bl

    statement: dict[str, Any] = {"stack": {}, "frontend": {}, "modules": {m["id"]: {"status": "沿用"} for m in bl.functions()["modules"]}}
    for kind, getter in (("stack", bl.stack_items), ("frontend", bl.frontend_items)):
        statement[kind] = {i["id"]: {"status": "沿用"} for i in getter()}
    (Path(root) / "data").mkdir(parents=True, exist_ok=True)
    (Path(root) / "data" / "baseline.json").write_text(json.dumps(statement, ensure_ascii=False), encoding="utf-8")


def note_step(root: Path, stage: str, step: str) -> None:
    flow_steps.record_step(root, stage, step, f"TEST ONLY: {step} of {stage}（离线演练：读了该阶段的规则卡，采用其中的规则）", "测试")


def crawl(root: Path, stage: str) -> None:
    complete_fixture(evidence_session(root), pc._stage_record(pc.load_project(root), stage)["owner"], stage, source_urls=[source["url"] for source in dev_fixture.SOURCES])
    import template_library
    template_library.select(root, "luz-project", stage, "showcase", pc.stage_document_path(stage, root))
    template_library.select(root, "luz-project", stage, "xlsx", "docs/01-需求对接/06-需求变更台账.xlsx")


def dummy_file(root: Path, stage: str, path: str, kind: str) -> None:
    target = locate(root, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"%PDF-1.4 rehearsal " + path.encode("utf-8"))
    bind_template_fixture(root, stage, path)
    pc.register_artifact(root, stage, target, kind)


def bind_template_fixture(root: Path, stage: str, path: str) -> None:
    """Post-bind explicit offline routing placeholders, never real business output."""
    import template_library
    from project_template_gate import output_contract
    caller, identifier = output_contract(root, stage, {"path": path})
    template_library.select(root, caller, stage, identifier, path)
    if caller == "luz-ops":
        # Ops discovers its formal PDF outputs through its own real writer
        # index as well as the shared Design post-binding.  Keep the routing
        # placeholder explicit while exercising that public binding API.
        from ops_core import design_template
        design_template(root, stage, locate(root, path), identifier, post=True,
                        generator="TEST ONLY: isolated routing fixture")
    else:
        template_library.record_output(root, caller, stage, locate(root, path), identifier, generator="TEST ONLY: isolated routing fixture")


def review_spec(stage: str) -> dict[str, Any]:
    return {"title": f"{stage} 离线演练", "conclusion": "只验证路由和门禁，非产品验收。", "sections": [{"title": "阶段结果", "content": "合成测试数据，不构成真实业务批准。"}], "sources": []}


def link_all(root: Path) -> None:
    spec = cd.load_features(root)
    for f in cd.active_features(spec):
        cf.link_feature(root, f["id"], arch=[f["module"]], design=[], dev=[])


def ops_checks(root: Path, stage: str, tmp: Path) -> None:
    from ops_core import operations_matrix, record_check
    from ops_fixtures import evidence_for

    proof = Path(tmp) / f"offline-{stage}.json"
    proof.write_text(json.dumps({"kind": "test-fixture", "stage": stage}), encoding="utf-8")
    for check in operations_matrix()["checks"]:
        if check["phase"] == stage:
            record_check(root, check["id"], "passed", [str(p) for p in evidence_for(check["id"], Path(tmp) / "records", proof)], "仅路由测试证据")


def specialist(root: Path, stage: str, tmp: Path) -> None:
    """The specialists' data for the stage, as far as the stage needs it before the files are built."""
    if stage == "requirements":
        client_fixture.requirements_provided(root)
    elif stage == "proposal":
        client_fixture.write_all(root)
    elif stage in {"architecture", "design", "technical-plan"}:
        baseline_statement(root)
    elif stage == "implementation":
        (pc.deliver_root(root) / "src").mkdir(exist_ok=True)
        (pc.deliver_root(root) / "src" / "app.py").write_text("print('rehearsal')\n", encoding="utf-8")
    elif stage in OPS:
        ops_checks(root, stage, tmp)
    elif stage == "handover":
        features = cd.load_features(root)
        checklist = cf.generate_acceptance(root)
        for item in checklist["items"]:
            if item["status"] != "waived":
                item.update({"status": "passed", "signed_by": "验收人（测试）", "signed_at": "2026-11-02"})
        cd.save(root, checklist, "acceptance", "checklist.json")
        scoped = cf.effective_features(root, features)
        names = {m["name"]: [f["id"] for f in scoped if f["module"] == m["id"]] for m in features["modules"]}
        cd.save(root, client_fixture.manual({k: v for k, v in names.items() if v}), "client", "manual.json")


def build(root: Path, stage: str) -> None:
    """The files of the stage (and, for a development stage, the document that is also its review page)."""
    if stage == "proposal":
        cf.build_proposal(root)
    elif stage == "client-intake":
        cf.build_intake_form(root)
    elif stage == "handover":
        cf.build_acceptance_xlsx(root)
        cf.build_manual(root)
        for c in cf._ledger(root)["changes"]:
            if c["status"] == "已确认":
                cf.update_change(root, c["id"], status="已实施")
        cf.snapshot_ledger(root)
    elif dev_documents.has_standard(stage) or stage in OPS:
        spec = dev_fixture.sample_spec(stage, root) if dev_documents.has_standard(stage) else review_spec(stage)
        if stage == "design":
            dev_fixture.install_source(root, spec)
        write_document(root, stage, spec)
        if stage == "architecture":
            dev_fixture.frontend_handover(root)
            link_all(root)
        pdfs = {"implementation": [("docs/03-验收交付/07-用户协议.pdf", "legal-pdf"), ("docs/03-验收交付/08-隐私政策.pdf", "legal-pdf")],
                "verification": [("docs/03-验收交付/04-验收测试报告.pdf", "ops-client-pdf")], "release": [("docs/03-验收交付/05-发布说明.pdf", "ops-client-pdf")],
                "operations": [("docs/03-验收交付/06-运维手册.pdf", "ops-client-pdf")]}
        for path, kind in pdfs.get(stage, []):
            dummy_file(root, stage, path, kind)


def records(root: Path, stage: str) -> None:
    if stage in {"requirements", "research", "proposal", "client-intake", "handover"}:
        write_document(root, stage, review_spec(stage))
    if stage == "handover":
        link_all(root)


def drive(root: Path, stage: str, tmp: Path) -> None:
    """Everything before the user is asked: rules, Crawl, specialists, build, records. Does not approve."""
    note_step(root, stage, "rules")
    crawl(root, stage)
    specialist(root, stage, tmp)
    note_step(root, stage, "specialist")
    build(root, stage)
    records(root, stage)


def approve_all(root: Path, stage: str, approver: str = "测试用户") -> list[dict[str, Any]]:
    out = []
    for d in ad.documents(root, stage):
        out.append(ad.approve_document(root, stage, d["path"], TEST_NOTE, approver))
    return out


def finish(root: Path, stage: str, tmp: Path) -> None:
    """What completes the stage after its files are approved: the client's input, the action gates; a stage without files completes by itself."""
    if stage == "client-intake":
        cf.import_intake(root, client_fixture.fill_intake(cf.build_intake_form(root), root))
    if not ad.documents(root, stage):
        pc.approve_stage(root, stage)
    for action in pc._stage_defs()[stage].get("action_gates", []):
        ad.record_action(root, stage, action["id"], "TEST ONLY: 用户授权（离线演练）", "测试用户")


def run_stage(root: Path, stage: str, tmp: Path) -> None:
    drive(root, stage, tmp)
    approve_all(root, stage)
    finish(root, stage, tmp)


def run_through(root: Path, last: str, tmp: Path) -> None:
    """Run the stages in order up to and including ``last`` (all the user's approvals are synthetic)."""
    for stage in ad.stage_order():
        run_stage(root, stage, tmp)
        if stage == last:
            return


# --- shortcuts for the tests of the record mechanics (they skip the internal steps on purpose; the tests of the gates do not use them) ---------------------

def internal_complete(root: Path, stage: str) -> dict[str, Any]:
    """An internal completion record for a stage without files, written straight into the ledger."""
    ctx = ad.Ctx(Path(root))
    return ad._new_record(ctx, scope="stage", stage=stage, mode=ad.INTERNAL, approver="internal-gates", note="TEST ONLY", source_hashes=ad.source_hashes(ctx, stage), upstream=ctx.stage_upstream(stage))


def files_for(root: Path, stage: str) -> list[dict[str, Any]]:
    """Register a placeholder for every file of the stage that does not exist yet (kind from the matrix); returns the stage's documents."""
    for d in ad.documents(root, stage):
        if not locate(root, d["path"]).is_file():
            target = locate(root, d["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"rehearsal " + d["path"].encode("utf-8"))
        bind_template_fixture(root, stage, d["path"])
        pc.register_artifact(root, stage, locate(root, d["path"]), d.get("kind", "html"))
    return ad.documents(root, stage)


def force_records(root: Path, stage: str, mode: str = ad.USER, note: str = TEST_NOTE) -> None:
    """Approval records for all files of a stage, written straight into the ledger in the global order (no checks)."""
    for d in files_for(root, stage):
        ctx = ad.Ctx(Path(root))
        ad._new_record(ctx, scope="document", stage=stage, document=d["path"], hash=ctx.hash_of(d["path"]), source_hashes=ad.source_hashes(ctx, stage), upstream=ctx.upstream_of(d["path"]),
                       mode=mode, approver="测试用户" if mode == ad.USER else "测试用户（整体预先授权，代为记录）", note=note)
    ad.refresh(Path(root))


def set_policy(root: Path, **policy: Any) -> None:
    manifest = pc.load_project(root)
    manifest["approval_policy"] = {**manifest.get("approval_policy", {}), **policy}
    pc._save_manifest(Path(root), manifest)


def clone(root: Path, tmp: Path | str) -> Path:
    """A copy of a project (state root and project directory) in another temporary folder with ``deliver_root`` pointed at the copy; returns the copy's state root."""
    import os
    import shutil

    root = Path(root)
    deliver, session = pc.deliver_root(root), root.parent
    new_deliver, new_session = Path(tmp) / "work" / deliver.name, Path(tmp) / "out" / session.name
    shutil.copytree(deliver, new_deliver)
    shutil.copytree(session, new_session)
    new_root = new_session / "raw"
    for name in ("project.json", "MANIFEST.json", "data/project.json"):
        path = new_root / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data["deliver_root"] = str(new_deliver)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # A copied fixture keeps identical bytes but has a different absolute
    # destination; update only the test copy's template path bindings.
    for record_path in (new_root / "00-design").glob("*.json"):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        for item in record.get("template_uses", []):
            for key in ("applies_to",):
                value = item.get(key)
                if isinstance(value, str) and Path(value).is_absolute():
                    for old, new in ((deliver, new_deliver), (root, new_root)):
                        if Path(value).is_relative_to(old):
                            item[key] = str(new / Path(value).relative_to(old))
                            break
            output = item.get("output")
            if isinstance(output, dict) and isinstance(output.get("path"), str):
                for old, new in ((deliver, new_deliver), (root, new_root)):
                    if Path(output["path"]).is_relative_to(old):
                        output["path"] = str(new / Path(output["path"]).relative_to(old))
                        break
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.environ["LUZ_PROJECT_OUTPUT"] = str(Path(tmp) / "out")
    return new_root


def write_step(root: Path, stage: str, step: str) -> None:
    """A step note written straight into data/steps.json (record_step refuses while the stage in front is not through; a test of the hold needs the note anyway)."""
    data = ad.load_steps(Path(root))
    data["records"].setdefault(stage, {})[step] = {"note": f"TEST ONLY: {step} of {stage}（直接写入的演练记录）", "by": "测试", "at": pc.now_iso(), "backfilled": False}
    pc._write_json(Path(root).joinpath(*ad.STEPS_FILE), data)
