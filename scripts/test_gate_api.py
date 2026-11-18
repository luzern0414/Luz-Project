"""The three small interfaces other Luz skills call: ``action-status`` (is an action gate authorized and does it still hold), ``crawl-expiry-waived`` (is the stage's Crawl record
free of the seven days) and the files the ``rules`` step reads for the skills that have no context.py rule card (Luz-Ops, Luz-Crawl)."""
from __future__ import annotations

import json
import subprocess
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
from test_doc_approval import gates_off, rewrite
from test_doc_flow import cli

PROJECT_SCRIPTS = Path(__file__).resolve().parent
SKILLS = PROJECT_SCRIPTS.parents[1]


class ActionStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = new_project("动作状态", self._tmp.name, model="document")
        for stage in ad.stage_order()[:9]:
            if ad.documents(self.root, stage):
                df.force_records(self.root, stage)
            else:
                df.internal_complete(self.root, stage)
        df.files_for(self.root, "release")
        df.crawl(self.root, "release")
        for patch in (gates_off(), mock.patch.object(cf, "stage_checks", return_value=[])):
            patch.start()
            self.addCleanup(patch.stop)

    def grant(self) -> dict:
        for d in ad.documents(self.root, "release"):
            ad.approve_document(self.root, "release", d["path"], "用户原话：通过", "用户")
        return ad.record_action(self.root, "release", "production-release", "用户原话：可以发布到生产", "李总")

    def test_before_the_user_has_authorized_it_the_answer_is_no_and_says_what_is_missing(self) -> None:
        status = ad.action_status(self.root, "release", "production-release")
        self.assertFalse(status["granted"])
        self.assertIn("用户还没有授权", status["reason"])
        self.assertEqual(ad.action_granted(self.root, "release", "production-release"), (False, status["reason"]))
        code, text = cli("action-status", self.root, "release", "production-release")
        self.assertEqual(code, 1)
        self.assertIn("未授权", text)
        code, text = cli("action-status", self.root, "release", "production-release", "--json")
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)["granted"])

    def test_after_the_users_words_it_is_granted_with_who_when_and_the_files_it_is_bound_to(self) -> None:
        record = self.grant()
        status = ad.action_status(self.root, "release", "production-release")
        self.assertTrue(status["granted"])
        self.assertEqual((status["approver"], status["record"], status["note"]), ("李总", record["id"], "用户原话：可以发布到生产"))
        self.assertTrue(status["time"])
        self.assertEqual(set(status["bound_files"]), {d["path"] for d in ad.documents(self.root, "release")})
        self.assertEqual(ad.action_granted(self.root, "release", "production-release"), (True, ""))
        code, text = cli("action-status", self.root, "release", "production-release", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(text)
        self.assertTrue(payload["granted"])
        self.assertEqual(payload["approver"], "李总")
        code, text = cli("action-status", str(pc.deliver_root(self.root)), "release", "production-release")
        self.assertEqual(code, 0, "the project directory works as well as the state root")
        self.assertIn("已授权", text)

    def test_a_changed_bound_file_or_a_reopened_stage_takes_the_authorization_back_and_says_which(self) -> None:
        self.grant()
        changed = ad.documents(self.root, "release")[0]["path"]
        rewrite(self.root, changed, "发布评审改了")
        granted, reason = ad.action_granted(self.root, "release", "production-release")
        self.assertFalse(granted)
        self.assertIn(changed, reason)
        self.assertIn("哈希", reason)
        self.assertEqual(cli("action-status", self.root, "release", "production-release")[0], 1)
        # a change that reopens the stage voids it too
        other = new_project("动作状态二", self._tmp.name + "/b", model="document")
        for stage in ad.stage_order()[:9]:
            df.force_records(other, stage) if ad.documents(other, stage) else df.internal_complete(other, stage)
        df.files_for(other, "release")
        df.crawl(other, "release")
        for d in ad.documents(other, "release"):
            ad.approve_document(other, "release", d["path"], "用户原话：通过", "用户")
        ad.record_action(other, "release", "production-release", "用户原话：发", "用户")
        self.assertTrue(ad.action_granted(other, "release", "production-release")[0])
        ad.void_from(other, "release", "变更重开了发布阶段")
        granted, reason = ad.action_granted(other, "release", "production-release")
        self.assertFalse(granted)
        self.assertIn("作废", reason)

    def test_unknown_stage_unknown_action_an_older_project_and_a_missing_project_are_answered_not_raised(self) -> None:
        self.assertIn("没有动作门", ad.action_granted(self.root, "release", "no-such-action")[1])
        self.assertIn("production-release", ad.action_granted(self.root, "release", "no-such-action")[1], "it names the gates the stage has")
        self.assertIn("没有动作门", ad.action_granted(self.root, "proposal", "production-release")[1])
        self.assertIn("未知阶段", ad.action_granted(self.root, "nowhere", "x")[1])
        self.assertFalse(ad.action_granted(Path(self._tmp.name) / "nothing-here", "release", "production-release")[0])
        old = new_project("旧模型", self._tmp.name + "/c", model="stage")
        granted, reason = ad.action_granted(old, "release", "production-release")
        self.assertFalse(granted)
        self.assertIn("旧模型", reason)
        code, text = cli("action-status", old, "release", "production-release")
        self.assertEqual(code, 1)


class CrawlExpiryWaivedTests(unittest.TestCase):
    def test_a_complete_stage_is_waived_and_a_stage_being_worked_on_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("豁免", tmp, model="document")
            self.assertFalse(ad.crawl_expiry_waived(root, "research"))
            code, text = cli("crawl-expiry-waived", root, "research")
            self.assertEqual(code, 1)
            self.assertIn("不豁免", text)
            df.internal_complete(root, "research")                                     # a stage without files is complete once its internal record stands
            self.assertTrue(ad.crawl_expiry_waived(root, "research"))
            waived, reason = ad.crawl_expiry_status(root, "research")
            self.assertTrue(waived)
            self.assertIn("只核对存在、有效、已 conclude", reason)
            code, text = cli("crawl-expiry-waived", root, "research")
            self.assertEqual(code, 0)
            self.assertIn("豁免", text)
            code, text = cli("crawl-expiry-waived", str(pc.deliver_root(root)), "research", "--json")
            self.assertEqual((code, json.loads(text)["waived"]), (0, True))
            self.assertFalse(ad.crawl_expiry_waived(root, "proposal"))
            waived, reason = ad.crawl_expiry_status(root, "proposal")
            self.assertIn("还差", reason)
            self.assertEqual(cli("crawl-expiry-waived", root, "proposal", "--json")[0], 1)
            self.assertFalse(ad.crawl_expiry_status(root, "nowhere")[0])
            ad.void_from(root, "research", "变更重开了调研")                          # the stage is reopened: the age counts again
            self.assertFalse(ad.crawl_expiry_waived(root, "research"))

    def test_an_older_project_waives_the_stage_it_has_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("旧模型", tmp, model="stage")
            self.assertFalse(ad.crawl_expiry_waived(root, "requirements"))
            manifest = pc.load_project(root)
            pc._stage_record(manifest, "requirements")["status"] = "approved"
            pc._save_manifest(root, manifest)
            self.assertTrue(ad.crawl_expiry_waived(root, "requirements"))
            self.assertEqual(cli("crawl-expiry-waived", root, "requirements")[0], 0)

    def test_flow_steps_and_project_core_ask_the_same_function(self) -> None:
        """One judgement: the step check, ``check`` and ``gate`` all pass the answer of ``approval_docs.crawl_expiry_waived`` to the Crawl check."""
        import project_crawl_gate

        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("同一判定", tmp, model="document")
            df.internal_complete(root, "requirements")
            df.internal_complete(root, "research")
            manifest = pc.load_project(root)
            for name in ("requirements", "research"):
                pc._stage_record(manifest, name)["status"] = "approved"
            pc._save_manifest(root, manifest)
            for answer in (True, False):
                seen: list[tuple[str, bool]] = []

                def recorder(project, stage=None, caller=None, *, waive_expiry=False):
                    seen.append((stage, waive_expiry))
                    return []

                with mock.patch.object(ad, "crawl_expiry_waived", return_value=answer), mock.patch.object(project_crawl_gate, "crawl_errors", recorder):
                    flow_steps.internal_errors(root, "research", phases=(flow_steps.PREPARE,))
                    pc.validate_project(root)
                    pc.gate_stage(root, "research", specialist_checks=False)
                self.assertTrue(seen and all(flag is answer for _, flag in seen), (answer, seen))
                self.assertGreaterEqual(len(seen), 3, "the step, check and gate each asked")

    def test_a_skill_with_its_own_modules_can_call_both_functions_by_path(self) -> None:
        ops = SKILLS / "Luz-Ops" / "scripts"
        if not ops.is_dir():
            self.skipTest("Luz-Ops is not here")
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("别的技能调用", tmp, model="document")
            df.internal_complete(root, "research")
            code = ("import sys\nsys.path.insert(0, sys.argv[1])\nsys.path.append(sys.argv[2])\nimport approval_docs as ad\n"
                    "print(ad.crawl_expiry_waived(sys.argv[3], 'research'), ad.crawl_expiry_waived(sys.argv[3], 'proposal'), ad.action_granted(sys.argv[3], 'release', 'production-release')[0])\n")
            run = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(ops), str(PROJECT_SCRIPTS), str(root)], capture_output=True, text=True, encoding="utf-8", cwd=ops)
            self.assertEqual(run.returncode, 0, run.stderr[-600:])
            self.assertEqual(run.stdout.split(), ["True", "False", "False"])
            for command, expected in ((["crawl-expiry-waived", str(root), "research"], 0), (["crawl-expiry-waived", str(root), "proposal"], 1), (["action-status", str(root), "release", "production-release"], 1)):
                run = subprocess.run([sys.executable, "-X", "utf8", str(PROJECT_SCRIPTS / "project.py"), *command], capture_output=True, text=True, encoding="utf-8", cwd=ops)
                self.assertEqual(run.returncode, expected, (command, run.stdout, run.stderr[-300:]))


