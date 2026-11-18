"""A generated document can cite only its stage's verified Crawl sources."""
import copy
import json

import pytest

import client_fixture as fx
import dev_fixture
from project_core import ProjectError
from project_paths import locate
from stage_documents import write_document


def researched_spec(tmp_path):
    root = fx.new_project("来源对照", tmp_path)
    fx.crawled(root, "architecture")
    spec = copy.deepcopy(dev_fixture.sample_spec("architecture", root))
    import crawl_preflight as cp
    from project_crawl_gate import evidence_session
    assert cp.validate_preflight(evidence_session(root), "luz-system", "architecture") == []
    record = cp.read(cp.record_path(evidence_session(root), "luz-system", "architecture"))
    assert {(s["id"], s["url"]) for s in spec["sources"]} == {(s["id"], s["url"]) for s in record["sources"]}
    return root, spec, record


@pytest.mark.parametrize("change", ["id", "url", "hash"])
def test_document_rejects_a_source_not_bound_to_its_archive(tmp_path, change):
    root, spec, _ = researched_spec(tmp_path)
    if change == "id":
        spec["sources"][0]["id"] = "SRC-999"
    elif change == "url":
        spec["sources"][0]["url"] = "https://unread.example/fabricated"
    else:
        spec["sources"][0]["manifest_sha256"] = "0" * 64
    target = locate(root, "docs/02-产品开发/01-系统架构.html")
    with pytest.raises(ProjectError, match="来源"):
        write_document(root, "architecture", spec)
    assert not target.exists()
    assert not (root / "data/stages/architecture.json").exists()


def test_document_persists_the_verified_archive_hashes(tmp_path):
    root, spec, record = researched_spec(tmp_path)
    write_document(root, "architecture", spec)
    saved = json.loads((root / "data/stages/architecture.json").read_text(encoding="utf-8"))
    assert [(s["id"], s["url"], s.get("manifest_sha256")) for s in saved["sources"]] == [(s["id"], s["url"], s["manifest_sha256"]) for s in record["sources"]]


def test_document_rejects_a_changed_body_before_writing(tmp_path):
    root, spec, record = researched_spec(tmp_path)
    import crawl_preflight as cp
    archive = cp.archive_dir(record["sources"][0]["archive"])
    (archive / "content.json").write_text('{"text":"changed"}', encoding="utf-8")
    with pytest.raises(ProjectError, match="Crawl"):
        write_document(root, "architecture", spec)
    assert not locate(root, "docs/02-产品开发/01-系统架构.html").exists()
    assert not (root / "data/stages/architecture.json").exists()


def test_document_requires_a_luz_design_template_selection_before_writing(tmp_path):
    root, spec, _ = researched_spec(tmp_path)
    (root / "00-design" / "luz-project-architecture.json").unlink(missing_ok=True)
    target = locate(root, "docs/02-产品开发/01-系统架构.html")
    with pytest.raises(ProjectError, match="Luz-Design|模板"):
        write_document(root, "architecture", spec)
    assert not target.exists()
    assert not (root / "data/stages/architecture.json").exists()


@pytest.mark.parametrize("field", ["id", "url", "manifest_sha256"])
def test_persisted_document_source_binding_is_rechecked(tmp_path, field):
    root, spec, _ = researched_spec(tmp_path)
    write_document(root, "architecture", spec)
    saved = json.loads((root / "data/stages/architecture.json").read_text(encoding="utf-8"))
    import dev_documents
    assert dev_documents.source_binding_errors("architecture", saved, root) == []
    saved["sources"][0][field] = "fabricated"
    assert dev_documents.source_binding_errors("architecture", saved, root)


def test_document_rejects_a_finding_that_is_not_in_the_concluded_crawl(tmp_path):
    root, spec, _ = researched_spec(tmp_path)
    spec["sources"][0]["finding"] = "MODEL INVENTED CLAIM WITH NO QUOTE"
    with pytest.raises(ProjectError, match="finding|结论"):
        # The stage can be rendered only after the specialist gate in a real
        # project; this fixture targets the source-binding guard directly.
        from project_crawl_gate import bind_document_sources
        bind_document_sources(root, "architecture", spec["sources"])


