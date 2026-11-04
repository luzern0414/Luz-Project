"""Offline rehearsal of the client-facing documents. Renders real PDF/XLSX through Luz-Design (needs Edge via Playwright)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))

import client_data as cd
import client_flow as cf
import client_fixture as fx
from client_fixture import fill_intake
from project_core import ProjectError, create_project, load_project, validate_project


class ClientFlowTests(unittest.TestCase):
    def test_features_validation_rejects_bad_data(self):
        bad = fx.features()
        bad["features"][0]["surface"] = "tv"
        bad["features"][1]["rules"] = "待补充"
        errors = cd.validate_features(bad)
        self.assertTrue(any("使用端无效" in e for e in errors))
        self.assertTrue(any("占位" in e for e in errors))

    def test_no_client_document_is_written_before_the_stage_has_crawled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("先检索", Path(tmp))
            fx.write_all(root)
            builders = {"proposal": lambda: cf.build_proposal(root), "client-intake": lambda: cf.build_intake_form(root),
                        "handover": lambda: cf.build_manual(root)}
            for stage, build in builders.items():
                with self.subTest(stage=stage):
                    with self.assertRaises(ProjectError) as refused:
                        build()
                    self.assertIn("Crawl", str(refused.exception))
            with self.assertRaises(ProjectError):
                cf.build_acceptance_xlsx(root)
            with self.assertRaises(ProjectError):
                cf.proposal_draft(root)
            self.assertEqual(list((root / "docs" / "01-需求对接").glob("*.pdf")) + list((root / "docs" / "01-需求对接").glob("*.xlsx")), [])
            fx.crawled(root, "proposal")
            self.assertTrue(cf.build_proposal(root))

    def test_there_is_a_requirements_document_before_there_is_a_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("先有需求", Path(tmp))
            fx.crawled(root, "requirements", "proposal")
            cd.save(root, fx.features(), "client", "features.json")
            cd.save(root, fx.proposal(), "client", "proposal.json")
            cd.save(root, fx.architecture(), "client", "architecture.json")
            cf.set_theme(root, "fitness-gym")
            with self.assertRaises(ProjectError) as refused:                      # no requirements document: the proposal is not written
                cf.build_proposal(root)
            self.assertIn("需求文档", str(refused.exception))
            self.assertTrue(any("没有需求文档" in e for e in cf.stage_checks(root, "requirements")))
            # a draft is written first; it has placeholders and cannot be built
            self.assertEqual(len(cf.requirements_draft(root)), 1)
            draft = cd.load(root, "client", "requirements.json")
            self.assertEqual([s["key"] for s in draft["sections"]], [k for k, _ in cd.REQUIREMENT_SECTIONS])
            self.assertEqual(draft["sections"][3]["blocks"][0], {"type": "auto", "what": "requirement_list"})       # the needs come from the feature list
            with self.assertRaises(ProjectError):
                cf.build_requirements(root)
            # the finished document is built, registered in the requirements stage and goes stale when its source changes
            cd.save(root, fx.requirements(), "client", "requirements.json")
            files = cf.build_requirements(root)
            self.assertEqual([p.name for p in files], ["01-需求说明书.pdf"])
            self.assertTrue(files[0].stat().st_size > 3000)
            self.assertEqual(cf.stage_checks(root, "requirements"), [])
            self.assertTrue(cf.build_proposal(root))
            spec = fx.requirements()
            spec["sections"][1]["blocks"] = [{"type": "text", "text": "预约转化为到店不低于 85%，前台登记耗时降低一半以上。"}]
            cd.save(root, spec, "client", "requirements.json")
            self.assertTrue(any("已过期" in e for e in cf.stage_checks(root, "requirements")))
            self.assertTrue(any("已过期" in e for e in cf.stage_checks(root, "proposal")))

    def test_the_requirements_document_needs_every_chapter_and_the_client_may_bring_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("需求章节", Path(tmp))
            fx.crawled(root, "requirements")
            cd.save(root, fx.features(), "client", "features.json")
            cf.set_theme(root, "fitness-gym")
            spec = fx.requirements()
            spec["sections"] = [s for s in spec["sections"] if s["key"] not in {"rules", "acceptance"}]
            cd.save(root, spec, "client", "requirements.json")
            with self.assertRaises(ProjectError) as refused:
                cf.build_requirements(root)
            self.assertIn("业务规则与约束", str(refused.exception))
            self.assertIn("验收标准", str(refused.exception))
            fx.requirements_provided(root)                                         # the client's own document is registered instead
            self.assertEqual(cf.requirements_errors(root), [])
            with self.assertRaises(ProjectError):
                cf.build_requirements(root)
            cd.save(root, {"client_document": {"file": "docs/01-需求对接/客户需求.docx", "note": "放错了地方"}}, "client", "requirements.json")
            self.assertTrue(any("raw/uploads" in e for e in cf.requirements_errors(root)))
            cd.save(root, {"client_document": {"file": "raw/uploads/没有这个文件.docx", "note": "文件不存在"}}, "client", "requirements.json")
            self.assertTrue(any("不存在" in e for e in cf.requirements_errors(root)))

    def test_proposal_requires_real_content_and_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("方案", Path(tmp))
            fx.crawled(root, "proposal")
            cd.save(root, fx.features(), "client", "features.json")
            with self.assertRaises(ProjectError):
                cf.build_proposal(root)
            cf.proposal_draft(root)
            self.assertTrue(any("待补充" in e or "占位" in e for e in cd.validate_proposal(cd.load(root, "client", "proposal.json"), "b2b-graphite")))
            with self.assertRaises(ProjectError):
                cf.set_theme(root, "no-such-theme")

    def test_full_client_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("示例健身", Path(tmp))
            fx.write_all(root)
            fx.crawled(root, "proposal", "client-intake", "handover")
            # proposal: three PDFs in 01-需求对接, registered, built once and reused while sources are unchanged
            files = cf.build_proposal(root)
            self.assertEqual(sorted(p.name for p in files), sorted(["02-方案说明书.pdf", "03-系统架构图.pdf", "04-功能清单.xlsx"]))
            self.assertTrue(all(p.parent.name == "01-需求对接" and p.stat().st_size > 3000 for p in files))
            before = [p.read_bytes() for p in files]
            cf.build_proposal(root)
            self.assertEqual(before, [p.read_bytes() for p in files])
            self.assertEqual(cf.stage_checks(root, "proposal"), [])
            self.assertEqual(validate_project(root, strict=True), [])
            # intake form -> client fills -> import
            form = cf.build_intake_form(root)
            self.assertEqual(form.name, "05-业务逻辑确认表.xlsx")
            status = cf.intake_status(root)
            self.assertTrue(status["missing_required"])
            filled = fill_intake(form, root)
            result = cf.import_intake(root, filled)
            self.assertEqual(result["missing_required"], [])
            choices = cd.load(root, "client", "intake.json")["feature_choices"]
            self.assertEqual(choices["FN-003"], "需要")
            self.assertEqual(choices["FN-009"], "不需要")
            ids = {f["id"] for f in cf.effective_features(root, cd.load_features(root))}
            self.assertIn("FN-003", ids)
            self.assertNotIn("FN-009", ids)
            self.assertNotIn("FN-008", ids)
            self.assertTrue(any(c["auto"] == "intake" for c in cf._ledger(root)["changes"]))
            self.assertEqual(cf.stage_checks(root, "client-intake"), [])
            # change ledger: a confirmed feature change updates features.json, bumps its version and re-renders the xlsx
            change = cf.add_change(root, type="修改", category="规则", title="积分抵扣比例调整", detail="100 分抵 1 元改为 50 分抵 1 元，其余规则不变", source="客户", requester="店长",
                                   refs=["FN-002"], affects=["proposal"], status="已确认", confirmed_by="店长（微信确认）",
                                   feature_ops=[{"op": "update", "feature": {"id": "FN-002", "rules": "1 元累计 1 分；50 分抵 1 元；积分 12 个月有效"}}])
            updated = next(f for f in cd.load_features(root)["features"] if f["id"] == "FN-002")
            self.assertEqual(updated["version"], 2)
            self.assertTrue((root / "docs/01-需求对接/06-需求变更台账.xlsx").is_file())
            self.assertTrue(any("已过期" in e for e in cf.stage_checks(root, "proposal")))
            with self.assertRaises(ProjectError):
                cf.add_change(root, type="修改", category="规则", title="x", detail="  ", source="客户", requester="")
            self.assertEqual(change["id"], "CHG-%03d" % int(change["id"][-3:]))

    def test_acceptance_manual_and_handover_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("交付", Path(tmp))
            fx.write_all(root)
            fx.crawled(root, "handover")
            checklist = cf.generate_acceptance(root)
            ids = [i["id"] for i in checklist["items"]]
            self.assertEqual(len(ids), len(set(ids)))
            by_feature = {}
            for i in checklist["items"]:
                by_feature.setdefault(i["feature_id"], []).append(i)
            self.assertEqual(len(by_feature["FN-009"]), 2)
            self.assertIn("rules_calc", by_feature["FN-009"][0]["evidence_checks"])
            self.assertIn("miniprogram_automation", by_feature["FN-001"][0]["evidence_checks"])
            xlsx = cf.build_acceptance_xlsx(root)
            self.assertTrue(xlsx.is_file())
            # draft manual cannot be built until placeholders are replaced
            cf.manual_draft(root)
            with self.assertRaises(ProjectError):
                cf.build_manual(root)
            spec = fx.manual({m["name"]: [f["id"] for f in cd.active_features(cd.load_features(root)) if f["module"] == m["id"]] for m in cd.load_features(root)["modules"]})
            cd.save(root, spec, "client", "manual.json")
            pdf = cf.build_manual(root)
            self.assertTrue(pdf.name == "使用说明.pdf" and pdf.parent.name == "03-验收交付")
            trace = cf.trace(root)
            self.assertEqual(trace["gaps"], [])
            cf.link_feature(root, "FN-001", arch=["M-1"], design=["P-1"], dev=[])
            self.assertEqual(next(r for r in cf.trace(root)["rows"] if r["feature"] == "FN-001")["architecture"], ["M-1"])
            # handover is blocked until every item is signed or waived with a reason, and the ledger snapshot exists
            problems = cf.stage_checks(root, "handover")
            self.assertTrue(any("验收未完成" in p for p in problems))
            self.assertTrue(any("快照" in p for p in problems))
            data = cd.load(root, "acceptance", "checklist.json")
            for item in data["items"]:
                item.update({"status": "passed", "signed_by": "验收人（测试）", "signed_at": "2026-11-02"})
            cd.save(root, data, "acceptance", "checklist.json")
            cf.add_change(root, type="补充", category="规则", title="补充核销超时说明", detail="核销超时时间为预约结束后 30 分钟", source="客户", requester="店长", status="已确认", confirmed_by="店长", reopen=False)
            self.assertTrue(any("未实施" in p for p in cf.stage_checks(root, "handover")))
            cf.update_change(root, "CHG-001", status="已实施")
            cf.snapshot_ledger(root)
            self.assertEqual(cf.stage_checks(root, "handover"), [])

    def test_signature_cannot_be_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("签字", Path(tmp))
            fx.write_all(root)
            fx.crawled(root, "handover")
            cf.generate_acceptance(root)
            xlsx = cf.build_acceptance_xlsx(root)
            from openpyxl import load_workbook

            wb = load_workbook(xlsx)
            ws = wb.active
            header = next(r for r in range(1, 8) if any(c.value == "验收项编号" for c in ws[r]))
            idx = {c.value: c.column for c in ws[header]}
            ws.cell(header + 1, idx["验收结果"]).value = "通过"
            out = xlsx.with_name("signed.xlsx")
            wb.save(out)
            with self.assertRaises(ProjectError):
                cf.import_acceptance(root, out)

    def test_pending_change_blocks_stage_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("待确认", Path(tmp))
            cf.add_change(root, type="新增", category="需求", title="新增储值功能", detail="客户希望增加储值充值，档位 200/500/1000", source="客户", requester="老板", affects=["proposal"])
            self.assertTrue(any("待确认" in e for e in cf.stage_checks(root, "proposal")))


class TraceArchitectureTests(unittest.TestCase):
    """trace reads the function cards of the tabs-structured architecture spec, so a missing or wrong link is a gap and "no gaps" is true."""

    MODULE_NAMES = {"M01": "会员与积分", "M02": "预约服务", "M03": "后台管理", "M04": "智能助手"}

    def _project(self, tmp: str, *, tabs: bool = True) -> Path:
        root = create_project("追溯", Path(tmp))
        spec = fx.features()
        cd.save(root, spec, "client", "features.json")
        by_module: dict[str, list[str]] = {}
        for f in spec["features"]:
            by_module.setdefault(f["module"], []).append(f["id"])
        if tabs:
            architecture = {"title": "架构", "tabs": [
                {"title": "技术栈", "layout": "tabs", "sections": [{"title": "技术栈总览", "blocks": [{"type": "text", "text": "x"}]}]},
                {"title": "功能与技术方案", "layout": "modules", "sections": [
                    {"title": self.MODULE_NAMES[m], "blocks": [{"type": "text", "text": "模块说明"}] + [{"type": "function", "id": i, "name": i, "module": self.MODULE_NAMES[m]} for i in ids]}
                    for m, ids in by_module.items()]}]}
        else:
            architecture = {"logic": {"modules": [{"id": m} for m in by_module]}}
        (root / "data" / "stages").mkdir(parents=True, exist_ok=True)
        (root / "data" / "stages" / "architecture.json").write_text(json.dumps(architecture, ensure_ascii=False), encoding="utf-8")
        return root

    def _link_all(self, root: Path) -> None:
        for f in fx.features()["features"]:
            cf.link_feature(root, f["id"], arch=[f["module"]], design=[], dev=[])

    def test_correct_links_have_no_architecture_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self._link_all(root)
            self.assertEqual(cf.trace(root)["gaps"], [])
            self.assertEqual(cf.architecture_cards(json.loads((root / "data/stages/architecture.json").read_text(encoding="utf-8")))["FN-005"], "预约服务")

    def test_a_feature_without_any_link_is_a_gap_where_the_old_code_said_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self.assertEqual(len([g for g in cf.trace(root)["gaps"] if "未关联架构模块" in g]), 9)       # nothing is linked yet
            self._link_all(root)
            links = cd.load(root, "client", "trace-links.json")
            links.pop("FN-005")
            cd.save(root, links, "client", "trace-links.json")
            gaps = cf.trace(root)["gaps"]
            self.assertEqual(gaps, ["FN-005 未关联架构模块（project.py link FN-005 --arch <模块ID>）"])

    def test_a_link_to_another_module_than_the_function_card_is_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self._link_all(root)
            links = cd.load(root, "client", "trace-links.json")
            links["FN-005"] = {"arch": ["M01"]}                                   # the card sits in 预约服务 (M02)
            cd.save(root, links, "client", "trace-links.json")
            gaps = cf.trace(root)["gaps"]
            self.assertEqual(len(gaps), 1)
            self.assertIn("FN-005", gaps[0])
            self.assertIn("不一致", gaps[0])
            self.assertIn("预约服务", gaps[0])
            links["FN-005"] = {"arch": ["M99"]}
            cd.save(root, links, "client", "trace-links.json")
            self.assertTrue(any("不存在的架构模块 M99" in g for g in cf.trace(root)["gaps"]))
            links["FN-005"] = {"arch": ["预约服务"]}                               # the module name is accepted as well as its number
            cd.save(root, links, "client", "trace-links.json")
            self.assertEqual(cf.trace(root)["gaps"], [])

    def test_an_in_scope_feature_without_a_function_card_is_a_gap_and_an_out_of_scope_one_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self._link_all(root)
            path = root / "data" / "stages" / "architecture.json"
            arch = json.loads(path.read_text(encoding="utf-8"))
            for section in arch["tabs"][1]["sections"]:
                section["blocks"] = [b for b in section["blocks"] if b.get("id") != "FN-007"]
            path.write_text(json.dumps(arch, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(cf.trace(root)["gaps"], ["FN-007 在系统架构里没有功能卡"])
            cd.save(root, {"feature_choices": {"FN-007": "不需要"}}, "client", "intake.json")      # the client declined it: out of scope, no gap
            self.assertEqual(cf.trace(root)["gaps"], [])

    def test_the_older_logic_modules_structure_still_works_and_no_architecture_means_no_architecture_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, tabs=False)
            self.assertEqual(len([g for g in cf.trace(root)["gaps"] if "未关联架构模块" in g]), 9)
            self._link_all(root)
            self.assertEqual(cf.trace(root)["gaps"], [])
            links = cd.load(root, "client", "trace-links.json")
            links["FN-001"] = {"arch": ["M99"]}
            cd.save(root, links, "client", "trace-links.json")
            self.assertEqual(cf.trace(root)["gaps"], ["FN-001 引用了不存在的架构模块 M99"])
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("没有架构", Path(tmp))
            cd.save(root, fx.features(), "client", "features.json")
            self.assertEqual(cf.trace(root)["gaps"], [])


def _ledger_sheet(path: Path) -> tuple[list[str], list[list]]:
    """Header names and data rows of a ledger workbook."""
    from openpyxl import load_workbook

    ws = load_workbook(path).active
    header = next(r for r in range(1, 8) if any(c.value == "变更编号" for c in ws[r]))
    names = [c.value for c in ws[header]]
    return names, [[c.value for c in ws[r]] for r in range(header + 1, ws.max_row + 1) if ws.cell(r, 1).value]


class ChangeLedgerClientViewTests(unittest.TestCase):
    """06-需求变更台账 and its delivery snapshot are client documents: internal changes, process logs and UTC dates must not reach them."""

    LEDGER = "docs/01-需求对接/06-需求变更台账.xlsx"

    def _project(self, tmp: str) -> Path:
        root = create_project("台账", Path(tmp))
        fx.write_all(root)
        return root

    def _add_mixed(self, root: Path) -> None:
        cf.add_change(root, type="修改", category="规则", title="积分抵扣比例调整", detail="100 分抵 1 元改为 50 分抵 1 元，不追溯订单", source="客户", requester="店长", refs=["FN-002"], status="已确认", confirmed_by="店长（微信确认）", reopen=False)
        cf.add_change(root, type="修改", category="技术", title="组件库选 Vant", detail="手机页改用 Vant，基线 FE-IC-08 调整", source="内部", requester="开发", status="已确认", confirmed_by="用户", reopen=False)
        cf.add_change(root, type="修改", category="界面", title="界面按新版分工重做", detail="视觉层在设计阶段重做", source="客户", requester="店长", status="已确认", confirmed_by="用户", reopen=False)
        cf.add_change(root, type="新增", category="范围", title="新增储值功能", detail="档位 200/500/1000，不可提现", source="内部", requester="老板", client_visible=True, status="已确认", confirmed_by="老板", reopen=False)

    def test_default_visibility_and_explicit_override(self):
        self.assertTrue(cf.is_client_visible({"source": "客户", "category": "规则"}))
        self.assertTrue(cf.is_client_visible({"source": "客户", "category": "范围"}))
        self.assertTrue(cf.is_client_visible({"source": "客户", "category": "需求"}))
        self.assertFalse(cf.is_client_visible({"source": "内部", "category": "规则"}))
        self.assertFalse(cf.is_client_visible({"source": "客户", "category": "技术"}))
        self.assertFalse(cf.is_client_visible({"source": "客户", "category": "界面"}))
        self.assertTrue(cf.is_client_visible({"source": "内部", "category": "技术", "client_visible": True}))
        self.assertFalse(cf.is_client_visible({"source": "客户", "category": "规则", "client_visible": False}))

    def test_the_client_ledger_and_the_delivery_snapshot_only_carry_visible_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self._add_mixed(root)
            ledger = json.loads((root / "data" / "changes.json").read_text(encoding="utf-8"))["changes"]
            self.assertEqual(len(ledger), 4)                                       # the data keeps everything
            self.assertNotIn("client_visible", ledger[0])                          # the default is not frozen into the entry
            self.assertIs(ledger[3]["client_visible"], True)
            _, rows = _ledger_sheet(root / self.LEDGER)
            self.assertEqual([r[0] for r in rows], ["CHG-001", "CHG-004"])
            text = json.dumps(rows, ensure_ascii=False, default=str)
            for leak in ("Vant", "FE-IC-08", "组件库", "视觉层"):
                self.assertNotIn(leak, text)
            for change_id in ("CHG-001", "CHG-002", "CHG-003", "CHG-004"):
                cf.update_change(root, change_id, status="已实施")
            snap = cf.snapshot_ledger(root)
            self.assertEqual([r[0] for r in _ledger_sheet(snap)[1]], ["CHG-001", "CHG-004"])

    def test_change_update_sets_and_clears_the_flag_and_rerenders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self._add_mixed(root)
            path = root / self.LEDGER
            cf.update_change(root, "CHG-002", client_visible=True, detail="手机页改用统一的移动端组件，页面与功能不变")   # status stays, the flag moves
            self.assertEqual([r[0] for r in _ledger_sheet(path)[1]], ["CHG-001", "CHG-002", "CHG-004"])
            self.assertEqual(cf._ledger(root)["changes"][1]["status"], "已确认")
            cf.update_change(root, "CHG-001", client_visible=False)
            self.assertNotIn("CHG-001", [r[0] for r in _ledger_sheet(path)[1]])
            cf.update_change(root, "CHG-001", client_visible="default")
            self.assertIn("CHG-001", [r[0] for r in _ledger_sheet(path)[1]])
            self.assertNotIn("client_visible", cf._ledger(root)["changes"][0])
            with self.assertRaises(ProjectError):
                cf.update_change(root, "CHG-001")                                  # nothing to change

    def test_the_cli_sets_the_flag(self):
        import project as cli

        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            self.assertEqual(cli.main(["change", str(root), "add", "--type", "修改", "--category", "规则", "--title", "内部口径", "--detail", "按月核算而不是按周", "--source", "内部", "--client-visible", "是"]), 0)
            self.assertEqual(cli.main(["change", str(root), "add", "--type", "新增", "--category", "需求", "--title", "客户要的功能", "--detail", "新增预约提醒，提前一天发送", "--client-visible", "否", "--note", "来自周会"]), 0)
            changes = cf._ledger(root)["changes"]
            self.assertIs(changes[0]["client_visible"], True)
            self.assertIs(changes[1]["client_visible"], False)
            self.assertIn("来自周会", changes[1]["note"])
            self.assertEqual(cli.main(["change", str(root), "update", "CHG-002", "--client-visible", "默认"]), 0)
            self.assertNotIn("client_visible", cf._ledger(root)["changes"][1])
            self.assertEqual(cli.main(["change", str(root), "update", "CHG-001", "--client-visible", "否"]), 0)
            self.assertIs(cf._ledger(root)["changes"][0]["client_visible"], False)
            self.assertEqual(cli.main(["change", str(root), "render"]), 0)

    def test_the_process_log_goes_to_note_never_into_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            cf.add_change(root, type="新增", category="范围", title="补三项提醒", detail="管理员可查看登录失败记录，保存 90 天", source="客户", requester="店长")
            detail_before = cf._ledger(root)["changes"][0]["detail"]
            cf.update_change(root, "CHG-001", status="已确认", confirmed_by="店长", note="已更新并获批（APPROVAL-016、017、018）", reopen=False)
            entry = cf._ledger(root)["changes"][0]
            self.assertEqual(entry["detail"], detail_before)
            self.assertIn("APPROVAL-016", entry["note"])
            _, rows = _ledger_sheet(root / self.LEDGER)
            self.assertNotIn("APPROVAL", json.dumps(rows, ensure_ascii=False, default=str))

    def test_process_log_lines_an_older_version_put_in_detail_do_not_reach_the_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            cf.add_change(root, type="新增", category="范围", title="补三项提醒", detail="管理员可查看登录失败记录，保存 90 天", source="客户", requester="店长", status="已确认", confirmed_by="店长", reopen=False)
            ledger = cf._ledger(root)
            ledger["changes"][0]["detail"] += "\n[2026-11-04] 用户确认变更\n[2026-11-04] 方案已更新并获批（APPROVAL-016）"
            cd.save(root, ledger, "changes.json")
            cf.render_ledger(root)
            _, rows = _ledger_sheet(root / self.LEDGER)
            self.assertEqual(rows[0][5], "管理员可查看登录失败记录，保存 90 天")

    def test_entries_the_intake_logged_with_the_old_wording_are_shown_without_the_file_name_and_module_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            old = {"date": "2026-11-03", "category": "范围", "source": "客户", "requester": "客户（业务逻辑确认表）", "affects": ["architecture"], "impact": "", "status": "已确认", "confirmed_by": None,
                   "confirmed_at": "2026-11-03T04:13:01Z", "feature_ops": [], "reopened": [], "auto": "intake"}
            cd.save(root, {"schema_version": "1.0", "changes": [
                {**old, "id": "CHG-001", "type": "新增", "title": "客户选择可选功能：会员等级", "detail": "来自业务逻辑确认表的功能勾选（M01）；功能规则：三级会员，升级即时生效", "refs": ["FN-003"]},
                {**old, "id": "CHG-002", "type": "删除", "title": "客户在业务逻辑确认表中放弃基础功能：商品与套餐管理", "detail": "来自业务逻辑确认表的功能勾选（M03）；功能规则：下架商品不出现在小程序", "refs": ["FN-006"]}]}, "changes.json")
            self.assertEqual(cf.ledger_warnings(root), [])
            cf.render_ledger(root)
            _, rows = _ledger_sheet(root / self.LEDGER)
            text = json.dumps(rows, ensure_ascii=False, default=str)
            self.assertNotIn("业务逻辑确认表", text)
            self.assertNotRegex(text, r"M\d\d")
            self.assertEqual(rows[0][5], "客户在确认业务逻辑时选择了该功能；功能规则：三级会员，升级即时生效")
            self.assertEqual(rows[1][4], "客户放弃基础功能：商品与套餐管理")
            self.assertEqual(rows[1][7], "客户")
            self.assertIn("业务逻辑确认表", cf._ledger(root)["changes"][0]["detail"])         # the data itself is not rewritten

    def test_visible_text_may_not_carry_internal_numbers_or_other_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            with self.assertRaises(ProjectError):
                cf.add_change(root, type="修改", category="规则", title="口径调整", detail="已批准架构（STK-AD-01）的口径改为按月", source="客户", requester="店长")
            with self.assertRaises(ProjectError):
                cf.add_change(root, type="修改", category="规则", title="口径调整", detail="见《业务逻辑确认表》第 3 行", source="客户", requester="店长")
            self.assertEqual(cf._ledger(root)["changes"], [])
            # the same words are fine in an internal entry, and an internal entry cannot be flipped to visible while it carries them
            cf.add_change(root, type="修改", category="技术", title="基线调整", detail="STK-AD-01 调整为自写布局", source="内部", requester="开发")
            with self.assertRaises(ProjectError):
                cf.update_change(root, "CHG-001", client_visible=True)
            self.assertEqual(cf.ledger_warnings(root), [])
            # data written by an older version is reported, not rewritten
            ledger = cf._ledger(root)
            ledger["changes"][0].update({"source": "客户", "category": "规则"})
            cd.save(root, ledger, "changes.json")
            self.assertTrue(any("CHG-001" in w for w in cf.ledger_warnings(root)))

    def test_entries_the_intake_logs_do_not_name_files_or_module_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = create_project("确认表", Path(tmp))
            fx.write_all(root)
            fx.crawled(root, "proposal", "client-intake")
            cf.build_proposal(root)
            cf.import_intake(root, fill_intake(cf.build_intake_form(root), root))
            auto = [c for c in cf._ledger(root)["changes"] if c.get("auto") == "intake"]
            self.assertTrue(auto)
            for c in auto:
                text = c["title"] + c["detail"] + c["requester"]
                self.assertNotIn("业务逻辑确认表", text)
                self.assertNotRegex(text, r"M\d\d")
                self.assertIn("业务逻辑确认表", c["note"])                          # where it came from is kept in the note
            _, rows = _ledger_sheet(root / self.LEDGER)
            self.assertNotIn("业务逻辑确认表", json.dumps(rows, ensure_ascii=False, default=str))
            before = len(cf._ledger(root)["changes"])                              # logging again does not duplicate the entries
            cf.log_choice_changes(root, cd.load(root, "client", "intake.json"))
            self.assertEqual(len(cf._ledger(root)["changes"]), before)

    def test_ledger_dates_are_beijing_dates_and_both_date_columns_are_dates(self):
        from datetime import date, datetime
        from openpyxl import load_workbook

        self.assertEqual(cf.cn_date("2026-11-03T23:15:54Z"), date(2026, 11, 4))         # 07:15 on the 4th in Beijing
        self.assertEqual(cf.cn_date("2026-11-04T15:59:59Z"), date(2026, 11, 4))
        self.assertEqual(cf.cn_date("2026-11-04T16:00:00Z"), date(2026, 11, 5))
        self.assertIsNone(cf.cn_date(None))
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            cf.add_change(root, type="修改", category="规则", title="积分抵扣比例调整", detail="100 分抵 1 元改为 50 分抵 1 元", source="客户", requester="店长", status="已确认", confirmed_by="店长", reopen=False)
            cf.add_change(root, type="新增", category="需求", title="新增储值功能", detail="档位 200/500/1000", source="客户", requester="老板")
            ledger = cf._ledger(root)
            ledger["changes"][0]["confirmed_at"] = "2026-11-03T23:15:54Z"
            cd.save(root, ledger, "changes.json")
            cf.render_ledger(root)
            names, rows = _ledger_sheet(root / self.LEDGER)
            asked, confirmed = names.index("提出日期"), names.index("确认日期")
            self.assertIsInstance(rows[0][asked], datetime)                                   # a real date cell ...
            self.assertEqual(rows[0][confirmed], datetime(2026, 11, 4))                       # ... in both columns, Beijing date
            self.assertEqual(rows[1][confirmed], "—")                                          # not confirmed yet
            ws = load_workbook(root / self.LEDGER).active
            header = next(r for r in range(1, 8) if any(c.value == "变更编号" for c in ws[r]))
            self.assertEqual(ws.cell(header + 1, asked + 1).number_format, ws.cell(header + 1, confirmed + 1).number_format)

    def test_a_ledger_with_only_internal_entries_still_renders_and_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            cf.add_change(root, type="修改", category="技术", title="组件库选 Vant", detail="手机页改用 Vant", source="内部", requester="开发", status="已确认", confirmed_by="用户", reopen=False)
            self.assertEqual(_ledger_sheet(root / self.LEDGER)[1], [])
            cf.update_change(root, "CHG-001", status="已实施")
            self.assertTrue(cf.snapshot_ledger(root).is_file())


if __name__ == "__main__":
    unittest.main()
