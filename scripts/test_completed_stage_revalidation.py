"""Completed-stage history cannot replace its still-valid internal evidence.

These are isolated offline routing fixtures with synthetic approvals.  The
stage-specific Crawl and template validators themselves remain active.
"""
from __future__ import annotations

from pathlib import Path

import approval_docs as ad
import client_fixture
import doc_fixture as df
import flow_steps
import project_core as pc


def completed(tmp_path: Path, last: str = "requirements") -> Path:
    root = client_fixture.new_project("completed evidence", tmp_path, model="document")
    df.run_through(root, last, tmp_path)
    assert pc._stage_record(pc.load_project(root), last)["status"] == "approved"
    return root


def crawl_record(root: Path, stage: str) -> Path:
    import crawl_preflight
    from project_crawl_gate import evidence_session

    owner = pc._stage_record(pc.load_project(root), stage)["owner"]
    return crawl_preflight.record_path(evidence_session(root), owner, stage)


def test_refresh_reopens_a_completed_stage_when_its_crawl_record_disappears(tmp_path):
    root = completed(tmp_path)
    path = crawl_record(root, "requirements")
    original = path.read_bytes()
    approvals = (root / "APPROVALS.json").read_bytes()
    path.unlink()

    refreshed = ad.refresh(root)

    assert pc._stage_record(refreshed, "requirements")["status"] not in {"approved", "completed"}
    assert refreshed["current_stage"] == "requirements"
    assert refreshed["status"] != "completed"
    assert (root / "APPROVALS.json").read_bytes() == approvals
    path.write_bytes(original)
    recovered = ad.refresh(root)
    assert pc._stage_record(recovered, "requirements")["status"] == "approved"
    assert recovered["current_stage"] == "research"


def test_next_returns_to_an_approved_stage_whose_crawl_evidence_disappears(tmp_path):
    root = completed(tmp_path)
    crawl_record(root, "requirements").unlink()

    report = flow_steps.next_report(root)

    assert report["kind"] == "internal"
    assert report["stage"] == "requirements"
    assert "crawl" in report["internal"]["open"]
    assert report["current_step"]["id"] == "crawl"


def test_terminal_route_rechecks_evidence_before_reporting_done(tmp_path, monkeypatch):
    root = completed(tmp_path)
    # Restrict only the route's stage order to this genuinely completed stage
    # so the terminal branch is exercised without unrelated future stages.
    monkeypatch.setattr(ad, "stage_order", lambda root=None: ["requirements"])
    assert flow_steps.next_report(root)["kind"] == "done"
    crawl_record(root, "requirements").unlink()

    report = flow_steps.next_report(root)

    assert report["kind"] == "internal"
    assert report["stage"] == "requirements"
    assert "crawl" in report["internal"]["open"]


def test_approved_documents_reopen_when_their_post_bindings_disappear(tmp_path):
    root = completed(tmp_path, "proposal")
    path = root / "00-design/luz-project-proposal.json"
    original = path.read_bytes()
    approvals = (root / "APPROVALS.json").read_bytes()
    path.unlink()

    refreshed = ad.refresh(root)
    report = flow_steps.next_report(root)

    assert pc._stage_record(refreshed, "proposal")["status"] not in {"approved", "completed"}
    assert refreshed["current_stage"] == "proposal"
    assert report["kind"] == "internal"
    assert report["stage"] == "proposal"
    assert "build" in report["internal"]["open"]
    # Crawl also binds the real template selection, so its missing record is
    # the earliest failing step; the final-output build gate fails as well.
    assert report["current_step"]["id"] == "crawl"
    assert (root / "APPROVALS.json").read_bytes() == approvals
    path.write_bytes(original)
    recovered = ad.refresh(root)
    assert pc._stage_record(recovered, "proposal")["status"] == "approved"
    assert recovered["current_stage"] == "client-intake"
