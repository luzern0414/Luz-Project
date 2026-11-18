"""Approval by document: the user approves the files in docs/, one at a time, in order; everything else is an internal gate that cannot be skipped.

The mechanics tests (DocumentRecordTests) switch the internal steps off on purpose to test what a record binds; the gate tests (InternalGateTests, FullRehearsalTests) use
the real steps. All approvals here are synthetic and say TEST ONLY."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Ops" / "scripts"))

import approval_docs as ad
import client_fixture
import client_flow as cf
import doc_fixture as df
import flow_steps
import project_core as pc
from client_fixture import new_project
from project_core import ProjectError
from project_paths import locate

P2 = "docs/01-需求对接/02-方案说明书.pdf"
P3 = "docs/01-需求对接/03-系统架构图.pdf"
P4 = "docs/01-需求对接/04-功能清单.xlsx"
P5 = "docs/01-需求对接/05-业务逻辑确认表.xlsx"


def gates_off():
    """Switch the internal steps off (a test of the record mechanics, not of the gates)."""
    return mock.patch.object(flow_steps, "internal_errors", return_value=[])


def mech_project(tmp: str) -> Path:
    """A project by document in which requirements and research are complete and proposal has its three files (placeholders) and its Crawl fixture."""
    root = new_project("机制", tmp, model="document")
    client_fixture.requirements_provided(root)
    df.internal_complete(root, "requirements")
    df.internal_complete(root, "research")
    df.crawl(root, "proposal")
    df.files_for(root, "proposal")
    return root


def status(root: Path, path: str) -> dict:
    ctx = ad.Ctx(root)
    return ad.document_status(ctx, next(d for d in ctx.docs if d["path"] == path))


def rewrite(root: Path, path: str, text: str) -> None:
    locate(root, path).write_bytes(text.encode("utf-8"))
    stage = next(d["stage"] for d in ad.all_documents(root) if d["path"] == path)
    pc.register_artifact(root, stage, locate(root, path), "x")


class MatrixTests(unittest.TestCase):
    def test_every_stage_declares_documents_internal_records_and_an_ordered_path(self) -> None:
        matrix = pc.load_matrix()
        self.assertEqual(matrix["approval_unit"], "document")
        known = set(flow_steps.CHECKS)
        for stage in matrix["stages"]:
            sid = stage["id"]
            ids = [s["id"] for s in stage["steps"]]
            self.assertEqual(len(ids), len(set(ids)), sid)
            self.assertEqual(ids[:3], ["upstream", "rules", "crawl"], f"{sid}: the first three steps are the preparation every stage needs")
            self.assertIn("specialist", ids)
            self.assertIn("records", ids)
            for step in stage["steps"]:
                self.assertIn(step["check"], known, f"{sid}.{step['id']}")
                self.assertIn(step["gate"], {"internal", "user", "client", "action"})
                self.assertIn(step["phase"], {"prepare", "produce", "review", "complete"})
                self.assertTrue(step["proof"].strip() and step["command"].strip() and step["skill"].startswith("luz-"), f"{sid}.{step['id']} 要写判据、命令和负责技能")
            phases = [s["phase"] for s in stage["steps"]]
            order = {"prepare": 0, "produce": 1, "review": 2, "complete": 3}
            self.assertEqual(phases, sorted(phases, key=order.get), f"{sid}: steps run in the order prepare, produce, review, complete")
            if any(d.get("path") or d.get("dynamic") for d in stage["documents"] if not d.get("living") and not d.get("client_input")):
                self.assertTrue({"build", "present", "decide", "record"} <= set(ids), sid)
            else:
                self.assertIn("auto", ids, f"{sid} has no file for the user: it completes by itself")
            for action in stage.get("action_gates", []):
                self.assertIn(f"action-{action['id']}", ids)
            for record in stage["internal_records"]:
                self.assertIn(record["kind"], {"review-page", "stage-spec", "frontend-spec-bundle", "crawl-record"})

    def test_deliverables_and_documents_plus_internal_records_say_the_same(self) -> None:
        for stage in pc.load_matrix()["stages"]:
            listed = {d["path"] for d in stage["deliverables"]}
            declared = {d["path"] for d in stage["documents"] if d.get("path")} | {r["path"] for r in stage["internal_records"] if r.get("path") and r["kind"] == "review-page"}
            prototypes = {d["path"] for d in stage["deliverables"] if d.get("kind") == "prototype"}
            self.assertEqual(listed - prototypes - {d["path"] for d in stage["documents"] if d.get("path")} - {r["path"] for r in stage["internal_records"] if r.get("path")}, set(), stage["id"])
            self.assertTrue((declared - listed) <= {"docs/01-需求对接/06-需求变更台账.xlsx"}, f"{stage['id']}: documents/internal_records name files the deliverables do not: {declared - listed}")

    def test_the_global_order_puts_the_prototypes_before_the_design_document_that_embeds_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("顺序", tmp, model="document")
            order = [Path(d["path"]).name for d in ad.all_documents(root)]
            self.assertEqual(order[:4], ["01-需求说明书.pdf", "02-方案说明书.pdf", "03-系统架构图.pdf", "04-功能清单.xlsx"])
            design = [n for n in order if n.startswith(("02-前端", "03-", "04-后台"))]
            self.assertLess(order.index("03-小程序原型.html"), order.index("02-前端界面设计.html"))
            self.assertLess(order.index("04-后台原型.html"), order.index("02-前端界面设计.html"))
            self.assertEqual(order.index("04-后台原型.html"), order.index("03-小程序原型.html") + 1, design)
            self.assertNotIn("06-需求变更台账.xlsx", order, "the living change ledger is not approved on its own")
            self.assertNotIn("05-业务逻辑确认表-回填.xlsx", order, "the client's filled-in form is an input, not a file for the user")

    def test_a_client_who_brings_a_requirements_document_leaves_the_stage_without_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("自带需求", tmp, model="document")
            self.assertIn("docs/01-需求对接/01-需求说明书.pdf", [d["path"] for d in ad.documents(root, "requirements")])
            client_fixture.requirements_provided(root)
            self.assertEqual(ad.documents(root, "requirements"), [])
            self.assertIn("auto", [s["id"] for s in flow_steps.steps_of(root, "requirements")])

    def test_a_new_project_approves_by_document_and_never_by_blanket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("默认", tmp, model="document")
            self.assertEqual(pc.load_project(root)["approval_policy"], {"model": "document", "mode": "user"})
            older = new_project("旧模型", tmp + "/x", model="stage")
            self.assertNotIn("approval_policy", pc.load_project(older))


class DocumentRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = mech_project(self._tmp.name)
        patch = gates_off()
        patch.start()
        self.addCleanup(patch.stop)

    def approve(self, path: str, note: str = "用户原话：通过", approver: str = "用户") -> dict:
        return ad.approve_document(self.root, "proposal", path, note, approver)

    def test_a_record_binds_the_files_hash_its_sources_and_the_files_before_it(self) -> None:
        first = self.approve(P2)
        self.assertEqual((first["scope"], first["mode"], first["document"], first["stage"]), ("document", "user", P2, "proposal"))
        self.assertEqual(first["hash"], pc.sha256_file(locate(self.root, P2)))
        for key in ("approver", "note", "time", "source_hashes", "upstream", "id"):
            self.assertIn(key, first)
        self.assertEqual(first["upstream"], {})
        second = self.approve(P3)
        self.assertEqual(second["upstream"], {P2: first["hash"]}, "the second file rests on the first")
        ledger = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]
        self.assertEqual([r["document"] for r in ledger if r.get("scope") == "document"], [P2, P3])

    def test_files_are_approved_in_order_one_at_a_time(self) -> None:
        with self.assertRaises(ProjectError) as error:
            self.approve(P3)
        self.assertIn(P2, str(error.exception))
        self.approve(P2)
        with self.assertRaises(ProjectError) as error:
            self.approve(P4)
        self.assertIn(P3, str(error.exception), "04 waits for 03, not only for 02")
        self.approve(P3)
        self.approve(P4)
        self.assertEqual({status(self.root, p)["state"] for p in (P2, P3, P4)}, {"approved"})

    def test_a_file_of_the_next_stage_waits_for_every_file_of_the_stage_before_it(self) -> None:
        df.crawl(self.root, "client-intake")
        df.files_for(self.root, "client-intake")
        with self.assertRaises(ProjectError) as error:
            ad.approve_document(self.root, "client-intake", P5, "用户原话：通过", "用户")
        self.assertIn(P2, str(error.exception))
        for path in (P2, P3, P4):
            self.approve(path)
        ad.approve_document(self.root, "client-intake", P5, "用户原话：通过", "用户")

    def test_an_open_note_blocks_approval_and_done_needs_a_changed_file(self) -> None:
        note = ad.review_add(self.root, P2, "第三章的业务规则数字要改", "用户")
        self.assertEqual((note["status"], note["document"]), ("open", P2))
        self.assertEqual(status(self.root, P2)["state"], "notes")
        with self.assertRaises(ProjectError) as error:
            self.approve(P2)
        self.assertIn(note["id"], str(error.exception))
        with self.assertRaises(ProjectError) as error:
            ad.review_done(self.root, note["id"], "已改")
        self.assertIn("没有变化", str(error.exception), "marking an opinion done without changing the file is refused")
        rewrite(self.root, P2, "第三章已按意见修改")
        done = ad.review_done(self.root, note["id"], "第三章数字已改为 30 分钟")
        self.assertEqual(done["status"], "done")
        self.assertEqual(status(self.root, P2)["state"], "ready")
        self.approve(P2)
        withdrawn = ad.review_add(self.root, P3, "再想想", "用户")
        with self.assertRaises(ProjectError):
            ad.review_done(self.root, withdrawn["id"], "")
        ad.review_done(self.root, withdrawn["id"], "用户撤回了意见", unchanged=True)
        self.assertEqual(ad.review_list(self.root, P3)[0]["status"], "done")

    def test_an_approved_file_takes_no_review_note_it_goes_through_the_change_ledger(self) -> None:
        self.approve(P2)
        with self.assertRaises(ProjectError) as error:
            ad.review_add(self.root, P2, "还要改", "用户")
        self.assertIn("变更台账", str(error.exception))

    def test_changing_an_approved_file_voids_it_and_every_file_after_it(self) -> None:
        for path in (P2, P3, P4):
            self.approve(path)
        self.assertTrue(ad.stage_complete(ad.Ctx(self.root), "proposal"))
        rewrite(self.root, P2, "方案说明书改过了")
        self.assertEqual(status(self.root, P2)["state"], "ready", "the changed file is simply waiting for review again")
        self.assertEqual({status(self.root, p)["state"] for p in (P3, P4)}, {"voided"}, "the files after it lose their approval")
        self.assertFalse(ad.stage_complete(ad.Ctx(self.root), "proposal"))
        self.assertTrue(any("因变更作废" in e for e in ad.hold_errors(ad.Ctx(self.root), "client-intake")))
        self.assertIn(pc._stage_record(pc.load_project(self.root), "proposal")["status"], {"pending-review", "in-progress"})
        self.approve(P2)
        self.assertEqual(status(self.root, P3)["state"], "voided", "re-approving the first file does not bring the later approvals back")
        self.approve(P3)
        self.approve(P4)
        self.assertTrue(ad.stage_complete(ad.Ctx(self.root), "proposal"))

    def test_a_confirmed_change_that_reopens_the_stage_voids_its_files_and_those_after_it(self) -> None:
        for path in (P2, P3, P4):
            self.approve(path)
        pc.set_stage_status(self.root, "proposal", "pending-review")
        self.assertEqual({status(self.root, p)["state"] for p in (P2, P3, P4)}, {"voided"})
        ledger = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]
        voided = [r for r in ledger if r.get("scope") == "document"]
        self.assertTrue(all(r["status"] == "voided" and r["voided_reason"] for r in voided), "history stays, with the reason")
        self.assertTrue(ad.stage_record_effective(ad.Ctx(self.root), "requirements"), "the stages before it keep their approval")

    def test_a_change_touching_a_stage_with_only_some_files_approved_reopens_it_too(self) -> None:
        self.approve(P2)
        self.assertTrue(cf._approved_files(self.root, "proposal"))
        self.assertFalse(cf._approved_files(self.root, "client-intake"))

    def test_the_living_ledger_and_the_clients_filled_in_form_are_not_files_for_the_user(self) -> None:
        with self.assertRaises(ProjectError) as error:
            ad.find_document(self.root, "requirements", "docs/01-需求对接/06-需求变更台账.xlsx")
        self.assertIn("活文件", str(error.exception))
        with self.assertRaises(ProjectError) as error:
            ad.find_document(self.root, "client-intake", "docs/01-需求对接/05-业务逻辑确认表-回填.xlsx")
        self.assertIn("客户的输入", str(error.exception))

    def test_stage_level_approval_is_refused_for_a_stage_with_files_and_names_them(self) -> None:
        with self.assertRaises(ProjectError) as error:
            pc.approve_stage(self.root, "proposal", "整体通过", "用户")
        text = str(error.exception)
        for path in (P2, P3, P4):
            self.assertIn(path, text)
        self.assertIn("逐个", text)

    def test_a_user_record_cannot_carry_the_wording_of_a_blanket_authorization_or_an_agent(self) -> None:
        with self.assertRaises(ProjectError):
            self.approve(P2, note="用户整体预先授权：我都批准")
        with self.assertRaises(ProjectError):
            self.approve(P2, approver="演示审批人（整体预先授权，Claude 代为记录）")
        with self.assertRaises(ProjectError):
            self.approve(P2, note="", approver="用户")

    def test_a_pre_authorization_can_only_be_recorded_in_the_blanket_mode_the_user_sets(self) -> None:
        with self.assertRaises(ProjectError) as error:
            ad.approve_document(self.root, "proposal", P2, "用户整体预先授权：我都批准，未逐件审阅", "用户", mode="pre-authorized")
        self.assertIn("blanket", str(error.exception))
        df.set_policy(self.root, mode="blanket")
        with self.assertRaises(ProjectError) as error:
            ad.approve_document(self.root, "proposal", P2, "我都批准", "用户", mode="pre-authorized")
        self.assertIn("用户整体预先授权", str(error.exception), "the wording of the note must be honest")
        record = ad.approve_document(self.root, "proposal", P2, "用户整体预先授权：我都批准，未逐件审阅", "用户", mode="pre-authorized")
        self.assertEqual(record["mode"], "pre-authorized")
        self.assertEqual(status(self.root, P2)["label"], "待复核（预先授权）")

    def test_the_summary_labels_cover_the_six_states(self) -> None:
        self.assertEqual(set(ad.STATE_LABELS.values()), {"待生成", "待审", "有修改意见", "已通过", "待复核（预先授权）", "因变更作废"})


class PreAuthorizedHoldTests(unittest.TestCase):
    """Files that stand on an old blanket authorization wait for the user's review and hold back everything new, unless the user set the blanket mode."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        base = new_project("预先授权", cls._tmp.name, model="document")
        df.run_stage(base, "requirements", cls.tmp)
        df.run_stage(base, "research", cls.tmp)
        df.drive(base, "proposal", cls.tmp)
        df.force_records(base, "proposal", mode="pre-authorized", note="用户整体预先授权（原话：我都批准），未逐件审阅")
        df.write_step(base, "client-intake", "rules")
        df.crawl(base, "client-intake")
        df.write_step(base, "client-intake", "specialist")
        cls.base = base

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def setUp(self) -> None:
        self._copy = tempfile.TemporaryDirectory()
        self.addCleanup(self._copy.cleanup)
        self.root = df.clone(self.base, self._copy.name)

    def test_the_files_stay_valid_but_are_waiting_for_review(self) -> None:
        states = {p: status(self.root, p) for p in (P2, P3, P4)}
        self.assertEqual({s["state"] for s in states.values()}, {"pending-review"})
        self.assertTrue(ad.stage_complete(ad.Ctx(self.root), "proposal"), "valid for the downstream hashes: nothing is voided")
        self.assertEqual(pc._stage_record(pc.load_project(self.root), "proposal")["status"], "approved")

    def test_a_new_stage_cannot_generate_while_a_file_waits_for_the_users_review(self) -> None:
        errors = flow_steps.generation_errors(self.root, "client-intake")
        self.assertTrue(any("待用户复核" in e and P2 in e for e in errors), errors)
        with self.assertRaises(ProjectError) as error:
            pc.require_crawl(self.root, "client-intake")
        self.assertIn("待用户复核", str(error.exception))
        with self.assertRaises(ProjectError):
            cf.build_intake_form(self.root)
        self.assertTrue(any("待用户复核" in e for e in pc.gate_stage(self.root, "client-intake")))

    def test_the_users_review_one_file_at_a_time_lifts_the_hold(self) -> None:
        for path in (P2, P3, P4):
            self.assertTrue(flow_steps.generation_errors(self.root, "client-intake"), "still held while any file waits")
            ad.approve_document(self.root, "proposal", path, "用户原话：看过了，通过", "用户")
        self.assertEqual({status(self.root, p)["state"] for p in (P2, P3, P4)}, {"approved"})
        self.assertEqual(flow_steps.generation_errors(self.root, "client-intake"), [])

    def test_a_file_changed_while_it_waited_has_to_be_reviewed_anew(self) -> None:
        rewrite(self.root, P2, "复核之前被改过")
        self.assertEqual(status(self.root, P2)["state"], "ready")
        self.assertEqual({status(self.root, p)["state"] for p in (P3, P4)}, {"voided"})

    def test_the_blanket_mode_the_user_sets_lets_new_stages_generate(self) -> None:
        self.assertTrue(flow_steps.generation_errors(self.root, "client-intake"))
        df.set_policy(self.root, mode="blanket")
        self.assertEqual(flow_steps.generation_errors(self.root, "client-intake"), [])
        self.assertFalse([e for e in pc.gate_stage(self.root, "client-intake") if "待用户复核" in e])

    def test_next_puts_the_waiting_files_first_in_order(self) -> None:
        report = flow_steps.next_report(self.root)
        self.assertEqual(report["kind"], "present")
        self.assertEqual(report["document"]["path"], P2)
        self.assertEqual(report["document"]["state"], "pending-review")
        self.assertIn("预先授权", report["why"])
        self.assertEqual([q["document"] for q in report["queue"]][:2], [P3, P4])
        self.assertEqual(len(report["report"]), 3, "what the user is told is three lines about this one file")

    def test_the_check_refuses_a_user_record_that_is_really_a_blanket_one(self) -> None:
        ledger = json.loads((self.root / "APPROVALS.json").read_text(encoding="utf-8"))
        for record in ledger["approvals"]:
            if record.get("document") == P2:
                record["mode"] = "user"
        (self.root / "APPROVALS.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        self.assertTrue(any("整体预先授权" in e for e in pc.validate_project(self.root)))


class InternalGateTests(unittest.TestCase):
    """The user's approval of a stage's files never replaces the stage's internal steps: a missing Crawl conclusion, review page, rule-card note or check stops the file
    from being shown and the stages after it from starting."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = new_project("内部门", cls._tmp.name, model="document")
        cls.tmp = Path(cls._tmp.name)
        df.run_stage(cls.root, "requirements", cls.tmp)
        df.run_stage(cls.root, "research", cls.tmp)
        df.drive(cls.root, "proposal", cls.tmp)
        cls.backup = Path(cls._tmp.name) / "backup"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def break_and_restore(self, relative: str):
        """Move a state-root file away for the duration of a test and put it back."""
        source = self.root / relative
        saved = self.backup / relative.replace("/", "_")
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, saved)
        self.addCleanup(lambda: shutil.copyfile(saved, source))
        return source

    def refused(self, step: str) -> str:
        with self.assertRaises(ProjectError) as error:
            ad.approve_document(self.root, "proposal", P2, "用户原话：通过", "用户")
        self.assertIn(step, str(error.exception), "the refusal names the missing step")
        return str(error.exception)

    def test_with_every_internal_step_done_the_first_file_can_be_approved(self) -> None:
        self.assertEqual(flow_steps.internal_errors(self.root, "proposal"), [])
        report = flow_steps.next_report(self.root)
        self.assertEqual((report["kind"], report["document"]["path"]), ("present", P2))
        self.assertIn("内部检查", report["internal"]["summary"])

    def test_without_the_rule_card_note_nothing_is_shown_or_approved(self) -> None:
        steps = self.break_and_restore("data/steps.json")
        data = json.loads(steps.read_text(encoding="utf-8"))
        del data["records"]["proposal"]["rules"]
        steps.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.refused("rules")
        self.assertEqual(flow_steps.next_report(self.root)["kind"], "internal")
        with self.assertRaises(ProjectError) as error:
            pc.require_crawl(self.root, "proposal")                     # no generation either
        self.assertIn("rules", str(error.exception))

    def test_without_the_crawl_conclusion_nothing_is_approved(self) -> None:
        page = self.break_and_restore("00-crawl/luz-project-proposal.html")
        page.unlink()
        message = self.refused("crawl")
        self.assertIn("Luz-Crawl", message)

    def test_without_the_specialists_note_or_data_nothing_is_approved(self) -> None:
        steps = self.break_and_restore("data/steps.json")
        data = json.loads(steps.read_text(encoding="utf-8"))
        del data["records"]["proposal"]["specialist"]
        steps.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.refused("specialist")
        steps.write_text(json.dumps(json.loads((self.backup / "data_steps.json").read_text(encoding="utf-8")), ensure_ascii=False), encoding="utf-8")
        features = self.break_and_restore("data/client/proposal.json")
        features.unlink()
        self.refused("specialist")

    def test_a_stale_file_is_not_shown_to_the_user(self) -> None:
        source = self.break_and_restore("data/client/features.json")
        data = json.loads(source.read_text(encoding="utf-8"))
        data["features"][0]["summary"] = data["features"][0]["summary"] + "（改过）"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        message = self.refused("build")
        self.assertIn("过期", message)

    def test_without_the_review_page_the_internal_records_are_incomplete(self) -> None:
        page = self.break_and_restore("reviews/03-方案评审.html")
        page.unlink()
        message = self.refused("records")
        self.assertIn("03-方案评审.html", message)

    def test_the_user_is_never_asked_to_look_at_the_internal_records(self) -> None:
        report = flow_steps.next_report(self.root)
        text = flow_steps.format_next(report)
        for hidden in ("reviews", "评审页", "00-crawl", "steps.json", "规则卡"):
            self.assertNotIn(hidden, "\n".join(report["report"]), hidden)
        self.assertNotIn("reviews/", text.split("给用户的汇报")[1].split("用户通过后记录")[0])


class DownstreamNeedsUpstreamInternalStepsTests(unittest.TestCase):
    """Even with every file of a stage approved by the user, a stage whose internal records went missing does not let the stage after it start or be approved."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.root = new_project("下游", cls._tmp.name, model="document")
        for stage in ("requirements", "research", "proposal"):
            df.run_stage(cls.root, stage, cls.tmp)
        df.note_step(cls.root, "client-intake", "rules")
        df.crawl(cls.root, "client-intake")
        df.note_step(cls.root, "client-intake", "specialist")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_all_files_approved_and_everything_in_place_lets_the_next_stage_start(self) -> None:
        self.assertEqual([s["state"] for s in ad.stage_documents_state(ad.Ctx(self.root), "proposal")], ["approved"] * 3)
        self.assertEqual(flow_steps.generation_errors(self.root, "client-intake"), [])
        self.assertFalse([e for e in pc.gate_stage(self.root, "client-intake") if "前置" in e or "待用户" in e])

    def blocked_by(self, relative: str, needle: str, restore: bool = True) -> None:
        source = self.root / relative
        saved = self.tmp / "saved" / relative.replace("/", "_")
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, saved)
        try:
            source.unlink()
            errors = flow_steps.generation_errors(self.root, "client-intake")
            self.assertTrue(any(needle in e and "proposal" in e for e in errors), errors)
            self.assertTrue(any(needle in e for e in pc.gate_stage(self.root, "client-intake")))
            with self.assertRaises(ProjectError):
                cf.build_intake_form(self.root)                         # a generation command refuses
            with self.assertRaises(ProjectError):
                pc.require_crawl(self.root, "client-intake")
        finally:
            shutil.copyfile(saved, source)
        self.assertEqual(flow_steps.generation_errors(self.root, "client-intake"), [], "put back, the way is open again")

    def test_a_missing_crawl_conclusion_upstream_stops_the_next_stage(self) -> None:
        self.blocked_by("00-crawl/luz-project-proposal.html", "crawl")

    def test_a_missing_review_page_upstream_stops_the_next_stage(self) -> None:
        self.blocked_by("reviews/03-方案评审.html", "records")

    def test_a_missing_stage_fact_file_upstream_stops_the_next_stage(self) -> None:
        self.blocked_by("data/stages/proposal.json", "records")

    def test_a_forgotten_rule_card_note_upstream_stops_the_next_stage(self) -> None:
        steps = self.root / "data" / "steps.json"
        saved = steps.read_text(encoding="utf-8")
        data = json.loads(saved)
        del data["records"]["proposal"]["rules"]
        steps.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            self.assertTrue(any("rules" in e and "proposal" in e for e in flow_steps.generation_errors(self.root, "client-intake")))
        finally:
            steps.write_text(saved, encoding="utf-8")

    def test_a_stage_without_files_needs_its_internal_steps_before_it_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("无文件", tmp, model="document")
            client_fixture.requirements_provided(root)
            with self.assertRaises(ProjectError) as error:
                pc.approve_stage(root, "requirements")
            for step in ("rules", "specialist", "records"):
                self.assertIn(step, str(error.exception))
            df.drive(root, "requirements", Path(tmp))
            record = pc.approve_stage(root, "requirements")
            self.assertEqual((record["scope"], record["mode"], record["approver"]), ("stage", "internal", "internal-gates"))
            self.assertTrue(ad.stage_complete(ad.Ctx(root), "requirements"))
            self.assertEqual(pc._stage_record(pc.load_project(root), "requirements")["status"], "approved")


