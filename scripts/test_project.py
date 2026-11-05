from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
from test_crawl_preflight import complete_fixture

from client_fixture import new_project
from legacy_fixture import legacy_project
from crawl_gate import evidence_session
from project_paths import locate
from project_core import (  # type: ignore[import-not-found]
    approve_stage,
    register_artifact,
    render_project,
    validate_project,
)


class ProjectScaffoldTests(unittest.TestCase):
    def test_init_creates_the_session_with_the_state_root_and_the_project_directory_with_results_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("示例项目", tmp, repository="D:/repo/example")
            session, deliver = state.parent, Path(tmp) / "work" / "014-示例项目"
            self.assertEqual(sorted(p.name for p in session.iterdir()), ["014-示例项目.html", "raw"], "会话根只有 raw 和同名汇总页")
            self.assertEqual(state.name, "raw")
            self.assertEqual(sorted(p.name for p in state.iterdir()), ["APPROVALS.json", "MANIFEST.json", "config", "data", "project.json"])
            self.assertEqual(sorted(p.name for p in (state / "data").iterdir()), ["artifacts.json", "changes.json", "client", "ops", "project.json", "stages"])
            self.assertEqual(sorted(p.name for p in (state / "config").iterdir()), ["documents.json", "keys.example.json", "paths.json"])
            self.assertEqual(sorted(p.name for p in deliver.iterdir()), [".env.example", ".gitignore", "docs"], "项目目录只有成果，src 等有东西要写时才建")
            self.assertEqual(sorted(p.name for p in (deliver / "docs").iterdir()), ["01-需求对接", "02-产品开发", "03-验收交付"])
            for folder in ("01-需求对接", "02-产品开发", "03-验收交付"):
                self.assertEqual(list((deliver / "docs" / folder).iterdir()), [], f"docs/{folder} 开始是空的，只有一层")
            manifest = json.loads((state / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["repository"], "D:/repo/example")
            self.assertEqual(manifest["status"], "draft")
            self.assertEqual(manifest["project_id"], "PROJECT-014")
            self.assertEqual(Path(manifest["deliver_root"]), deliver.resolve())
            self.assertEqual(manifest["schema_version"], "1.2")
            import check_output_layout
            self.assertEqual(check_output_layout.check_project(deliver)[0], [])
            self.assertEqual(check_output_layout.check_session(session, False)[0], [])

    def test_artifact_registration_renders_the_summary_page_and_the_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("文档项目", tmp)
            artifact = project / "reviews" / "需求.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html><body><h1>需求</h1></body></html>", encoding="utf-8")
            record = register_artifact(project, "requirements", artifact, "html", ["SRC-001"])
            self.assertEqual(record["stage"], "requirements")
            self.assertEqual(record["path"], "reviews/需求.html", "状态根里的文件，路径相对状态根")
            self.assertTrue(record["sha256"])
            pages = render_project(project)
            self.assertEqual(pages, [project.parent / "014-文档项目.html"])
            self.assertFalse((project / "README.html").exists() and True, "状态根里不再有 README.html")
            self.assertFalse((Path(tmp) / "work" / "014-文档项目" / "README.html").exists())
            artifacts = json.loads((project / "data" / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(artifacts[0]["source_ids"], ["SRC-001"])

    def test_approval_and_validation_require_current_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("审批项目", tmp)
            artifact = project / "reviews" / "需求.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html><body><h1>需求</h1></body></html>", encoding="utf-8")
            register_artifact(project, "requirements", artifact, "html")
            import client_fixture
            client_fixture.requirements_provided(project)
            complete_fixture(evidence_session(project), "luz-project", "requirements")
            approve_stage(project, "requirements", "需求范围确认", "用户")
            errors = validate_project(project, strict=True)
            self.assertEqual(errors, [])

    def test_the_summary_page_lists_results_stages_and_sessions_in_the_standard_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("索引项目", tmp)
            deliver = Path(tmp) / "work" / "014-索引项目"
            summary = project.parent / "014-索引项目.html"
            page = summary.read_text(encoding="utf-8")
            self.assertTrue(page.lstrip().startswith("<!doctype html>"))
            self.assertEqual(page.count("<h1>"), 1)
            self.assertIn("<h1>索引项目项目总览</h1>", page)
            self.assertIn("阶段与审批", page)
            self.assertNotIn("<h2>成果</h2>", page, "没有成果的节不写")
            for stub in ("architecture.html", "design.html", "technical-plan.html", "implementation.html"):
                self.assertFalse((deliver / "docs" / "02-产品开发" / stub).exists(), stub)
            doc = deliver / "docs" / "02-产品开发" / "01-系统架构.html"
            doc.write_text("<html>x</html>", encoding="utf-8")
            register_artifact(project, "architecture", doc, "html")
            render_project(project)
            page = summary.read_text(encoding="utf-8")
            self.assertIn("<h2>成果</h2>", page)
            self.assertIn("docs\\02-产品开发\\01-系统架构.html", page, "成果的位置是项目内的相对路径")
            self.assertIn("系统架构", page)
            import project_summary
            project_summary.register_session(project, "Luz-System", Path(tmp) / "skill" / "Luz-System" / "005-系统设计", "architecture", "系统架构页")
            render_project(project)
            page = summary.read_text(encoding="utf-8")
            self.assertIn("<h2>技能会话</h2>", page)
            self.assertIn("Luz-System", page)
            import check_output_layout
            self.assertEqual(check_output_layout.check_session(project.parent, False)[0], [])

    def test_every_developer_document_has_a_numbered_chinese_name(self) -> None:
        from project_core import stage_document_path
        names = {s: stage_document_path(s) for s in ("requirements", "research", "proposal", "client-intake", "architecture", "design", "technical-plan", "implementation")}
        for stage, name in (("requirements", "01-需求评审"), ("research", "02-调研结论"), ("proposal", "03-方案评审"), ("client-intake", "04-业务逻辑确认评审")):
            self.assertEqual(names[stage], f"reviews/{name}.html")                 # the review pages are internal: the state root's reviews, not docs
        self.assertEqual(names["architecture"], "docs/02-产品开发/01-系统架构.html")
        self.assertEqual(names["design"], "docs/02-产品开发/02-前端界面设计.html")
        self.assertEqual(names["technical-plan"], "docs/02-产品开发/05-后端设计规范.html")
        self.assertEqual(names["implementation"], "docs/02-产品开发/06-实现报告.html")
        for path in names.values():
            self.assertRegex(Path(path).name, r"^\d\d-[\u4e00-\u9fff]+\.html$")
            self.assertTrue(path.startswith(("reviews/", "docs/02-产品开发/")), path)

    def test_secret_and_hash_drift_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("安全项目", tmp)
            artifact = project / "reviews" / "secret.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html>" + "sk-" + "x" * 32 + "</html>", encoding="utf-8")      # built at run time so the source holds no key-shaped literal
            register_artifact(project, "requirements", artifact, "html")
            self.assertTrue(any("秘密" in error for error in validate_project(project)))
            artifact.write_text("<html>safe</html>", encoding="utf-8")
            self.assertTrue(any("哈希" in error for error in validate_project(project)))


