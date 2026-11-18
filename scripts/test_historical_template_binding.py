"""Offline history regressions: real writers and approval gates, synthetic data only.

The installed templates and DemoKit are never changed. A private catalog copy
simulates a checker update after the fixture's real approval was recorded.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

import approval_docs as ad
import client_data as cd
import client_fixture as fx
import client_flow as cf
import doc_fixture as df
import project_core as pc
from project_paths import locate
from project_template_gate import output_errors
from stage_documents import write_document

import crawl_preflight as crawl
import evidence_policy as policy
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Design/scripts"))
import template_library as library
from test_evidence_policy import broad_fixture, payload_for

DOCUMENT = "docs/01-需求对接/01-需求说明书.pdf"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def approved(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("history-source")
    root = fx.new_project("history", tmp, model="document")
    df.note_step(root, "requirements", "rules")
    df.crawl(root, "requirements")
    cd.save(root, fx.features(), "client", "features.json")
    cd.save(root, fx.requirements(), "client", "requirements.json")
    cf.set_theme(root, "fitness-gym")
    df.note_step(root, "requirements", "specialist")
    library.select(root, "luz-project", "requirements", "showcase", DOCUMENT)
    cf.build_requirements(root)
    write_document(root, "requirements", df.review_spec("requirements"))
    ad.approve_document(root, "requirements", DOCUMENT, df.TEST_NOTE, "TEST USER")
    df.run_stage(root, "research", tmp)
    assert ad.document_status(ad.Ctx(root), ad.documents(root, "requirements")[0])["state"] == "approved"
    assert ad.stage_record_effective(ad.Ctx(root), "research")
    return root


def drift(tmp, monkeypatch, file="scripts/check_document.py"):
    copied = tmp / "current-design"
    catalog = read(library.CATALOG)
    for relative in {p for item in catalog["templates"].values() for p in item["files"]}:
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(library.ROOT / relative, target)
    (copied / "references").mkdir(exist_ok=True)
    write(copied / "references/template-library.json", catalog)
    target = copied / file
    target.write_bytes(target.read_bytes() + b"\n# TEST ONLY: newer installed template revision\n")
    monkeypatch.setattr(library, "ROOT", copied)
    monkeypatch.setattr(library, "CATALOG", copied / "references/template-library.json")
    monkeypatch.setattr(policy, "design_library", lambda: library)
    monkeypatch.setattr(crawl, "_policy", lambda: policy)


@pytest.fixture
def history(approved, tmp_path, monkeypatch):
    root = df.clone(approved, tmp_path)
    drift(tmp_path, monkeypatch)
    return root


def selected(root, stage="requirements", target=DOCUMENT):
    path = root / "00-design" / f"luz-project-{stage}.json"
    value = read(path)
    item = next(i for i in value["template_uses"] if i["applies_to"] == target)
    return path, value, item


def post(root, stage="requirements", target=DOCUMENT):
    return library.require_selected(root, "luz-project", stage, locate(root, target), "showcase", phase="post")


def test_approved_document_survives_installed_template_update_without_rewriting_evidence(history):
    watched = [history / "APPROVALS.json", history / "project.json", selected(history)[0], locate(history, DOCUMENT)]
    before = {p: p.read_bytes() for p in watched}
    assert post(history)["output"]["generator"] == "Luz-Project/scripts/client_flow.py:requirements-pdf"
    assert output_errors(history, "requirements", {"path": DOCUMENT}) == []
    assert {p: p.read_bytes() for p in watched} == before


def test_new_generation_and_record_output_never_use_historical_approval(history):
    path, _, _ = selected(history)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="模板"):
        library.require_selected(history, "luz-project", "requirements", locate(history, DOCUMENT), "showcase", phase="pre")
    with pytest.raises(ValueError, match="模板"):
        library.record_output(history, "luz-project", "requirements", locate(history, DOCUMENT), "showcase", generator="Luz-Project/scripts/client_flow.py:requirements-pdf")
    assert path.read_bytes() == original


@pytest.mark.parametrize("damage", ["missing_receipt", "unknown_writer", "wrong_writer", "missing_snapshot", "deleted_snapshot", "changed_snapshot", "empty_files", "output_drift", "source_drift", "missing_source_binding", "missing_approval", "revoked_latest", "internal_mode", "preauthorized_mode", "wrong_project", "wrong_stage", "missing_artifact_binding", "open_note"])
def test_history_requires_all_original_evidence(history, damage):
    path, value, item = selected(history)
    ledger = read(history / "APPROVALS.json")
    record = next(r for r in ledger["approvals"] if r.get("document") == DOCUMENT)
    if damage == "missing_receipt":
        item.pop("output")
    elif damage in {"unknown_writer", "wrong_writer"}:
        item["output"]["generator"] = "unknown" if damage == "unknown_writer" else "ordinary record_output caller"
    elif damage == "missing_snapshot":
        item.pop("snapshots")
    elif damage == "deleted_snapshot":
        (path.parent / item["snapshots"][0]["path"]).unlink()
    elif damage == "changed_snapshot":
        (path.parent / item["snapshots"][0]["path"]).write_bytes(b"TEST ONLY: changed snapshot")
    elif damage == "empty_files":
        item["files"], item["snapshots"] = [], []
    elif damage == "output_drift":
        target = locate(history, DOCUMENT)
        target.write_bytes(target.read_bytes() + b"TEST ONLY: changed output")
    elif damage == "source_drift":
        target = history / "data/client/requirements.json"
        target.write_bytes(target.read_bytes() + b"\n")
    elif damage == "missing_source_binding":
        record["source_hashes"] = {}
    elif damage == "missing_approval":
        ledger["approvals"] = [r for r in ledger["approvals"] if r is not record]
        # Cached approved stage status is deliberately left unchanged.
    elif damage == "revoked_latest":
        ledger["approvals"].append({**record, "id": "APPROVAL-999", "status": "voided"})
    elif damage == "internal_mode":
        record["mode"] = "internal"
    elif damage == "preauthorized_mode":
        record["mode"] = "pre-authorized"
    elif damage == "wrong_project":
        record["project_id"] = "PROJECT-OTHER"
    elif damage == "wrong_stage":
        record["stage"] = "research"
    elif damage == "missing_artifact_binding":
        record["artifact_hashes"] = {}
    elif damage == "open_note":
        notes_path = history.joinpath(*ad.NOTES_FILE)
        notes = ad.load_notes(history)
        notes["notes"].append({"id": "NOTE-TEST", "document": DOCUMENT, "status": "open"})
        write(notes_path, notes)
    write(path, value)
    write(history / "APPROVALS.json", ledger)
    with pytest.raises(ValueError):
        post(history)


@pytest.mark.parametrize("kind", ["caller", "stage", "template", "raw_namesake"])
def test_history_cannot_authorize_a_different_contract(history, kind):
    caller, stage, identifier, target = "luz-project", "requirements", "showcase", locate(history, DOCUMENT)
    if kind == "caller":
        caller = "luz-crawl"
    elif kind == "stage":
        stage = "research"
    elif kind == "template":
        identifier = "reading-html"
    else:
        target = history / DOCUMENT
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(locate(history, DOCUMENT).read_bytes())
    with pytest.raises(ValueError):
        library.require_selected(history, caller, stage, target, identifier, phase="post")


def test_internal_research_approval_is_bound_to_the_real_stage_artifact(history):
    target = pc.stage_document_path("research", history)
    assert post(history, "research", target)["output"]["generator"] == "Luz-Project/scripts/stage_documents.py"


@pytest.mark.parametrize("damage", ["user_mode", "revoked_stage", "missing_target_binding", "changed_spec", "changed_upstream_source", "revoked_upstream", "wrong_stage", "unapproved_review"])
def test_internal_history_has_its_own_approval_and_upstream_requirements(history, damage):
    target = pc.stage_document_path("research", history)
    ledger = read(history / "APPROVALS.json")
    record = next(r for r in ledger["approvals"] if r.get("scope") == "stage" and r.get("stage") == "research")
    if damage == "user_mode":
        record["mode"] = "user"
    elif damage == "revoked_stage":
        ledger["approvals"].append({**record, "id": "APPROVAL-999", "status": "voided"})
    elif damage == "missing_target_binding":
        art = ad.Ctx(history).registered("research", target)
        record["artifact_hashes"].pop(art["id"])
    elif damage == "changed_spec":
        source = history / "data/stages/research.json"
        source.write_bytes(source.read_bytes() + b"\n")
    elif damage == "changed_upstream_source":
        source = history / "data/client/requirements.json"
        source.write_bytes(source.read_bytes() + b"\n")
    elif damage == "revoked_upstream":
        doc = next(r for r in ledger["approvals"] if r.get("document") == DOCUMENT)
        ledger["approvals"].append({**doc, "id": "APPROVAL-999", "status": "voided"})
    elif damage == "wrong_stage":
        record["stage"] = "proposal"
    else:
        # A document approval binds the PDF, not every internal page nearby.
        with pytest.raises(ValueError):
            post(history, "requirements", pc.stage_document_path("requirements", history))
        return
    write(history / "APPROVALS.json", ledger)
    with pytest.raises(ValueError):
        post(history, "research", target)


def test_current_target_is_not_blocked_by_another_stale_selection(history):
    page = history / "00-crawl/luz-project-requirements.html"
    for phase in ("pre", "post"):
        assert library.require_selected(history, "luz-project", "requirements", page, "reading-html", phase=phase)


def test_new_current_selection_preserves_unrelated_historical_bindings(history):
    path, before, _ = selected(history)
    target = history / "reviews/new-current.html"
    library.select(history, "luz-project", "requirements", "reading-html", str(target))
    after = read(path)
    assert after["template_uses"][:-1] == before["template_uses"]
    assert library.require_selected(history, "luz-project", "requirements", target, "reading-html", phase="pre")


def test_approved_internal_crawl_page_can_audit_its_own_original_template(approved, tmp_path, monkeypatch):
    root = df.clone(approved, tmp_path)
    drift(tmp_path, monkeypatch, file="scripts/make_summary.py")
    path = root / "00-crawl/luz-crawl-research.json"
    assert crawl.report_errors(path, read(path), root) == []


def test_unapproved_crawl_page_cannot_use_snapshots_as_output_approval(tmp_path, monkeypatch):
    path, value, _ = broad_fixture(tmp_path, "luz-crawl", "research")
    crawl.conclude(tmp_path, "luz-crawl", payload_for(value), "research")
    drift(tmp_path, monkeypatch, file="scripts/make_summary.py")
    assert crawl.report_errors(path, read(path), tmp_path)


def test_duplicate_target_selections_are_ambiguous(history):
    path, value, item = selected(history)
    value["template_uses"].append(copy.deepcopy(item))
    write(path, value)
    with pytest.raises(ValueError):
        post(history)


def test_snapshot_and_record_output_alone_do_not_grant_historical_approval(tmp_path, monkeypatch):
    target = tmp_path / "page.html"
    library.select(tmp_path, "luz-design", "design", "showcase", target.name)
    target.write_text("TEST ONLY: ordinary output without approval", encoding="utf-8")
    library.record_output(tmp_path, "luz-design", "design", target, "showcase", generator="ordinary record_output caller")
    drift(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        library.require_selected(tmp_path, "luz-design", "design", target, "showcase", phase="post")


@pytest.fixture
def historical_crawl(tmp_path, monkeypatch):
    path, value, _ = broad_fixture(tmp_path, "luz-crawl", "research")
    target = "raw/reviews/research.html"
    library.select(tmp_path, "luz-crawl", "research", "showcase", target)
    payload = payload_for(value)
    payload["template_uses"] = [library.reference("showcase", target)]
    payload["coverage"][0]["applies_to"] = target
    crawl.conclude(tmp_path, "luz-crawl", payload, "research")
    drift(tmp_path, monkeypatch)
    return tmp_path, path, payload


def test_old_crawl_references_use_saved_snapshots_without_claiming_generation(historical_crawl):
    root, path, _ = historical_crawl
    assert crawl.validate_preflight(root, "luz-crawl", "research") == []
    target = root / "raw/reviews/research.html"
    assert not target.exists()
    with pytest.raises(ValueError):
        library.require_selected(root, "luz-crawl", "research", target, "showcase", phase="post")


def test_new_crawl_conclusion_still_requires_current_templates(historical_crawl):
    root, path, payload = historical_crawl
    before = path.read_bytes()
    with pytest.raises(ValueError, match="模板"):
        crawl.conclude(root, "luz-crawl", payload, "research")
    assert path.read_bytes() == before


@pytest.mark.parametrize("damage", ["log", "quote", "sources", "coverage", "blocking_gaps", "wrong_reference", "missing_snapshot", "changed_snapshot"])
def test_history_does_not_skip_crawl_evidence(historical_crawl, damage):
    root, path, _ = historical_crawl
    value = read(path)
    if damage == "log":
        value["steps"][0]["sha256"] = "0" * 64
    elif damage == "quote":
        value["findings"][0]["quote"] = "TEST ONLY fabricated quote absent from archived evidence"
    elif damage == "sources":
        value["sources"] = []
    elif damage == "coverage":
        value["coverage"][0]["finding_ids"] = ["NO-SUCH-FINDING"]
    elif damage == "blocking_gaps":
        value["blocking_gaps"] = ["unresolved"]
    elif damage == "wrong_reference":
        value["template_uses"][0]["applies_to"] = "raw/unrelated.html"
    else:
        selected_path = root / "raw/00-design/luz-crawl-research.json"
        selected_value = read(selected_path)
        item = selected_value["template_uses"][0]
        if damage == "missing_snapshot":
            item.pop("snapshots")
            write(selected_path, selected_value)
        else:
            (selected_path.parent / item["snapshots"][0]["path"]).write_bytes(b"changed")
    value["approved"] = True  # a self-declared label must never hide errors
    write(path, value)
    assert crawl.validate_preflight(root, "luz-crawl", "research")
