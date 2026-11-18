"""A real Ops project report keeps its own exact writer contract in Project."""
from __future__ import annotations

import json

import pytest

import client_fixture
import doc_fixture  # installs the actual sibling scripts used in a routing fixture
import ops_core
import project_core as pc
from project_template_gate import output_errors


@pytest.fixture
def ops_report(tmp_path):
    root = client_fixture.new_project("Ops writer handoff", tmp_path, model="stage")
    client_fixture.crawled(root, "verification")
    target = pc.locate(root, pc.stage_document_path("verification", root))
    import template_library

    template_library.select(root, "luz-ops", "verification", "showcase", str(target))
    assert ops_core.render_ops_report(root, "acceptance") == target
    return root, target


def test_project_accepts_the_actual_ops_writer_for_its_exact_report(ops_report):
    root, target = ops_report
    assert output_errors(root, "verification", {"path": pc.stage_document_path("verification", root)}) == []


@pytest.mark.parametrize("change", ["bytes", "index_stage", "missing_index"])
def test_project_rejects_a_changed_ops_report_or_missing_writer_binding(ops_report, change):
    root, target = ops_report
    index = root / "data/ops/template-outputs.json"
    if change == "bytes":
        target.write_bytes(target.read_bytes() + b"\nTEST ONLY: modified after the actual Ops writer")
        pc.register_artifact(root, "verification", target, "html")
    elif change == "index_stage":
        records = json.loads(index.read_text(encoding="utf-8"))
        records[str(target.resolve())]["stage"] = "release"
        index.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    else:
        index.unlink()

    assert output_errors(root, "verification", {"path": pc.stage_document_path("verification", root)})
