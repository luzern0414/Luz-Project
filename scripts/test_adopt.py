"""adopt: an existing repository becomes the project directory of a Luz project, its state goes to a session, moved docs are relinked, code folders aliased."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_core import ProjectError, adopt_project, deliver_root, load_project, validate_project


class AdoptTests(unittest.TestCase):
    def repo(self, tmp: str) -> Path:
        root = Path(tmp) / "work" / "007-演示"
        (root / "docs/旧需求/资料").mkdir(parents=True)
        (root / "tests/api").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "docs/旧需求/资料/规格.md").write_text("# 规格\n见 [说明](../说明.md) 与 `docs/旧需求/说明.md`\n", encoding="utf-8")
        (root / "docs/旧需求/说明.md").write_text("# 说明\n回到 [规格](资料/规格.md)\n", encoding="utf-8")
        (root / "README.md").write_text("入口 `docs/旧需求/说明.md`\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root)
        subprocess.run(["git", "add", "."], cwd=root)
        return root

    def test_adopt_moves_old_documents_out_of_the_project_and_aliases_code_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self.repo(tmp), Path(tmp) / "out"
            result = adopt_project(root, "演示项目", moves=[("docs/旧需求/资料/规格.md", "uploads/旧文档/资料/规格.md"), ("docs/旧需求/说明.md", "uploads/旧文档/说明.md")],
                                   aliases={"test": "tests"}, output=out)
            state = Path(result["state_root"])
            self.assertEqual(state, (out / "007-演示" / "raw").resolve())
            manifest = load_project(state)
            self.assertEqual(manifest["project_id"], "PROJECT-007")
            self.assertEqual(Path(manifest["deliver_root"]), root.resolve())
            self.assertTrue(all(s["status"] in {"in-progress", "pending"} for s in manifest["stages"]))
            self.assertFalse(json.loads((state / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"])
            self.assertTrue((state / "uploads/旧文档/资料/规格.md").is_file() and (state / "uploads/旧文档/说明.md").is_file(), "旧文档是源文件，搬到状态根")
            self.assertFalse((root / "docs/旧需求").exists(), "搬空的目录不留")
            self.assertTrue((root / "tests/api").is_dir() and not (root / "test").exists(), "代码目录不改名、不预先建")
            self.assertEqual(sorted(p.name for p in (root / "docs").iterdir()), ["01-需求对接", "02-产品开发", "03-验收交付"])
            self.assertEqual(sorted(p.name for p in root.iterdir() if p.name != ".git"), [".gitignore", "README.md", "docs", "src", "tests"])
            self.assertTrue((out / "007-演示" / "007-演示.html").is_file())
            self.assertEqual(validate_project(state, strict=True), [])
            self.assertEqual(json.loads((state / "config/paths.json").read_text(encoding="utf-8"))["aliases"], {"test": "tests"})

    def test_adopt_relinks_what_stays_in_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self.repo(tmp), Path(tmp) / "out"
            result = adopt_project(root, "演示项目", moves=[("docs/旧需求/资料/规格.md", "docs/资料/规格.md"), ("docs/旧需求/说明.md", "docs/说明.md")], output=out)
            moved = (root / "docs/资料/规格.md").read_text(encoding="utf-8")
            self.assertIn("](../说明.md)", moved)
            self.assertIn("`docs/说明.md`", moved)
            self.assertIn("](资料/规格.md)", (root / "docs/说明.md").read_text(encoding="utf-8"))
            self.assertIn("`docs/说明.md`", (root / "README.md").read_text(encoding="utf-8"))
            self.assertTrue(result["files_updated"])
            self.assertTrue(any("docs" in e for e in validate_project(Path(result["state_root"]))), "放进 docs 的 Markdown 不是成果，check 会指出")

    def test_adopt_adds_the_safe_ignore_lines_keeps_the_repository_own_and_makes_no_empty_skeletons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self.repo(tmp), Path(tmp) / "out"
            (root / ".gitignore").write_text("\n".join(["*.log", "node_modules/"]) + "\n", encoding="utf-8")
            result = adopt_project(root, "演示项目", aliases={"test": "tests"}, output=out)
            lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines.count("node_modules/"), 1, "仓库自己有的行不重复")
            self.assertIn("*.log", lines)
            for wanted in (".env", "dist/", "build/"):
                self.assertIn(wanted, lines)
            self.assertNotIn("raw/client-docs/", lines, "客户文档的构建中间件不在项目目录里")
            self.assertIn(".env", result["gitignore_added"])
            state = Path(result["state_root"])
            self.assertEqual(load_project(state)["crawl"]["evidence_index"], "00-crawl")
            for relative in ("data/sources.json", "data/decisions.json", "crawl/evidence.json", "data/acceptance"):
                self.assertFalse((state / relative).exists(), relative)
            errors = validate_project(state, strict=True)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("旧需求", errors[0], "仓库自己的旧文档目录还在 docs 里，check 指出它；用 --move 搬走")

    def test_adopt_makes_a_gitignore_when_the_repository_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp)
            self.assertFalse((root / ".gitignore").exists())
            adopt_project(root, "演示项目", aliases={"test": "tests"}, output=Path(tmp) / "out")
            lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
            for wanted in (".env", "node_modules/", "dist/", "build/"):
                self.assertIn(wanted, lines)

    def test_adopt_refuses_an_adopted_repository_an_old_layout_project_and_a_missing_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = self.repo(tmp), Path(tmp) / "out"
            with self.assertRaises(ProjectError):
                adopt_project(root, aliases={"test": "no-such-dir"}, output=out)
            adopt_project(root, output=out)
            with self.assertRaises(ProjectError):
                adopt_project(root, output=out)
            old = Path(tmp) / "work" / "008-旧布局"
            old.mkdir()
            (old / "project.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ProjectError) as refused:
                adopt_project(old, output=out)
            self.assertIn("migrate", str(refused.exception))
            (Path(tmp) / "work" / "没有序号").mkdir()
            with self.assertRaises(ProjectError) as named:
                adopt_project(Path(tmp) / "work" / "没有序号", output=out)
            self.assertIn("三位序号", str(named.exception))

    def test_the_project_directory_is_found_from_either_path(self):
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root, out = self.repo(tmp), Path(tmp) / "out"
            state = Path(adopt_project(root, output=out)["state_root"])
            os.environ["LUZ_PROJECT_OUTPUT"] = str(out)
            self.assertEqual(deliver_root(state), root.resolve())
            self.assertEqual(deliver_root(root), root.resolve())
            self.assertEqual(load_project(root)["project_id"], load_project(state.parent)["project_id"])


if __name__ == "__main__":
    unittest.main()
