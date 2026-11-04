"""Load the shared Crawl evidence gate without creating a project."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path

def crawl_errors(session, stage=None, caller=None):
    root = Path(os.environ.get("LUZ_CRAWL_ROOT") or Path(__file__).resolve().parents[2] / "Luz-Crawl")
    source = root / "scripts" / "crawl_preflight.py"
    if not source.is_file():
        return [f"Crawl 前置检索校验器不存在: {source}"]
    spec = importlib.util.spec_from_file_location("_luz_crawl_preflight", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    caller = caller or Path(__file__).resolve().parents[1].name.lower()
    return module.validate_preflight(Path(session), caller, stage)

