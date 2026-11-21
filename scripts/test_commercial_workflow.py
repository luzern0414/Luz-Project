"""Exercise the same Project CLI and client handoff used by commercial projects.

The renderer and external Crawl validator have their own integration tests. The
package-flow fixtures below use deterministic files to exercise the ledger.
"""
import json
from pathlib import Path

import pytest

import approval_docs as ad
import client_fixture
import client_flow
import commercial_documents
import commercial_workflow as cw
import flow_steps
import project
import project_core as pc
import project_crawl_gate


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("LUZ_PROJECT_OUTPUT", str(tmp_path / "sessions"))
    assert project.main(["init", "流程测试", "--project-dir", str(tmp_path / "work/036-商业测试"),
                         "--summary", "为门店提供预约办理。"]) == 0
    return tmp_path / "sessions/036-商业测试/raw"


def test_default_init_and_existing_manifest(root, tmp_path):
    assert pc.load_project(root)["workflow"] == cw.WORKFLOW
    readme = pc.deliver_root(root) / "README.md"
    assert readme.read_text(encoding="utf-8").startswith("# 流程测试\n\n为门店提供预约办理。\n")
    assert list(pc._stage_defs(root)) == [*cw.BATCHES, "implementation", "verification", "release", "operations", "handover"]
    assert set(p.name for p in pc.locate(root, "docs").iterdir()) == {p.split("/")[1] for p in cw.FOLDERS}
    assert pc.validate_project(root, strict=True) == []
    assert flow_steps.next_report(root)["stage"] == "scope"
    assert pc.stage_context(root, "design", "luz-dev")["blockers"]
    assert pc.stage_document_path("verification", root) == cw.DEVELOPMENT + "/07-验收测试评审.html"
    assert pc.client_document_files(root)["acceptance-checklist"][1] == "13-验收清单.xlsx"
    legacy = pc.create_project("旧矩阵", tmp_path / "work/037-旧矩阵", tmp_path / "sessions", workflow="legacy")
    assert "workflow" not in pc.load_project(legacy)
    assert flow_steps.next_report(legacy)["stage"] == "requirements"
    assert not ad.action_status(root, "release", "production-release")["granted"]


def test_adopt_recognizes_existing_layout_and_preserves_source_material(tmp_path):
    for number, folder, workflow in [(1, cw.ORIGINALS, cw.WORKFLOW), (2, pc.DELIVER_MADE[0], None)]:
        deliver = tmp_path / f"{number:03d}-已有仓库"
        original = deliver / folder / "未整理.txt"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"existing source")
        result = pc.adopt_project(deliver, "仓储系统", summary="办理收货和库存查询。", output=tmp_path / "sessions")
        assert pc.load_project(result["state_root"]).get("workflow") == workflow
        assert (deliver / "README.md").read_text(encoding="utf-8").startswith("# 仓储系统\n\n办理收货和库存查询。\n")
        assert original.read_bytes() == b"existing source"
        assert result["moves"] == []


def test_next_names_an_argument_that_resolves_with_a_custom_output_root(tmp_path, monkeypatch):
    from project_paths import command_project, resolve_state_root
    monkeypatch.setenv("LUZ_PROJECT_OUTPUT", str(tmp_path / "default-output"))
    deliver = tmp_path / "repository/046-临时项目"
    state = pc.create_project("临时项目", deliver, tmp_path / "custom-output")
    assert command_project(state) == state
    assert resolve_state_root(command_project(state)) == state
    assert f'"{state}"' in flow_steps.next_report(state)["command"]
    pc.create_project("同名项目", tmp_path / "another" / deliver.name, tmp_path / "default-output")
    with pytest.raises(pc.ProjectError, match="同名会话"):
        resolve_state_root(deliver)
    assert command_project(state) == state


