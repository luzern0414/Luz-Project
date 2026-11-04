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

from project_core import (  # type: ignore[import-not-found]
    approve_stage,
    create_project,
    register_artifact,
    render_project,
    validate_project,
)


class ProjectScaffoldTests(unittest.TestCase):
    def test_init_creates_complete_project_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("示例项目", Path(tmp), repository="D:/repo/example")
            required = [
                "src",
                "test",
                "assets",
                "infra",
                "raw",
                "config",
                "data/stages",
                "docs/01-需求对接",
                "docs/02-产品开发",
                "docs/03-验收交付",
            ]
            for relative in required:
                self.assertTrue((project / relative).is_dir(), relative)
            manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["repository"], "D:/repo/example")
            self.assertEqual(manifest["status"], "draft")
            for empty in ("src/frontend", "src/backend", "assets/fonts", "infra/dev", "test/unit", "raw/logs", "data/schema"):
                self.assertFalse((project / empty).exists(), f"{empty} 不提前建空目录")
            self.assertEqual([p.name for p in (project / "docs").iterdir() if p.is_dir()], ["01-需求对接", "02-产品开发", "03-验收交付"])
            for folder in ("01-需求对接", "02-产品开发", "03-验收交付"):
                self.assertEqual([p for p in (project / "docs" / folder).iterdir() if p.is_dir()], [], f"docs/{folder} 只有一层")

    def test_artifact_registration_renders_html_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("文档项目", Path(tmp))
            artifact = project / "raw" / "reviews" / "需求.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html><body><h1>需求</h1></body></html>", encoding="utf-8")
            record = register_artifact(project, "requirements", artifact, "html", ["SRC-001"])
            self.assertEqual(record["stage"], "requirements")
            self.assertTrue(record["sha256"])
            render_project(project)
            self.assertTrue((project / "README.html").is_file())
            artifacts = json.loads((project / "data" / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(artifacts[0]["source_ids"], ["SRC-001"])

    def test_approval_and_validation_require_current_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("审批项目", Path(tmp))
            artifact = project / "raw" / "reviews" / "需求.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html><body><h1>需求</h1></body></html>", encoding="utf-8")
            register_artifact(project, "requirements", artifact, "html")
            import client_fixture
            client_fixture.requirements_provided(project)
            complete_fixture(project, "luz-project", "requirements")
            approve_stage(project, "requirements", "需求范围确认", "用户")
            errors = validate_project(project, strict=True)
            self.assertEqual(errors, [])

    def test_the_index_names_the_developer_documents_and_no_stage_gets_an_empty_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("索引项目", Path(tmp))
            index = (project / "README.html").read_text(encoding="utf-8")
            self.assertIn("尚未编写", index)
            for stub in ("architecture.html", "design.html", "technical-plan.html", "implementation.html"):
                self.assertFalse((project / "docs" / "02-产品开发" / stub).exists(), stub)
            doc = project / "docs" / "02-产品开发" / "01-系统架构.html"
            doc.write_text("<html>x</html>", encoding="utf-8")
            render_project(project)
            self.assertIn("01-系统架构", (project / "README.html").read_text(encoding="utf-8"))

    def test_every_developer_document_has_a_numbered_chinese_name(self) -> None:
        from project_core import stage_document_path
        names = {s: stage_document_path(s) for s in ("requirements", "research", "proposal", "client-intake", "architecture", "design", "technical-plan", "implementation")}
        for stage, name in (("requirements", "01-需求评审"), ("research", "02-调研结论"), ("proposal", "03-方案评审"), ("client-intake", "04-业务逻辑确认评审")):
            self.assertEqual(names[stage], f"raw/reviews/{name}.html")                 # the review pages are internal: raw/reviews, not docs
        self.assertEqual(names["architecture"], "docs/02-产品开发/01-系统架构.html")
        self.assertEqual(names["design"], "docs/02-产品开发/02-前端界面设计.html")
        self.assertEqual(names["technical-plan"], "docs/02-产品开发/05-后端设计规范.html")
        self.assertEqual(names["implementation"], "docs/02-产品开发/06-实现报告.html")
        for path in names.values():
            self.assertRegex(Path(path).name, r"^\d\d-[\u4e00-\u9fff]+\.html$")
            self.assertTrue(path.startswith(("raw/reviews/", "docs/02-产品开发/")), path)

    def test_secret_and_hash_drift_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("安全项目", Path(tmp))
            artifact = project / "raw" / "reviews" / "secret.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html>" + "sk-" + "x" * 32 + "</html>", encoding="utf-8")      # built at run time so the source holds no key-shaped literal
            register_artifact(project, "requirements", artifact, "html")
            self.assertTrue(any("秘密" in error for error in validate_project(project)))
            artifact.write_text("<html>safe</html>", encoding="utf-8")
            self.assertTrue(any("哈希" in error for error in validate_project(project)))


