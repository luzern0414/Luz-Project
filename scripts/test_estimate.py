"""预算、人日与报价政策 (user, 2026-11-05): a project writes no person-days, budget or price unless a person asked for them, with the evidence; the quote is a person's number or nothing.

Covered: the two switches and their evidence, the old ``amounts`` switch, the ``estimate`` and ``quote`` commands and every way they refuse, the rendering of 04-功能清单 under each
switch, what the client reads when nothing was asked for, a switch or quote that changes after approval (a change, the files reopened), the wait for a human quote
(next / checklist / summary page) and the Crawl record age (counts for the stage being worked on only)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Ops" / "scripts"))

import approval_docs as ad
import client_data as cd
import client_estimate as ce
import client_fixture as fx
import client_flow as cf
import doc_fixture as df
import estimate_policy as ep
import flow_steps
import project_core as pc
from client_fixture import new_project
from project_crawl_gate import evidence_session
from project_core import ProjectError, validate_project
from project_paths import locate
from test_doc_flow import cli

AGENT_LIKE = ["agent", "Claude", "智能体", "系统", "示例", "skill", "暂估", "助手", "default", "自动生成", "系统生成", "tool"]      # what the shared vocabulary says is not a person


def write_config(root: Path, **estimate) -> None:
    """The documents config as a hand edit would leave it (the command is what refuses; the checks are what catch a hand edit)."""
    config = cd.documents_config(root)
    config["estimate"] = {**ep.default_estimate(), **estimate}
    (root / "config" / "documents.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")


def person_asked(**extra) -> dict:
    return {"requested_by": fx.REQUESTED_BY, "requested_at": fx.REQUESTED_AT, "request_note": fx.REQUEST_NOTE, **extra}


class SwitchEvidenceTests(unittest.TestCase):
    def test_a_new_project_writes_neither_person_days_nor_a_quote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("默认", tmp, model="document")
            config = json.loads((root / "config" / "documents.json").read_text(encoding="utf-8"))
            self.assertEqual(config["estimate"], {"workdays": False, "quote": False, "requested_by": "", "requested_at": "", "request_note": ""})
            self.assertNotIn("amounts", config)
            state = cd.estimate_state(root)
            self.assertFalse(state.workdays or state.quote or state.errors or state.notes)
            self.assertEqual(validate_project(root, strict=True), [])
            self.assertEqual(ep.user_todos(root), [])

    def test_a_switch_without_its_evidence_is_not_on_and_the_check_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("缺证据", tmp)
            for missing in ("requested_by", "requested_at", "request_note"):
                write_config(root, workdays=True, **{**person_asked(), missing: ""})
                state = cd.estimate_state(root)
                self.assertFalse(state.workdays, missing)
                self.assertTrue(any(missing in e for e in state.errors), (missing, state.errors))
                self.assertTrue(any(missing in e for e in validate_project(root)), missing)

    def test_a_requester_that_is_not_a_person_does_not_open_a_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("非人", tmp)
            for name in AGENT_LIKE:
                write_config(root, workdays=True, **person_asked(requested_by=name))
                self.assertFalse(cd.workdays_enabled(root), name)
                self.assertTrue(any("不是具体的人" in e for e in validate_project(root)), name)
            write_config(root, workdays=True, **person_asked())
            self.assertTrue(cd.workdays_enabled(root))
            self.assertEqual(validate_project(root), [])

    def test_the_quote_needs_workdays_and_the_words_and_the_date_must_be_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("规则", tmp)
            write_config(root, quote=True, **person_asked())
            self.assertFalse(cd.quote_enabled(root))
            self.assertTrue(any("workdays 必须同时为 true" in e for e in validate_project(root)))
            write_config(root, workdays=True, **person_asked(requested_at="昨天"))
            self.assertTrue(any("不是日期" in e for e in validate_project(root)))
            write_config(root, workdays=True, **person_asked(request_note="暂估一下"))
            self.assertTrue(any("原话" in e for e in validate_project(root)))
            write_config(root, workdays=1, **person_asked())
            self.assertTrue(any("true 或 false" in e for e in validate_project(root)))

    def test_the_old_amounts_switch_means_off_and_a_true_one_is_said_out_loud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("旧开关", tmp)
            for value, word in ((False, "amounts: false"), (True, "amounts: true")):
                (root / "config" / "documents.json").write_text(json.dumps({"theme": "fitness-gym", "amounts": value}), encoding="utf-8")
                state = cd.estimate_state(root)
                self.assertFalse(state.workdays or state.quote)
                self.assertTrue(any(word in n for n in state.notes), state.notes)
                self.assertEqual(validate_project(root), [], "the old switch is not an error: it only counts as off")
            code, text = cli("check", root)
            self.assertEqual(code, 0)
            self.assertIn("amounts: true", text)
            self.assertIn("没有谁要求", text)

    def test_the_section_the_files_depend_on_is_the_same_before_and_after_the_defaults_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("等价", tmp)
            digest = lambda: cd.source_digest(root, "config/documents.json#estimate")
            (root / "config" / "documents.json").write_text(json.dumps({"theme": "fitness-gym"}), encoding="utf-8")
            bare = digest()
            (root / "config" / "documents.json").write_text(json.dumps({"theme": "fitness-gym", "amounts": False}), encoding="utf-8")
            self.assertEqual(digest(), bare)
            write_config(root)
            self.assertEqual(digest(), bare, "adding the defaults to an old project makes none of its files stale")
            write_config(root, requested_by="某人", request_note="随便写")           # leftovers with both switches off do not count either
            self.assertEqual(digest(), bare)
            write_config(root, workdays=True, **person_asked())
            self.assertNotEqual(digest(), bare)


class SharedTermsTests(unittest.TestCase):
    """The words of the policy are Luz-Design's estimate_terms.py, copied whole into this folder (Design's sync script writes it; nobody edits the copy)."""

    MASTER = Path(__file__).resolve().parents[2] / "Luz-Design" / "scripts" / "estimate_terms.py"

    def test_the_copy_has_the_digest_of_the_master(self) -> None:
        if not self.MASTER.is_file():
            self.skipTest("Luz-Design's estimate_terms.py is not here")
        import importlib.util

        spec = importlib.util.spec_from_file_location("_master_estimate_terms", self.MASTER)
        master = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(master)
        self.assertEqual(ep.et.terms_digest(), master.terms_digest(), "the copy and the master carry different words: run Luz-Design's sync script, do not edit the copy")
        self.assertEqual(ep.et.TERMS, master.TERMS)

    def test_the_person_check_and_the_word_lists_are_the_shared_ones(self) -> None:
        for name in AGENT_LIKE + ["待补", "模板", "Gemini", "n/a"]:
            self.assertEqual(ep.not_a_person(name), ep.et.not_a_person(name), name)
        self.assertFalse(ep.not_a_person("王总（客户方负责人）"))
        self.assertTrue(ep.not_a_person("") and ep.not_a_person("   ") and ep.not_a_person(None))
        for word in ep.et.WORKDAY_WORDS:
            self.assertEqual(ep.workday_issues(f"本期共 {word} 若干"), [word], word)
        for word in ep.et.MONEY_WORDS:
            hit = bool(cd.money_issues(f"写着{word}的一句话"))
            self.assertEqual(hit, word not in cd.AMBIGUOUS_IN_PROSE, word)
        self.assertTrue(set(cd.AMBIGUOUS_IN_PROSE) <= set(ep.et.MONEY_WORDS), "a word that left the shared list is still listed here")
        self.assertEqual(cd.money_issues("订单金额满 200 元可用，会员折扣另议，预算管理功能"), [], "business sentences are not prices")
        self.assertTrue(cd.money_issues("金额 800 元", strict=True))

    def test_evidence_that_says_the_number_was_made_up_is_refused_even_with_words_after_it(self) -> None:
        for text in ("暂估", "默认值", "示例", "TBD", "暂估，先按这个算", "按默认值 800 元每人天", "自拟一个单价", "占位，之后再改"):
            self.assertTrue(ep.not_evidence(text), text)
        self.assertFalse(ep.not_evidence(fx.QUOTE_EVIDENCE))
        self.assertFalse(ep.not_evidence("uploads/客户报价单.xlsx"))
        self.assertTrue(ep.et.is_not_evidence("暂估") and not ep.et.is_not_evidence("暂估，先按这个算"), "is_not_evidence is the case of a text made only of placeholder words")
        self.assertTrue(ep.et.says_made_up("暂估，先按这个算"), "says_made_up is the case of a text that calls its own figure a 暂估: the shared vocabulary has both, Project asks both")
        self.assertFalse(hasattr(ep, "MADE_UP") or hasattr(ep, "MIN_NOTE"), "no second copy of the words or of the lengths: they come from estimate_terms")

    def test_the_lengths_are_the_shared_ones_a_short_request_may_be_a_few_words_but_the_evidence_of_a_number_names_a_source(self) -> None:
        self.assertEqual((ep.et.MIN_NOTE, ep.et.EVIDENCE_MIN), (4, 6))
        ask = {"requested_by": fx.REQUESTED_BY, "requested_at": fx.REQUESTED_AT}
        self.assertTrue(ep.evidence_errors({**ask, "request_note": "请报价"}), "three characters are not four")
        self.assertEqual(ep.evidence_errors({**ask, "request_note": "请给出报价"}), [])
        quote = {"unit_price": 800, "provided_by": fx.QUOTE_BY, "provided_at": "2026-11-05", "request_note": "请给出报价", "evidence": fx.QUOTE_EVIDENCE}
        self.assertEqual(ep.quote_errors(quote), [])
        for short in ("微信回复", "李经理说的"):                                   # four or five characters: a number needs a concrete source, not a pointer to one
            self.assertTrue(any("evidence" in e for e in ep.quote_errors({**quote, "evidence": short})), short)
        self.assertEqual(ep.quote_errors({**quote, "evidence": "微信回复800元"}), [])
        self.assertEqual(ep.quote_errors({**quote, "evidence": "uploads/报价单.xlsx"}), [])
        self.assertTrue(any("request_note" in e for e in ep.quote_errors({**quote, "request_note": "报价"})), "the request in the quote is held to the request length")

    def test_a_business_word_of_the_system_is_released_by_allow_terms_and_nothing_else_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("业务词", tmp)
            fx.write_all(root)
            proposal = cd.load(root, "client", "proposal.json")
            proposal["sections"][0]["blocks"].append({"type": "text", "text": "后台提供员工工时统计，供店长核对排班；共 3 人天。"})
            cd.save(root, proposal, "client", "proposal.json")
            found = "；".join(cf.estimate_errors(root))
            self.assertIn("工时", found)
            self.assertIn("人天", found)
            proposal["allow_terms"] = ["工时统计"]
            cd.save(root, proposal, "client", "proposal.json")
            found = "；".join(cf.estimate_errors(root))
            self.assertNotIn("工时", found.replace("人天或工时", ""), "the declared business word is released")
            self.assertIn("人天", found, "a person-day figure is not a business word")
            features = fx.features()
            features["features"][0]["allow_terms"] = ["工时统计"]
            cd.save(root, features, "client", "features.json")
            self.assertEqual(ep.project_allowed_terms(root), ("工时统计",))
            entry = {"title": "新增员工工时统计", "detail": "店长可按周查看员工工时统计", "impact": "", "requester": "店长"}
            self.assertEqual(cf.client_text_issues(entry, root), [], "a visible ledger entry may use the project's declared word")


class UpgradeTests(unittest.TestCase):
    """Projects made before the policy: migrate adds the defaults (both switches off) and drops the old switch; adopt and init write them from the start."""

    def old_config(self, root: Path, **extra) -> Path:
        path = root / "config" / "documents.json"
        path.write_text(json.dumps({"theme": "fitness-gym", **extra}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_migrate_previews_then_adds_the_estimate_defaults_and_drops_the_old_amounts_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("旧开关", tmp, model="document")
            for old, word in ((False, "amounts 开关去掉"), (True, "amounts: true 没有谁要求")):
                path = self.old_config(root, amounts=old)
                before = path.read_text(encoding="utf-8")
                preview = pc.migrate_project(root)
                self.assertTrue(any("补上 estimate 默认值" in n and word in n for n in preview["notes"]), preview["notes"])
                self.assertEqual(path.read_text(encoding="utf-8"), before, "the preview writes nothing")
                done = pc.migrate_project(root, apply=True)
                config = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(config["estimate"], ep.default_estimate())
                self.assertNotIn("amounts", config)
                self.assertEqual(config["theme"], "fitness-gym")
                self.assertFalse(any("补上 estimate" in n for n in pc.migrate_project(root)["notes"]), "nothing left to add the second time")

    def test_adding_the_defaults_leaves_the_files_built_before_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("等价", tmp)
            fx.write_all(root)
            fx.crawled(root, "proposal")
            path = self.old_config(root, amounts=False)
            cf.build_proposal(root)
            self.assertEqual(cd.stale_sources(root, "proposal"), [])
            pc.migrate_project(root, apply=True)
            self.assertEqual(cd.stale_sources(root, "proposal"), [], "the project is on the new policy and nothing it built is out of date")
            self.assertEqual(cf.stage_checks(root, "proposal"), [])

    def test_an_old_layout_project_gets_the_defaults_in_its_new_state_root(self) -> None:
        from legacy_fixture import legacy_project

        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("旧布局", tmp)
            (root / "config" / "documents.json").write_text(json.dumps({"theme": None, "amounts": True}), encoding="utf-8")
            out = Path(tmp) / "out"
            preview = pc.migrate_project(root, output=out)
            self.assertTrue(any("补上 estimate 默认值" in n for n in preview["notes"]), preview["notes"])
            result = pc.migrate_project(root, apply=True, output=out)
            state = Path(result["state_root"])
            config = json.loads((state / "config" / "documents.json").read_text(encoding="utf-8"))
            self.assertEqual(config["estimate"], ep.default_estimate())
            self.assertNotIn("amounts", config)

    def test_adopt_and_init_write_the_defaults(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "work" / "007-演示"
            (repo / "src").mkdir(parents=True)
            subprocess.run(["git", "init", "-q"], cwd=repo)
            result = pc.adopt_project(repo, "演示项目", output=Path(tmp) / "out")
            config = json.loads((Path(result["state_root"]) / "config" / "documents.json").read_text(encoding="utf-8"))
            self.assertEqual(config["estimate"], ep.default_estimate())
            self.assertEqual(validate_project(Path(result["state_root"]), strict=True), [])
            code, text = cli("init", "新项目", "--project-dir", str(Path(tmp) / "work" / "031-新项目"), "--output-root", str(Path(tmp) / "out"))
            self.assertEqual(code, 0, text)
            made = Path(json.loads(text)["state_root"])
            self.assertEqual(json.loads((made / "config" / "documents.json").read_text(encoding="utf-8"))["estimate"], ep.default_estimate())


class EstimateCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = new_project("开关命令", self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def ask(self, **kw):
        return ce.set_estimate(self.root, **{**{"requested_by": fx.REQUESTED_BY, "requested_at": fx.REQUESTED_AT, "request_note": fx.REQUEST_NOTE}, **kw})

    def test_opening_a_switch_needs_all_three_items_of_evidence(self) -> None:
        for missing in ("requested_by", "requested_at", "request_note"):
            with self.assertRaises(ProjectError, msg=missing) as refused:
                self.ask(workdays=True, **{missing: ""})
            self.assertIn("证据", str(refused.exception))
        self.assertFalse(cd.workdays_enabled(self.root), "nothing was written")
        for name in AGENT_LIKE:
            with self.assertRaises(ProjectError, msg=name):
                self.ask(workdays=True, requested_by=name)
        with self.assertRaises(ProjectError):
            self.ask(workdays=True, requested_at="下周")
        with self.assertRaises(ProjectError):
            self.ask(workdays=True, request_note="好的")
        self.assertEqual(json.loads((self.root / "config" / "documents.json").read_text(encoding="utf-8"))["estimate"], ep.default_estimate())

    def test_the_quote_cannot_be_on_without_workdays(self) -> None:
        with self.assertRaises(ProjectError) as refused:
            self.ask(quote=True)
        self.assertIn("workdays", str(refused.exception))
        with self.assertRaises(ProjectError):
            self.ask(quote=True, workdays=False)
        result = self.ask(workdays=True, quote=True)                              # both at once is fine
        self.assertEqual(result["now"], "写人日与报价")

    def test_workdays_on_records_who_when_and_in_what_words_and_asks_for_the_hours(self) -> None:
        result = self.ask(workdays=True)
        self.assertEqual(result["now"], "写人日、不写报价")
        self.assertIn("hours_basis", result["next"])
        self.assertIn("拟定", result["next"])
        stored = json.loads((self.root / "config" / "documents.json").read_text(encoding="utf-8"))["estimate"]
        self.assertEqual(stored, {"workdays": True, "quote": False, **person_asked()})
        self.assertTrue(cd.workdays_enabled(self.root) and not cd.quote_enabled(self.root))
        self.assertEqual(validate_project(self.root), [])

    def test_with_the_quote_on_and_no_human_quote_the_command_succeeds_and_the_project_waits(self) -> None:
        result = self.ask(workdays=True, quote=True)
        self.assertTrue(result["waiting_for_quote"])
        self.assertIn("等待人工报价", result["todo"])
        state = cd.estimate_state(self.root)
        self.assertTrue(state.quote and state.waiting_for_quote and state.quote_missing)
        self.assertEqual(validate_project(self.root), [], "waiting is a state, not an error")
        todos = ep.user_todos(self.root)
        self.assertEqual(len(todos), 1)
        self.assertIn("等待人工报价", todos[0])
        self.assertIn("agent 不得自拟", todos[0])
        fx.human_quote(self.root)
        self.assertEqual(ep.user_todos(self.root), [])
        self.assertFalse(cd.estimate_state(self.root).waiting_for_quote)

    def test_turning_off_needs_a_reason_and_forgets_the_request_but_keeps_the_history(self) -> None:
        self.ask(workdays=True, quote=True)
        with self.assertRaises(ProjectError) as refused:
            ce.set_estimate(self.root, quote=False)
        self.assertIn("--note", str(refused.exception))
        result = ce.set_estimate(self.root, quote=False, note="客户说先不报价了")
        self.assertEqual(result["now"], "写人日、不写报价")
        self.assertTrue(cd.workdays_enabled(self.root) and not cd.quote_enabled(self.root))
        ce.set_estimate(self.root, workdays=False, note="只给功能清单")
        config = json.loads((self.root / "config" / "documents.json").read_text(encoding="utf-8"))
        self.assertEqual(config["estimate"], ep.default_estimate(), "nothing is on: the last request is not left lying around as evidence")
        self.assertEqual([h["workdays"] for h in config["estimate_history"]], [True, True, False])
        self.assertEqual(config["estimate_history"][-1]["note"], "只给功能清单")
        with self.assertRaises(ProjectError):                                       # nothing changes
            ce.set_estimate(self.root, workdays=False, note="再关一次")

    def test_the_command_line_and_its_status(self) -> None:
        code, text = cli("client", self.root, "estimate")
        self.assertEqual(code, 0)
        self.assertIn("不写人日与报价", text)
        code, text = cli("client", self.root, "estimate", "--workdays", "on")
        self.assertEqual(code, 2)
        self.assertIn("证据", text)
        code, text = cli("client", self.root, "estimate", "--workdays", "on", "--quote", "on", "--requested-by", fx.REQUESTED_BY, "--requested-at", fx.REQUESTED_AT, "--request-note", fx.REQUEST_NOTE)
        self.assertEqual(code, 0, text)
        self.assertIn("等待人工报价", text)
        code, text = cli("client", self.root, "quote", "--unit-price", "800")
        self.assertEqual(code, 2)
        self.assertIn("--provided-by", text)
        code, text = cli("client", self.root, "quote", "--unit-price", "800", "--provided-by", "agent", "--evidence", "我估的")
        self.assertEqual(code, 2)
        self.assertIn("不是具体的人", text)
        code, text = cli("client", self.root, "quote", "--unit-price", "800", "--provided-by", fx.QUOTE_BY, "--evidence", fx.QUOTE_EVIDENCE)
        self.assertEqual(code, 0, text)
        code, text = cli("client", self.root, "estimate")
        self.assertIn("写人日与报价", text)
        self.assertIn(fx.QUOTE_BY, text)
        code, help_text = cli("client", "--help")
        self.assertIn("agent 不得自拟", help_text)


class QuoteRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = new_project("报价单", self._tmp.name)
        ce.set_estimate(self.root, workdays=True, quote=True, **person_asked())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def record(self, **kw):
        base = {"unit_price": 800, "provided_by": fx.QUOTE_BY, "evidence": fx.QUOTE_EVIDENCE}
        return ce.write_quote(self.root, **{**base, **kw})

    def test_a_quote_is_recorded_with_who_when_the_request_and_the_words(self) -> None:
        result = self.record()
        quote = cd.load_quote(self.root)
        self.assertEqual(quote, result["quote"])
        self.assertEqual({k: quote[k] for k in ("unit_price", "provided_by", "request_note", "evidence")},
                         {"unit_price": 800, "provided_by": fx.QUOTE_BY, "request_note": fx.REQUEST_NOTE, "evidence": fx.QUOTE_EVIDENCE})
        self.assertTrue(ep.is_date(quote["provided_at"]))
        self.assertEqual(ep.quote_errors(quote, self.root), [])

    def test_a_quote_without_a_person_without_words_or_without_a_price_is_refused(self) -> None:
        refusals = [({"provided_by": ""}, "--provided-by"), ({"evidence": ""}, "--evidence"), ({"evidence": "  "}, "--evidence"),
                    ({"unit_price": 0}, "大于 0"), ({"unit_price": -5}, "大于 0"), ({"unit_price": float("nan")}, "大于 0"),
                    ({"evidence": "暂估，先按这个算"}, "暂估"), ({"evidence": "默认值"}, "暂估"), ({"evidence": "示例"}, "暂估")]
        refusals += [({"provided_by": name}, "不是具体的人") for name in AGENT_LIKE]
        for kw, word in refusals:
            with self.assertRaises(ProjectError, msg=str(kw)) as refused:
                self.record(**kw)
            self.assertIn(word, str(refused.exception), kw)
        self.assertIsNone(cd.load_quote(self.root), "nothing was written by a refused command")
        with self.assertRaises(ProjectError):
            ce.write_quote(self.root, provided_by=fx.QUOTE_BY, evidence=fx.QUOTE_EVIDENCE)           # neither a price nor a quote sheet
        with self.assertRaises(ProjectError):
            ce.write_quote(self.root, unit_price=800, from_file=self.tmp / "x.json", provided_by=fx.QUOTE_BY, evidence=fx.QUOTE_EVIDENCE)   # both

    def test_a_quote_json_without_its_evidence_is_not_rendered_and_not_approved_and_not_silently_passed(self) -> None:
        cd.save(self.root, {"unit_price": 800}, "client", "quote.json")                       # the old shape: a bare number
        state = cd.estimate_state(self.root)
        self.assertTrue(state.waiting_for_quote and state.quote_errors)
        self.assertTrue(any("provided_by" in e and "evidence" in e for e in state.quote_errors), state.quote_errors)
        self.assertTrue(any("报价单" in e for e in validate_project(self.root)))
        for field, value in (("provided_by", "agent（自动估算）"), ("evidence", "暂估"), ("evidence", "默认值"), ("provided_at", "今天"), ("unit_price", True), ("unit_price", 0)):
            good = {"unit_price": 800, "provided_by": fx.QUOTE_BY, "provided_at": "2026-11-05", "request_note": fx.REQUEST_NOTE, "evidence": fx.QUOTE_EVIDENCE}
            cd.save(self.root, {**good, field: value}, "client", "quote.json")
            self.assertTrue(cd.estimate_state(self.root).quote_errors, (field, value))
        self.assertEqual(ep.quote_errors({"unit_price": 800, "provided_by": fx.QUOTE_BY, "provided_at": "2026-11-05", "request_note": fx.REQUEST_NOTE, "evidence": fx.QUOTE_EVIDENCE}), [])

    def test_a_quote_left_behind_while_the_switch_is_off_is_not_read_or_held_to_anything(self) -> None:
        ce.set_estimate(self.root, quote=False, note="客户说先不报价了")
        cd.save(self.root, {"unit_price": 800}, "client", "quote.json")
        state = cd.estimate_state(self.root)
        self.assertEqual((state.quote, state.quote_errors, state.waiting_for_quote), (False, [], False))
        self.assertEqual(validate_project(self.root), [])

    def test_a_quote_sheet_is_read_kept_in_uploads_and_bound_by_its_hash(self) -> None:
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.append(["项目", "内容"])
        sheet.append(["人天单价（元）", 650])
        sheet.append(["备注", "含税"])
        path = self.tmp / "客户报价单.xlsx"
        book.save(path)
        result = ce.write_quote(self.root, from_file=path, provided_by=fx.QUOTE_BY)
        quote = result["quote"]
        self.assertEqual(quote["unit_price"], 650)
        self.assertEqual(quote["evidence"], "uploads/客户报价单.xlsx", "the sheet itself is the evidence")
        self.assertTrue(locate(self.root, "uploads/客户报价单.xlsx").is_file())
        self.assertEqual(len(quote["evidence_sha256"]), 64)
        self.assertEqual(ep.quote_errors(cd.load_quote(self.root), self.root), [])
        locate(self.root, "uploads/客户报价单.xlsx").write_bytes(b"someone edited the sheet")
        self.assertTrue(any("不一致" in e for e in ep.quote_errors(cd.load_quote(self.root), self.root)))
        locate(self.root, "uploads/客户报价单.xlsx").unlink()
        self.assertTrue(any("不存在" in e for e in ep.quote_errors(cd.load_quote(self.root), self.root)))

    def test_json_and_csv_quote_sheets_and_the_ones_that_say_nothing_or_two_things(self) -> None:
        (self.tmp / "q.json").write_text(json.dumps({"unit_price": 700}), encoding="utf-8")
        self.assertEqual(ce.read_unit_price(self.tmp / "q.json"), 700)
        (self.tmp / "q.csv").write_text("项目,金额\n人天单价,\"1,200\"\n", encoding="utf-8-sig")
        self.assertEqual(ce.read_unit_price(self.tmp / "q.csv"), 1200)
        (self.tmp / "none.csv").write_text("项目,说明\n人天,看情况\n", encoding="utf-8-sig")
        with self.assertRaises(ProjectError) as refused:
            ce.read_unit_price(self.tmp / "none.csv")
        self.assertIn("找不到", str(refused.exception))
        (self.tmp / "two.csv").write_text("单价,600\n人天单价,900\n", encoding="utf-8-sig")
        with self.assertRaises(ProjectError) as refused:
            ce.read_unit_price(self.tmp / "two.csv")
        self.assertIn("几个不同的单价", str(refused.exception))
        with self.assertRaises(ProjectError):
            ce.read_unit_price(self.tmp / "q.docx")
        with self.assertRaises(ProjectError):
            ce.write_quote(self.root, from_file=self.tmp / "missing.xlsx", provided_by=fx.QUOTE_BY)

    def test_without_a_request_on_record_the_quote_needs_the_words_that_asked_for_it(self) -> None:
        ce.set_estimate(self.root, quote=False, note="先不报价")
        ce.set_estimate(self.root, workdays=False, note="都不写")
        with self.assertRaises(ProjectError) as refused:
            self.record()
        self.assertIn("request-note", str(refused.exception))
        result = self.record(request_note="客户来函：请按人天报价")
        self.assertIn("没有开启", result["warning"])


class FeatureListRenderTests(unittest.TestCase):
    """04-功能清单 under each switch (renders through Luz-Design; needs Edge via Playwright like the other client tests)."""

    def _project(self, tmp: str, *, workdays: bool = False, quote: bool = False) -> Path:
        root = new_project("示例健身", tmp)
        fx.write_all(root)
        cd.save(root, fx.features(), "client", "features.json")
        if workdays:
            fx.switch_on(root, workdays=True, quote=quote)
        if quote:
            fx.human_quote(root)
        fx.crawled(root, "proposal")
        return root

    def _book(self, root: Path, data_only: bool = False):
        from openpyxl import load_workbook

        return load_workbook(locate(root, "docs/01-需求对接/04-功能清单.xlsx"), data_only=data_only)

    def test_by_default_it_is_one_sheet_of_functions_with_no_days_no_money_no_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            cf.build_proposal(root)
            book = self._book(root)
            self.assertEqual(book.sheetnames, ["功能清单"])
            self.assertIsNone(book.properties.description, "no evidence is carried because no switch is on")
            cells = [c.value for ws in book.worksheets for row in ws.iter_rows() for c in row if c.value is not None]
            header = next(r for r in book.active.iter_rows(min_row=1, max_row=5) if any(c.value == "功能" for c in r))
            self.assertEqual([c.value for c in header], ["使用端", "功能模块", "使用角色", "功能", "功能说明", "类型"])
            self.assertEqual(book.active.freeze_panes, "D4")
            merges = {str(region) for region in book.active.merged_cells.ranges if region.min_row >= 4}
            self.assertEqual(merges, {"A4:A7", "A8:A10", "A11:A12", "B4:B6", "B9:B10", "B11:B12", "C4:C6", "C11:C12"})
            self.assertEqual([book.active[f"B{row}"].value for row in (7, 8)], ["预约服务", "预约服务"])
            self.assertEqual([book.active[f"C{row}"].value for row in (9, 10)], ["店长", "店长、老板"])
            self.assertFalse([v for v in cells if isinstance(v, str) and (v.startswith("=") or any(w in v for w in ("工时", "人天", "小计", "合计", "金额", "单价", "报价", "元每")))], cells)
            self.assertEqual(cf.estimate_errors(root), [])
            self.assertEqual(ep.user_todos(root), [])

    def test_workdays_on_and_quote_off_adds_the_hours_column_with_formula_totals_and_no_money(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, workdays=True)
            cf.build_proposal(root)
            book = self._book(root)
            self.assertEqual(book.sheetnames, ["功能清单"])
            self.assertIn("要求人：" + fx.REQUESTED_BY, book.properties.description)
            ws = book.active
            rows = [[c.value for c in r] for r in ws.iter_rows(min_row=3)]
            self.assertEqual(rows[0][-1], "工时（人天）")
            hours = [r[-1] for r in rows[1:10]]
            self.assertEqual(hours, [0.5 * (k + 1) for k in range(9)])
            totals = {r[0]: r[-1] for r in rows[10:]}
            self.assertEqual(totals["工时合计"], "=SUM(G4:G12)")
            self.assertEqual(totals["基础功能小计"], '=SUMIF($F$4:$F$12,"基础",G$4:G$12)')
            self.assertEqual(totals["可选功能小计，选用后另计"], '=SUMIF($F$4:$F$12,"可选",G$4:G$12)')
            text = json.dumps(rows, ensure_ascii=False)
            for word in ("报价", "单价", "金额", "元"):
                self.assertNotIn(word, text)
            self.assertEqual(cf.estimate_errors(root), [])

    def test_both_on_adds_the_quote_sheet_whose_every_number_is_the_persons_or_a_formula_of_the_hours(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, workdays=True, quote=True)
            cf.build_proposal(root)
            book = self._book(root)
            self.assertEqual(book.sheetnames, ["功能清单", "报价清单"])
            self.assertIn(fx.QUOTE_BY, book.properties.description)
            self.assertIn(fx.QUOTE_EVIDENCE, book.properties.description)
            ws = book["报价清单"]
            rows = [[c.value for c in r] for r in ws.iter_rows(min_row=3)]
            self.assertEqual(rows[0][-3:], ["工时（人天）", "单价（元每人天）", "报价（元）"])
            body = rows[1:10]
            self.assertEqual([r[-3] for r in body], [0.5 * (k + 1) for k in range(9)], "hours come from features.json")
            self.assertEqual({r[-2] for r in body}, {800}, "the unit price comes from quote.json, nothing else")
            self.assertEqual([r[-1] for r in body], [f"=G{4 + k}*H{4 + k}" for k in range(9)], "each amount is hours x price as a formula")
            footer = {r[0]: r for r in rows[10:]}
            self.assertEqual(footer["基础功能小计"][-1], '=SUMIF($F$4:$F$12,"基础",I$4:I$12)')
            self.assertEqual(footer["报价合计，基础功能；可选功能另计"][-1], "=I13")
            numbers = [v for r in rows[1:] for v in r if isinstance(v, (int, float))]
            self.assertTrue(set(numbers) <= {800} | {0.5 * (k + 1) for k in range(9)}, "no number in the sheet that is not the person's or a function's hours")
            self.assertEqual(cf.estimate_errors(root), [])
            self.assertEqual(cf.stage_checks(root, "proposal"), [])
            quote = cd.load_quote(root)
            self.assertIn("data/client/quote.json", cd.load(root, "client", "build.json")["proposal"]["sources"])
            self.assertIn("config/documents.json#estimate", cd.load(root, "client", "build.json")["proposal"]["sources"])
            cd.save(root, {**quote, "unit_price": 900}, "client", "quote.json")
            self.assertTrue(any("quote.json" in s for s in cd.stale_sources(root, "proposal")), "another number makes the file stale")

    def test_the_file_goes_stale_when_a_switch_changes_and_the_old_sheet_is_not_accepted_under_the_new_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, workdays=True)
            cf.build_proposal(root)
            self.assertEqual(cd.stale_sources(root, "proposal"), [])
            ce.set_estimate(root, workdays=False, note="只给功能清单")
            self.assertTrue(any("config/documents.json#estimate" in s for s in cd.stale_sources(root, "proposal")))
            errors = cf.estimate_errors(root)
            self.assertTrue(any("不应有人天" in e for e in errors), errors)
            self.assertTrue(any("方案文档已过期" in e for e in cf.stage_checks(root, "proposal")))
            cf.build_proposal(root)
            self.assertEqual(self._book(root).sheetnames, ["功能清单"])
            self.assertEqual(cf.estimate_errors(root), [])

    def test_with_the_quote_on_nothing_is_built_until_a_person_has_given_the_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, workdays=True)
            ce.set_estimate(root, quote=True, **person_asked())
            with self.assertRaises(ProjectError) as refused:
                cf.build_proposal(root)
            self.assertIn("等待人工报价", str(refused.exception))
            self.assertTrue(any("等待人工报价" in e for e in cf.stage_checks(root, "proposal")), "the stage's build step is not done")
            self.assertFalse(locate(root, "docs/01-需求对接/02-方案说明书.pdf").exists(), "no proposal file either: the three are built together")
            fx.human_quote(root)
            self.assertEqual(len(cf.build_proposal(root)), 3)
            self.assertEqual(self._book(root).sheetnames, ["功能清单", "报价清单"])

    def test_an_agent_cannot_get_a_price_into_the_sheet_through_the_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, workdays=True)
            spec = cr_spec(root, quote={"unit_price": 800, "provided_by": "agent", "provided_at": "2026-11-05", "request_note": fx.REQUEST_NOTE, "evidence": "我估的"})
            from client_render import build_xlsx

            with self.assertRaises(ProjectError):
                build_xlsx(root, "feature-list", spec)
            bare = cr_spec(root, quote=None)
            bare["sheets"] = [{**bare, "columns": bare["columns"] + [{"name": "报价（元）", "type": "money"}], "rows": [r + [1] for r in bare["rows"]]}]      # a money column with no switch for it
            with self.assertRaises(ProjectError):
                build_xlsx(root, "feature-list", {"title": "x", "theme": bare["theme"], "sheets": bare["sheets"]})


def cr_spec(root: Path, quote):
    import client_render as cr

    features = cd.load_features(root)
    block = {"workdays": True, "quote": bool(quote), "requested_by": fx.REQUESTED_BY, "request_note": fx.REQUEST_NOTE}
    if quote:
        block.update({"provided_by": quote["provided_by"], "evidence": quote["evidence"]})
    spec = cr.feature_list_xlsx_spec(features, "示例", cd.project_theme(root), None, estimate={**block, "quote": False})
    if quote:
        spec = cr.feature_list_xlsx_spec(features, "示例", cd.project_theme(root), quote, estimate=block)
    return spec


class WaitForQuoteAndDraftMarkTests(unittest.TestCase):
    """next / checklist / the summary page: the wait for a human quote is the user's to do; the person-days are a draft until the user approves the function list."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.base = new_project("等报价", cls._tmp.name, model="document")
        for stage in ("requirements", "research"):
            df.run_stage(cls.base, stage, cls.tmp)
        df.note_step(cls.base, "proposal", "rules")
        df.crawl(cls.base, "proposal")
        fx.write_all(cls.base)
        fx.switch_on(cls.base, workdays=True, quote=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_while_the_quote_is_missing_next_names_it_as_the_users_to_do_and_nothing_is_shown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            df.note_step(root, "proposal", "specialist")
            report = flow_steps.next_report(root)
            self.assertEqual(report["stage"], "proposal")
            self.assertEqual(report["kind"], "waiting")
            self.assertTrue(any("等待人工报价" in t for t in report["user_todos"]))
            self.assertTrue(any("等待人工报价" in t for t in report["waiting_for"]))
            text = flow_steps.format_next(report)
            self.assertTrue(text.startswith("需要你先做"), text)
            self.assertIn("等待人工报价", text)
            self.assertIn("单价", text)
            self.assertIn("报价单", text)
            checklist = flow_steps.checklist(root, "proposal", project=str(pc.deliver_root(root)))
            self.assertTrue(any("等待人工报价" in t for t in checklist["user_todos"]))
            self.assertIn("等待人工报价", flow_steps.format_checklist(checklist))
            build = next(r for r in checklist["steps"] if r["id"] == "build")
            self.assertTrue(any("等待人工报价" in b for b in build["blocked_by"]))
            with self.assertRaises(ProjectError) as refused:
                cf.build_proposal(root)
            self.assertIn("等待人工报价", str(refused.exception))
            with self.assertRaises(ProjectError):
                ad.approve_document(root, "proposal", "docs/01-需求对接/02-方案说明书.pdf", "TEST ONLY", "测试用户")
            code, out = cli("next", root)
            self.assertEqual(code, 0)
            self.assertIn("等待人工报价", out)
            page = pc.render_project(root)[0].read_text(encoding="utf-8")
            self.assertIn("需要你先做", page)
            self.assertIn("等待人工报价", page)

    def test_once_a_person_has_given_the_number_the_files_are_built_and_the_hours_are_marked_as_a_draft_until_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            df.note_step(root, "proposal", "specialist")
            fx.human_quote(root)
            self.assertEqual(ep.user_todos(root), [])
            cf.build_proposal(root)
            df.records(root, "proposal")
            report = flow_steps.next_report(root)
            self.assertEqual(report["kind"], "present")
            self.assertEqual(report["document"]["path"], "docs/01-需求对接/02-方案说明书.pdf")
            self.assertNotIn("拟定", report["document"]["what"], "the proposal text carries no estimate")
            for path in ("docs/01-需求对接/02-方案说明书.pdf", "docs/01-需求对接/03-系统架构图.pdf"):
                ad.approve_document(root, "proposal", path, df.TEST_NOTE, "测试用户")
            report = flow_steps.next_report(root)
            doc = report["document"]
            self.assertEqual(doc["path"], "docs/01-需求对接/04-功能清单.xlsx")
            self.assertIn("拟定", doc["what"])
            self.assertIn("hours_basis", doc["what"])
            self.assertIn(fx.QUOTE_BY, doc["what"])
            self.assertIn("拟定", doc["label"])
            self.assertIn("拟定", report["report"][1])
            self.assertEqual(len(report["report"]), 3)
            ad.approve_document(root, "proposal", "docs/01-需求对接/04-功能清单.xlsx", df.TEST_NOTE, "测试用户")
            ctx = ad.Ctx(root)
            approved = ad.document_status(ctx, next(d for d in ctx.docs if d["path"].endswith("04-功能清单.xlsx")))
            self.assertEqual(flow_steps.label_of(ctx, {"kind": "feature-list-xlsx"}, approved), "已通过", "the mark goes once the user has approved")
            self.assertEqual(flow_steps.draft_mark(root, {"kind": "feature-list-xlsx"}, "approved"), "")


class SwitchChangeAfterApprovalTests(unittest.TestCase):
    """Turning a switch (or giving another number) after the proposal files were approved is a change: logged in the ledger, the stage reopened, every file looked at again."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.base = new_project("开关变更", cls._tmp.name, model="document")
        for stage in ("requirements", "research", "proposal"):
            df.run_stage(cls.base, stage, cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_turning_workdays_on_logs_a_change_and_voids_the_three_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            self.assertEqual({d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")}, {"approved"})
            cd.save(root, fx.with_hours(cd.load_features(root)), "client", "features.json")
            result = ce.set_estimate(root, workdays=True, **person_asked())
            self.assertRegex(result["change"], r"CHG-\d+")
            entry = next(c for c in cf._ledger(root)["changes"] if c["id"] == result["change"])
            self.assertEqual((entry["type"], entry["category"], entry["status"], entry["affects"], entry["source"]), ("修改", "范围", "已确认", ["proposal"], "内部"))
            self.assertIn("proposal", entry["reopened"])
            self.assertFalse(cf.is_client_visible(entry), "an internal decision does not go into the client's ledger")
            self.assertIn("列功能和工作量", entry["detail"])
            self.assertNotIn("人天", entry["detail"] + entry["title"], "the entry could be visible: it carries none of the words the policy keeps out")
            states = [d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")]
            self.assertNotIn("approved", states, "none of the three keeps its approval")
            voided = [r for r in json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"] if r.get("scope") == "document" and r["status"] == "voided"]
            self.assertEqual(len(voided), 3)
            self.assertEqual(pc.load_project(root)["current_stage"], "proposal")
            self.assertEqual(flow_steps.next_report(root)["stage"], "proposal")
            self.assertTrue(any("前置审批未完成" in e for e in pc.gate_stage(root, "client-intake")))
            self.assertTrue(ad.stage_record_effective(ad.Ctx(root), "requirements"), "the stages before it keep their approval")
            cf.build_proposal(root)                                                    # the files are written again, and each is approved again, one by one
            df.records(root, "proposal")
            self.assertEqual(flow_steps.next_report(root)["document"]["path"], "docs/01-需求对接/02-方案说明书.pdf")

    def test_a_client_who_asks_for_it_puts_the_change_in_the_clients_ledger_and_turning_it_off_is_a_change_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            cd.save(root, fx.with_hours(cd.load_features(root)), "client", "features.json")
            on = ce.set_estimate(root, workdays=True, source="客户", **person_asked())
            entry = next(c for c in cf._ledger(root)["changes"] if c["id"] == on["change"])
            self.assertTrue(cf.is_client_visible(entry))
            self.assertEqual(entry["requester"], fx.REQUESTED_BY)
            rows = cf.ledger_rows(root)
            self.assertIn("功能清单的工作量与价格写法调整", [r[4] for r in rows])
            cf.build_proposal(root)
            df.records(root, "proposal")
            df.approve_all(root, "proposal")
            off = ce.set_estimate(root, workdays=False, note="客户改主意了：只要功能清单", source="客户")
            self.assertRegex(off["change"], r"CHG-\d+")
            self.assertNotEqual(off["change"], on["change"])
            self.assertNotIn("approved", [d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")])
            self.assertEqual(cf.ledger_warnings(root), [])

    def test_a_hand_edit_of_the_switches_voids_the_three_approvals_through_the_source_hash_and_check_reports_the_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            self.assertEqual(validate_project(root, strict=True), [])
            ids = [r for r in json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"] if r.get("scope") == "document" and "04-功能清单" in r["document"]]
            self.assertIn("config/documents.json#estimate", ids[-1]["source_hashes"], "an approval of the proposal files rests on the switches")
            write_config(root, workdays=True, **person_asked())                       # not through the command: no change is logged
            states = {d["document"]: d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")}
            self.assertEqual(set(states.values()), {"voided"}, states)
            self.assertEqual(cf._ledger(root)["changes"], [])
            self.assertTrue(any("方案文档已过期" in e and "estimate" in e for e in cf.stage_checks(root, "proposal")))

    def test_before_anything_is_approved_a_switch_is_not_a_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("还没批", tmp, model="document")
            result = ce.set_estimate(root, workdays=True, **person_asked())
            self.assertIsNone(result["change"])
            self.assertEqual(cf._ledger(root)["changes"], [])

    def test_a_new_number_after_approval_is_a_change_and_the_first_number_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            cd.save(root, fx.with_hours(cd.load_features(root)), "client", "features.json")
            ce.set_estimate(root, workdays=True, quote=True, **person_asked())
            first = fx.human_quote(root, 800)
            self.assertNotIn("change", first, "the first number: the project had been waiting for it")
            cf.build_proposal(root)
            df.records(root, "proposal")
            df.approve_all(root, "proposal")
            again = fx.human_quote(root, 900)
            self.assertRegex(again["change"], r"CHG-\d+")
            self.assertNotIn("approved", [d["state"] for d in ad.stage_documents_state(ad.Ctx(root), "proposal")])
            self.assertNotIn("900", json.dumps(cf._ledger(root)["changes"][-1], ensure_ascii=False), "the ledger entry carries no figure")


class _Aged(datetime):
    """``datetime`` as it was ``days`` ago: Luz-Crawl's own clock while an old record is made (an offline fixture; nothing about it is a real search)."""

    days = 0

    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) - timedelta(days=cls.days)