class DocsLayoutTests(unittest.TestCase):
    """The project directory holds results only: docs/ has three folders, one level each, and the folder names say what goes in."""

    def test_the_check_names_every_misplaced_file_and_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("目录检查", tmp)
            deliver = Path(tmp) / "work" / "014-目录检查"
            self.assertEqual(validate_project(project), [])
            (deliver / "docs/02-产品开发/原型").mkdir()
            (deliver / "docs/02-产品开发/原型/演示.html").write_text("<html>x</html>", encoding="utf-8")
            (deliver / "docs/02-产品开发/说明.md").write_text("# 旧说明", encoding="utf-8")
            (deliver / "docs/02-产品开发/方案.pdf").write_text("x", encoding="utf-8")
            (deliver / "docs/01-需求对接/07-需求评审.html").write_text("<html>x</html>", encoding="utf-8")
            (deliver / "docs/01-需求对接/00-客户原始资料").mkdir()
            (deliver / "docs/01-需求对接/随手.docx").write_text("x", encoding="utf-8")
            (deliver / "docs/03-验收交付/交付资料").mkdir()
            (deliver / "docs/03-验收交付/使用说明.pdf").write_text("x", encoding="utf-8")
            (deliver / "docs/多余").mkdir()
            (deliver / "docs/随手.docx").write_text("x", encoding="utf-8")
            errors = "\n".join(validate_project(project))
            for expected in ("02-产品开发 平铺", "说明.md", "方案.pdf", "00-客户原始资料", "01-需求对接 只放", "07-需求评审.html", "交付资料", "docs 下只能是", "多出 多余", "多出文件 随手.docx", "使用说明.pdf 应以两位序号开头"):
                self.assertIn(expected, errors)

    def test_source_and_process_files_in_the_project_directory_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("混入检查", tmp)
            deliver = Path(tmp) / "work" / "014-混入检查"
            for folder in ("raw/00-crawl", "reviews", "uploads", "client-docs", "backup"):
                (deliver / folder).mkdir(parents=True)
            for name in ("project.json", "MANIFEST.json", "APPROVALS.json", "README.html", "x.tmp"):
                (deliver / name).write_text("{}", encoding="utf-8")
            (deliver / "data/client").mkdir(parents=True)
            (deliver / "data/stages").mkdir(parents=True)
            (deliver / "config").mkdir()
            (deliver / "config/paths.json").write_text("{}", encoding="utf-8")
            (deliver / "data/seeds").mkdir()
            (deliver / "src").mkdir()
            (deliver / "docs/README.md").write_text("# 导航", encoding="utf-8")
            errors = validate_project(project)
            text = "\n".join(errors)
            for expected in ("raw\\", "reviews\\", "uploads\\", "client-docs\\", "backup\\", "project.json", "MANIFEST.json", "APPROVALS.json", "README.html", "x.tmp", "data\\client", "data\\stages", "config\\paths.json", "docs 下只有三个目录，多出文件 README.md"):
                self.assertIn(expected, text)
            self.assertNotIn("data\\seeds", text, "开发与测试用的业务数据和 src 是成果，不报错")
            self.assertNotIn("src", text)

    def test_a_requirement_page_in_the_development_folder_and_the_reverse_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("阶段目录", tmp)
            wrong = locate(project, "docs/02-产品开发/01-需求评审.html")
            wrong.write_text("<html>x</html>", encoding="utf-8")
            register_artifact(project, "requirements", wrong, "html")
            wrong_dev = locate(project, "docs/01-需求对接/01-系统架构.html")
            wrong_dev.write_text("<html>y</html>", encoding="utf-8")
            register_artifact(project, "architecture", wrong_dev, "html")
            errors = "\n".join(validate_project(project))
            self.assertIn("requirements 阶段的 .html 文件放 reviews", errors)
            self.assertIn("architecture 阶段的 .html 文件放 docs/02-产品开发", errors)


