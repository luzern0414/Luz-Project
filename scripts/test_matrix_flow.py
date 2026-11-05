"""Full routing rehearsal with explicitly synthetic approvals and offline evidence.

This verifies the gate plumbing; it never represents a human approving a real project.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Crawl/scripts"))
sys.path.append(str(Path(__file__).resolve().parents[2] / "Luz-Ops/scripts"))
from test_crawl_preflight import complete_fixture
from client_fixture import new_project
from crawl_gate import evidence_session
from project_core import ProjectError, approve_stage, create_project, gate_stage, load_matrix, load_project, validate_project
from stage_documents import write_document
import dev_documents
import dev_fixture
import client_fixture
import client_flow
from ops_core import operations_matrix, record_check
from ops_fixtures import evidence_for


class MatrixFlowTests(unittest.TestCase):
    def test_every_stage_requires_its_own_research_before_synthetic_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("离线路由演练", tmp)
            stages = load_matrix()["stages"]
            for definition in stages:
                stage, owner = definition["id"], definition["owner"]
                with self.subTest(stage=stage):
                    self.assertEqual(load_project(root)["current_stage"], stage)
                    spec = dev_fixture.sample_spec(stage, root) if dev_documents.has_standard(stage) else {
                        "title": f"{stage} 离线演练",
                        "conclusion": "只验证路由和门禁，非产品验收。",
                        "sections": [{"title": "阶段结果", "content": "合成测试数据，不构成真实业务批准。"}],
                        "sources": [],
                    }
                    with self.assertRaises(ProjectError) as refused:               # nothing is written before the stage has crawled
                        write_document(root, stage, spec)
                    self.assertIn("Crawl", str(refused.exception))
                    self.assertTrue(any("Crawl" in e for e in gate_stage(root, stage)))
                    complete_fixture(evidence_session(root), owner, stage)
                    write_document(root, stage, spec)
                    if stage in {"requirements", "proposal", "client-intake", "handover"}:
                        client_fixture.prepare(root, stage)
                    if stage == "architecture":                                    # a project with screens hands over its 界面功能说明 and entrance tables
                        self.assertTrue(any("--kind frontend-spec" in e for e in client_flow.stage_checks(root, stage)))
                        dev_fixture.frontend_handover(root)
                    if owner == "luz-ops":
                        proof = Path(tmp) / f"offline-{stage}.json"
                        proof.write_text(json.dumps({"kind": "test-fixture", "stage": stage}), encoding="utf-8")
                        for check in operations_matrix()["checks"]:
                            if check["phase"] == stage:
                                record_check(root, check["id"], "passed", [str(p) for p in evidence_for(check["id"], Path(tmp) / "records", proof)], "仅路由测试证据")
                    self.assertEqual(gate_stage(root, stage), [])
                    approve_stage(root, stage, "TEST ONLY: synthetic approval in isolated fixture", "TEST FIXTURE")
                    self.assertEqual(validate_project(root, strict=True), [])
            self.assertEqual(load_project(root)["status"], "completed")
            self.assertEqual(len(json.loads((root / "APPROVALS.json").read_text(encoding="utf-8"))["approvals"]), len(stages))
            # Editing a previously reviewed input must invalidate the final gate.
            architecture = root / "data/stages/architecture.json"
            architecture.write_text(architecture.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertTrue(gate_stage(root, "operations"))


if __name__ == "__main__":
    unittest.main()