@pytest.mark.parametrize("change", ["finding", "applies_to", "empty_applies_to", "empty_id"])
def test_a_real_finding_id_does_not_authorize_unrecorded_claims_or_scope(tmp_path, change):
    from project_crawl_gate import bind_document_sources

    root, spec, record = researched_spec(tmp_path)
    source = copy.deepcopy(spec["sources"][0])
    finding = next(item for item in record["findings"] if item["source_id"] == source["id"] and item["adopted"])
    source.update({"finding_id": finding["id"], "finding": finding["summary"], "applies_to": finding["applies_to"]})
    if change == "finding":
        source["finding"] = "MODEL INVENTED CLAIM WITH A REAL ID"
    elif change == "applies_to":
        source["applies_to"] = "MODEL INVENTED SCOPE WITH A REAL ID"
    elif change == "empty_applies_to":
        source["applies_to"] = ""
    else:
        source["finding_id"] = ""
    with pytest.raises(ProjectError, match="finding|coverage|applies_to"):
        bind_document_sources(root, "architecture", [source])


def test_coverage_connects_to_a_finding_id_instead_of_its_source_id(tmp_path):
    from project_crawl_gate import bind_document_sources

    root, spec, record = researched_spec(tmp_path)
    source = copy.deepcopy(spec["sources"][0])
    finding = next(item for item in record["findings"] if item["source_id"] == source["id"] and item["adopted"])
    row = next(item for item in record["coverage"] if finding["id"] in item["finding_ids"])
    assert row["applies_to"] != finding["applies_to"], "the fixture must exercise coverage rather than the direct finding scope"
    source.update({"finding": finding["summary"], "applies_to": row["applies_to"]})
    bound = bind_document_sources(root, "architecture", [source])
    assert bound[0]["applies_to"] == row["applies_to"]
    source["finding_id"] = finding["id"]
    assert bind_document_sources(root, "architecture", [source])[0]["finding_id"] == finding["id"]

def test_existing_material_can_generate_and_register_a_stage_without_web_sources(tmp_path):
    from flow_steps import _c_records
    from approval_docs import Ctx
    from project_core import _load_artifacts, _register_evidence, load_project

    root, spec, _ = researched_spec(tmp_path)
    from crawl_preflight import run, validate_preflight

    stage, owner = "architecture", "luz-system"
    run(root, owner, "核对现有系统设计", stage=stage, research="local", reason="已确认的需求与本地系统合同")
    assert validate_preflight(root, owner, stage) == []
    spec["sources"] = []

    page = write_document(root, stage, spec)
    html = page.read_text(encoding="utf-8")
    assert "检索来源与采用位置" not in html
    _register_evidence(root, stage)
    assert load_project(root)["crawl"]["task_root"] is None
    records = [a["path"] for a in _load_artifacts(root) if a["kind"] == "research-evidence"]
    assert records == ["00-crawl/luz-system-architecture.json"]
    # The architecture can still need additional specialist records. The local
    # preflight record itself must satisfy its internal-record step.
    errs = _c_records(Ctx(root), stage, {"command": "project.py document"})
    assert not any("Crawl" in message or "结论页" in message for message in errs)


def test_local_record_cannot_support_a_web_citation(tmp_path):
    root, spec, _ = researched_spec(tmp_path)
    from crawl_preflight import run
    run(root, "luz-system", "核对现有系统设计", stage="architecture", research="local", reason="本地系统合同")
    with pytest.raises(ProjectError, match="本地"):
        write_document(root, "architecture", spec)
    assert not locate(root, "docs/02-产品开发/01-系统架构.html").exists()


def test_local_requirement_review_advances_a_document_based_project(tmp_path):
    import doc_fixture
    import project_core as pc
    from crawl_preflight import run

    root = fx.new_project("客户需求已提供", tmp_path, model="document")
    stage = "requirements"
    doc_fixture.note_step(root, stage, "rules")
    fx.crawled(root, stage)
    run(root, "luz-project", "整理客户的需求原稿", stage=stage, research="local", reason="客户已提供本地需求原稿")
    doc_fixture.specialist(root, stage, tmp_path)
    doc_fixture.note_step(root, stage, "specialist")
    doc_fixture.records(root, stage)

    pc.approve_stage(root, stage)
    manifest = pc.load_project(root)
    assert manifest["current_stage"] == "research"
    assert manifest["crawl"]["task_root"] is None
