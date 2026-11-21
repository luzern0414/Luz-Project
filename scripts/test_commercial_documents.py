"""Regressions specific to the commercial batch renderers."""
import copy
import json
from pathlib import Path

import pytest

import commercial_documents as docs
from project_paths import ProjectError


SAMPLE = Path(__file__).resolve().parents[1] / "templates" / "商业项目批次"


def test_reader_copy_preserves_business_rules_and_field_names():
    assert docs._reader_paragraph("下面是修改后的内容：核准后发运。", "流程") == "核准后发运。"
    assert docs._reader_paragraph("我帮你删掉了旧段落，主管核准后发运。", "流程") == "主管核准后发运。"
    assert docs._reader_paragraph("备注字段由收货员填写。", "字段") == "备注字段由收货员填写。"
    assert docs._reader_paragraph("对不起。收货数量为正整数。", "字段") == "收货数量为正整数。"


def test_first_scope_preserves_business_terms_and_estimate_policy(tmp_path):
    sections = [{"title": "制造执行", "paragraphs": ["工时登记由车间主管确认。"]}]
    docs._check_scope_estimates(tmp_path, sections, ["工时登记"])
    sections[0]["paragraphs"].append("实施需要 12 人天，项目报价为 24000 元。")
    with pytest.raises(ProjectError, match="人工报价依据.*人日估算"):
        docs._check_scope_estimates(tmp_path, sections, ["工时登记"])


def test_acceptance_cells_keep_formula_columns_and_authorized_quote_sheet():
    facts = docs._read(SAMPLE / "design.json")["features"]
    for feature in facts["features"]:
        feature["hours"] = 2
    first = docs.cr.ordered_features(facts)[0]
    first.pop("acceptance")
    plan = docs.cr.feature_list_xlsx_spec(facts, "演练", "industrial", quote={"unit_price": 100},
                                          estimate={"workdays": True, "quote": True})
    listing, quotation = plan["sheets"]
    footer, previous_quote = copy.deepcopy(listing["footer"]), copy.deepcopy(quotation)
    original_columns = list(listing["columns"])
    docs._add_acceptance_criteria(plan, facts)
    assert listing["columns"][:-1] == original_columns and listing["footer"] == footer
    assert listing["rows"][0][-1] == first["rules"] and listing["columns"][-1]["name"] == "验收场景与预期"
    assert quotation == previous_quote


def test_frozen_rules_and_coverage():
    design = docs._read(SAMPLE / "design.json")
    agreed = docs._agreed_rules(design)
    assert {row[0] for row in agreed} == {f["id"] for f in design["features"]["features"]}
    assert docs._agreed_rules(design, docs._read(SAMPLE / "baseline.json")) == agreed
    changed = copy.deepcopy(design["business_rules"])
    changed[0]["decision"] = "提交后立即扣减库存"
    with pytest.raises(ProjectError, match="第二次确认"):
        docs._agreed_rules(design, {"rules": changed})
    design["business_rules"].pop()
    with pytest.raises(ProjectError, match="覆盖"):
        docs._agreed_rules(design)


def test_select_returns_real_reusable_template_receipts(tmp_path):
    state, project = tmp_path / "raw", tmp_path / "project"
    state.mkdir()
    (state / "project.json").write_text(json.dumps({"deliver_root": str(project)}), encoding="utf-8")
    uses = docs.select_templates(project, state, "scope")
    assert len(uses) == 2
    assert all(use["snapshots"] and Path(use["applies_to"]).suffix == ".pdf" for use in uses)
    assert uses == docs.select_templates(project, state, "scope")
    assert docs.output_errors(project, state, "scope")


def test_walkthrough_checks_observable_changes(tmp_path):
    record = docs._read(SAMPLE / "demo.json")
    ids = docs._demo_scope(docs._read(SAMPLE / "design.json")["features"])
    _, observed = docs._walk_demo(SAMPLE / "demo.json", record, ids)
    assert set().union(*(row["verified"] for row in observed)) == ids
    source = tmp_path / "demo.html"
    source.write_text('<p id="result">已经完成</p><button>查看</button>', encoding="utf-8")
    record = {"html": "demo.html", "journeys": [{"feature": "FN-001", "name": "完成操作", "result": "#result",
              "expected": "已经完成", "steps": [{"action": "click", "selector": "button"}]}]}
    with pytest.raises(ProjectError, match="操作前已经显示"):
        docs._walk_demo(tmp_path / "facts.json", record, ids)


def test_partial_demo_cannot_approve_an_entire_scope(tmp_path):
    (tmp_path / "test.html").write_text('<button onclick="document.querySelector(\'output\').textContent=\'已收货\'">收货</button><output></output>', encoding="utf-8")
    record = {"html": "test.html", "journeys": [{"feature": "FN-001", "name": "收货", "result": "output",
              "expected": "已收货", "steps": [{"action": "click", "selector": "button"}]}]}
    with pytest.raises(ProjectError, match="待补原型操作与查验：FN-002"):
        docs._walk_demo(tmp_path / "facts.json", record, {"FN-001", "FN-002"})


@pytest.mark.parametrize(("style", "failure"), [
    ("position:fixed;inset:0 0 0 auto;width:45vw;background:white;z-index:4", "business-or-edge-overlay"),
    ("position:fixed;inset:auto 0 0;height:50vh;background:white;z-index:4", "business-or-edge-overlay"),
    ("background:#d8f2e5", "green-interface-color"),
    ("background:white", None),
])
def test_inspect_form_before_it_disappears(tmp_path, style, failure):
    page = """<html lang="zh"><body style="background:white">
    <button id="start" onclick="this.hidden=true;entry.hidden=false">新建</button>
    <section hidden id="entry" style="STYLE"><label>货品<select><option>钢尺</option></select></label>
    <button id="save" onclick="entry.hidden=true;result.textContent='已保存'">保存</button></section>
    <output id="result"></output></body></html>""".replace("STYLE", style)
    (tmp_path / "sample.html").write_text(page, encoding="utf8")
    facts = {"html": "sample.html", "journeys": [{"name": "入库", "feature": "入库", "result": "output", "expected": "已保存",
             "steps": [{"action": "click", "selector": "#start"}, {"action": "click", "selector": "#save"}]}]}
    if failure:
        with pytest.raises(ProjectError, match=failure):
            docs._walk_demo(tmp_path / "facts.json", facts, {"入库"})
    else:
        _, rows = docs._walk_demo(tmp_path / "facts.json", facts, {"入库"})
        assert rows[0]["ui_states"] == ["打开页面", "click #start", "click #save", "结果可见"]