class RuleFilesTests(unittest.TestCase):
    OPS = ["SKILL.md", "references/operations-matrix.json", "references/release-gates.md", "references/evidence-formats.md"]

    def test_the_matrix_lists_what_luz_ops_and_luz_crawl_read_where_there_is_no_rule_card(self) -> None:
        expected = {
            "research": ("luz-crawl", ["SKILL.md", "references/preflight.md", "references/research-method.md"]),
            "verification": ("luz-ops", self.OPS + ["references/test-playbooks/"]),
            "release": ("luz-ops", self.OPS + ["references/ops-playbooks/release-rollback.md", "references/ops-playbooks/backup-restore.md", "references/ops-playbooks/monitoring-alerting.md",
                                               "references/ops-playbooks/compliance-baseline.md"]),
            "operations": ("luz-ops", self.OPS + ["references/ops-playbooks/handoff-runbook.md", "references/ops-playbooks/incident-response.md"]),
        }
        for stage, (skill, files) in expected.items():
            listed = pc.rule_files(stage)
            self.assertEqual([f["file"] for f in listed], files, stage)
            self.assertTrue(all(f["skill"] == skill and f["for"] for f in listed), stage)
            self.assertTrue(all(f["exists"] for f in listed), [f["path"] for f in listed if not f["exists"]])
            self.assertTrue(all(Path(f["path"]).is_absolute() for f in listed))
        for stage in ("requirements", "proposal", "architecture", "design", "technical-plan", "implementation", "handover"):
            self.assertEqual(pc.rule_files(stage), [], f"{stage} has rule cards or none to name")

    def test_context_and_route_print_the_files_and_the_rules_step_asks_for_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("规则文件", tmp, model="document")
            code, text = cli("context", root, "verification", "--skill", "luz-ops")
            self.assertEqual(code, 0, text[:300])
            context = json.loads(text)
            self.assertEqual([f["file"] for f in context["rule_files"]], self.OPS + ["references/test-playbooks/"])
            self.assertTrue(all(f["exists"] for f in context["rule_files"]))
            self.assertEqual(context["rule_files"][0]["path"], str(SKILLS / "Luz-Ops" / "SKILL.md"))
            self.assertEqual([f["file"] for f in json.loads(cli("route", root, "research")[1])["rule_files"]], ["SKILL.md", "references/preflight.md", "references/research-method.md"])
            self.assertEqual(json.loads(cli("context", root, "proposal", "--skill", "luz-project")[1])["rule_files"], [])
            for stage in ("research", "verification", "release", "operations"):
                step = next(s for s in pc._stage_defs()[stage]["steps"] if s["id"] == "rules")
                self.assertIn("rule_files", step["command"], stage)
                self.assertIn("rule_files", step["proof"], stage)
                self.assertIn("规则文件", step["title"], stage)
                for f in pc._stage_defs()[stage]["rule_files"]:
                    self.assertIn(f["file"], step["command"], (stage, f["file"]))

    def test_checklist_shows_the_files_when_the_rules_step_is_the_one_to_do(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("清单", tmp, model="document")
            client_fixture.requirements_provided(root)                                # the client brought its own requirements document: the stage has no file for the user
            df.internal_complete(root, "requirements")
            with gates_off():
                data = flow_steps.checklist(root, "research", project=str(pc.deliver_root(root)))
            rules = next(r for r in data["steps"] if r["id"] == "rules")
            self.assertTrue(rules.get("current"), [(r["id"], r["status"]) for r in data["steps"]])
            self.assertEqual(len(rules["rule_files"]), 3)
            self.assertTrue(all(p.startswith(str(SKILLS / "Luz-Crawl")) for p in rules["rule_files"]))
            text = flow_steps.format_checklist(data)
            self.assertIn("要读的文件：", text)
            self.assertIn("research-method.md", text)
            self.assertIn("rule_files 列出的哪些文件", text, "the criterion names the files")
            plain = flow_steps.checklist(root, "requirements", project=str(pc.deliver_root(root)))
            self.assertFalse(any(r.get("rule_files") for r in plain["steps"]), "a stage with rule cards has no file list")


if __name__ == "__main__":
    unittest.main()
