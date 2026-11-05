"""Where the files of a Luz project live.

A project has two roots. The *deliver root* is the project directory (``D:\\Codes\\NNN-名称``) and holds results only: ``docs/`` and the
implementation. The *state root* is the ``raw/`` of the project's Luz-Project session (``<输出根>\\NNN-名称\\raw``) and holds everything the
tools need: project.json, MANIFEST.json, APPROVALS.json, ``data/``, ``config/``, ``00-crawl/``, ``uploads/``, ``reviews/``, ``client-docs/``.

A project made before this layout has no ``deliver_root`` in project.json: its project root is both roots and its tool folders sit under ``raw/``
(``raw/reviews`` and so on) until ``project.py migrate`` moves them.

Every tool takes either path. Stored paths (artifacts, deliverables) are written relative to the root they belong to and found again with
:func:`locate`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


class ProjectError(ValueError):
    """Raised for an invalid project operation."""


DEFAULT_OUTPUT_ROOT = r"D:\Codes\skill输出\Luz-Project"
OUTPUT_ROOT_ENV = "LUZ_PROJECT_OUTPUT"
SESSION_NAME = re.compile(r"^\d{3}-[^\\/:*?\"<>|]+$")

# What belongs to the project directory. Everything else a path can name is tool state and lives in the state root.
DELIVER_DIRS = ("docs", "src", "test", "assets", "infra", "scripts")
# Below data/ and config/ only these names are tool state; business data (schema, seeds, fixtures ...) and the product's own config are results.
STATE_DATA = ("client", "stages", "ops", "acceptance", "artifacts.json", "changes.json", "baseline.json", "project.json", "sessions.json")
STATE_CONFIG = ("paths.json", "documents.json", "keys.example.json")


def output_root() -> Path:
    """Where the Luz-Project sessions are (``LUZ_PROJECT_OUTPUT`` overrides the default; tests use it)."""
    return Path(os.environ.get(OUTPUT_ROOT_ENV) or DEFAULT_OUTPUT_ROOT)


def _absolute(path: Path | str) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = Path.cwd() / value
    return value.resolve()


_CACHE: dict[str, tuple[int, int, dict]] = {}


def _manifest(root: Path) -> dict:
    """project.json of exactly this directory ({} without one); read again only when the file changed."""
    file = root / "project.json"
    try:
        stat = file.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        cached = _CACHE.get(str(file))
        if cached and cached[:2] == key:
            return cached[2]
        value = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    value = value if isinstance(value, dict) else {}
    _CACHE[str(file)] = (key[0], key[1], value)
    return value


def legacy_at(root: Path | str) -> bool:
    """Whether the project.json in exactly this directory belongs to a project of the old layout (a directory without one counts as new)."""
    manifest = _manifest(_absolute(root))
    return bool(manifest) and not manifest.get("deliver_root")


def resolve_state_root(project: Path | str) -> Path:
    """The state root for a path given either way: a path with project.json is the state root itself (a pre-migration project root too);
    a session directory resolves to its ``raw``; any other directory is a project directory whose state root is ``<输出根>\\<目录名>\\raw``."""
    path = _absolute(project)
    if (path / "project.json").is_file():
        return path
    if (path / "raw" / "project.json").is_file():
        return path / "raw"
    candidate = output_root() / path.name / "raw"
    if (candidate / "project.json").is_file():
        return candidate.resolve()
    raise ProjectError(f"不是 Luz 项目（{path} 下没有 project.json，{candidate} 也不存在）；新项目用 project.py init <名称> --project-dir <项目目录>")


def deliver_root(project: Path | str) -> Path:
    """The project directory: ``deliver_root`` of project.json; a project without one keeps its results in its own root."""
    root = resolve_state_root(project)
    value = _manifest(root).get("deliver_root")
    return _absolute(value) if value else root


def is_legacy(project: Path | str) -> bool:
    """True for a project made before the two-root layout: no ``deliver_root``, tool folders under ``raw/``."""
    return not _manifest(resolve_state_root(project)).get("deliver_root")


def session_dir(project: Path | str) -> Path | None:
    """The Luz-Project session directory (the parent of the state root), None for a project that has not been migrated."""
    root = resolve_state_root(project)
    return root.parent if not is_legacy(root) and root.name == "raw" else None


def summary_path(project: Path | str) -> Path | None:
    session = session_dir(project)
    return session / f"{session.name}.html" if session else None


def state_name(project: Path | str, name: str) -> str:
    """A tool folder as a path relative to the state root: ``reviews``, or ``raw/reviews`` in a project that still has the old layout."""
    return f"raw/{name}" if is_legacy(project) else name


def kind_of(rel: str) -> str:
    """``deliver`` or ``state`` for a project-relative path of the two-root layout."""
    parts = [p for p in str(rel).replace("\\", "/").split("/") if p and p != "."]
    if not parts:
        return "state"
    head = parts[0]
    if head in DELIVER_DIRS:
        return "deliver"
    if head == "data":
        return "state" if len(parts) < 2 or parts[1] in STATE_DATA else "deliver"
    if head == "config":
        return "state" if len(parts) < 2 or parts[1] in STATE_CONFIG else "deliver"
    return "state"


def locate(project: Path | str, rel: Path | str) -> Path:
    """The absolute path of a project-relative path: results in the project directory, everything else in the state root."""
    text = str(rel)
    if Path(text).is_absolute():
        return Path(text)
    root = resolve_state_root(project)
    deliver = deliver_root(root)
    text = text.replace("\\", "/")
    if deliver == root:
        return root / text
    if text.startswith("raw/"):                    # a reference written in the old layout (raw/reviews/...) names the folder of the state root
        text = text[4:]
    return (deliver if kind_of(text) == "deliver" else root) / text


def relative_to_project(project: Path | str, path: Path | str) -> str:
    """The project-relative form (posix) of an absolute path inside the state root or the project directory."""
    root = resolve_state_root(project)
    deliver = deliver_root(root)
    target = _absolute(path)
    inside = []
    for base in {root, deliver}:
        try:
            rel = target.relative_to(base).as_posix()
        except ValueError:
            continue
        inside.append((len(base.parts), rel, base))
    if not inside:
        raise ProjectError(f"产物必须位于项目目录或状态根内: {target}")
    inside.sort(key=lambda item: -item[0])
    for _, rel, base in inside:
        if base == root and deliver != root and kind_of(rel) == "deliver":
            continue
        if base == deliver and deliver != root and kind_of(rel) == "state":
            continue
        return rel
    raise ProjectError(f"产物所在位置不属于成果也不属于状态文件: {target}（成果放 docs、src、test、assets、infra、scripts，状态文件放状态根）")
