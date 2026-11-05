"""A project of the old layout for the tests of ``migrate`` and of the compatibility of the old layout (never a real project)."""
from __future__ import annotations

from pathlib import Path


def legacy_project(name: str, tmp: Path | str) -> Path:
    """A project as the first layout made it: project.json, MANIFEST.json, APPROVALS.json, README.html, ``config/``, ``data/`` and ``raw/`` in the project
    root next to ``docs/`` and the implementation folders, no ``deliver_root``, the review pages under ``raw/reviews``. Returns the project root
    (``<tmp>/legacy/014-<name>``), which is its state root and its project directory at once."""
    import project_core as pc

    root = Path(tmp) / "legacy" / f"014-{name}"
    for relative in (*pc.DELIVER_MADE, "src", "test", "assets", "infra", "scripts", "raw"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in ("src", "test", "assets", "infra", "raw"):
        (root / relative / ".gitkeep").write_text("", encoding="utf-8")
    pc._write_json(root / "project.json", {"schema_version": "1.1"})          # from here on the folder reads as a project of the old layout
    stages = [pc._empty_stage(item, current=(index == 0), root=root) for index, item in enumerate(pc._load_matrix()["stages"])]
    manifest = pc._new_manifest(name, root, stages, None)
    del manifest["deliver_root"]
    manifest["schema_version"] = "1.1"
    manifest["crawl"]["evidence_index"] = "raw/00-crawl"
    pc._write_state_files(root, manifest)
    paths = dict(pc.PATHS, raw="raw", crawl="raw/00-crawl")
    pc._write_json(root / "config" / "paths.json", paths)
    (root / ".gitignore").write_text("\n".join([*pc.GITIGNORE_LINES, "raw/logs/", "raw/uploads/", "raw/client-docs/"]) + "\n", encoding="utf-8")
    (root / "README.html").write_text("<!doctype html><html lang=\"zh-CN\"><body><h1>项目索引</h1></body></html>", encoding="utf-8")
    (root / "docs" / "README.md").write_text(f"# {name} · 文档导航\n", encoding="utf-8")
    return root