def test_scope_rejects_local_search_and_out_of_order_package(root):
    flow_steps.record_step(root, "scope", "rules", "测试读取范围与系统方案规则")
    assert flow_steps.next_report(root)["current_step"]["id"] == "templates"
    assert project.main(["templates", str(root), "scope"]) == 0
    assert flow_steps.next_report(root)["current_step"]["id"] == "crawl"
    evidence = project_crawl_gate.stage_record(root, pc.load_project(root), "scope")
    pc._write_json(evidence, {"research_mode": "local", "reason": "仅原件"})
    assert cw.scope_evidence_errors(root)
    assert project.main(["build", str(root), "design", "--data", "unused.json"]) == 2
    assert project.main(["approve", str(root), "scope", "--pre-authorized", "--approver", "夹具", "--note", "通过"]) == 2
    assert project.main(["approve", str(root), "scope", "--doc", cw.paths("scope")[0], "--note", "通过", "--approver", "夹具"]) == 2
    assert project.main(["approve", str(root), "scope", "--approver", "夹具", "--note", "等我看完再说"]) == 2
    assert project.main(["stage", str(root), "release", "in-progress"]) == 2
    assert project.main(["stage", str(root), "release", "pending-review"]) == 2
    assert project.main(["action", str(root), "handover", "final-acceptance", "--note", "同意", "--approver", "夹具"]) == 2


def test_scope_checks_every_external_source(root, tmp_path):
    ctx = ad.Ctx(root)
    page = "https://docs.example.org/warehouse"
    path = project_crawl_gate.stage_record(root, ctx.manifest, "scope")
    pc._write_json(path, {"findings": [{"source_id": "SRC-1", "adopted": True}],
                          "sources": [{"id": "SRC-1", "url": page}]})
    facts = tmp_path / "scope.json"
    pc._write_json(facts, {"sources": [{"reference": page + "#receipt"}, {"reference": "客户收货单"}]})
    cw.require_scope_sources(ctx, facts)
    pc._write_json(facts, {"sources": [{"reference": page}, {"reference": "https://other.example.org/shipment"}]})
    with pytest.raises(pc.ProjectError, match="逐项对应"):
        cw.require_scope_sources(ctx, facts)


@pytest.fixture
def package_facts(root, tmp_path, monkeypatch):
    monkeypatch.setattr(project_crawl_gate, "crawl_errors", lambda *a, **kw: [])
    monkeypatch.setattr(commercial_documents, "output_errors", lambda *a: [])
    # Selection order and actual template receipts are exercised separately from this ledger fixture.
    monkeypatch.setitem(flow_steps.CHECKS, "commercial-templates", lambda *_: [])
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"sources": [{"reference": "https://example.test/source"}]}), encoding="utf8")
    for stage in cw.BATCHES:
        record = project_crawl_gate.stage_record(root, pc.load_project(root), stage)
        evidence = {"research_mode": "local"}
        if stage == "scope":
            evidence = {"research_mode": "search", "steps": [{"command": "search", "search_performed": True}],
                        "task_root": str(tmp_path / "crawl"), "sources": [{"id": "S1", "url": "https://example.test/source"}],
                        "findings": [{"source_id": "S1", "adopted": True}]}
        pc._write_json(record, evidence)
        if stage == "scope":
            record.with_suffix(".html").write_text("<p>offline fixture</p>", encoding="utf8")

    def generate(deliver, state, stage, source):
        data = json.loads(Path(source).read_text(encoding="utf8"))
        if stage == "demo":
            data["journeys"] = [{"name": "夹具", "steps": [{"action": "click"}]}]
        pc._write_json(state / f"data/commercial/{stage}.json", data)
        for path in cw.paths(stage):
            if path.endswith(".xlsx"):
                from openpyxl import Workbook
                Workbook().save(deliver / path)
            else:
                (deliver / path).write_text(json.dumps(data), encoding="utf8")
        if stage == "demo":
            import hashlib
            rules = commercial_documents.UI_STATE_RULES.read_bytes()
            pc._write_json(state / commercial_documents.DEMO_WALKTHROUGH, [{"name": "夹具", "width": 1280,
                "ui_states": ["打开页面", "click", "结果可见"], "design_rules_sha256": hashlib.sha256(rules).hexdigest(),
                "html_sha256": hashlib.sha256((deliver / cw.paths(stage)[0]).read_bytes()).hexdigest()}])
        if stage == "baseline":
            for path, content in [("client/features.json", client_fixture.features()), ("client/trace-links.json", {}),
                                  ("client/architecture.json", {}), ("stages/architecture.json", {})]:
                pc._write_json(state / "data" / path, content)
    monkeypatch.setattr(commercial_documents, "build", generate)
    return facts