class DirectoryContractTests(unittest.TestCase):
    def deliverables(self):
        from project_core import load_matrix
        return [(s["id"], d) for s in load_matrix()["stages"] for d in s.get("deliverables", [])]

    def test_what_the_client_receives_is_pdf_or_xlsx_in_the_two_client_folders(self) -> None:
        for stage, d in self.deliverables():
            if d["audience"] == "client":
                with self.subTest(stage=stage, deliverable=d["id"]):
                    self.assertIn(d["format"], {"pdf", "xlsx"})
                    self.assertTrue(d["path"].startswith(("docs/01-需求对接/", "docs/03-验收交付/")), d["path"])
                    self.assertTrue(d["path"].endswith("." + d["format"]), d["path"])

    def test_every_file_sits_in_the_folder_its_stage_names(self) -> None:
        from project_core import expected_doc_folder
        for stage, d in self.deliverables():
            with self.subTest(stage=stage, deliverable=d["id"]):
                folder = "/".join(d["path"].split("/")[:-1])
                self.assertEqual(folder, expected_doc_folder(stage, "." + d["format"]), d["path"])

    def test_every_deliverable_has_a_two_digit_number_and_the_numbers_do_not_repeat(self) -> None:
        paths = [d["path"] for _, d in self.deliverables()]
        for path in paths:
            self.assertRegex(Path(path).name, r"^\d{2}-.+", f"成果文件名是 NN-名称: {path}")
            self.assertEqual(len(path.split("/")), 3 if path.startswith("docs/") else 2, f"docs 下只有一层目录，评审页平铺在 reviews: {path}")
        for folder in ("docs/02-产品开发/", "docs/03-验收交付/", "reviews/"):               # 01-需求对接 has 05 twice: the form and the client's filled copy
            numbers = [Path(p).name[:2] for p in paths if p.startswith(folder)]
            self.assertEqual(len(numbers), len(set(numbers)), f"{folder} 里的序号不能重复")
        for p in paths:
            if p.startswith("docs/02-产品开发/"):
                self.assertTrue(p.endswith(".html"), p)

    def test_the_handover_folder_is_numbered_in_the_order_the_documents_are_made(self) -> None:
        names = sorted(Path(d["path"]).name for _, d in self.deliverables() if d["path"].startswith("docs/03-验收交付/"))
        self.assertEqual(names, ["01-使用说明.pdf", "02-验收清单.xlsx", "03-需求变更台账-交付快照.xlsx", "04-验收测试报告.pdf", "05-发布说明.pdf", "06-运维手册.pdf", "07-用户协议.pdf", "08-隐私政策.pdf"])


class LinkValidationTests(unittest.TestCase):
    """A page's links are its static markup; template strings in a script or style body are code, not files."""

    def check(self, body: str) -> list[str]:
        import project_core
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs" / "02"
            root.mkdir(parents=True)
            page = root / "p.html"
            page.write_text(body, encoding="utf-8")
            return project_core._validate_links(page)

    def test_template_strings_inside_a_script_are_not_links(self) -> None:
        body = ("<!doctype html><html><body><script>const a = `<img src=\"${P(i)}\"><a href='%23s'>x</a>`;"
                "const b = '<img src=\"${ASSETS.icons[st][n]}\">';</script><style>.x{background:url(missing.png)}</style></body></html>")
        self.assertEqual(self.check(body), [])

    def test_a_broken_static_link_is_still_reported(self) -> None:
        errors = self.check('<!doctype html><html><body><a href="nowhere.html">x</a><img src="gone.png"></body></html>')
        self.assertEqual(len(errors), 2, errors)

    def test_the_src_of_a_script_tag_is_still_checked_and_comments_are_skipped(self) -> None:
        errors = self.check('<!doctype html><html><body><!-- <a href="old.html">x</a> --><script src="missing.js"></script></body></html>')
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("missing.js", errors[0])


