"""The runbook (references/runbook.md) is the one manual another agent follows: its commands must parse and run (dry run on a copy of a project), the scripts it names must exist,
and it must cover every stage and every file of the matrix."""
from __future__ import annotations

import os
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Ops" / "scripts"))

import approval_docs as ad
import project
import project_core as pc
from client_fixture import new_project
from test_doc_flow import cli

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "references" / "runbook.md"
SUBCOMMANDS = set(project.build_parser()._subparsers._group_actions[0].choices)       # type: ignore[union-attr]
PREFIX = re.compile(r"^(?:py -X utf8 D:\\Codes\\Luz-Project\\scripts\\project\.py|project\.py)\s+")


def spans(text: str) -> list[str]:
    """Every fenced line and inline code span of the runbook."""
    found: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            found.append(line.strip())
        else:
            found += re.findall(r"`([^`]+)`", line)
    return found


def project_commands(text: str) -> list[str]:
    """The runbook's project.py commands, without the prefix: a span whose first word is a subcommand of project.py and that names the project (or init's name)."""
    out = []
    for span in spans(text):
        body = PREFIX.sub("", span.strip())
        first = body.split(" ", 1)[0]
        if first in SUBCOMMANDS and ('"<项目>"' in body or "<名称>" in body or first == "matrix"):
            out.append(body)
    return list(dict.fromkeys(out))


class RunbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNBOOK.read_text(encoding="utf-8")

    def test_the_runbook_exists_and_skill_md_points_to_it_and_stays_small(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/runbook.md", skill)
        self.assertLessEqual(len((ROOT / "SKILL.md").read_bytes()), 12 * 1024, "SKILL.md keeps to a card: the detail is in references")
        for needle in ("三次项目确认", "一次出示整批", "已有逐文件项目", "内部步骤不省略", "project.py next", "project.py checklist", "project.py review", "动作门"):
            self.assertTrue(needle in skill, needle)

    def test_the_runbook_covers_every_stage_and_every_file_of_the_matrix(self) -> None:
        for number, stage in enumerate(pc.load_matrix()["stages"], 1):
            self.assertRegex(self.text, rf"### 4\.{number} {stage['id']} ", stage["id"])
            for doc in stage["documents"]:
                if doc.get("path") and not doc.get("client_input"):
                    self.assertIn(Path(doc["path"]).name, self.text, f"{stage['id']}: {doc['path']}")
            for record in stage["internal_records"]:
                if record["kind"] == "review-page":
                    self.assertIn(Path(record["path"]).name, self.text)
            for action in stage.get("action_gates", []):
                self.assertIn(action["id"], self.text)
        for step in ("upstream", "rules", "crawl", "specialist", "build", "records", "trace", "present", "decide", "record"):
            self.assertIn(f"`{step}`", self.text)

    def test_the_relative_links_resolve(self) -> None:
        for target in re.findall(r"\]\(([^)#]+\.md)\)", self.text):
            self.assertTrue((RUNBOOK.parent / target).is_file(), target)

    def test_the_other_skills_scripts_it_names_exist(self) -> None:
        for path in re.findall(r"D:\\Codes\\(Luz-[A-Za-z]+)\\scripts\\([\w.\-]+\.(?:py|mjs))", self.text):
            self.assertTrue((ROOT.parent / path[0] / "scripts" / path[1]).is_file(), "\\".join(path))
        names = set(re.findall(r"\b([\w\-]+\.py)\b", self.text)) - {"project.py"}
        folders = [ROOT.parent / f"Luz-{n}" / "scripts" for n in ("Crawl", "Ops", "Dev", "System", "Design", "Writing")] + [ROOT / "scripts"]
        for name in names:
            self.assertTrue(any((folder / name).is_file() for folder in folders), f"{name} is named in the runbook but is in no skill's scripts")

    def test_every_command_of_the_runbook_parses_and_runs_on_a_copy(self) -> None:
        commands = project_commands(self.text)
        self.assertGreaterEqual(len(commands), 50, "the runbook's commands were found")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["LUZ_PROJECT_OUTPUT"] = str(Path(tmp) / "out")
            root = new_project("手册演练", tmp, model="document")
            (Path(tmp) / "facts.json").write_text("{}", encoding="utf-8")
            (Path(tmp) / "x.html").write_text("<html></html>", encoding="utf-8")
            values = {"项目": str(root), "阶段": "proposal", "路径": "docs/01-需求对接/02-方案说明书.pdf", "用户原话": "TEST ONLY 用户原话", "用户": "测试用户", "意见原文": "测试意见",
                      "评审事实.json": str(Path(tmp) / "facts.json"), "回填表.xlsx": str(Path(tmp) / "missing.xlsx"), "文件": str(Path(tmp) / "x.html"), "类型": "html", "编号": "RN-001",
                      "技能": "luz-writing", "主题": "b2b-graphite", "名称": "手册演练二", "项目目录": str(Path(tmp) / "work" / "031-手册演练二"),
                      "怎么改的": "已改", "为什么不用改": "用户撤回", "哪个技能产出了什么；检查结论": "luz-system 产出了功能清单；检查通过", "原文": "x", "标题": "积分抵扣比例调整", "变更后的具体逻辑": "100 分抵 1 元改为 50 分抵 1 元；历史订单不追溯", "提出人": "店长", "确认人与方式": "店长（微信确认）", "确认人": "店长", "过程记录": "随版本实施",
                      "要求的人": "agent", "日期": "2026-11-05", "要求的原话": "x", "关闭的原因": "客户说先不写", "数字": "0", "动作": "production-release", "提供报价的人": "agent", "提供数字的原话或来源": "x", "报价单.xlsx": str(Path(tmp) / "missing.xlsx")}
            unknown: set[str] = set()

            def fill(token: str) -> str:
                def one(match: re.Match[str]) -> str:
                    key = match.group(1)
                    if key not in values:
                        unknown.add(key)
                    return values.get(key, key)

                return re.sub(r"<([^<>]+)>", one, token)

            for command in commands:
                tokens = [fill(t) for t in shlex.split(command)]
                self.assertFalse(unknown, f"{command}: placeholders the dry run does not know {unknown}")
                parser = project.build_parser()
                try:
                    parser.parse_args(tokens)
                except SystemExit:
                    self.fail(f"the runbook's command does not parse: {command}")
                code, text = cli(*tokens)
                self.assertIn(code, {0, 1, 2}, f"{command} -> {text[:300]}")
                self.assertNotIn("Traceback", text, command)
            self.assertFalse(Path(r"E:\Skill输出\Luz-Project\031-手册演练二").exists(), "the dry run never writes to the real output root")

    def test_the_runbook_tells_how_to_go_when_budget_or_quote_is_asked_for_and_that_the_default_is_not_to_write_it(self) -> None:
        commands = project_commands(self.text)
        self.assertTrue(any(c.startswith("client") and " estimate --workdays on --quote on --requested-by" in c for c in commands))
        self.assertTrue(any(c.startswith("client") and " quote --unit-price" in c and "--provided-by" in c and "--evidence" in c for c in commands))
        self.assertTrue(any(c.startswith("client") and " quote --from-file" in c and "--provided-by" in c for c in commands))
        self.assertTrue(any(c.startswith("client") and " estimate --quote off --note" in c for c in commands))
        section = self.text.split("## 11 用户要求预算或报价时怎么走", 1)[1]
        for needle in ("默认", "不自拟、不暂估", "等待人工报价", "hours_basis", "拟定", "三项证据", "变更台账"):
            self.assertIn(needle, section, needle)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("默认不写", "estimate", "等待人工报价", "agent 不得自拟"):
            self.assertIn(needle, skill, needle)
        self.assertNotIn('"amounts"', skill + self.text)

    def test_the_runbook_tells_other_skills_how_to_call_the_three_read_only_interfaces_and_which_files_the_rules_step_reads(self) -> None:
        commands = project_commands(self.text)
        self.assertTrue(any(c.startswith("action-status ") for c in commands))
        self.assertTrue(any(c.startswith("crawl-expiry-waived ") for c in commands))
        section = self.text.split("## 12 给其它技能的只读接口", 1)[1]
        for needle in ("action_granted", "action_status", "crawl_expiry_waived", "crawl_expiry_status", "rule_files", "sys.path.append", "检索记录超过七天", "退出码 0=已授权"):
            self.assertIn(needle, section, needle)
        for needle in ("references/operations-matrix.json", "references/release-gates.md", "references/evidence-formats.md", "references/preflight.md", "references/research-method.md", "ops-playbooks", "没有 context.py 规则卡"):
            self.assertIn(needle, self.text, needle)

    def test_the_runbook_says_the_crawl_records_age_counts_for_the_stage_being_worked_on_only(self) -> None:
        self.assertIn("七天期限只管正在做的阶段", self.text)
        self.assertIn("不看是否超过七天", self.text)
        self.assertIn("重新算作进行中", self.text)
        mode = (ROOT / "references" / "project-mode.md").read_text(encoding="utf-8")
        self.assertIn("Crawl 记录的七天期限只管正在做的阶段", mode)

    def test_the_commands_that_ought_to_work_on_a_fresh_project_do(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["LUZ_PROJECT_OUTPUT"] = str(Path(tmp) / "out")
            root = new_project("新手册", tmp, model="document")
            for argv in (("next", root), ("checklist", root, "requirements"), ("status", root), ("route", root, "proposal"), ("review", root, "list"), ("approvals-upgrade", root), ("render", root)):
                code, text = cli(*argv)
                self.assertEqual(code, 0, f"{argv[0]}: {text[:200]}")
            code, text = cli("gate", root, "proposal")
            self.assertEqual(code, 1, "gate says what is missing")


if __name__ == "__main__":
    unittest.main()
