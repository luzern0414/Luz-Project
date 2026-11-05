from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path

from client_fixture import new_project
from crawl_gate import evidence_session
from project_core import ProjectError, approve_stage, create_project, register_artifact, set_stage_status
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
from test_crawl_preflight import complete_fixture


from project_core import expected_doc_folder


import client_fixture


class ProjectGateTests(unittest.TestCase):
    def artifact(self, root: Path, stage: str, text: str = "范围和验收已明确") -> Path:
        path = root / expected_doc_folder(stage, ".html") / f"{stage}-review.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<!doctype html><html><body><h1>{stage}</h1><p>{text}</p></body></html>", encoding="utf-8")
        register_artifact(root, stage, path, "html")
        client_fixture.requirements_provided(root)
        complete_fixture(evidence_session(root), "luz-crawl" if stage == "research" else "luz-project", stage)
        return path

    def test_changed_predecessor_blocks_later_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("hash", tmp)
            req = self.artifact(root, "requirements")
            approve_stage(root, "requirements", "用户确认需求", "用户")
            self.artifact(root, "research")
            req.write_text("changed", encoding="utf-8")
            with self.assertRaises(ProjectError):
                approve_stage(root, "research", "用户确认调研", "用户")

    def test_moving_approved_stage_back_invalidates_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("reopen", tmp)
            for stage in ("requirements", "research"):
                self.artifact(root, stage)
                approve_stage(root, stage, "用户确认", "用户")
            set_stage_status(root, "requirements", "in-progress")
            manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
            research = next(s for s in manifest["stages"] if s["id"] == "research")
            self.assertIsNone(research["approval_id"])
            self.assertEqual(research["status"], "superseded")

    def test_json_without_review_html_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("no-html", tmp)
            path = root / "data" / "stages" / "requirements.json"
            path.write_text('{}', encoding="utf-8")
            register_artifact(root, "requirements", path, "json")
            complete_fixture(evidence_session(root), "luz-project", "requirements")
            with self.assertRaises(ProjectError):
                approve_stage(root, "requirements", "用户确认", "用户")


if __name__ == "__main__":
    unittest.main()