def build_package(root, stage, facts):
    for step in ("rules", "specialist"):
        flow_steps.record_step(root, stage, step, "离线测试夹具采用本阶段规则并核实项目资料")
    assert project.main(["build", str(root), stage, "--data", str(facts)]) == 0


def confirm(root, stage):
    return project.main(["approve", str(root), stage, "--approver", "单测审批人", "--note", "本批文件已核对，通过"])


def test_package_review_changes_and_handoff(root, package_facts):
    original = pc.locate(root, cw.ORIGINALS) / "客户手稿.txt"
    original.write_bytes(b"original")
    for stage in ("scope", "design", "demo"):
        build_package(root, stage, package_facts)
        report = flow_steps.next_report(root)
        assert (report["kind"], report["documents"]) == ("present", cw.paths(stage))
        if stage == "scope":
            note = ad.review_add(root, cw.paths(stage)[-1], "核对边界条件", "单测")
            assert confirm(root, stage) == 2
            assert flow_steps.next_report(root)["kind"] == "revise"
            ad.review_done(root, note["id"], "客户已核对并撤回意见", unchanged=True)
        assert confirm(root, stage) == 0
    assert [r["scope"] for r in pc._load_approvals(root)["approvals"]] == ["batch"] * 3
    assert flow_steps.next_report(root)["stage"] == "baseline"
    build_package(root, "baseline", package_facts)
    assert flow_steps.next_report(root)["stage"] == "implementation"
    ctx = pc.stage_context(root, "implementation", "luz-dev")
    assert {a["path"] for a in ctx["inputs"]} == {p for stage in cw.BATCHES for p in cw.paths(stage)}
    assert [a["stage"] for a in ctx["approved_facts"]] == list(cw.BATCHES)
    assert [r["mode"] for r in pc._load_approvals(root)["approvals"]] == ["user", "user", "user", "internal"]
    link_file = root / "data/client/trace-links.json"
    pc._write_json(link_file, {"FN-001": {"arch": ["M1"], "dev": ["test-file"]}})
    assert cw.build_errors(ad.Ctx(root), "baseline")
    pc._write_json(link_file, {})
    (original.parent / "后续验收材料.txt").write_bytes(b"later acceptance material")
    assert not cw.version_errors(ad.Ctx(root), "scope")
    original.write_bytes(b"changed original")
    assert flow_steps.next_report(root)["stage"] == "scope"
    assert not pc.stage_context(root, "implementation", "luz-dev")["inputs"]
    assert pc.validate_project(root, strict=True)


def test_ui_approval_binds_walkthrough_and_rules_edition(root, package_facts, tmp_path, monkeypatch):
    rules = tmp_path / "rules.js"
    rules.write_text("() => []", encoding="utf8")
    monkeypatch.setattr(commercial_documents, "UI_STATE_RULES", rules)
    for stage in ("scope", "design"):
        build_package(root, stage, package_facts)
        assert confirm(root, stage) == 0
    build_package(root, "demo", package_facts)
    rules.write_text("() => [] /* v2 */", encoding="utf8")
    assert confirm(root, "demo") == 2
    rules.write_text("() => []", encoding="utf8")
    assert confirm(root, "demo") == 0
    rules.write_text("() => [] /* v2 */", encoding="utf8")
    assert not cw.version_errors(ad.Ctx(root), "demo")
    (root / commercial_documents.DEMO_WALKTHROUGH).write_text("[]", encoding="utf8")
    assert cw.version_errors(ad.Ctx(root), "demo")


