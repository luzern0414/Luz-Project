"""The two roots of a project: path rules, the old layout kept working, migrate (preview and apply), the command line and the context."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
from crawl_preflight import conclude
from test_crawl_preflight import complete_fixture, fixture as crawl_fixture

import client_fixture as fx
import project as cli
from client_fixture import new_project
from crawl_gate import evidence_session
from legacy_fixture import legacy_project
from project_core import (
    ProjectError,
    approve_stage,
    deliver_root,
    is_legacy,
    kind_of,
    load_project,
    locate,
    migrate_project,
    register_artifact,
    relative_to_project,
    render_project,
    resolve_state_root,
    stage_context,
    validate_project,
)


def tree(root: Path) -> dict[str, str]:
    """Every file below ``root`` with its hash (what a preview must leave exactly as it is)."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def crawled_outside(root: Path, tmp: str, caller: str, stage: str) -> None:
    """The offline Crawl fixture with its task folder outside the project, where Luz-Crawl keeps its tasks."""
    session = evidence_session(root)
    crawl_fixture(session, caller, stage, task_parent=Path(tmp) / "crawl")
    conclude(session, caller, {"findings": [{"source_id": "SRC-001", "summary": "离线夹具中的补充信息", "applies_to": "测试场景的方案输入", "adopted": True}], "gaps": []}, stage)


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class PathRuleTests(unittest.TestCase):
    def test_results_belong_to_the_project_directory_and_everything_else_to_the_state_root(self) -> None:
        for rel in ("docs/01-需求对接/01-需求说明书.pdf", "src/app.py", "test/unit/a.py", "assets/logo.png", "infra/dev/x.yml", "scripts/build.py",
                    "data/schema/orders.sql", "data/seeds/users.json", "data/fixtures/a.json", "config/environments.json"):
            self.assertEqual(kind_of(rel), "deliver", rel)
        for rel in ("project.json", "MANIFEST.json", "APPROVALS.json", "data/client/features.json", "data/stages/design.json", "data/ops/checks.json", "data/acceptance/checklist.json",
                    "data/changes.json", "data/artifacts.json", "data/baseline.json", "config/paths.json", "config/documents.json", "config/keys.example.json",
                    "00-crawl/x.json", "reviews/01-需求评审.html", "uploads/a.docx", "client-docs/a.docx", "architecture/frontend-spec/entrances.json"):
            self.assertEqual(kind_of(rel), "state", rel)

    def test_a_project_is_found_from_its_state_root_its_session_or_its_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("三种写法", tmp)
            deliver = Path(tmp) / "work" / "014-三种写法"
            for given in (state, state.parent, deliver):
                self.assertEqual(resolve_state_root(given), state.resolve(), given)
                self.assertEqual(deliver_root(given), deliver.resolve(), given)
                self.assertEqual(load_project(given)["project_id"], "PROJECT-014")
                self.assertEqual(validate_project(given, strict=True), [])
                self.assertFalse(is_legacy(given))
            with self.assertRaises(ProjectError):
                resolve_state_root(Path(tmp) / "work")

    def test_a_path_is_written_relative_to_the_root_it_belongs_to_and_found_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("路径", tmp)
            deliver = Path(tmp) / "work" / "014-路径"
            cases = {"docs/02-产品开发/01-系统架构.html": deliver, "src/main.py": deliver, "data/seeds/a.json": deliver,
                     "reviews/01-需求评审.html": state, "data/client/features.json": state, "00-crawl/a.json": state, "config/paths.json": state}
            for rel, base in cases.items():
                self.assertEqual(locate(state, rel), base / rel, rel)
                self.assertEqual(locate(deliver, rel), base / rel, rel)
                self.assertEqual(relative_to_project(state, base / rel), rel, rel)
            self.assertEqual(locate(state, "reviews\\01-需求评审.html"), state / "reviews" / "01-需求评审.html")
            self.assertEqual(locate(state, "raw/reviews/01-需求评审.html"), state / "reviews" / "01-需求评审.html", "旧写法 raw/... 仍指向状态根的同名文件夹")
            with self.assertRaises(ProjectError):
                relative_to_project(state, Path(tmp) / "elsewhere" / "a.html")
            with self.assertRaises(ProjectError) as wrong:
                relative_to_project(state, deliver / "notes.txt")
            self.assertIn("成果放 docs", str(wrong.exception))

    def test_registered_files_keep_the_root_they_were_registered_from(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("登记位置", tmp)
            deliver = Path(tmp) / "work" / "014-登记位置"
            page = deliver / "docs" / "02-产品开发" / "01-系统架构.html"
            page.write_text("<html>架构</html>", encoding="utf-8")
            review = state / "reviews" / "01-需求评审.html"
            review.parent.mkdir()
            review.write_text("<html>评审</html>", encoding="utf-8")
            self.assertEqual(register_artifact(state, "architecture", page, "html")["path"], "docs/02-产品开发/01-系统架构.html")
            self.assertEqual(register_artifact(deliver, "requirements", review, "html")["path"], "reviews/01-需求评审.html")
            self.assertEqual(register_artifact(state, "architecture", "docs/02-产品开发/01-系统架构.html", "html")["version"], 1, "相对路径按同一规则找到文件")
            self.assertEqual(validate_project(state), [])


class LegacyProjectTests(unittest.TestCase):
    """A project made before the two roots has no deliver_root: its project root is both roots and everything keeps working there."""

    def test_the_old_layout_is_one_root_with_the_tool_folders_under_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("旧项目", tmp)
            self.assertTrue(is_legacy(root))
            self.assertEqual(resolve_state_root(root), root.resolve())
            self.assertEqual(deliver_root(root), root.resolve())
            self.assertEqual(locate(root, "raw/reviews/01-需求评审.html"), root / "raw" / "reviews" / "01-需求评审.html")
            self.assertEqual(locate(root, "docs/01-需求对接/01-需求说明书.pdf"), root / "docs" / "01-需求对接" / "01-需求说明书.pdf")
            self.assertEqual(render_project(root), [], "旧布局没有会话，没有汇总页")
            deliverables = {d["path"] for s in load_project(root)["stages"] for d in s["deliverables"]}
            self.assertIn("raw/reviews/01-需求评审.html", deliverables)
            self.assertNotIn("reviews/01-需求评审.html", deliverables)
            self.assertEqual(validate_project(root, strict=True), [])

    def test_a_stage_is_approved_in_the_old_layout_as_before(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("旧项目", tmp)
            page = root / "raw" / "reviews" / "01-需求评审.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text("<html><body><h1>需求</h1></body></html>", encoding="utf-8")
            register_artifact(root, "requirements", page, "html")
            fx.requirements_provided(root)
            self.assertTrue((root / "raw" / "uploads" / "客户需求说明.docx").is_file())
            complete_fixture(evidence_session(root), "luz-project", "requirements")
            self.assertTrue((root / "raw" / "00-crawl" / "luz-project-requirements.json").is_file())
            approve_stage(root, "requirements", "需求范围确认", "用户")
            self.assertEqual(validate_project(root, strict=True), [])
            context = stage_context(root, "research")
            self.assertEqual(context["state_root"], context["deliver_root"])
            self.assertEqual(Path(context["output_root"]), root.resolve() / "docs" / "01-需求对接")

    def test_check_reports_only_the_docs_rules_and_points_at_migrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("旧项目", tmp)
            os.environ["LUZ_PROJECT_OUTPUT"] = str(Path(tmp) / "out")
            code, text = run("check", str(root))
            self.assertEqual(code, 0, text)
            self.assertIn("migrate", text)
            (root / "docs" / "03-验收交付" / "随手.docx").write_text("x", encoding="utf-8")
            errors = validate_project(root)
            self.assertTrue(any("随手.docx" in e for e in errors), errors)
            self.assertFalse(any("project.json" in e for e in errors), "旧布局的状态文件在项目根里是正常的")


class MigrateTests(unittest.TestCase):
    def approved(self, tmp: str) -> Path:
        """An old-layout project with a registered review page, an upload, a Crawl record and an approved requirements stage, plus files of the older docs layouts."""
        root = legacy_project("旧项目", tmp)
        page = root / "raw" / "reviews" / "01-需求评审.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("<html><body><h1>需求</h1></body></html>", encoding="utf-8")
        register_artifact(root, "requirements", page, "html")
        fx.requirements_provided(root)
        crawled_outside(root, tmp, "luz-project", "requirements")
        approve_stage(root, "requirements", "需求范围确认", "用户")
        (root / "docs" / "03-验收交付" / "使用说明.pdf").write_text("手册", encoding="utf-8")                # a handover file from before the numbers
        (root / "docs" / "01-需求对接" / "00-客户原始资料").mkdir()
        (root / "docs" / "01-需求对接" / "00-客户原始资料" / "客户清单.docx").write_text("原件", encoding="utf-8")
        (root / "src").mkdir(exist_ok=True)
        (root / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
        (root / "data" / "seeds").mkdir()
        (root / "data" / "seeds" / "users.json").write_text("[]", encoding="utf-8")
        (root / "config" / "environments.json").write_text("{}", encoding="utf-8")
        (root / "raw" / "architecture-tools").mkdir()
        (root / "raw" / "architecture-tools" / "build.py").write_text("pass\n", encoding="utf-8")
        return root

    def test_a_preview_changes_nothing_and_says_what_would_move_and_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.approved(tmp)
            before = tree(root)
            result = migrate_project(root, output=Path(tmp) / "out")
            self.assertEqual(tree(root), before, "预演不改任何文件")
            self.assertFalse((Path(tmp) / "out").exists(), "预演不建会话")
            moves = "\n".join(result["move"])
            for expected in ("project.json  →  [状态根] project.json", "raw/reviews  →  [状态根] reviews", "raw/00-crawl  →  [状态根] 00-crawl", "raw/uploads  →  [状态根] uploads",
                             "raw/architecture-tools  →  [状态根] architecture-tools", "data/client  →  [状态根] data/client", "config/paths.json  →  [状态根] config/paths.json",
                             "README.html  →  [状态根] backup/README.html", "docs/README.md  →  [状态根] backup/docs-README.md",
                             "docs/03-验收交付/使用说明.pdf  →  [项目目录] docs/03-验收交付/01-使用说明.pdf",
                             "docs/01-需求对接/00-客户原始资料/客户清单.docx  →  [状态根] uploads/客户清单.docx"):
                self.assertIn(expected, moves)
            for stays in ("src", "data/seeds", "config/environments.json", ".gitignore"):
                self.assertNotIn(f"{stays}  →", moves, f"{stays} 是成果，留在项目目录")
            self.assertIn("预演", result["mode"])
            self.assertEqual(Path(result["state_root"]), (Path(tmp) / "out" / "014-旧项目" / "raw").resolve())
            self.assertEqual(Path(result["deliver_root"]), root.resolve())
            self.assertTrue(any("data/artifacts.json" in r for r in result["rewrite"]), result["rewrite"])

    def test_apply_moves_the_state_out_keeps_the_results_and_leaves_every_approval_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.approved(tmp)
            out = Path(tmp) / "out"
            before = json.loads((root / "data" / "artifacts.json").read_text(encoding="utf-8"))
            hashes = {a["id"]: a["sha256"] for a in before}
            approvals = (root / "APPROVALS.json").read_bytes()
            result = migrate_project(root, apply=True, output=out)
            state = Path(result["state_root"])
            session = state.parent
            self.assertEqual(sorted(p.name for p in session.iterdir()), ["014-旧项目.html", "raw"])
            for gone in ("project.json", "MANIFEST.json", "APPROVALS.json", "README.html", "raw", "backup"):
                self.assertFalse((root / gone).exists(), gone)
            self.assertFalse((root / "data" / "client").exists() or (root / "data" / "artifacts.json").exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()), [".gitignore", "assets", "config", "data", "docs", "infra", "scripts", "src", "test"])
            self.assertEqual(sorted(p.name for p in (root / "config").iterdir()), ["environments.json"], "Luz 工具的 config 文件搬走，产品自己的留下")
            self.assertEqual(sorted(p.name for p in (root / "data").iterdir()), ["seeds"])
            self.assertEqual((root / "config" / "environments.json").read_text(encoding="utf-8"), "{}", "产品自己的配置留在项目目录")
            self.assertTrue((root / "src" / "app.py").is_file() and (root / "data" / "seeds" / "users.json").is_file())
            self.assertEqual(sorted(p.name for p in (root / "docs").iterdir()), ["01-需求对接", "02-产品开发", "03-验收交付"])
            self.assertEqual([p.name for p in (root / "docs" / "03-验收交付").iterdir()], ["01-使用说明.pdf"], "交付文件补上两位序号")
            self.assertEqual(list((root / "docs" / "01-需求对接").iterdir()), [])
            self.assertTrue((state / "uploads" / "客户清单.docx").is_file() and (state / "uploads" / "客户需求说明.docx").is_file())
            self.assertTrue((state / "reviews" / "01-需求评审.html").is_file() and (state / "00-crawl" / "luz-project-requirements.json").is_file())
            self.assertTrue((state / "architecture-tools" / "build.py").is_file())
            self.assertTrue((state / "backup" / "README.html").is_file() and (state / "backup" / "docs-README.md").is_file())
            manifest = json.loads((state / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(manifest["deliver_root"]), root.resolve())
            self.assertEqual(manifest["crawl"]["evidence_index"], "00-crawl")
            self.assertEqual(manifest["schema_version"], "1.2")
            self.assertEqual((state / "APPROVALS.json").read_bytes(), approvals, "审批记录原样搬过去")
            after = json.loads((state / "data" / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual({a["id"]: a["sha256"] for a in after}, hashes, "移动不改内容，审批绑定的哈希不变")
            self.assertTrue(all(not a["path"].startswith("raw/") for a in after))
            self.assertIn("reviews/01-需求评审.html", {a["path"] for a in after})
            self.assertFalse(is_legacy(state))
            requirements = next(s for s in manifest["stages"] if s["id"] == "requirements")
            self.assertEqual([d["path"] for d in requirements["deliverables"]][1], "reviews/01-需求评审.html")
            import check_output_layout
            self.assertEqual(check_output_layout.check_project(root)[0], [])
            self.assertEqual(check_output_layout.check_session(session, False)[0], [])
            self.assertEqual(result["leftovers"], [])
            # The Crawl record that the approval binds names its logs by the absolute paths they had in the old project root: it cannot be rewritten, and
            # crawl_gate reads the logs from the same place below the new evidence folder (their hashes are still checked).
            self.assertEqual(validate_project(state, strict=True), [])
            log = next((state / "00-crawl" / "logs").rglob("doctor.json"))
            log.write_text('{"ready": false}', encoding="utf-8")
            self.assertTrue(any("Crawl" in e for e in validate_project(state)), "搬家后日志的哈希照样核对，被改过的日志通不过")

    def test_the_summary_page_is_written_and_a_second_migration_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.approved(tmp)
            out = Path(tmp) / "out"
            result = migrate_project(root, apply=True, output=out)
            page = (Path(result["state_root"]).parent / "014-旧项目.html").read_text(encoding="utf-8")
            self.assertIn("<h1>旧项目项目总览</h1>", page)
            self.assertIn("需求对接", page)
            with self.assertRaises(ProjectError):
                migrate_project(root, apply=True, output=out)             # project.json is gone from the project directory
            os.environ["LUZ_PROJECT_OUTPUT"] = str(out)
            again = migrate_project(root, output=out)                      # the project directory now stands for the new project: nothing left to move
            self.assertEqual(again["move"], [])
            self.assertIn("两个根已分开", again["layout"])

    def test_the_new_session_must_not_exist_and_the_directory_name_must_carry_a_serial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("旧项目", tmp)
            blocker = Path(tmp) / "out" / "014-旧项目" / "raw"
            blocker.mkdir(parents=True)
            (blocker / "something").write_text("x", encoding="utf-8")
            with self.assertRaises(ProjectError) as taken:
                migrate_project(root, output=Path(tmp) / "out")
            self.assertIn("已存在", str(taken.exception))
            renamed = root.parent / "没有序号"
            root.rename(renamed)
            with self.assertRaises(ProjectError) as named:
                migrate_project(renamed, output=Path(tmp) / "out2")
            self.assertIn("三位序号", str(named.exception))

    def test_files_of_the_older_docs_layouts_go_to_their_flat_places_in_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = legacy_project("旧项目", tmp)
            for relative, stage in {"docs/02-产品开发/00-需求与方案/01-需求对接.html": "requirements", "docs/02-产品开发/03-后端设计规范.html": "technical-plan",
                                    "docs/02-产品开发/原型/01-小程序原型.html": "design"}.items():
                file = root / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(f"<html><body><h1>{relative}</h1></body></html>", encoding="utf-8")
                register_artifact(root, stage, file, "html")
            hashes = {a["stage"]: a["sha256"] for a in json.loads((root / "data" / "artifacts.json").read_text(encoding="utf-8"))}
            result = migrate_project(root, apply=True, output=Path(tmp) / "out")
            state = Path(result["state_root"])
            now = {a["stage"]: a for a in json.loads((state / "data" / "artifacts.json").read_text(encoding="utf-8"))}
            self.assertEqual(now["requirements"]["path"], "reviews/01-需求评审.html")
            self.assertEqual(now["technical-plan"]["path"], "docs/02-产品开发/05-后端设计规范.html")
            self.assertEqual(now["design"]["path"], "docs/02-产品开发/03-小程序原型.html")
            for stage, record in now.items():
                self.assertEqual(hashlib.sha256(locate(state, record["path"]).read_bytes()).hexdigest(), hashes[stage])
            self.assertFalse((root / "docs" / "02-产品开发" / "00-需求与方案").exists() or (root / "docs" / "02-产品开发" / "原型").exists())
            self.assertEqual(result["leftovers"], [])


class CommandLineTests(unittest.TestCase):
    def test_init_check_and_context_through_the_command_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deliver, out = Path(tmp) / "work" / "021-命令行", Path(tmp) / "out"
            os.environ["LUZ_PROJECT_OUTPUT"] = str(out)
            code, text = run("init", "命令行项目", "--project-dir", str(deliver), "--output-root", str(out))
            self.assertEqual(code, 0, text)
            info = json.loads(text)
            self.assertEqual(Path(info["project"]), deliver.resolve())
            self.assertEqual(Path(info["state_root"]), (out / "021-命令行" / "raw").resolve())
            self.assertTrue(Path(info["summary"]).is_file())
            self.assertEqual(sorted(p.name for p in deliver.iterdir()), [".env.example", ".gitignore", "docs"])
            for given in (deliver, out / "021-命令行", out / "021-命令行" / "raw"):
                code, text = run("check", str(given), "--strict")
                self.assertEqual(code, 0, text)
                code, text = run("context", str(given), "requirements")
                context = json.loads(text)
                self.assertEqual(Path(context["state_root"]), (out / "021-命令行" / "raw").resolve())
                self.assertEqual(Path(context["deliver_root"]), deliver.resolve())
                self.assertEqual(Path(context["output_root"]), deliver.resolve() / "docs" / "01-需求对接")
            code, text = run("init", "命令行项目", "--project-dir", str(deliver), "--output-root", str(out))
            self.assertEqual(code, 2, "同一个项目不能 init 两次")
            code, text = run("init", "没序号", "--project-dir", str(Path(tmp) / "work" / "没序号"), "--output-root", str(out))
            self.assertEqual(code, 2)
            self.assertIn("三位序号", text)

    def test_check_reports_a_source_file_in_the_project_directory_as_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("混入", tmp)
            deliver = Path(tmp) / "work" / "014-混入"
            code, _ = run("check", str(deliver))
            self.assertEqual(code, 0)
            (deliver / "raw").mkdir()
            (deliver / "README.html").write_text("<html></html>", encoding="utf-8")
            (deliver / "docs" / "01-需求对接" / "草稿.docx").write_text("x", encoding="utf-8")
            code, text = run("check", str(deliver))
            self.assertEqual(code, 1)
            errors = json.loads(text)["errors"]
            self.assertTrue(any("raw" in e and "不保存源文件或过程文件" in e for e in errors), errors)
            self.assertTrue(any("README.html" in e for e in errors), errors)
            self.assertTrue(any("草稿.docx" in e for e in errors), errors)
            (deliver / "MANIFEST.json").write_text("{}", encoding="utf-8")
            code, text = run("check", str(state))
            self.assertEqual(code, 1, "从状态根检查也读同一个项目目录")
            self.assertTrue(any("MANIFEST.json" in e for e in json.loads(text)["errors"]))

    def test_migrate_previews_by_default_and_applies_only_with_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, out = legacy_project("旧命令行", tmp), Path(tmp) / "out"
            before = tree(root)
            code, text = run("migrate", str(root), "--output-root", str(out))
            self.assertEqual(code, 0, text)
            self.assertIn("预演", json.loads(text)["mode"])
            self.assertEqual(tree(root), before)
            code, text = run("migrate", str(root), "--apply", "--output-root", str(out))
            self.assertEqual(code, 0, text)
            result = json.loads(text)
            self.assertEqual(result["mode"], "已执行")
            self.assertTrue((Path(result["state_root"]) / "project.json").is_file())
            self.assertFalse((root / "project.json").exists())
            os.environ["LUZ_PROJECT_OUTPUT"] = str(out)
            code, text = run("check", str(root), "--strict")
            self.assertEqual(code, 0, text)

    def test_sessions_of_other_skills_are_recorded_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("会话索引", tmp)
            session = Path(tmp) / "skill" / "Luz-Design" / "003-配色"
            code, text = run("session", str(state), "add", "--skill", "Luz-Design", "--path", str(session), "--stage", "design", "--note", "配色方案")
            self.assertEqual(code, 0, text)
            run("session", str(state), "add", "--skill", "Luz-Design", "--path", str(session), "--note", "再次登记")
            code, text = run("session", str(state), "list")
            listed = json.loads(text)
            self.assertEqual(len(listed), 1, "同一个会话只记一次")
            self.assertEqual(listed[0]["note"], "再次登记")
            code, text = run("session", str(state), "add", "--skill", "Luz-Design", "--path", str(session), "--stage", "没有这个阶段")
            self.assertEqual(code, 2)
            render_project(state)
            self.assertIn("003-配色", (state.parent / "014-会话索引.html").read_text(encoding="utf-8"))


class ContextTests(unittest.TestCase):
    def test_the_context_names_both_roots_and_resolves_the_inputs_in_each(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("上下文", tmp)
            deliver = Path(tmp) / "work" / "014-上下文"
            page = state / "reviews" / "01-需求评审.html"
            page.parent.mkdir()
            page.write_text("<html>评审</html>", encoding="utf-8")
            doc = deliver / "docs" / "01-需求对接" / "01-需求说明书.pdf"
            doc.write_text("pdf", encoding="utf-8")
            register_artifact(state, "requirements", page, "html")
            register_artifact(state, "requirements", doc, "requirements-pdf")
            context = stage_context(deliver, "research")
            self.assertEqual(Path(context["state_root"]), state.resolve())
            self.assertEqual(Path(context["deliver_root"]), deliver.resolve())
            self.assertEqual(Path(context["session"]), state.parent.resolve())
            inputs = {i["path"]: Path(i["absolute_path"]) for i in context["inputs"]}
            self.assertEqual(inputs["reviews/01-需求评审.html"], page)
            self.assertEqual(inputs["docs/01-需求对接/01-需求说明书.pdf"], doc)
            self.assertEqual(context["crawl"]["evidence_index"], "00-crawl")
            self.assertEqual(Path(context["output_root"]), deliver.resolve() / "docs" / "01-需求对接")


if __name__ == "__main__":
    unittest.main()
