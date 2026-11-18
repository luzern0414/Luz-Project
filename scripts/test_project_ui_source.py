"""Cheap negative boundaries; real browser/tamper integration is in test_project."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import client_fixture as fx
import dev_fixture
import dev_documents as dd
import project_ui_source as ui
from project_core import ProjectError
import tempfile


class SourceBoundaryTests(unittest.TestCase):
    def test_padded_marker_html_does_not_replace_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = dev_fixture.sample_spec("design", root)
            block = next(ui.prototype_blocks(spec))
            block.pop("source")
            file = root / block["file"]
            file.parent.mkdir(parents=True)
            file.write_text('<html><dialog>UI.demo reduced-motion</dialog>' + 'x' * 140000, encoding="utf-8")
            self.assertTrue(any("source" in e or "来源" in e for e in dd.validate("design", spec, root)))

    def test_cross_project_source_is_rejected_before_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            root.mkdir()
            (root / "project.json").write_text("{}", encoding="utf-8")
            session = Path(tmp) / "001-design"
            manifest = session / "raw/99-delivery/MANIFEST.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"project": {"state_root": str(Path(tmp) / 'different'), "stage": "design"}}), encoding="utf-8")
            with patch.object(ui, "_source_check", side_effect=AssertionError("must reject before invoking verifier")):
                with self.assertRaisesRegex(ValueError, "项目状态根"):
                    ui.source_contract(root, {"session": str(session), "package": "raw/ui", "entry": "index.html"})

    def test_unregistered_source_is_rejected_before_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fx.new_project("未登记来源", tmp)
            session = Path(tmp) / "001-design"
            manifest = session / "raw/99-delivery/MANIFEST.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"project": {"state_root": str(root), "stage": "design"}}), encoding="utf-8")
            with patch.object(ui, "_source_check", side_effect=AssertionError("must reject before invoking verifier")):
                with self.assertRaisesRegex(ValueError, "登记"):
                    ui.source_contract(root, {"session": str(session), "package": "raw/ui", "entry": "index.html"})

    def test_public_link_writer_cannot_bypass_stage_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fx.new_project("写入门禁", tmp)
            target = Path(tmp) / "forged.html"
            with self.assertRaisesRegex(ProjectError, "Crawl"):
                ui.write_links(root, [({}, target, "FORGED")])
            self.assertFalse(target.exists())


class PackagedContractTests(unittest.TestCase):
    """A frontend.py package carries its UI contract as ui-requirements.json; it counts only inside a Design session linked to this project."""

    def _session(self, tmp, state):
        session = Path(tmp) / "001-design"
        manifest = session / "raw/99-delivery/MANIFEST.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"project": {"state_root": str(state), "stage": "design"}}), encoding="utf-8")
        package = session / "raw/04-ui/web-workspace"
        package.mkdir(parents=True)
        return package / "ui-requirements.json"

    def test_copy_in_a_linked_session_is_recognized(self):
        import project_ui_requirements as req
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            copy = self._session(tmp, state)
            copy.write_text("{}", encoding="utf-8")
            self.assertTrue(req._packaged_copy(state, copy.resolve()))

    def test_copy_in_another_projects_session_or_with_another_name_is_not(self):
        import project_ui_requirements as req
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            foreign = self._session(tmp, Path(tmp) / "other-state")
            foreign.write_text("{}", encoding="utf-8")
            self.assertFalse(req._packaged_copy(state, foreign.resolve()))
            renamed = foreign.with_name("contract.json")
            renamed.write_text("{}", encoding="utf-8")
            self.assertFalse(req._packaged_copy(state, renamed.resolve()))
            outside = Path(tmp) / "ui-requirements.json"
            outside.write_text("{}", encoding="utf-8")
            self.assertFalse(req._packaged_copy(state, outside.resolve()))


if __name__ == "__main__":
    unittest.main()
