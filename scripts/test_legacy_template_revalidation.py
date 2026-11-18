"""The retained stage-level approval route also checks final template bytes."""
from __future__ import annotations

import pytest

import client_data as cd
import client_fixture as fx
import client_flow
import doc_fixture
import project_core as pc
from project_core import ProjectError
from project_template_gate import output_errors
from stage_documents import write_document


def test_stage_level_approval_rejects_a_reregistered_document_with_a_stale_post_hash(tmp_path):
    root = fx.new_project("legacy post binding", tmp_path, model="stage")
    fx.crawled(root, "requirements")
    cd.save(root, fx.features(), "client", "features.json")
    cd.save(root, fx.requirements(), "client", "requirements.json")
    client_flow.set_theme(root, "fitness-gym")
    import template_library

    relative = "docs/01-需求对接/01-需求说明书.pdf"
    template_library.select(root, "luz-project", "requirements", "showcase", relative)
    target = client_flow.build_requirements(root)[0]
    write_document(root, "requirements", doc_fixture.review_spec("requirements"))
    assert pc.gate_stage(root, "requirements") == []
    assert output_errors(root, "requirements", {"path": relative}) == []

    original = target.read_bytes()
    target.write_bytes(original + b"\nTEST ONLY: modified after the real writer post-check")
    pc.register_artifact(root, "requirements", target, "requirements-pdf")
    assert output_errors(root, "requirements", {"path": relative})
    assert any("模板" in error for error in pc.gate_stage(root, "requirements"))
    with pytest.raises(ProjectError, match="模板"):
        pc.approve_stage(root, "requirements", "TEST ONLY: synthetic stage approval", "TEST FIXTURE")
    assert pc.load_project(root)["current_stage"] == "requirements"

    target.write_bytes(original)
    pc.register_artifact(root, "requirements", target, "requirements-pdf")
    assert pc.gate_stage(root, "requirements") == []
    approval = pc.approve_stage(root, "requirements", "TEST ONLY: original writer output restored", "TEST FIXTURE")
    assert approval["stage"] == "requirements"
    assert pc.load_project(root)["current_stage"] == "research"
