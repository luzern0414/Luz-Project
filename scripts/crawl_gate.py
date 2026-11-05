"""Load the shared Crawl evidence gate without creating a project."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path

from project_paths import ProjectError, resolve_state_root


def evidence_session(project) -> Path:
    """What Crawl takes as the session of a project: its state root. Crawl keeps the preflight records in the folder project.json's
    ``crawl.evidence_index`` names (``00-crawl``; ``raw/00-crawl`` in a project that still has the old layout)."""
    try:
        return resolve_state_root(project)
    except ProjectError:
        return Path(project)


def crawl_errors(project, stage=None, caller=None):
    root = Path(os.environ.get("LUZ_CRAWL_ROOT") or Path(__file__).resolve().parents[2] / "Luz-Crawl")
    source = root / "scripts" / "crawl_preflight.py"
    if not source.is_file():
        return [f"Crawl 前置检索校验器不存在: {source}"]
    spec = importlib.util.spec_from_file_location("_luz_crawl_preflight", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    caller = caller or Path(__file__).resolve().parents[1].name.lower()
    return module.validate_preflight(evidence_session(project), caller, stage)