def test_new_research_task_requires_a_confirmed_scope_reopening(root, package_facts, tmp_path):
    build_package(root, "scope", package_facts)
    assert confirm(root, "scope") == 0
    previous = pc.load_project(root)["crawl"]["task_root"]
    record_path = project_crawl_gate.stage_record(root, pc.load_project(root), "scope")
    record = pc._read_json(record_path)
    record["task_root"] = str(tmp_path / "新范围的调研")
    pc._write_json(record_path, record)
    with pytest.raises(pc.ProjectError, match="复用"):
        pc._register_evidence(root, "scope")
    # Restore the approved version before the change so the change reopens a real, previously valid decision.
    record["task_root"] = previous
    pc._write_json(record_path, record)
    change = client_flow.add_change(root, type="修改", category="范围", title="增加入库业务", detail="新增收货和上架单据并读取库位库存",
                                    source="客户", requester="测试", affects=["scope"], status="已确认", confirmed_by="测试")
    record["task_root"] = str(tmp_path / "新范围的调研")
    pc._write_json(record_path, record)
    pc._register_evidence(root, "scope")
    trail = pc.load_project(root)["crawl"]["task_history"]
    assert trail[-1]["previous_task"] == previous and trail[-1]["change"] == change["id"]
    assert pc.load_project(root)["crawl"]["task_root"] == record["task_root"]
    record["task_root"] = str(tmp_path / "另一项任务")
    pc._write_json(record_path, record)
    with pytest.raises(pc.ProjectError, match="复用"):
        pc._register_evidence(root, "scope")


def test_confirmed_change_requires_a_new_build(root, package_facts):
    build_package(root, "scope", package_facts)
    assert confirm(root, "scope") == 0
    build_package(root, "design", package_facts)
    assert confirm(root, "design") == 0
    entry = client_flow.add_change(root, type="修改", category="规则", title="更新订单处理条件",
                                   detail="订单完成后由主管确认退款金额并发送给财务", source="客户", requester="测试",
                                   affects=["scope"], status="已确认", confirmed_by="测试")
    assert entry["reopened"]
    assert all(r["status"] == "voided" for r in pc._load_approvals(root)["approvals"])
    assert confirm(root, "scope") == 2
    assert project.main(["build", str(root), "scope", "--data", str(package_facts)]) == 0
    assert confirm(root, "scope") == 0
    assert confirm(root, "design") == 2


def test_concurrent_review_build_lock(root):
    with cw.write_lock(root):
        assert project.main(["approve", str(root), "scope", "--note", "通过", "--approver", "测试"]) == 2
    assert not pc._load_approvals(root)["approvals"]


def test_baseline_binds_estimate_permission_and_supplied_quote_file(root, tmp_path):
    import client_estimate

    before = cw._source_hashes(ad.Ctx(root), "baseline")
    assert client_flow.ESTIMATE_SOURCE in before and client_flow.QUOTE_SOURCE not in before
    client_fixture.switch_on(root, quote=True)
    source = tmp_path / "人工提供的原始报价单.json"
    pc._write_json(source, {"unit_price": 900})
    result = client_estimate.write_quote(root, from_file=source, provided_by="测试报价人")
    rel = result["quote"]["evidence_file"]
    assert rel.startswith(cw.ORIGINALS + "/")
    bound = cw._source_hashes(ad.Ctx(root), "baseline")
    assert bound[client_flow.ESTIMATE_SOURCE] != before[client_flow.ESTIMATE_SOURCE]
    assert bound[client_flow.QUOTE_SOURCE] and bound[rel] == pc.sha256_file(source)
    pc._write_json(pc.locate(root, rel), {"unit_price": 1000})
    assert cw._source_hashes(ad.Ctx(root), "baseline")[rel] != bound[rel]


