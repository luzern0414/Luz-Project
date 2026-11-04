"""adopt: an existing repository becomes a Luz project in place, with moved docs relinked and code folders aliased."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_core import ProjectError, adopt_project, load_project, validate_project


class AdoptTests(unittest.TestCase):
    def repo(self, tmp: str) -> Path:
        root = Path(tmp) / "007演示"
        (root / "docs/旧需求/资料").mkdir(parents=True)
        (root / "tests/api").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "docs/旧需求/资料/规格.md").write_text("# 规格\n见 [说明](../说明.md) 与 `docs/旧需求/说明.md`\n", encoding="utf-8")
        (root / "docs/旧需求/说明.md").write_text("# 说明\n回到 [规格](资料/规格.md)\n", encoding="utf-8")
        (root / "README.md").write_text("入口 `docs/旧需求/说明.md`\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root)
        subprocess.run(["git", "add", "."], cwd=root)
        return root

    def test_adopt_moves_relinks_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp)
            result = adopt_project(root, "演示项目", moves=[("docs/旧需求/资料/规格.md", "raw/旧文档/资料/规格.md"), ("docs/旧需求/说明.md", "raw/旧文档/说明.md")], aliases={"test": "tests"})
            manifest = load_project(root)
            self.assertEqual(manifest["project_id"], "PROJECT-007")
            self.assertTrue(all(s["status"] in {"in-progress", "pending"} for s in manifest["stages"]))
            self.assertFalse(json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"])
            moved = (root / "raw/旧文档/资料/规格.md").read_text(encoding="utf-8")
            self.assertIn("](../说明.md)", moved)
            self.assertIn("`raw/旧文档/说明.md`", moved)
            self.assertIn("](资料/规格.md)", (root / "raw/旧文档/说明.md").read_text(encoding="utf-8"))
            self.assertIn("`raw/旧文档/说明.md`", (root / "README.md").read_text(encoding="utf-8"))
            self.assertTrue((root / "tests/api").is_dir() and not (root / "test").exists())
            self.assertEqual(validate_project(root, strict=True), [])
            self.assertIn("raw/client-docs/", (root / ".gitignore").read_text(encoding="utf-8"))
            self.assertTrue(result["files_updated"])

    def test_adopt_refuses_existing_project_and_missing_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.repo(tmp)
            with self.assertRaises(ProjectError):
                adopt_project(root, aliases={"test": "no-such-dir"})
            adopt_project(root)
            with self.assertRaises(ProjectError):
                adopt_project(root)


if __name__ == "__main__":
    unittest.main()