def old_crawl(root: Path, stage: str, days: int = 10) -> None:
    """The Crawl preflight record of ``stage`` as it would be after ``days`` days: made, concluded and registered at that time, so it is whole and valid, only old."""
    import crawl_preflight as crawl
    import test_crawl_preflight as fixtures
    from unittest import mock

    caller = pc._stage_record(pc.load_project(root), stage)["owner"]
    session = evidence_session(root)
    path = crawl.record_path(session, caller, stage)
    for old in (path, path.with_suffix(".html")):
        old.unlink(missing_ok=True)
    _Aged.days = days
    with mock.patch.object(crawl, "datetime", _Aged):
        fixtures.fixture(session, caller, stage, task_name=f"aged-{stage}")
        fixtures.conclude(session, caller, {"findings": [{"source_id": "SRC-001", "summary": "离线夹具中的补充信息", "applies_to": "测试场景的方案输入", "adopted": True}], "gaps": []}, stage)
    for written in (path, path.with_suffix(".html")):
        pc.register_artifact(root, stage, written, "research-evidence")                # the registry follows the file, as it did when the stage was approved


class CrawlRecordAgeTests(unittest.TestCase):
    """The seven days of a Crawl record count for the stage being worked on. A stage whose files the user approved only has to keep its record there, valid and concluded:
    a project that takes longer than a week does not redo the research of approved stages. A change that reopens a stage brings the age back for it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.base = new_project("检索过期", cls._tmp.name, model="document")
        for stage in ("requirements", "research", "proposal"):
            df.run_stage(cls.base, stage, cls.tmp)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def owner(self, root: Path, stage: str) -> str:
        return pc._stage_record(pc.load_project(root), stage)["owner"]

    def test_the_age_is_an_error_of_the_record_itself(self) -> None:
        from project_crawl_gate import crawl_errors

        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            self.assertEqual(crawl_errors(root, "proposal", self.owner(root, "proposal")), [])
            old_crawl(root, "proposal")
            errors = crawl_errors(root, "proposal", self.owner(root, "proposal"))
            self.assertEqual(len(errors), 1)
            self.assertIn("检索记录超过七天", errors[0], "Luz-Crawl's sentence: project_crawl_gate recognises the finding by it")
            self.assertEqual(crawl_errors(root, "proposal", self.owner(root, "proposal"), waive_expiry=True), [])

    def test_an_old_record_of_an_approved_stage_does_not_stop_the_stages_after_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            for stage in ("requirements", "research", "proposal"):
                old_crawl(root, stage)
            self.assertTrue(ad.stage_complete(ad.Ctx(root), "proposal"))
            ctx = ad.Ctx(root)
            self.assertEqual([e for e in ad.hold_errors(ctx, "client-intake") if "前置阶段" in e], [], ad.hold_errors(ctx, "client-intake"))
            gate = pc.gate_stage(root, "client-intake", specialist_checks=False)
            self.assertEqual([e for e in gate if "client-intake: 缺少记录" not in e], [], "nothing but the next stage's own record (not made yet) is missing")
            self.assertEqual(validate_project(root, strict=True), [], "check does not hold approved stages to the age either")
            for stage in ("requirements", "research", "proposal"):
                self.assertEqual(flow_steps.internal_errors(root, stage), [], stage)
            self.assertEqual(flow_steps.next_report(root)["stage"], "client-intake")

    def test_an_old_record_still_has_to_be_there_valid_and_concluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            old_crawl(root, "proposal")
            from crawl_preflight import record_path

            record = record_path(evidence_session(root), self.owner(root, "proposal"), "proposal")
            value = json.loads(record.read_text(encoding="utf-8"))
            value["steps"][0]["sha256"] = "0" * 64                                    # a log that no longer matches its hash
            record.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            problems = ad.hold_errors(ad.Ctx(root), "client-intake")
            self.assertTrue(any("前置阶段 proposal" in e and "哈希" in e for e in problems), problems)
            record.unlink()
            problems = ad.hold_errors(ad.Ctx(root), "client-intake")
            self.assertTrue(any("前置阶段 proposal" in e and "缺少记录" in e for e in problems), problems)

    def test_the_stage_being_worked_on_still_stops_at_an_old_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            df.note_step(root, "client-intake", "rules")
            df.crawl(root, "client-intake")
            old_crawl(root, "client-intake")
            problems = flow_steps.internal_errors(root, "client-intake")
            self.assertTrue(any(p.startswith("crawl") and "超过七天" in p for p in problems), problems)
            with self.assertRaises(ProjectError) as refused:
                pc.require_crawl(root, "client-intake")
            self.assertIn("超过七天", str(refused.exception))
            self.assertTrue(any("超过七天" in e for e in pc.gate_stage(root, "client-intake")))
            self.assertTrue(any("crawl" in r["id"] and r["status"] != "done" for r in flow_steps.checklist(root, "client-intake")["steps"]))

    def test_a_change_that_reopens_the_stage_brings_the_age_back_for_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = df.clone(self.base, tmp)
            for stage in ("requirements", "research", "proposal"):
                old_crawl(root, stage)
            self.assertEqual(flow_steps.internal_errors(root, "proposal"), [])
            cf.add_change(root, type="修改", category="规则", title="积分抵扣比例调整", detail="100 分抵 1 元改为 50 分抵 1 元，历史订单不追溯", source="客户", requester="店长", refs=["FN-002"],
                          affects=["proposal"], status="已确认", confirmed_by="店长（微信确认）")
            self.assertFalse(ad.stage_complete(ad.Ctx(root), "proposal"), "the change voided its approvals")
            problems = flow_steps.internal_errors(root, "proposal")
            self.assertTrue(any(p.startswith("crawl") and "超过七天" in p for p in problems), problems)
            with self.assertRaises(ProjectError) as refused:
                pc.require_crawl(root, "proposal")
            self.assertIn("超过七天", str(refused.exception))
            self.assertEqual(flow_steps.internal_errors(root, "requirements"), [], "the stage in front of it is untouched, so its old record is still fine")
            df.crawl(root, "proposal")                                                  # a fresh search for the reopened stage settles it
            self.assertFalse([p for p in flow_steps.internal_errors(root, "proposal") if p.startswith("crawl")])


if __name__ == "__main__":
    unittest.main()
