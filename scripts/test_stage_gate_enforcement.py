"""Negative coverage for the ordered stage gates.

These tests deliberately stop after Crawl and rules.  A formal document must
remain unwritable until the specialist has produced and checked its fact file.
"""
from __future__ import annotations

import pytest
from unittest import mock

import approval_docs
import client_data as cd
import client_fixture as fx
import client_flow
import flow_steps
from project_core import ProjectError
from project_paths import locate
from stage_documents import write_document
import dev_fixture


@pytest.mark.parametrize(
    ("stage", "draft", "expected"),
    [
        ("requirements", client_flow.requirements_draft, ("requirements.json",)),
        ("proposal", client_flow.proposal_draft, ("proposal.json", "architecture.json")),
        ("handover", client_flow.manual_draft, ("manual.json",)),
    ],
)
def test_draft_is_prepared_before_the_specialist_can_complete(tmp_path, monkeypatch, stage, draft, expected):
    """A scaffold is input to specialist work, never evidence that it is done."""
    root = fx.new_project("draft preparation", tmp_path, model="document")
    # Upstream approval mechanics have their own integration coverage.  Keep
    # the real rule-record and stage-specific Crawl gate active here.
    monkeypatch.setattr(approval_docs, "hold_errors", lambda *_args, **_kwargs: [])
    cd.save(root, fx.features(), "client", "features.json")
    flow_steps.record_step(root, stage, "rules", "已读取本阶段规则卡，采用先检索后准备资料与模板规则", "测试")
    fx.crawled(root, stage)

    draft(root)

    assert all((root / "data" / "client" / filename).is_file() for filename in expected)
    assert any("specialist" in error for error in flow_steps.generation_errors(root, stage))
    assert not list(locate(root, "docs").rglob("*.pdf"))
    assert not list(locate(root, "docs").rglob("*.xlsx"))


@pytest.mark.parametrize(
    ("stage", "draft"),
    [
        ("requirements", client_flow.requirements_draft),
        ("proposal", client_flow.proposal_draft),
        ("handover", client_flow.manual_draft),
    ],
)
def test_draft_still_requires_rules_and_its_own_crawl(tmp_path, monkeypatch, stage, draft):
    root = fx.new_project("draft blocked", tmp_path, model="document")
    monkeypatch.setattr(approval_docs, "hold_errors", lambda *_args, **_kwargs: [])
    cd.save(root, fx.features(), "client", "features.json")
    with pytest.raises(ProjectError, match="rules|crawl|Crawl"):
        draft(root)
    flow_steps.record_step(root, stage, "rules", "已读取本阶段规则卡，采用先检索后准备资料与模板规则", "测试")
    with pytest.raises(ProjectError, match="crawl|Crawl"):
        draft(root)
    assert not any((root / "data" / "client" / name).exists() for name in ("requirements.json", "proposal.json", "architecture.json", "manual.json"))


def test_generation_errors_include_the_specialist_step(tmp_path):
    root = fx.new_project("specialist gate", tmp_path, model="document")
    fx.crawled(root, "requirements")
    flow_steps.record_step(root, "requirements", "rules", "已读取需求、系统和设计规则卡并记录采用规则", "测试")
    errors = flow_steps.generation_errors(root, "requirements")
    assert any("specialist" in error for error in errors)


def test_stage_document_cannot_be_written_before_specialist_output(tmp_path):
    root = fx.new_project("specialist document gate", tmp_path, model="document")
    fx.crawled(root, "architecture")
    # The fixture supplies evidence and the template selection, but no rules
    # or specialist record.  The first missing internal step must stop output.
    with pytest.raises(ProjectError, match="内部步骤|rules|specialist"):
        write_document(root, "architecture", dev_fixture.sample_spec("architecture", root))