class InitContractTests(unittest.TestCase):
    """init makes what project-structure.md lists, one level, and nothing a stage has not yet filled."""

    def test_init_makes_only_the_first_level_and_the_data_and_config_it_uses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("目录契约", tmp)
            deliver = Path(tmp) / "work" / "014-目录契约"
            self.assertEqual(sorted(p.name for p in state.iterdir() if p.is_dir()), ["config", "data"], "00-crawl、reviews、uploads 等有东西要写时才建")
            self.assertEqual(sorted(p.name for p in deliver.iterdir() if p.is_dir()), ["docs"], "src、test、assets、infra、scripts 有东西要写时才建")
            self.assertEqual(sorted(p.name for p in (state / "data").iterdir() if p.is_dir()), ["client", "ops", "stages"])      # the folders the tools write to; acceptance, schema, users ... come with content
            self.assertFalse((state / "data" / "acceptance").exists())
            self.assertEqual(list((state / "data" / "stages").iterdir()), [])

    def test_config_holds_no_empty_files_and_data_no_unread_skeletons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = new_project("空文件", tmp)
            self.assertEqual(sorted(p.name for p in (state / "config").iterdir()), ["documents.json", "keys.example.json", "paths.json"])
            for name in ("project.json", "environments.json", "urls.json", "features.json", "validation.json"):
                self.assertFalse((state / "config" / name).exists(), f"config/{name} 由对应阶段写，不在 init 里造空文件")
            for relative in ("data/sources.json", "data/decisions.json", "crawl/evidence.json"):
                self.assertFalse((state / relative).exists(), f"{relative} 没有任何工具读取，不生成")
            paths = json.loads((state / "config/paths.json").read_text(encoding="utf-8"))
            self.assertNotIn("crawl", paths)
            self.assertNotIn("raw", paths)
            self.assertEqual(paths["docs"], "docs")

    def test_the_crawl_evidence_index_points_at_the_real_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("证据位置", tmp)
            manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["crawl"]["evidence_index"], "00-crawl")
            complete_fixture(evidence_session(project), "luz-project", "requirements")
            self.assertTrue((project / manifest["crawl"]["evidence_index"] / "luz-project-requirements.json").is_file())      # where the preflight really writes

    def test_the_gitignore_template_covers_secrets_dependencies_and_build_output_and_not_the_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            new_project("忽略清单", tmp)
            lines = (Path(tmp) / "work" / "014-忽略清单" / ".gitignore").read_text(encoding="utf-8").splitlines()
            for wanted in (".env", "node_modules/", "dist/", "build/"):
                self.assertIn(wanted, lines)
            self.assertIn("!.env.example", lines)
            self.assertFalse([line for line in lines if line.startswith("raw/")], "客户文档的构建中间件和上传件不在项目目录里")

    def test_the_contract_text_lists_what_init_makes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "references" / "project-structure.md").read_text(encoding="utf-8")
        tree = text.split("```")[1]                                                          # the directory tree of the contract
        for gone in ("sources.json", "decisions.json", "raw/crawl", "crawl/ 检索证据"):
            self.assertNotIn(gone, tree)
        for there in ("paths.json", "documents.json", "keys.example.json", "00-crawl", "baseline.json", "project.json", "docs", "reviews", "uploads", "client-docs"):
            self.assertIn(there, tree)
        self.assertIn("不预先建", text)

    def test_migrate_repoints_an_older_project_and_names_the_empty_skeletons_without_deleting_them(self) -> None:
        from project_core import migrate_project
        with tempfile.TemporaryDirectory() as tmp:
            project = legacy_project("旧骨架", tmp)
            manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
            manifest["crawl"]["evidence_index"] = "raw/crawl/evidence.json"
            for name in ("project.json", "MANIFEST.json", "data/project.json"):
                (project / name).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            (project / "raw/crawl").mkdir()
            (project / "raw/crawl/evidence.json").write_text(json.dumps({"task_id": None, "task_root": None, "sources": [], "coverage": [], "unresolved": []}), encoding="utf-8")
            (project / "data/sources.json").write_text("[]", encoding="utf-8")
            (project / ".gitignore").write_text("\n# Luz 客户文档构建中间件\nraw/client-docs/\n", encoding="utf-8")
            result = migrate_project(project, apply=True, output=Path(tmp) / "out")
            state = Path(result["state_root"])
            self.assertEqual(json.loads((state / "project.json").read_text(encoding="utf-8"))["crawl"]["evidence_index"], "00-crawl")
            self.assertNotIn("crawl", json.loads((state / "config/paths.json").read_text(encoding="utf-8")))
            lines = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines.count("raw/client-docs/"), 1)
            for wanted in (".env", "node_modules/", "dist/", "build/"):
                self.assertIn(wanted, lines)
            notes = "\n".join(result["notes"])
            self.assertIn("crawl/evidence.json 是空骨架", notes)
            self.assertIn("data/sources.json 是空骨架", notes)
            self.assertTrue((state / "crawl/evidence.json").is_file() and (project / "data/sources.json").is_file(), "migrate 只指出，不删")
            self.assertEqual(validate_project(state, strict=True), [])