class ActionGateTests(unittest.TestCase):
    """Release to production and the final acceptance are not files: the user authorizes them in words, once the files of the stage are through."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = new_project("动作门", self._tmp.name, model="document")
        for stage in ad.stage_order()[:9]:
            if ad.documents(self.root, stage):
                df.force_records(self.root, stage)
            else:
                df.internal_complete(self.root, stage)
        df.files_for(self.root, "release")
        df.crawl(self.root, "release")
        for patch in (gates_off(), mock.patch.object(cf, "stage_checks", return_value=[])):          # the client's input of the stages before is not what these tests are about
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_stage_does_not_complete_with_its_files_alone(self) -> None:
        for d in ad.documents(self.root, "release"):
            ad.approve_document(self.root, "release", d["path"], "用户原话：通过", "用户")
        ctx = ad.Ctx(self.root)
        self.assertTrue(ad.stage_docs_done(ctx, "release"))
        self.assertFalse(ad.stage_complete(ctx, "release"))
        self.assertTrue(any("production-release" in e for e in ad.completion_open(ctx, "release")))
        self.assertTrue(any("动作门" in e for e in pc.gate_stage(self.root, "operations")))
        report = flow_steps.next_report(self.root)
        self.assertEqual(report["kind"], "waiting")
        self.assertIn("动作门", report["message"])

    def test_the_action_needs_the_files_through_first_and_the_users_own_words(self) -> None:
        with self.assertRaises(ProjectError) as error:
            ad.record_action(self.root, "release", "production-release", "用户原话：发", "用户")
        self.assertIn("还没有全部由用户通过", str(error.exception))
        for d in ad.documents(self.root, "release"):
            ad.approve_document(self.root, "release", d["path"], "用户原话：通过", "用户")
        for note, approver in (("用户整体预先授权：都发", "用户"), ("发吧", "Claude 代为记录")):
            with self.assertRaises(ProjectError):
                ad.record_action(self.root, "release", "production-release", note, approver)
        with self.assertRaises(ProjectError):
            ad.record_action(self.root, "release", "no-such-action", "用户原话：发", "用户")
        record = ad.record_action(self.root, "release", "production-release", "用户原话：可以发布到生产", "用户")
        self.assertEqual((record["scope"], record["mode"], record["action"]), ("action", "user", "production-release"))
        self.assertTrue(ad.stage_complete(ad.Ctx(self.root), "release"))

    def test_changing_a_file_after_the_authorization_voids_it(self) -> None:
        for d in ad.documents(self.root, "release"):
            ad.approve_document(self.root, "release", d["path"], "用户原话：通过", "用户")
        ad.record_action(self.root, "release", "production-release", "用户原话：可以发布到生产", "用户")
        rewrite(self.root, ad.documents(self.root, "release")[0]["path"], "发布评审改了")
        self.assertFalse(ad.action_effective(ad.Ctx(self.root), "release", "production-release"))
        self.assertFalse(ad.stage_complete(ad.Ctx(self.root), "release"))


if __name__ == "__main__":
    unittest.main()