def test_final_action_binds_real_checklist_results(root, tmp_path, monkeypatch):
    """Isolate final sign-off after upstream document gates, exercised separately above."""
    from openpyxl import Workbook
    monkeypatch.setattr(ad, "hold_errors", lambda *a, **kw: [])
    monkeypatch.setattr(ad, "stage_docs_done", lambda *a, **kw: True)
    monkeypatch.setattr(flow_steps, "internal_errors", lambda *a, **kw: [])
    monkeypatch.setattr(ad, "refresh", lambda *a, **kw: None)
    pc._write_json(root / "data/client/features.json", client_fixture.features())
    data = root / "data/acceptance/checklist.json"
    pc._write_json(data, {"items": [{"id": "ACC-001", "status": "pending"}]})
    for doc in ad.documents(root, "handover"):
        pc.locate(root, doc["path"]).write_bytes(b"approved fixture")
    with pytest.raises(pc.ProjectError, match="签收"):
        ad.record_action(root, "handover", "final-acceptance", "确认最终验收", "测试人")
    signed = tmp_path / "签收.xlsx"
    workbook = Workbook()
    workbook.active.append(["验收项编号", "验收结果", "客户签字", "签字日期", "备注"])
    workbook.active.append(["ACC-001", "通过", "测试签字人", "2026-11-20", "测试记录"])
    workbook.save(signed)
    client_flow.import_acceptance(root, signed)
    ad.record_action(root, "handover", "final-acceptance", "确认最终验收", "测试人")
    assert ad.action_granted(root, "handover", "final-acceptance")[0]
    changed = pc._read_json(data)
    changed["items"][0]["signed_by"] = "其他用户"
    pc._write_json(data, changed)
    assert not ad.action_granted(root, "handover", "final-acceptance")[0]


def test_historical_template_uses_exact_batch_decision(root, package_facts, tmp_path, monkeypatch):
    import project_template_history as history
    from test_historical_template_binding import drift

    build_package(root, "scope", package_facts)
    target = pc.locate(root, cw.paths("scope")[0])
    record = {"id": "docx-paginated",
              "output": {"path": str(target.resolve()), "sha256": pc.sha256_file(target),
                         "generator": "Luz-Project/scripts/commercial_documents.py:docx-paginated"}}

    def historical():
        history.require_approved_output(root, "luz-project", "scope", target, record)

    with pytest.raises(ValueError, match="原批准"):
        historical()
    library = commercial_documents._design()
    library.select(root, "luz-project", "scope", record["id"], str(target))
    library.record_output(root, "luz-project", "scope", target, record["id"], generator=record["output"]["generator"])
    assert confirm(root, "scope") == 0
    historical()
    drift(tmp_path, monkeypatch, file="scripts/make_docx_paginated.py")
    assert library.require_selected(root, "luz-project", "scope", target, record["id"], phase="post")
    with pytest.raises(ValueError):
        library.require_selected(root, "luz-project", "scope", target, record["id"], phase="pre")
    evidence = project_crawl_gate.stage_record(root, pc.load_project(root), "scope").with_suffix(".html")
    history.require_approved_output(root, "luz-system", "scope", evidence,
                                    {"id": "reading-html", "output": {"path": str(evidence), "sha256": pc.sha256_file(evidence),
                                     "generator": "Luz-Crawl/scripts/crawl_preflight.py:render_report"}})
    other = pc.locate(root, cw.paths("scope")[1])
    other.write_bytes(b"edited sibling")
    with pytest.raises(ValueError, match="原批准"):
        historical()
    with pytest.raises(ValueError):
        library.require_selected(root, "luz-project", "scope", target, record["id"], phase="post")