def test_client_document_entry_runs_generation_gate_before_writing(tmp_path, monkeypatch):
    """The client-document route cannot bypass the matrix specialist gate."""
    root = fx.new_project("client specialist gate", tmp_path, model="document")
    fx.write_all(root)
    # Keep this focused on the hand-off: the separate Crawl test owns the
    # real-browser evidence contract, while this regression proves that the
    # formal client writer consults the ordered project gate first.
    monkeypatch.setattr(client_flow, "require_crawl", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(flow_steps, "generation_errors", lambda *_args, **_kwargs: ["specialist（专家产出）: data/client/manual.json 缺失"])

    with pytest.raises(ProjectError, match="specialist|内部步骤"):
        client_flow.build_intake_form(root)

    assert not list(locate(root, "docs").rglob("*.xlsx"))


def test_change_registration_and_update_defer_formal_output_until_stage_ready(tmp_path):
    root = fx.new_project("early change registration", tmp_path, model="document")
    client_flow.set_theme(root, "fitness-gym")
    entry = client_flow.add_change(root, type="补充", category="规则", title="补充取消规则", detail="预约开始前两小时可以取消", source="客户", requester="客户", affects=["requirements"])

    assert entry["ledger_render"]["status"] == "deferred"
    assert "requirements" in entry["ledger_render"]["reason"]
    assert len(client_flow._ledger(root)["changes"]) == 1
    assert not list(locate(root, "docs").rglob("*.xlsx"))
    updated = client_flow.update_change(root, entry["id"], status="已确认", confirmed_by="客户")
    assert updated["ledger_render"]["status"] == "deferred"
    assert client_flow._ledger(root)["changes"][0]["status"] == "已确认"
    assert len(client_flow._ledger(root)["changes"]) == 1


def test_snapshot_checks_handover_before_touching_live_ledger(tmp_path, monkeypatch):
    root = fx.new_project("snapshot gate first", tmp_path, model="document")
    ledger = locate(root, "docs/01-需求对接/06-需求变更台账.xlsx")
    ledger.write_bytes(b"previous approved workbook")
    render = mock.Mock(return_value=ledger)
    monkeypatch.setattr(client_flow, "render_ledger", render)

    with pytest.raises(ProjectError, match="handover|内部步骤"):
        client_flow.snapshot_ledger(root)

    render.assert_not_called()
    assert ledger.read_bytes() == b"previous approved workbook"
    assert not locate(root, "docs/03-验收交付/03-需求变更台账-交付快照.xlsx").exists()


def test_live_ledger_uses_current_stage_crawl_and_exact_template(tmp_path, monkeypatch):
    import doc_fixture as df

    root = fx.new_project("current ledger stage", tmp_path, model="document")
    monkeypatch.setattr(approval_docs, "hold_errors", lambda *_args, **_kwargs: [])
    fx.write_all(root)
    # The requirements stage is current; proposal evidence must not stand in
    # for its own Crawl record even though this is a client workbook.
    fx.crawled(root, "proposal")
    df.write_step(root, "requirements", "rules")
    df.write_step(root, "requirements", "specialist")
    change = client_flow.add_change(root, type="补充", category="规则", title="补充取消规则", detail="预约开始前两小时可以取消", source="客户", requester="客户")
    assert change["ledger_render"]["status"] == "deferred"
    assert not locate(root, "docs/01-需求对接/06-需求变更台账.xlsx").exists()

    fx.crawled(root, "requirements")
    import template_library  # Luz-Design's scripts are on the path once the fixtures have loaded them

    target = locate(root, "docs/01-需求对接/06-需求变更台账.xlsx")
    template_library.select(root, "luz-project", "requirements", "xlsx", str(target))
    assert client_flow.render_ledger(root) == target
    template_library.require_selected(root, "luz-project", "requirements", target, "xlsx", phase="post")


def test_formal_build_gate_rejects_unbound_or_changed_template_output(tmp_path, monkeypatch):
    import template_library
    from project_core import register_artifact

    root = fx.new_project("post binding", tmp_path, model="document")
    target = locate(root, "docs/01-需求对接/05-业务逻辑确认表.xlsx")
    target.write_bytes(b"TEST ONLY: offline document bytes")
    register_artifact(root, "client-intake", target, "intake-form")
    monkeypatch.setattr(client_flow, "stage_checks", lambda *_args, **_kwargs: [])

    errors = flow_steps._c_build(approval_docs.Ctx(root), "client-intake", {})
    assert any("模板最终输出" in error for error in errors)
    template_library.record_output(root, "luz-project", "client-intake", target, "xlsx", generator="TEST ONLY: isolated gate fixture")
    assert flow_steps._c_build(approval_docs.Ctx(root), "client-intake", {}) == []

    target.write_bytes(b"TEST ONLY: bytes changed after the writer post-check")
    register_artifact(root, "client-intake", target, "intake-form")
    errors = flow_steps._c_build(approval_docs.Ctx(root), "client-intake", {})
    assert any("模板最终输出" in error and "哈希" in error for error in errors)
