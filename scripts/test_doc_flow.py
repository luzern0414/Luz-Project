"""The by-document flow end to end: all twelve stages, the upgrade of stage-level approvals, the CLI, the user's summary page, and the older model alongside."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Ops" / "scripts"))

import approval_docs as ad
import client_fixture
import doc_fixture as df
import flow_steps
import project
import project_core as pc
from client_fixture import new_project
from project_crawl_gate import evidence_session
from project_core import ProjectError
from project_paths import locate
from stage_documents import write_document
from test_crawl_preflight import complete_fixture

P2 = "docs/01-需求对接/02-方案说明书.pdf"
P3 = "docs/01-需求对接/03-系统架构图.pdf"
P4 = "docs/01-需求对接/04-功能清单.xlsx"
BLANKET = "用户整体预先授权（原话：我都批准，你做完整的我看看就行），未逐件审阅，交付后由用户复核。批准对象：{}"


def cli(*argv: str) -> tuple[int, str]:
    """Run project.py main() in process; returns (exit code, stdout)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = project.main([str(a) for a in argv])
        except SystemExit as exit_:                                                    # argparse refuses an unknown choice or a missing argument
            code = int(exit_.code or 0)
    return code, out.getvalue() + err.getvalue()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FullRehearsalTests(unittest.TestCase):
    """Twelve real routing stages with OFFLINE business/research/approval fixtures and actual UI-source audits."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.root = new_project("全流程", cls._tmp.name, model="document")
        cls.seen: dict[str, object] = {}
        for stage in ad.stage_order():
            df.drive(cls.root, stage, cls.tmp)
            if stage == "architecture":                                              # before the user has seen anything of it
                cls.seen["architecture_next"] = flow_steps.next_report(cls.root)
            df.approve_all(cls.root, stage)
            if stage == "release":
                ctx = ad.Ctx(cls.root)
                cls.seen["release_docs_done"] = ad.stage_docs_done(ctx, "release", allow_pre=False)
                cls.seen["release_complete_before_action"] = ad.stage_complete(ctx, "release")
                cls.seen["gate_operations_before_action"] = pc.gate_stage(cls.root, "operations")
                cls.seen["next_before_action"] = flow_steps.next_report(cls.root)
            df.finish(cls.root, stage, cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_stage_completes_and_the_project_is_valid_and_done(self) -> None:
        manifest = pc.load_project(self.root)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual([s["status"] for s in manifest["stages"]][:-1], ["approved"] * 11)
        self.assertEqual(manifest["stages"][-1]["status"], "completed")
        self.assertEqual(pc.validate_project(self.root, strict=True), [])
        self.assertEqual(flow_steps.next_report(self.root)["kind"], "done")

    def test_every_file_of_docs_has_its_own_user_record_and_no_stage_has_one_for_all(self) -> None:
        ledger = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]
        docs = [d["path"] for d in ad.all_documents(self.root)]
        per_file = [r["document"] for r in ledger if r.get("scope") == "document" and r["status"] == "approved"]
        self.assertEqual(per_file, docs, "one record per file, in the global order")
        self.assertTrue(all(r["mode"] == "user" for r in ledger if r.get("scope") == "document"))
        self.assertEqual([r["stage"] for r in ledger if r.get("scope") == "stage"], ["requirements", "research"], "the stages without a file complete by themselves")
        self.assertEqual([r["action"] for r in ledger if r.get("scope") == "action"], ["production-release", "final-acceptance"])
        self.assertFalse([r for r in ledger if r.get("scope") is None], "no stage-level user approval was written")
        for index, record in enumerate(r for r in ledger if r.get("scope") == "document"):
            self.assertEqual(set(record["upstream"]), set(docs[:index]), "each record rests on every file before it")

    def test_the_documents_are_approved_in_the_order_the_matrix_gives(self) -> None:
        names = [Path(d["path"]).name for d in ad.all_documents(self.root)]
        self.assertEqual(names[:5], ["02-方案说明书.pdf", "03-系统架构图.pdf", "04-功能清单.xlsx", "05-业务逻辑确认表.xlsx", "01-系统架构.html"])
        self.assertLess(names.index("02-前端界面设计.html"), names.index("05-后端设计规范.html"))
        self.assertEqual(names[-3:], ["01-使用说明.pdf", "02-验收清单.xlsx", "03-需求变更台账-交付快照.xlsx"])

    def test_the_action_gate_is_not_a_file_and_still_needs_the_user(self) -> None:
        self.assertTrue(self.seen["release_docs_done"])
        self.assertFalse(self.seen["release_complete_before_action"], "the release files alone do not complete the stage")
        self.assertTrue(any("production-release" in e for e in self.seen["gate_operations_before_action"]))
        report = self.seen["next_before_action"]
        self.assertEqual(report["kind"], "waiting")
        self.assertIn("production-release", report["message"])

    def test_before_the_user_sees_a_file_next_names_it_with_the_three_lines_and_the_internal_summary(self) -> None:
        report = self.seen["architecture_next"]
        self.assertEqual(report["kind"], "present")
        self.assertEqual(report["document"]["path"], "docs/02-产品开发/01-系统架构.html")
        self.assertEqual(len(report["report"]), 3)
        self.assertTrue(report["report"][0].startswith("文件：") and report["report"][1].startswith("是什么：") and report["report"][2].startswith("怎么看："))
        self.assertEqual(report["internal"]["open"], [])
        self.assertEqual(report["queue"][0]["document"], "docs/02-产品开发/03-小程序原型.html")

    def test_changing_an_early_file_afterwards_voids_the_files_after_it_and_reopens_the_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.root, tmp)
            target = locate(root, "docs/02-产品开发/01-系统架构.html")
            target.write_text(target.read_text(encoding="utf-8") + "<!-- 改 -->", encoding="utf-8")
            pc.register_artifact(root, "architecture", target, "html")
            states = {d["path"]: ad.document_status(ad.Ctx(root), d)["state"] for d in ad.all_documents(root)}
            self.assertEqual(states["docs/02-产品开发/01-系统架构.html"], "ready")
            later = [p for p, st in states.items() if p > "docs/02-产品开发/01-系统架构.html" and "docs/02-产品开发/0" in p]
            self.assertTrue(all(states[p] in {"voided", "approved"} for p in later))
            self.assertEqual(states["docs/02-产品开发/05-后端设计规范.html"], "voided")
            self.assertEqual(states["docs/01-需求对接/02-方案说明书.pdf"], "approved", "the files before it keep their approval")
            manifest = pc.load_project(root)
            self.assertEqual(manifest["current_stage"], "architecture")
            self.assertNotEqual(pc._stage_record(manifest, "design")["status"], "approved")
            self.assertEqual(flow_steps.next_report(root)["document"]["path"], "docs/02-产品开发/01-系统架构.html")


class GenerationOrderTests(unittest.TestCase):
    def test_a_stage_cannot_be_generated_before_the_stage_in_front_of_it_is_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("次序", tmp, model="document")
            for stage in ("requirements", "research", "proposal"):
                df.run_stage(root, stage, Path(tmp))
            df.drive(root, "client-intake", Path(tmp))                                   # built, but the user has not approved the form yet
            import dev_fixture

            complete_fixture(evidence_session(root), "luz-system", "architecture")
            with self.assertRaises(ProjectError) as error:
                write_document(root, "architecture", dev_fixture.sample_spec("architecture", root))
            self.assertIn("upstream", str(error.exception))
            self.assertIn("05-业务逻辑确认表.xlsx", str(error.exception), "the error names the file that has not passed")
            df.approve_all(root, "client-intake")
            with self.assertRaises(ProjectError) as error:                               # the file is through, the client's answer is not
                write_document(root, "architecture", dev_fixture.sample_spec("architecture", root))
            self.assertIn("回填", str(error.exception))
            df.finish(root, "client-intake", Path(tmp))
            with self.assertRaises(ProjectError) as error:                               # upstream is clear now, the stage's own preparation is not
                write_document(root, "architecture", dev_fixture.sample_spec("architecture", root))
            self.assertIn("rules", str(error.exception))
            self.assertNotIn("upstream", str(error.exception))


class ChangeReopensFilesTests(unittest.TestCase):
    """A client change goes through the ledger first; a confirmed one voids the approvals of the stage it touches and of every file after it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.base = new_project("变更", cls._tmp.name, model="document")
        for stage in ("requirements", "research", "proposal"):
            df.run_stage(cls.base, stage, cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_a_confirmed_change_voids_the_stage_files_and_the_gate_closes_until_they_are_through_again(self) -> None:
        import client_flow as cf

        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            self.assertEqual({d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")}, {"approved"})
            cf.add_change(root, type="修改", category="规则", title="积分抵扣比例调整", detail="100 分抵 1 元改为 50 分抵 1 元，历史订单不追溯", source="客户", requester="店长", refs=["FN-002"],
                          affects=["proposal"], impact="", status="已确认", confirmed_by="店长（微信确认）",
                          feature_ops=[{"op": "update", "feature": {"id": "FN-002", "rules": "1 元累计 1 分；50 分抵 1 元；积分 12 个月有效"}}])
            states = [d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")]
            self.assertNotIn("approved", states, "none of the stage's files keeps its approval")
            ledger = json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]
            voided = [r for r in ledger if r.get("scope") == "document" and r["status"] == "voided"]
            self.assertEqual(len(voided), 3)
            self.assertTrue(all("proposal" in r["voided_reason"] for r in voided))
            self.assertEqual(pc.load_project(root)["current_stage"], "proposal")
            self.assertTrue(any("前置审批未完成" in e for e in pc.gate_stage(root, "client-intake")))
            report = flow_steps.next_report(root)
            self.assertEqual(report["stage"], "proposal")
            self.assertNotEqual(report["kind"], "done")
            self.assertEqual(ad.stage_record_effective(ad.Ctx(root), "requirements"), True, "the stages before the changed one keep their approval")

    def test_a_pending_change_blocks_the_files_of_the_stage_it_names(self) -> None:
        import client_flow as cf

        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            cf.add_change(root, type="补充", category="规则", title="核销超时", detail="核销超时为预约结束后 30 分钟", source="客户", requester="店长", refs=["FN-005"], affects=["client-intake"],
                          impact="", status="待确认")
            self.assertTrue(any("待确认的变更" in e for e in cf.stage_checks(root, "client-intake", phase="build")))


class UpgradeTests(unittest.TestCase):
    """A project of the stage-level model: requirements approved by the user, proposal under the old blanket authorization."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        root = new_project("旧批准", cls._tmp.name, model="stage")
        for stage in ("requirements", "research", "proposal"):
            client_fixture.crawled(root, stage)
            write_document(root, stage, df.review_spec(stage))
            if stage == "requirements":
                client_fixture.requirements_provided(root)
            elif stage == "proposal":
                client_fixture.write_all(root)
                import client_flow

                client_flow.build_proposal(root)
            note = BLANKET.format("方案说明书、系统架构图、功能清单") if stage == "proposal" else f"用户原话：{stage} 通过"
            pc.approve_stage(root, stage, note, "演示审批人（整体预先授权，Claude 代为记录）" if stage == "proposal" else "演示审批人")
        cls.base = root

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def setUp(self) -> None:
        self._copy = tempfile.TemporaryDirectory()
        self.addCleanup(self._copy.cleanup)
        self.root = df.clone(self.base, self._copy.name)

    def test_the_preview_writes_nothing_and_says_what_each_file_becomes(self) -> None:
        before = {p: sha(p) for p in (self.root / "APPROVALS.json", self.root / "project.json")}
        result = ad.approvals_upgrade(self.root)
        self.assertFalse(result["applied"])
        self.assertEqual({p: sha(p) for p in before}, before)
        self.assertFalse((self.root / "backup").exists())
        by_doc = {row["document"]: row for row in result["plan"]}
        for path in (P2, P3, P4):
            self.assertEqual((by_doc[path]["mode"], by_doc[path]["result"]), ("pre-authorized", "待用户复核（预先授权）"))
        self.assertEqual(by_doc[None]["mode"] if None in by_doc else "internal", "internal")
        self.assertEqual(result["pre_authorized"], [P2, P3, P4])
        self.assertEqual(result["unmapped"], [])
        self.assertFalse(ad.is_document_model(self.root))

    def test_apply_backs_up_splits_the_record_and_keeps_the_project_valid(self) -> None:
        old = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))
        old_proposal = next(a for a in old["approvals"] if a["stage"] == "proposal")
        artifacts_before = (self.root / "data" / "artifacts.json").read_text(encoding="utf-8")
        result = ad.approvals_upgrade(self.root, apply=True)
        self.assertTrue(result["applied"])
        backup = Path(result["backup"])
        self.assertEqual(json.loads((backup / "APPROVALS.json").read_text(encoding="utf-8")), old, "the backup is the ledger as it was")
        self.assertTrue((backup / "project.json").is_file())
        new = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))
        self.assertEqual(new["approvals"][: len(old["approvals"])], old["approvals"], "old records are kept as history")
        added = new["approvals"][len(old["approvals"]):]
        docs = [r for r in added if r["scope"] == "document"]
        self.assertEqual([r["document"] for r in docs], [P2, P3, P4])
        self.assertTrue(all(r["mode"] == "pre-authorized" and r["migrated_from"] == old_proposal["id"] and r["note"].startswith("用户整体预先授权") for r in docs))
        self.assertTrue(all(r["hash"] == pc.sha256_file(locate(self.root, r["document"])) for r in docs), "bound to the bytes that were approved")
        self.assertEqual([(r["stage"], r["mode"]) for r in added if r["scope"] == "stage"], [("requirements", "internal"), ("research", "internal")])
        self.assertEqual((self.root / "data" / "artifacts.json").read_text(encoding="utf-8"), artifacts_before, "no artifact hash changes: the downstream stays valid")
        manifest = pc.load_project(self.root)
        self.assertEqual(manifest["approval_policy"]["model"], "document")
        self.assertEqual(manifest["approval_policy"]["mode"], "user", "the upgrade never makes the project blanket")
        self.assertEqual(pc.validate_project(self.root, strict=True), [])
        self.assertEqual(pc._stage_record(manifest, "proposal")["status"], "approved")

    def test_a_second_run_changes_nothing(self) -> None:
        ad.approvals_upgrade(self.root, apply=True)
        ledger = (self.root / "APPROVALS.json").read_text(encoding="utf-8")
        again = ad.approvals_upgrade(self.root, apply=True)
        self.assertTrue(again["already_upgraded"])
        self.assertEqual((self.root / "APPROVALS.json").read_text(encoding="utf-8"), ledger)
        self.assertEqual(len(list((self.root / "backup").glob("approvals-upgrade-*"))), 1)

    def test_after_the_upgrade_the_waiting_files_come_first_and_hold_the_rest(self) -> None:
        ad.approvals_upgrade(self.root, apply=True)
        report = flow_steps.next_report(self.root)
        self.assertEqual((report["kind"], report["document"]["path"], report["document"]["state"]), ("present", P2, "pending-review"))
        self.assertEqual([q["document"] for q in report["queue"]][:2], [P3, P4])
        self.assertTrue(any("待用户复核" in e for e in pc.gate_stage(self.root, "client-intake")))
        df.write_step(self.root, "client-intake", "rules")
        df.crawl(self.root, "client-intake")
        with self.assertRaises(ProjectError) as error:
            pc.require_crawl(self.root, "client-intake")
        self.assertIn("待用户复核", str(error.exception))
        for path in (P2, P3, P4):
            ad.approve_document(self.root, "proposal", path, "用户原话：看过了，通过", "用户")
        df.note_step(self.root, "client-intake", "specialist")
        self.assertEqual(flow_steps.generation_errors(self.root, "client-intake"), [])
        self.assertEqual({d["state"] for d in ad.stage_documents_state(ad.Ctx(self.root), "proposal")}, {"approved"})

    def test_a_steps_backfill_is_marked_as_such(self) -> None:
        ad.approvals_upgrade(self.root, apply=True)
        record = ad.step_record(self.root, "proposal", "rules")
        self.assertTrue(record["backfilled"])
        rows = flow_steps.checklist(self.root, "proposal")["steps"]
        self.assertTrue(next(r for r in rows if r["id"] == "rules")["backfilled"])

    def test_a_file_that_changed_after_its_approval_gets_no_record(self) -> None:
        locate(self.root, P3).write_bytes(b"changed after approval")
        result = ad.approvals_upgrade(self.root)
        self.assertEqual(result["unmapped"], [P3])
        ad.approvals_upgrade(self.root, apply=True)
        self.assertNotEqual(ad.document_status(ad.Ctx(self.root), {"path": P3, "stage": "proposal"})["state"], "pending-review")

    def test_a_user_approval_without_the_blanket_wording_keeps_mode_user(self) -> None:
        ad.approvals_upgrade(self.root, apply=True)
        ledger = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]
        requirements = [r for r in ledger if r.get("scope") == "stage"]
        self.assertTrue(all(r["mode"] == "internal" for r in requirements))
        self.assertEqual(ad.Ctx(self.root).manifest["approval_policy"]["upgraded_from"], "stage")

    def test_a_project_of_the_old_layout_has_to_be_migrated_first(self) -> None:
        from legacy_fixture import legacy_project

        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("老布局", tmp)
            with self.assertRaises(ProjectError) as error:
                ad.approvals_upgrade(root)
            self.assertIn("migrate", str(error.exception))


class CommandLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.base = new_project("命令行", cls._tmp.name, model="document")
        df.run_stage(cls.base, "requirements", cls.tmp)
        df.run_stage(cls.base, "research", cls.tmp)
        df.drive(cls.base, "proposal", cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def setUp(self) -> None:
        self._copy = tempfile.TemporaryDirectory()
        self.addCleanup(self._copy.cleanup)
        self.root = df.clone(self.base, self._copy.name)

    def test_next_prints_the_one_file_with_the_three_lines(self) -> None:
        code, text = cli("next", self.root)
        self.assertEqual(code, 0)
        self.assertIn(f"当前待审文件：{P2}", text)
        self.assertIn("给用户的汇报", text)
        self.assertIn(P3, text, "the queue after it")
        code, raw = cli("next", self.root, "--json")
        data = json.loads(raw)
        self.assertEqual((data["kind"], data["document"]["path"], len(data["report"])), ("present", P2, 3))

    def test_approve_by_document_in_order_and_nothing_else(self) -> None:
        code, text = cli("approve", self.root, "proposal", "--doc", P3, "--note", "用户原话：通过", "--approver", "用户")
        self.assertEqual(code, 2)
        self.assertIn(P2, text)
        code, text = cli("approve", self.root, "proposal", "--doc", P2, "--approver", "用户")
        self.assertEqual(code, 2, "the user's words are required")
        code, text = cli("approve", self.root, "proposal", "--note", "整体通过", "--approver", "用户")
        self.assertEqual(code, 2)
        self.assertIn("逐个", text)
        code, text = cli("approve", self.root, "proposal", "--doc", P2, "--note", "用户原话：通过", "--approver", "用户")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["mode"], "user")
        code, text = cli("next", self.root)
        self.assertIn(f"当前待审文件：{P3}", text)

    def test_review_notes_block_the_file_until_they_are_done(self) -> None:
        code, text = cli("review", self.root, "add", "--doc", P2, "--text", "功能说明太长")
        self.assertEqual(code, 0)
        note = json.loads(text)["id"]
        code, text = cli("review", self.root, "list")
        self.assertEqual(json.loads(text)[0]["status"], "open")
        code, text = cli("approve", self.root, "proposal", "--doc", P2, "--note", "用户原话：通过", "--approver", "用户")
        self.assertEqual(code, 2)
        self.assertIn(note, text)
        code, text = cli("next", self.root)
        self.assertIn("功能说明太长", text)
        code, text = cli("review", self.root, "done", "--id", note)
        self.assertEqual(code, 2, "not done while the file is unchanged")
        locate(self.root, P2).write_bytes(b"revised")
        pc.register_artifact(self.root, "proposal", locate(self.root, P2), "proposal-pdf")
        code, text = cli("review", self.root, "done", "--id", note, "--resolution", "已精简")
        self.assertEqual(code, 0)

    def test_checklist_shows_every_step_with_its_state_and_the_current_command(self) -> None:
        code, text = cli("checklist", self.root, "proposal")
        self.assertEqual(code, 0)
        for step in ("upstream", "rules", "crawl", "specialist", "build", "records", "present", "decide", "record"):
            self.assertIn(step, text)
        self.assertIn("[x] upstream", text)
        self.assertIn("现在该做", text.replace("← 现在该做这一步", "现在该做"))
        code, raw = cli("checklist", self.root, "proposal", "--json")
        rows = json.loads(raw)["steps"]
        self.assertEqual([r["gate"] for r in rows if r["id"] in {"present", "record"}], ["user", "user"])
        self.assertTrue(all(r["status"] == "done" for r in rows if r["gate"] == "internal"))

    def test_step_records_need_the_steps_in_front_and_enough_words(self) -> None:
        code, text = cli("step", self.root, "client-intake", "rules", "--note", "读了规则卡并采用了其中的全部规则")
        self.assertEqual(code, 2)
        self.assertIn("upstream", text)
        code, text = cli("step", self.root, "proposal", "rules", "--note", "短")
        self.assertEqual(code, 2)
        code, text = cli("step", self.root, "proposal", "bogus", "--note", "读了规则卡并采用了其中的全部规则")
        self.assertEqual(code, 2)

    def test_the_stage_level_approval_without_files_completes_by_itself(self) -> None:
        code, text = cli("approve", self.root, "research")
        self.assertEqual(code, 0, text)

    def test_status_and_route_report_files_and_internal_gates_separately(self) -> None:
        code, text = cli("status", self.root)
        data = json.loads(text)
        self.assertEqual(data["approval_policy"], {"model": "document", "mode": "user"})
        proposal = next(s for s in data["stages"] if s["id"] == "proposal")
        self.assertEqual([d["label"] for d in proposal["documents"]], ["待审"] * 3)
        self.assertEqual(proposal["internal_gates"]["open"], [])
        self.assertEqual(data["next"], P2)
        code, text = cli("route", self.root, "proposal")
        route = json.loads(text)
        self.assertEqual(route["approval_model"], "document")
        self.assertEqual([d["path"] for d in route["documents"]], [P2, P3, P4])
        self.assertIn("reviews/03-方案评审.html", [r["path"] for r in route["internal_records"] if r.get("path")])
        self.assertEqual([s["id"] for s in route["steps"]][:3], ["upstream", "rules", "crawl"])

    def test_confirm_is_approve_by_document_without_naming_the_stage(self) -> None:
        code, text = cli("confirm", self.root, "--doc", "02-方案说明书.pdf", "--note", "用户原话：通过", "--approver", "用户")
        self.assertEqual(code, 0, text)
        self.assertEqual(json.loads(text)["document"], P2)

    def test_the_action_command_names_the_gates_the_stage_has(self) -> None:
        code, text = cli("action", self.root, "proposal", "production-release", "--note", "发", "--approver", "用户")
        self.assertEqual(code, 2)
        self.assertIn("没有动作门", text)

    def test_init_makes_a_project_that_approves_by_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import os

            out = Path(tmp) / "out"
            os.environ["LUZ_PROJECT_OUTPUT"] = str(out)
            code, text = cli("init", "新项目", "--project-dir", Path(tmp) / "work" / "021-新项目", "--output-root", out)
            self.assertEqual(code, 0, text)
            state = Path(json.loads(text)["state_root"])
            self.assertEqual(pc.load_project(state)["approval_policy"], {"model": "document", "mode": "user"})
            code, text = cli("next", state)
            self.assertIn("rules", text, "the first thing to do is the preparation, not a file")


class SummaryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.root = new_project("汇总页", cls._tmp.name, model="document")
        df.run_stage(cls.root, "requirements", cls.tmp)
        df.run_stage(cls.root, "research", cls.tmp)
        df.drive(cls.root, "proposal", cls.tmp)
        ad.approve_document(cls.root, "proposal", P2, "用户原话：通过", "用户")
        ad.review_add(cls.root, P3, "架构图少一个使用端", "用户")
        pc.render_project(cls.root)
        cls.page = pc.summary_path(cls.root).read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_top_of_the_page_is_the_one_file_waiting_and_the_files_in_order(self) -> None:
        top = self.page.split("<details>")[0]
        self.assertEqual(self.page.count("<h1>"), 1)
        self.assertLess(top.index("当前待审文件"), top.index("文件清单与状态"))
        self.assertIn(P3.replace("/", "\\"), top.split("文件清单与状态")[0], "the file waiting is named first")
        self.assertIn("架构图少一个使用端", top, "a file with an open opinion shows the opinion")
        listing = top.split("文件清单与状态")[1]
        order = [listing.index(Path(p).name) for p in (P2, P3, P4, "05-业务逻辑确认表.xlsx", "01-系统架构.html")]
        self.assertEqual(order, sorted(order))
        for label in ("已通过", "有修改意见", "待审", "待生成"):
            self.assertIn(label, top)

    def test_the_process_records_are_folded_at_the_end_and_the_top_never_names_them(self) -> None:
        self.assertEqual(self.page.count("<details>"), 1)
        self.assertIn("<summary>过程记录（无需审阅）</summary>", self.page)
        top, folded = self.page.split("<details>")
        for word in ("reviews", "评审页", "00-crawl", "Crawl", "调研", "steps.json", "规则卡"):
            self.assertNotIn(word, top, f"{word} is for the folded process records")
        self.assertIn("各阶段的内部检查", folded)
        self.assertIn("审批记录", folded)
        self.assertNotIn("<details open", self.page, "folded by default")

    def test_the_page_follows_the_reading_page_standard(self) -> None:
        design = Path(__file__).resolve().parents[2] / "Luz-Design" / "scripts" / "check_document.py"
        result = subprocess.run([sys.executable, "-X", "utf8", str(design), str(pc.summary_path(self.root))], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        import check_output_layout

        self.assertEqual(check_output_layout.check_session(pc.summary_path(self.root).parent, False)[0], [])

    def test_a_project_of_the_older_model_keeps_the_stage_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("旧模型", tmp, model="stage")
            page = pc.summary_path(root).read_text(encoding="utf-8")
            self.assertIn("阶段与审批", page)
            self.assertNotIn("当前待审文件", page)


class OlderModelStillWorksTests(unittest.TestCase):
    def test_stage_level_approval_check_and_gate_work_as_before_and_point_to_the_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("旧项目", tmp, model="stage")
            client_fixture.crawled(root, "requirements")
            client_fixture.requirements_provided(root)
            write_document(root, "requirements", df.review_spec("requirements"))
            record = pc.approve_stage(root, "requirements", "用户原话：通过", "用户")
            self.assertNotIn("scope", record, "a stage-level record is what it was")
            self.assertEqual(pc.validate_project(root, strict=True), [])
            self.assertEqual([e for e in pc.gate_stage(root, "research") if "前置审批" in e], [])
            report = flow_steps.next_report(root)
            self.assertEqual(report["kind"], "legacy")
            self.assertIn("approvals-upgrade", report["message"])
            with self.assertRaises(ProjectError) as error:
                ad.approve_document(root, "proposal", P2, "用户原话：通过", "用户")
            self.assertIn("approvals-upgrade", str(error.exception))
            code, text = cli("status", root)
            self.assertEqual(json.loads(text)["approval_policy"], {"model": "stage"})


if __name__ == "__main__":
    unittest.main()