class DesignDeliverablesTests(unittest.TestCase):
    """The design stage lists one prototype per front end of the project's own design document, named after that front end."""

    def design_spec(self, root: Path, frontends, surfaces=None) -> dict:
        import dev_fixture
        (root / "data" / "client").mkdir(parents=True, exist_ok=True)
        surfaces = surfaces or [surface for _, surface, _ in frontends]
        feats = [{"id": f"FN-{n + 1:03d}", "module": "M01", "name": f"功能{n + 1}", "surface": surface} for n, surface in enumerate(surfaces)]
        (root / "data" / "client" / "features.json").write_text(json.dumps({"modules": [{"id": "M01", "name": "登录"}], "features": feats}, ensure_ascii=False), encoding="utf-8")
        return dev_fixture.sample_spec("design", root, frontends)

    def named_prototypes(self, spec: dict, names: list[str]) -> None:
        """Give the fixture prototypes the file names the standard asks for: serial number, front end name, 原型."""
        for number, (tab, name) in enumerate(zip([t for t in spec["tabs"] if t.get("layout") == "frontend"], names), 3):
            for section in tab["sections"]:
                for block in section["blocks"]:
                    if block["type"] == "prototype":
                        block["file"] = f"docs/02-产品开发/{number:02d}-{name}原型.html"

    def design_item(self) -> dict:
        from project_core import load_matrix
        return next(s for s in load_matrix()["stages"] if s["id"] == "design")

    def write_design(self, project: Path, spec: dict) -> None:
        (project / "data" / "stages").mkdir(parents=True, exist_ok=True)
        (project / "data" / "stages" / "design.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    def test_without_a_design_document_the_matrix_default_stands(self) -> None:
        from project_core import stage_deliverables
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("默认原型", tmp)
            record = next(s for s in json.loads((project / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "design")
            default = self.design_item()["deliverables"]
            self.assertEqual(record["deliverables"], default)
            self.assertEqual(stage_deliverables(project, self.design_item()), default)

    def test_a_phone_page_and_a_back_office_give_two_prototypes_named_after_them(self) -> None:
        from project_core import migrate_project, stage_context
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("手机加后台", tmp)
            spec = self.design_spec(project, [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide")])
            self.named_prototypes(spec, ["手机", "后台"])
            self.write_design(project, spec)
            result = migrate_project(project, apply=True)
            record = next(s for s in json.loads((project / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "design")
            self.assertEqual([d["path"] for d in record["deliverables"]], ["docs/02-产品开发/02-前端界面设计.html", "docs/02-产品开发/03-手机原型.html", "docs/02-产品开发/04-后台原型.html"])
            self.assertEqual([d["name"] for d in record["deliverables"][1:]], ["手机页可交互原型", "管理后台可交互原型"])
            self.assertNotIn("小程序", json.dumps(record["deliverables"], ensure_ascii=False))
            self.assertTrue(all(d["kind"] == "prototype" and d["format"] == "html" and d["audience"] == "dev" for d in record["deliverables"][1:]))
            self.assertEqual(result["added"], [])
            context = stage_context(project, "design")                                                # context reads the design document too, not only the stored list
            self.assertEqual([d["path"] for d in context["client"]["deliverables"]][1:], ["docs/02-产品开发/03-手机原型.html", "docs/02-产品开发/04-后台原型.html"])
            self.assertEqual(context["document"], "docs/02-产品开发/02-前端界面设计.html")

    def test_context_follows_the_design_document_even_before_migrate_refreshes_the_stored_list(self) -> None:
        from project_core import stage_context
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("先上下文", tmp)
            spec = self.design_spec(project, [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide")])
            self.named_prototypes(spec, ["手机", "后台"])
            self.write_design(project, spec)
            stored = next(s for s in json.loads((project / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "design")
            self.assertIn("03-小程序原型.html", json.dumps(stored["deliverables"], ensure_ascii=False))       # the list stored by init is the matrix default
            shown = [d["path"] for d in stage_context(project, "design")["client"]["deliverables"]]
            self.assertNotIn("docs/02-产品开发/03-小程序原型.html", shown)
            self.assertIn("docs/02-产品开发/03-手机原型.html", shown)

    def test_a_mini_program_and_a_back_office_give_the_mini_program_name(self) -> None:
        from project_core import stage_deliverables
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("小程序加后台", tmp)
            spec = self.design_spec(project, None, surfaces=["miniprogram", "web-admin"])          # one tab per use: 小程序 and 管理后台
            self.assertEqual([t["title"] for t in spec["tabs"]], ["前端规范", "小程序", "管理后台", "检查与差异"])
            self.named_prototypes(spec, ["小程序", "后台"])
            self.write_design(project, spec)
            paths = [d["path"] for d in stage_deliverables(project, self.design_item())]
            self.assertEqual(paths[1:], ["docs/02-产品开发/03-小程序原型.html", "docs/02-产品开发/04-后台原型.html"])

    def test_three_front_ends_give_three_prototypes(self) -> None:
        from project_core import stage_deliverables
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("三端", tmp)
            spec = self.design_spec(project, [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide"), ("平板页", "web-admin", "phone")])
            self.named_prototypes(spec, ["手机", "后台", "平板"])
            self.write_design(project, spec)
            found = stage_deliverables(project, self.design_item())
            self.assertEqual([d["frontend"] for d in found if d["kind"] == "prototype"], ["手机页", "管理后台", "平板页"])
            self.assertEqual(len({d["id"] for d in found}), len(found), "每个交付物有自己的编号")

    def test_the_design_document_registers_its_prototypes_and_updates_the_deliverable_list(self) -> None:
        from project_core import stage_context
        from stage_documents import write_document
        import client_fixture as fx
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("登记原型", tmp)
            spec = self.design_spec(project, [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide")])
            fx.crawled(project, "design")
            write_document(project, "design", spec)
            artifacts = json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))
            design = [a for a in artifacts if a["stage"] == "design"]
            self.assertEqual(sorted(a["path"] for a in design if a["kind"] == "html"),
                             sorted(["docs/02-产品开发/02-前端界面设计.html", "docs/02-产品开发/03-proto1.html", "docs/02-产品开发/04-proto2.html"]))
            self.assertEqual(len({a["id"] for a in artifacts}), len(artifacts))
            record = next(s for s in json.loads((project / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "design")
            self.assertEqual([d["path"] for d in record["deliverables"]][1:], ["docs/02-产品开发/03-proto1.html", "docs/02-产品开发/04-proto2.html"])
            self.assertEqual(sorted(record["artifact_ids"]), sorted(a["id"] for a in design))
            self.assertTrue(all(d["registered"] and d["exists"] for d in stage_context(project, "design")["client"]["deliverables"]))
            write_document(project, "design", spec)                                                  # writing it again registers nothing twice
            again = json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(len(again), len(artifacts))
            self.assertEqual(validate_project(project, strict=True), [])

    def test_a_listed_prototype_that_does_not_exist_is_an_error_once_the_design_document_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("缺原型", tmp)
            document = locate(project, "docs/02-产品开发/02-前端界面设计.html")
            document.write_text("<html><body>x</body></html>", encoding="utf-8")
            self.assertEqual(validate_project(project), [])                                          # nothing registered yet: a stage still being written is not an error
            register_artifact(project, "design", document, "html")
            errors = validate_project(project)
            self.assertTrue(any("交付物不存在" in e and "03-小程序原型.html" in e and "design" in e for e in errors), errors)
            self.assertTrue(any("04-后台原型.html" in e for e in errors), errors)
            for name in ("03-小程序原型.html", "04-后台原型.html"):
                (locate(project, "docs/02-产品开发") / name).write_text("<html></html>", encoding="utf-8")
            self.assertEqual(validate_project(project), [])

    def test_only_html_deliverables_of_a_stage_with_a_registered_page_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("只查网页", tmp)
            page = project / "reviews/03-方案评审.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text("<html><body>x</body></html>", encoding="utf-8")
            register_artifact(project, "proposal", page, "html")                                      # the three client files of the proposal do not exist yet: approve and Ops gate those
            self.assertEqual(validate_project(project), [])


class ArtifactNumberTests(unittest.TestCase):
    """An artifact number names one registered file: never twice in a list, never handed out again."""

    def write(self, project: Path, name: str, text: str = "x") -> Path:
        path = project / "reviews" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<html><body>{text}</body></html>", encoding="utf-8")
        return path

    def test_a_number_listed_twice_in_a_stage_is_reported_and_registering_stops(self) -> None:
        from project_core import ProjectError, migrate_project
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("重复编号", tmp)
            register_artifact(project, "requirements", self.write(project, "01-需求评审.html"), "html")
            manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
            record = next(s for s in manifest["stages"] if s["id"] == "requirements")
            record["artifact_ids"].append(record["artifact_ids"][0])                                  # what happened to ART-030 of a real project
            for name in ("project.json", "MANIFEST.json", "data/project.json"):
                (project / name).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            errors = validate_project(project)
            self.assertTrue(any("产物编号重复" in e and "requirements" in e and "ART-001" in e for e in errors), errors)
            with self.assertRaises(ProjectError) as refused:
                register_artifact(project, "requirements", self.write(project, "另一页.html"), "html")
            self.assertIn("重复", str(refused.exception))
            self.assertTrue(any("requirements" in n and "重复" in n for n in migrate_project(project, apply=True)["notes"]))      # migrate drops the repeated entry ...
            self.assertEqual(validate_project(project), [])                                           # ... and the register works again
            register_artifact(project, "requirements", self.write(project, "另一页.html"), "html")

    def test_the_register_with_one_number_twice_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("登记表重复", tmp)
            register_artifact(project, "requirements", self.write(project, "a.html"), "html")
            register_artifact(project, "research", self.write(project, "b.html", "y"), "html")
            artifacts = json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))
            artifacts[1]["id"] = artifacts[0]["id"]
            (project / "data/artifacts.json").write_text(json.dumps(artifacts), encoding="utf-8")
            self.assertTrue(any("产物编号重复" in e and "data/artifacts.json" in e for e in validate_project(project)))

    def test_a_number_that_a_stage_still_lists_is_not_handed_out_again_after_its_file_was_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = new_project("不复用编号", tmp)
            first = register_artifact(project, "requirements", self.write(project, "a.html"), "html")
            second = register_artifact(project, "research", self.write(project, "b.html", "y"), "html")
            artifacts = [a for a in json.loads((project / "data/artifacts.json").read_text(encoding="utf-8")) if a["id"] != second["id"]]
            (project / "data/artifacts.json").write_text(json.dumps(artifacts), encoding="utf-8")      # removed by hand: the stage list still holds the number
            third = register_artifact(project, "research", self.write(project, "c.html", "z"), "html")
            self.assertEqual(first["id"], "ART-001")
            self.assertNotEqual(third["id"], second["id"], "编号用过就不再发")
            self.assertEqual(third["id"], "ART-003")


class ArchitectureBaselineTrackingTests(unittest.TestCase):
    """data/baseline.json belongs to the architecture stage for its stack and modules sections; the frontend section belongs to design."""

    def statement(self) -> dict:
        import baseline as bl
        return {"baseline_version": "1", "stack": {i["id"]: {"status": "沿用"} for i in bl.stack_items()}, "frontend": {i["id"]: {"status": "沿用"} for i in bl.frontend_items()},
                "modules": {m["id"]: {"status": "沿用"} for m in bl.functions()["modules"]}}

    def write(self, root: Path, statement: dict) -> None:
        (root / "data" / "baseline.json").write_text(json.dumps(statement, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_only_stack_and_modules_make_the_hash(self) -> None:
        import client_flow as cf
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("底座跟踪", tmp)
            self.assertEqual(cf.tracked_hashes(root, "architecture"), {})                             # no baseline.json yet: nothing to track
            statement = self.statement()
            self.write(root, statement)
            key = "data/baseline.json#stack,modules"
            self.assertEqual(list(cf.tracked_hashes(root, "architecture")), [key])
            before = cf.tracked_hashes(root, "architecture")[key]
            statement["frontend"][next(iter(statement["frontend"]))] = {"status": "调整", "value": "x", "reason": "design 阶段的改动"}
            statement["baseline_version"] = "2"
            self.write(root, statement)
            self.assertEqual(cf.tracked_hashes(root, "architecture")[key], before, "frontend 段和版本号不影响架构的哈希")
            statement["stack"][next(iter(statement["stack"]))] = {"status": "调整", "value": "x", "reason": "改了技术栈"}
            self.write(root, statement)
            self.assertNotEqual(cf.tracked_hashes(root, "architecture")[key], before)
            moved = self.statement()
            moved["modules"][next(iter(moved["modules"]))] = {"status": "不用", "reason": "本项目没有这个基础功能"}
            self.write(root, moved)
            self.assertNotEqual(cf.tracked_hashes(root, "architecture")[key], before)
            fresh = self.statement()
            reordered = {k: fresh[k] for k in ("modules", "frontend", "stack", "baseline_version")}      # the order of keys is not content
            self.write(root, reordered)
            self.assertEqual(cf.tracked_hashes(root, "architecture")[key], before)

    def approved_architecture(self, tmp: str) -> Path:
        import dev_fixture
        root = new_project("架构已批", tmp)
        self.write(root, self.statement())
        (root / "data" / "stages" / "architecture.json").write_text(json.dumps(dev_fixture.sample_spec("architecture", root), ensure_ascii=False), encoding="utf-8")
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        record = next(s for s in manifest["stages"] if s["id"] == "architecture")
        record["status"] = "approved"                                                              # a stage approved before the baseline was tracked: nothing recorded for it
        record["approved_sources"] = {}
        for name in ("project.json", "MANIFEST.json", "data/project.json"):
            (root / name).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return root

    def test_an_approved_architecture_before_the_tracking_is_not_turned_red_by_it(self) -> None:
        import client_flow as cf
        with tempfile.TemporaryDirectory() as tmp:
            root = self.approved_architecture(tmp)
            manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(cf.tracked_drift(root, manifest), [])
            statement = self.statement()
            statement["stack"][next(iter(statement["stack"]))] = {"status": "调整", "value": "x", "reason": "之后有人改了"}
            self.write(root, statement)
            self.assertEqual(cf.tracked_drift(root, manifest), [], "批准时没有记录的，不会因为新增的跟踪项突然报错")

    def test_migrate_binds_an_approved_architecture_only_when_its_document_still_agrees_with_the_file(self) -> None:
        from project_core import migrate_project
        with tempfile.TemporaryDirectory() as tmp:
            root = self.approved_architecture(tmp)
            result = migrate_project(root, apply=True)
            self.assertTrue(any("已纳入架构阶段的跟踪" in n for n in result["notes"]), result["notes"])
            record = next(s for s in json.loads((root / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "architecture")
            self.assertEqual(list(record["approved_sources"]), ["data/baseline.json#stack,modules"])
            approvals = json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]
            self.assertEqual(approvals, [], "migrate 不写任何审批记录")
            statement = self.statement()
            statement["frontend"][next(iter(statement["frontend"]))] = {"status": "调整", "value": "x", "reason": "design 阶段改 frontend 段"}
            self.write(root, statement)
            self.assertFalse(any("baseline" in e for e in validate_project(root)), "frontend 段的改动不使架构的批准失效")
            statement["stack"][next(iter(statement["stack"]))] = {"status": "调整", "value": "x", "reason": "有人改了技术栈"}
            self.write(root, statement)
            errors = validate_project(root)
            self.assertTrue(any("architecture" in e and "data/baseline.json" in e and "stack、modules" in e and "已变化" in e for e in errors), errors)

    def test_migrate_does_not_bind_a_baseline_that_disagrees_with_the_approved_document(self) -> None:
        from project_core import migrate_project
        with tempfile.TemporaryDirectory() as tmp:
            root = self.approved_architecture(tmp)
            statement = self.statement()
            first = next(iter(statement["stack"]))
            statement["stack"][first] = {"status": "调整", "value": "x", "reason": "文档批准之后才改的"}        # the document says 沿用 for it
            self.write(root, statement)
            result = migrate_project(root, apply=True)
            self.assertTrue(any("对不上" in n for n in result["notes"]), result["notes"])
            record = next(s for s in json.loads((root / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "architecture")
            self.assertEqual(record["approved_sources"], {})

    def test_the_tracking_is_written_in_the_baseline_reference(self) -> None:
        text = (Path(__file__).resolve().parents[1] / "references" / "tech-baseline.md").read_text(encoding="utf-8")
        self.assertIn("stack", text)
        self.assertIn("modules", text)
        self.assertIn("架构阶段", text)
        self.assertIn("baseline.json#stack,modules", text)


class MatrixTextTests(unittest.TestCase):
    """The numbers in the matrix, the contract texts and the skill agree with the paths the deliverables really have."""

    def test_the_numbers_in_a_stage_output_text_are_the_numbers_of_its_deliverables(self) -> None:
        from project_core import load_matrix
        matrix = load_matrix()
        names = {Path(d["path"]).stem for s in matrix["stages"] for d in s.get("deliverables", [])}
        for stage in matrix["stages"]:
            for text in stage.get("outputs", []):
                for number, title in re.findall(r"(\d\d)-([一-鿿]+)", text):
                    with self.subTest(stage=stage["id"], output=text):
                        self.assertIn(f"{number}-{title}", names)

    def test_the_texts_agree_on_where_the_interface_function_description_lives(self) -> None:
        """The 界面功能说明 and the entrance tables are products of the architecture stage (registered, hash bound), not a tab of the architecture document."""
        root = Path(__file__).resolve().parents[1]
        std = (root / "references" / "dev-documents.md").read_text(encoding="utf-8")
        mode = (root / "references" / "project-mode.md").read_text(encoding="utf-8")
        ownership = (root.parent / "Luz-Design" / "references" / "ui-ownership.md").read_text(encoding="utf-8")
        for kind in ("frontend-spec", "frontend-spec-page", "entrances", "proto-logic"):
            self.assertIn(f"`{kind}`", std)
        self.assertIn("架构文档本身不设前端页签", std)
        self.assertIn("架构文档本身不设前端页签", mode)
        self.assertNotIn("系统架构文档的前端页签", mode + ownership)
        from project_core import load_matrix
        outputs = " ".join(next(s for s in load_matrix()["stages"] if s["id"] == "architecture")["outputs"])
        self.assertIn("界面功能说明", outputs)
        self.assertIn("entrances*.json", outputs)

    def test_the_development_pages_have_the_numbers_of_the_standard(self) -> None:
        from project_core import stage_document_path
        for stage, name in (("architecture", "01-系统架构"), ("design", "02-前端界面设计"), ("technical-plan", "05-后端设计规范"), ("implementation", "06-实现报告")):
            self.assertEqual(Path(stage_document_path(stage)).stem, name)

    def test_the_texts_name_the_prototype_files_by_front_end_not_by_a_fixed_kind(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ("SKILL.md", "references/project-structure.md", "references/dev-documents.md", "references/development-matrix.json"):
            text = (root / relative).read_text(encoding="utf-8")
            with self.subTest(file=relative):
                self.assertNotIn("05-系统架构", text)
                self.assertNotIn("06-前端界面设计", text)
                self.assertNotIn("09-后端设计规范", text)
                self.assertNotIn("10-实现报告", text)
                self.assertNotIn("03-小程序原型, 04-后台原型", text)
                self.assertNotIn("03 小程序原型、04 后台原型", text)
                self.assertIn("前端名称", text)


if __name__ == "__main__":
    unittest.main()