class DocsLayoutTests(unittest.TestCase):
    """docs/ has three folders, one level each, and the folder names say what goes in."""

    def test_the_check_names_every_misplaced_file_and_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("目录检查", Path(tmp))
            self.assertEqual(validate_project(project), [])
            (project / "docs/02-产品开发/原型").mkdir()
            (project / "docs/02-产品开发/原型/演示.html").write_text("<html>x</html>", encoding="utf-8")
            (project / "docs/02-产品开发/说明.md").write_text("# 旧说明", encoding="utf-8")
            (project / "docs/02-产品开发/方案.pdf").write_text("x", encoding="utf-8")
            (project / "docs/01-需求对接/07-需求评审.html").write_text("<html>x</html>", encoding="utf-8")
            (project / "docs/01-需求对接/00-客户原始资料").mkdir()
            (project / "docs/01-需求对接/随手.docx").write_text("x", encoding="utf-8")
            (project / "docs/03-验收交付/交付资料").mkdir()
            (project / "docs/多余").mkdir()
            (project / "docs/随手.docx").write_text("x", encoding="utf-8")
            errors = "\n".join(validate_project(project))
            for expected in ("02-产品开发 只有一层", "说明.md", "方案.pdf", "00-客户原始资料/", "01-需求对接 只放", "07-需求评审.html", "交付资料/", "docs/多余/", "docs/随手.docx"):
                self.assertIn(expected, errors)

    def test_a_requirement_page_in_the_development_folder_and_the_reverse_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("阶段目录", Path(tmp))
            wrong = project / "docs" / "02-产品开发" / "01-需求评审.html"
            wrong.write_text("<html>x</html>", encoding="utf-8")
            register_artifact(project, "requirements", wrong, "html")
            wrong_dev = project / "docs" / "01-需求对接" / "01-系统架构.html"
            wrong_dev.write_text("<html>y</html>", encoding="utf-8")
            register_artifact(project, "architecture", wrong_dev, "html")
            errors = "\n".join(validate_project(project))
            self.assertIn("requirements 阶段的 .html 文件放 raw/reviews", errors)
            self.assertIn("architecture 阶段的 .html 文件放 docs/02-产品开发", errors)

    def test_an_older_layout_is_moved_by_what_each_folder_is_named_with_paths_and_hashes_kept(self) -> None:
        from project_core import migrate_project, sha256_file
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("旧布局", Path(tmp))
            docs = project / "docs"
            old = {"02-产品开发/00-需求与方案/01-需求对接.html": "requirements", "02-产品开发/01-系统架构.html": "architecture",
                   "02-产品开发/03-后端设计规范.html": "technical-plan",
                   "02-产品开发/原型/01-小程序原型.html": "design", "03-验收交付/verification-report.html": "verification",
                   "02-产品开发/10-实现报告.html": "implementation"}              # a file of the second (flat) layout, too
            for relative, stage in old.items():
                file = docs / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(f"<html><body><h1>{relative}</h1></body></html>", encoding="utf-8")
                register_artifact(project, stage, file, "html")
            original = project / "docs/01-需求对接/00-客户原始资料/客户清单.docx"
            original.parent.mkdir(parents=True)
            original.write_text("客户给的原件", encoding="utf-8")
            (project / "docs/02-产品开发/杂记.md").write_text("# 谁也不知道放哪", encoding="utf-8")
            before = {a["stage"]: a["sha256"] for a in json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))}
            result = migrate_project(project)
            self.assertEqual(len(result["layout"]["moved"]), 6)
            now = {a["stage"]: a for a in json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))}
            self.assertEqual(now["requirements"]["path"], "raw/reviews/01-需求评审.html")              # 需求阶段的评审页是内部页，放 raw/reviews
            self.assertEqual(now["architecture"]["path"], "docs/02-产品开发/01-系统架构.html")
            self.assertEqual(now["technical-plan"]["path"], "docs/02-产品开发/05-后端设计规范.html")
            self.assertEqual(now["design"]["path"], "docs/02-产品开发/03-小程序原型.html")
            self.assertEqual(now["verification"]["path"], "docs/02-产品开发/07-验收测试评审.html")
            for stage, record in now.items():
                self.assertEqual(sha256_file(project / record["path"]), before[stage], "移动不改内容，审批绑定的哈希不变")
            self.assertTrue((project / "raw/uploads/客户清单.docx").is_file())
            for gone in ("docs/02-产品开发/00-需求与方案", "docs/02-产品开发/原型", "docs/01-需求对接/00-客户原始资料"):
                self.assertFalse((project / gone).exists(), gone)
            errors = validate_project(project)
            self.assertTrue(any("杂记.md" in e for e in errors), errors)             # a file nobody can place is named, not guessed
            self.assertFalse(any("只有一层" in e or "放 docs/" in e for e in errors), errors)
            self.assertTrue(any("杂记.md" in n for n in result["notes"]))


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
                folder = "/".join(d["path"].split("/")[:2])
                self.assertEqual(folder, expected_doc_folder(stage, "." + d["format"]), d["path"])

    def test_no_deliverable_sits_below_a_second_level_and_development_numbers_do_not_repeat(self) -> None:
        paths = [d["path"] for _, d in self.deliverables()]
        for path in paths:
            self.assertEqual(len(path.split("/")), 3, f"docs 下只有一层目录: {path}")
        development = [Path(p).name[:2] for p in paths if p.startswith("docs/02-产品开发/")]
        self.assertEqual(len(development), len(set(development)), "02-产品开发 里的序号不能重复")
        for p in paths:
            if p.startswith("docs/02-产品开发/"):
                self.assertTrue(p.endswith(".html"), p)


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
            project = create_project("目录契约", Path(tmp))
            top = sorted(p.name for p in project.iterdir() if p.is_dir())
            self.assertEqual(top, ["assets", "config", "data", "docs", "infra", "raw", "scripts", "src", "test"])
            for folder in ("src", "test", "assets", "infra", "scripts"):
                self.assertEqual([p.name for p in (project / folder).iterdir() if p.is_dir()], [], f"{folder} 下不预先建二级目录")
            self.assertEqual(sorted(p.name for p in (project / "data").iterdir() if p.is_dir()), ["client", "ops", "stages"])      # the three the tools write to; acceptance, schema, users ... come with content
            self.assertEqual(sorted(p.name for p in (project / "raw").iterdir() if p.is_dir()), [])                                  # raw/crawl was only ever the home of an empty placeholder
            self.assertFalse((project / "data" / "acceptance").exists())

    def test_config_holds_no_empty_files_and_data_no_unread_skeletons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("空文件", Path(tmp))
            self.assertEqual(sorted(p.name for p in (project / "config").iterdir()), ["documents.json", "keys.example.json", "paths.json"])
            for name in ("project.json", "environments.json", "urls.json", "features.json", "validation.json"):
                self.assertFalse((project / "config" / name).exists(), f"config/{name} 由对应阶段写，不在 init 里造空文件")
            for relative in ("data/sources.json", "data/decisions.json", "raw/crawl/evidence.json"):
                self.assertFalse((project / relative).exists(), f"{relative} 没有任何工具读取，不生成")
            paths = json.loads((project / "config/paths.json").read_text(encoding="utf-8"))
            self.assertEqual(paths["crawl"], "raw/00-crawl")

    def test_the_crawl_evidence_index_points_at_the_real_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("证据位置", Path(tmp))
            manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["crawl"]["evidence_index"], "raw/00-crawl")
            complete_fixture(project, "luz-project", "requirements")
            self.assertTrue((project / manifest["crawl"]["evidence_index"] / "luz-project-requirements.json").is_file())      # where the preflight really writes

    def test_the_gitignore_template_covers_secrets_dependencies_build_output_and_the_client_document_intermediates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("忽略清单", Path(tmp))
            lines = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
            for wanted in (".env", "node_modules/", "dist/", "build/", "raw/client-docs/", "raw/uploads/"):
                self.assertIn(wanted, lines)
            self.assertIn("!.env.example", lines)
            self.assertNotIn("raw/00-crawl/", lines, "检索记录是审批依据，不忽略")

    def test_the_contract_text_lists_what_init_makes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "references" / "project-structure.md").read_text(encoding="utf-8")
        tree = text.split("```")[1]                                                          # the directory tree of the contract
        for gone in ("sources.json", "decisions.json", "raw/crawl", "crawl/ 检索证据"):
            self.assertNotIn(gone, tree)
        for there in ("paths.json", "documents.json", "keys.example.json", "00-crawl/", "baseline.json"):
            self.assertIn(there, tree)
        self.assertIn("不预先建", text)

    def test_migrate_repoints_an_older_project_and_names_the_empty_skeletons_without_deleting_them(self) -> None:
        from project_core import migrate_project
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("旧骨架", Path(tmp))
            manifest = json.loads((project / "project.json").read_text(encoding="utf-8"))
            manifest["crawl"]["evidence_index"] = "raw/crawl/evidence.json"
            for name in ("project.json", "MANIFEST.json", "data/project.json"):
                (project / name).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            (project / "raw/crawl").mkdir()
            (project / "raw/crawl/evidence.json").write_text(json.dumps({"task_id": None, "task_root": None, "sources": [], "coverage": [], "unresolved": []}), encoding="utf-8")
            (project / "data/sources.json").write_text("[]", encoding="utf-8")
            (project / ".gitignore").write_text("\n# Luz 客户文档构建中间件\nraw/client-docs/\n", encoding="utf-8")
            paths = json.loads((project / "config/paths.json").read_text(encoding="utf-8"))
            paths["crawl"] = "raw/crawl"
            (project / "config/paths.json").write_text(json.dumps(paths), encoding="utf-8")
            result = migrate_project(project)
            self.assertEqual(json.loads((project / "project.json").read_text(encoding="utf-8"))["crawl"]["evidence_index"], "raw/00-crawl")
            self.assertEqual(json.loads((project / "config/paths.json").read_text(encoding="utf-8"))["crawl"], "raw/00-crawl")
            lines = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines.count("raw/client-docs/"), 1)
            for wanted in (".env", "node_modules/", "dist/", "build/"):
                self.assertIn(wanted, lines)
            notes = "\n".join(result["notes"])
            self.assertIn("raw/crawl/evidence.json 是空骨架", notes)
            self.assertIn("data/sources.json 是空骨架", notes)
            self.assertTrue((project / "raw/crawl/evidence.json").is_file() and (project / "data/sources.json").is_file(), "migrate 只指出，不删")
            self.assertEqual(validate_project(project, strict=True), [])


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
            project = create_project("默认原型", Path(tmp))
            record = next(s for s in json.loads((project / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "design")
            default = self.design_item()["deliverables"]
            self.assertEqual(record["deliverables"], default)
            self.assertEqual(stage_deliverables(project, self.design_item()), default)

    def test_a_phone_page_and_a_back_office_give_two_prototypes_named_after_them(self) -> None:
        from project_core import migrate_project, stage_context
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("手机加后台", Path(tmp))
            spec = self.design_spec(project, [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide")])
            self.named_prototypes(spec, ["手机", "后台"])
            self.write_design(project, spec)
            result = migrate_project(project)
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
            project = create_project("先上下文", Path(tmp))
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
            project = create_project("小程序加后台", Path(tmp))
            spec = self.design_spec(project, None, surfaces=["miniprogram", "web-admin"])          # one tab per use: 小程序 and 管理后台
            self.assertEqual([t["title"] for t in spec["tabs"]], ["前端规范", "小程序", "管理后台", "检查与差异"])
            self.named_prototypes(spec, ["小程序", "后台"])
            self.write_design(project, spec)
            paths = [d["path"] for d in stage_deliverables(project, self.design_item())]
            self.assertEqual(paths[1:], ["docs/02-产品开发/03-小程序原型.html", "docs/02-产品开发/04-后台原型.html"])

    def test_three_front_ends_give_three_prototypes(self) -> None:
        from project_core import stage_deliverables
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("三端", Path(tmp))
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
            project = create_project("登记原型", Path(tmp))
            spec = self.design_spec(project, [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide")])
            fx.crawled(project, "design")
            write_document(project, "design", spec)
            artifacts = json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))
            design = [a for a in artifacts if a["stage"] == "design"]
            self.assertEqual(sorted(a["path"] for a in design if a["kind"] == "html"),
                             sorted(["docs/02-产品开发/02-前端界面设计.html", "raw/fixtures/proto1.html", "raw/fixtures/proto2.html"]))
            self.assertEqual(len({a["id"] for a in artifacts}), len(artifacts))
            record = next(s for s in json.loads((project / "project.json").read_text(encoding="utf-8"))["stages"] if s["id"] == "design")
            self.assertEqual([d["path"] for d in record["deliverables"]][1:], ["raw/fixtures/proto1.html", "raw/fixtures/proto2.html"])
            self.assertEqual(sorted(record["artifact_ids"]), sorted(a["id"] for a in design))
            self.assertTrue(all(d["registered"] and d["exists"] for d in stage_context(project, "design")["client"]["deliverables"]))
            write_document(project, "design", spec)                                                  # writing it again registers nothing twice
            again = json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(len(again), len(artifacts))
            self.assertEqual(validate_project(project, strict=True), [])

    def test_a_listed_prototype_that_does_not_exist_is_an_error_once_the_design_document_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("缺原型", Path(tmp))
            document = project / "docs/02-产品开发/02-前端界面设计.html"
            document.write_text("<html><body>x</body></html>", encoding="utf-8")
            self.assertEqual(validate_project(project), [])                                          # nothing registered yet: a stage still being written is not an error
            register_artifact(project, "design", document, "html")
            errors = validate_project(project)
            self.assertTrue(any("交付物不存在" in e and "03-小程序原型.html" in e and "design" in e for e in errors), errors)
            self.assertTrue(any("04-后台原型.html" in e for e in errors), errors)
            for name in ("03-小程序原型.html", "04-后台原型.html"):
                (project / "docs/02-产品开发" / name).write_text("<html></html>", encoding="utf-8")
            self.assertEqual(validate_project(project), [])

    def test_only_html_deliverables_of_a_stage_with_a_registered_page_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("只查网页", Path(tmp))
            page = project / "raw/reviews/03-方案评审.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text("<html><body>x</body></html>", encoding="utf-8")
            register_artifact(project, "proposal", page, "html")                                      # the three client files of the proposal do not exist yet: approve and Ops gate those
            self.assertEqual(validate_project(project), [])


class ArtifactNumberTests(unittest.TestCase):
    """An artifact number names one registered file: never twice in a list, never handed out again."""

    def write(self, project: Path, name: str, text: str = "x") -> Path:
        path = project / "raw" / "reviews" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<html><body>{text}</body></html>", encoding="utf-8")
        return path

    def test_a_number_listed_twice_in_a_stage_is_reported_and_registering_stops(self) -> None:
        from project_core import ProjectError, migrate_project
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("重复编号", Path(tmp))
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
            self.assertTrue(any("requirements" in n and "重复" in n for n in migrate_project(project)["notes"]))      # migrate drops the repeated entry ...
            self.assertEqual(validate_project(project), [])                                           # ... and the register works again
            register_artifact(project, "requirements", self.write(project, "另一页.html"), "html")

    def test_the_register_with_one_number_twice_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("登记表重复", Path(tmp))
            register_artifact(project, "requirements", self.write(project, "a.html"), "html")
            register_artifact(project, "research", self.write(project, "b.html", "y"), "html")
            artifacts = json.loads((project / "data/artifacts.json").read_text(encoding="utf-8"))
            artifacts[1]["id"] = artifacts[0]["id"]
            (project / "data/artifacts.json").write_text(json.dumps(artifacts), encoding="utf-8")
            self.assertTrue(any("产物编号重复" in e and "data/artifacts.json" in e for e in validate_project(project)))

    def test_a_number_that_a_stage_still_lists_is_not_handed_out_again_after_its_file_was_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project("不复用编号", Path(tmp))
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
            root = create_project("底座跟踪", Path(tmp))
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
        root = create_project("架构已批", Path(tmp))
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
            result = migrate_project(root)
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
            result = migrate_project(root)
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
