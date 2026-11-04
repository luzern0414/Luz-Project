"""Core project control-plane helpers for the :mod:`luz-project` skill.

The module deliberately uses only the Python standard library.  ``project.json``
is the canonical project state; the root ``MANIFEST.json`` and
``APPROVALS.json`` are human and tooling friendly mirrors/ledgers.  Generated
HTML is always derived from that state so a reviewer can inspect a project
without having to run the CLI.
"""

from __future__ import annotations

import html
import json
import re
import hashlib
import os
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MATRIX_FILE = ROOT / "references" / "development-matrix.json"

REQUIRED_DIRS = (
    "src",
    "test",
    "assets",
    "infra",
    "raw",
    "scripts",
    "config",
    "data",
    "data/stages",
    "docs/01-需求对接",
    "docs/02-产品开发",
    "docs/03-验收交付",
)
# Added in schema 1.1 (client documents, change ledger, acceptance checklist); older projects get them from ``migrate``. Only the folder every project
# uses at once is made up front: data/acceptance appears when the checklist is first written (project-structure.md rule 3, no empty folders in advance).
V11_DIRS = ("data/client",)
# What a project's .gitignore starts with: secrets, dependencies, build output, the Word sources and build intermediates of the client documents, local data.
GITIGNORE_LINES = (".env", ".env.*", "!.env.example", "config/*.local.*", "config/secrets*", "!config/keys.example.json", "node_modules/", ".venv/", "__pycache__/",
                   "dist/", "build/", "coverage/", "raw/logs/", "raw/uploads/", "raw/client-docs/", "data/users/*", "data/imports/*", "data/exports/*", "data/snapshots/*")
# The part of that list an existing repository can take without surprises (adopt and migrate append the missing lines only).
GITIGNORE_SAFE = (".env", ".env.*", "!.env.example", "node_modules/", "dist/", "build/", "raw/client-docs/")
# Where the Crawl preflight records really are (raw/00-crawl/<caller>-<stage>.json and .html); project.json points at that folder.
EVIDENCE_DIR = "raw/00-crawl"
# docs/ has exactly three folders and no folder below them, and holds only what is handed over: the PDF and XLSX of the client in 需求对接 and
# 验收交付, the HTML of the development stages in 产品开发. The review pages of the other stages (for your approval and for developers) are internal:
# they live in raw/reviews.
REVIEW_DIR = "raw/reviews"
DOC_FOLDERS = {
    "docs/01-需求对接": ((".pdf", ".xlsx"), "需求对接阶段交给客户的 PDF 和 XLSX"),
    "docs/02-产品开发": ((".html",), "开发阶段（架构、前端、后端、实现、测试、发布、运维）的 HTML"),
    "docs/03-验收交付": ((".pdf", ".xlsx"), "交付给客户的 PDF 和 XLSX"),
}
REQUIREMENT_STAGES = ("requirements", "research", "proposal", "client-intake")
DEVELOPMENT_STAGES = ("architecture", "design", "technical-plan", "implementation", "verification", "release", "operations")
DOC_DIRS = {**{stage: "docs/01-需求对接" for stage in REQUIREMENT_STAGES}, **{stage: "docs/02-产品开发" for stage in DEVELOPMENT_STAGES}, "handover": "docs/03-验收交付"}


def expected_doc_folder(stage: str, suffix: str) -> str | None:
    """Where a file of this stage and type belongs. The client's PDF and XLSX go to 需求对接 (requirement stages) or 验收交付 (handover and what the
    development stages hand over); the HTML of a development stage goes to 产品开发; the review pages of the other stages go to raw/reviews."""
    html = suffix.lower() == ".html"
    if stage in REQUIREMENT_STAGES:
        return REVIEW_DIR if html else "docs/01-需求对接"
    if stage == "handover":
        return REVIEW_DIR if html else "docs/03-验收交付"
    if stage in DEVELOPMENT_STAGES:
        return "docs/02-产品开发" if html else "docs/03-验收交付"
    return None


_ORIGINAL = "docs/02-产品开发/00-需求与方案"
_FLAT_V1 = "docs/02-产品开发"
# Where the files of the older layouts go (``migrate`` moves them): the first layout had 00-需求与方案/ and 原型/ below 02-产品开发 and the
# evidence pages in 03-验收交付; the second was flat but put every HTML in 02-产品开发. Folders that are not listed are never guessed.
LAYOUT_MOVES = (
    (f"{_ORIGINAL}/01-需求对接.html", f"{REVIEW_DIR}/01-需求评审.html"),
    (f"{_ORIGINAL}/02-调研结论.html", f"{REVIEW_DIR}/02-调研结论.html"),
    (f"{_ORIGINAL}/03-方案评审.html", f"{REVIEW_DIR}/03-方案评审.html"),
    (f"{_ORIGINAL}/04-业务逻辑确认评审.html", f"{REVIEW_DIR}/04-业务逻辑确认评审.html"),
    (f"{_FLAT_V1}/03-后端设计规范.html", "docs/02-产品开发/05-后端设计规范.html"),
    (f"{_FLAT_V1}/04-实现报告.html", "docs/02-产品开发/06-实现报告.html"),
    (f"{_FLAT_V1}/原型/01-小程序原型.html", "docs/02-产品开发/03-小程序原型.html"),
    (f"{_FLAT_V1}/原型/02-后台原型.html", "docs/02-产品开发/04-后台原型.html"),
    ("docs/03-验收交付/verification-report.html", "docs/02-产品开发/07-验收测试评审.html"),
    ("docs/03-验收交付/release-report.html", "docs/02-产品开发/08-发布评审.html"),
    ("docs/03-验收交付/operations-report.html", "docs/02-产品开发/09-运维评审.html"),
    ("docs/03-验收交付/handover-review.html", f"{REVIEW_DIR}/05-交付评审.html"),
    (f"{_FLAT_V1}/01-需求对接.html", f"{REVIEW_DIR}/01-需求评审.html"),
    (f"{_FLAT_V1}/02-调研结论.html", f"{REVIEW_DIR}/02-调研结论.html"),
    (f"{_FLAT_V1}/03-方案评审.html", f"{REVIEW_DIR}/03-方案评审.html"),
    (f"{_FLAT_V1}/04-业务逻辑确认评审.html", f"{REVIEW_DIR}/04-业务逻辑确认评审.html"),
    (f"{_FLAT_V1}/05-系统架构.html", "docs/02-产品开发/01-系统架构.html"),
    (f"{_FLAT_V1}/06-前端界面设计.html", "docs/02-产品开发/02-前端界面设计.html"),
    (f"{_FLAT_V1}/07-小程序原型.html", "docs/02-产品开发/03-小程序原型.html"),
    (f"{_FLAT_V1}/08-后台原型.html", "docs/02-产品开发/04-后台原型.html"),
    (f"{_FLAT_V1}/09-后端设计规范.html", "docs/02-产品开发/05-后端设计规范.html"),
    (f"{_FLAT_V1}/10-实现报告.html", "docs/02-产品开发/06-实现报告.html"),
    (f"{_FLAT_V1}/11-验收测试评审.html", "docs/02-产品开发/07-验收测试评审.html"),
    (f"{_FLAT_V1}/12-发布评审.html", "docs/02-产品开发/08-发布评审.html"),
    (f"{_FLAT_V1}/13-运维评审.html", "docs/02-产品开发/09-运维评审.html"),
    (f"{_FLAT_V1}/14-交付评审.html", f"{REVIEW_DIR}/05-交付评审.html"),
    # the layout that put the review pages next to the client files (07 to 10 in 需求对接) and the handover review in 验收交付
    ("docs/01-需求对接/07-需求评审.html", f"{REVIEW_DIR}/01-需求评审.html"),
    ("docs/01-需求对接/08-调研结论.html", f"{REVIEW_DIR}/02-调研结论.html"),
    ("docs/01-需求对接/09-方案评审.html", f"{REVIEW_DIR}/03-方案评审.html"),
    ("docs/01-需求对接/10-业务逻辑确认评审.html", f"{REVIEW_DIR}/04-业务逻辑确认评审.html"),
    ("docs/03-验收交付/交付评审.html", f"{REVIEW_DIR}/05-交付评审.html"),
    # the client files got a number in front of them when the requirements document became the first one
    ("docs/01-需求对接/05-需求变更台账.xlsx", "docs/01-需求对接/06-需求变更台账.xlsx"),
    ("docs/01-需求对接/04-业务逻辑确认表-回填.xlsx", "docs/01-需求对接/05-业务逻辑确认表-回填.xlsx"),
    ("docs/01-需求对接/04-业务逻辑确认表.xlsx", "docs/01-需求对接/05-业务逻辑确认表.xlsx"),
    ("docs/01-需求对接/03-功能清单.xlsx", "docs/01-需求对接/04-功能清单.xlsx"),
    ("docs/01-需求对接/02-系统架构图.pdf", "docs/01-需求对接/03-系统架构图.pdf"),
    ("docs/01-需求对接/01-方案说明书.pdf", "docs/01-需求对接/02-方案说明书.pdf"),
)
# Client originals (a client's own Word, PDF, spreadsheets) are inputs, not deliverables: they live in raw/uploads.
CLIENT_ORIGINALS_DIR = "docs/01-需求对接/00-客户原始资料"
STAGE_STATUSES = {
    "pending",
    "pending-review",
    "in-progress",
    "approved",
    "blocked",
    "rejected",
    "superseded",
    "completed",
}
SECRET_PATTERNS = (
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:access[_-]?token|auth[_-]?token|bearer|cookie)\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|client[_-]?secret|password)\s*[:=]\s*[\"']?(?!\$\{|[A-Z][A-Z0-9_]+\b)[A-Za-z0-9._~+/=-]{10,}"),
)


class ProjectError(ValueError):
    """Raised for an invalid project operation."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"JSON 无法解析: {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _slug(name: str) -> str:
    value = unicodedata.normalize("NFKC", str(name)).strip()
    value = re.sub(r"[^\w\-\u3400-\u9fff]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "project"


def _load_matrix() -> dict[str, Any]:
    matrix = _read_json(MATRIX_FILE)
    if not isinstance(matrix, dict) or not isinstance(matrix.get("stages"), list):
        raise ProjectError(f"开发矩阵无效: {MATRIX_FILE}")
    return matrix


def load_matrix() -> dict[str, Any]:
    """Return a copy of the development matrix for callers and the CLI."""
    return json.loads(json.dumps(_load_matrix(), ensure_ascii=False))


def _stage_defs() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in _load_matrix()["stages"]}


def _project_root(project: Path | str) -> Path:
    root = Path(project).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _manifest_path(project: Path) -> Path:
    return project / "project.json"


def load_project(project: Path | str) -> dict[str, Any]:
    root = _project_root(project)
    manifest = _read_json(_manifest_path(root))
    if not isinstance(manifest, dict):
        raise ProjectError(f"不是 Luz 项目目录（缺少 project.json）: {root}")
    return manifest


def _save_manifest(project: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = now_iso()
    _write_json(_manifest_path(project), manifest)
    _write_json(project / "MANIFEST.json", manifest)
    # data/project.json is intentionally a mirror so data exports can be moved
    # independently while retaining the project identity.
    _write_json(project / "data" / "project.json", manifest)


def _next_number(parent: Path) -> int:
    numbers = []
    if parent.is_dir():
        for child in parent.iterdir():
            if not child.is_dir():
                continue
            match = re.match(r"^(\d{3,})-", child.name)
            if match:
                numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _design_prototypes(root: Path | None) -> list[dict[str, Any]]:
    """The prototypes the design document of the project declares: one per ``prototype`` block, named after the front end (the tab title)."""
    if root is None:
        return []
    spec = _read_json(root / "data" / "stages" / "design.json", None)
    found: list[dict[str, Any]] = []
    for tab in (spec.get("tabs") if isinstance(spec, dict) else None) or []:
        for section in (tab.get("sections") or []) if isinstance(tab, dict) else []:
            for block in (section.get("blocks") or []) if isinstance(section, dict) else []:
                if isinstance(block, dict) and block.get("type") == "prototype" and str(block.get("file", "")).strip():
                    file = str(block["file"]).replace(chr(92), "/").strip()
                    name = str(tab.get("title") or block.get("title") or Path(file).stem)
                    number = re.match(r"(\d+)-", Path(file).name)
                    found.append({"id": f"prototype-{number.group(1) if number else len(found) + 1}", "name": f"{name}可交互原型", "audience": "dev", "format": "html", "kind": "prototype",
                                  "required": True, "path": file, "frontend": name})
    return found


def stage_deliverables(root: Path | None, item: dict[str, Any]) -> list[dict[str, Any]]:
    """The deliverables of a stage. Those of the matrix, except that the design stage lists one prototype per front end of the project's own design
    document (data/stages/design.json: a phone page and a back office give 03-手机原型 and 04-后台原型, a mini program gives 03-小程序原型);
    without that document the matrix default stands."""
    base = [dict(d) for d in item.get("deliverables", [])]
    if item.get("id") != "design":
        return base
    found = _design_prototypes(root)
    if not found:
        return base
    first = next((i for i, d in enumerate(base) if d.get("kind") == "prototype"), len(base))
    return [d for d in base[:first] if d.get("kind") != "prototype"] + found + [d for d in base[first:] if d.get("kind") != "prototype"]


def _empty_stage(item: dict[str, Any], current: bool = False, root: Path | None = None) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item.get("name", item["id"]),
        "owner": item.get("owner", "luz-project"),
        "contributors": list(item.get("contributors", [])),
        "docs_dir": item.get("docs_dir", DOC_DIRS.get(item["id"], "docs")),
        "required_inputs": list(item.get("required_inputs", [])),
        "outputs": list(item.get("outputs", [])),
        "crawl_focus": item.get("crawl_focus", ""),
        "approval": item.get("approval"),
        "next": item.get("next"),
        "failure_route": item.get("failure_route", item["id"]),
        "status": "in-progress" if current else "pending",
        "artifact_ids": [],
        "approval_id": None,
        "approved_hashes": {},
        "approved_sources": {},
        "client_dir": item.get("client_dir"),
        "deliverables": stage_deliverables(root, item),
        "standard": item.get("standard"),
        "rule_cards": list(item.get("rule_cards", [])),
        "updated_at": now_iso(),
    }


def schema_at_least(manifest: dict[str, Any], version: str) -> bool:
    def key(value: str) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", str(value or "0")))
    return key(manifest.get("schema_version", "1.0")) >= key(version)


def _write_initial_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def create_project(name: str, output_root: Path | str, repository: str | None = None) -> Path:
    """Create a numbered project root and its complete, safe scaffold."""
    if not str(name).strip():
        raise ProjectError("项目名称不能为空")
    parent = Path(output_root).expanduser()
    if not parent.is_absolute():
        parent = Path.cwd() / parent
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    number = _next_number(parent)
    folder = parent / f"{number:03d}-{_slug(name)}"
    folder.mkdir(parents=False, exist_ok=False)
    for relative in (*REQUIRED_DIRS, *V11_DIRS):
        (folder / relative).mkdir(parents=True, exist_ok=True)
    for relative in ("src/.gitkeep", "test/.gitkeep", "assets/.gitkeep", "infra/.gitkeep", "raw/.gitkeep"):     # folders below the first level are made when something is written there
        _write_initial_file(folder / relative)

    matrix = _load_matrix()
    stages = [_empty_stage(item, current=(index == 0), root=folder) for index, item in enumerate(matrix["stages"])]
    manifest: dict[str, Any] = {
        "schema_version": "1.1",
        "project_id": f"PROJECT-{number:03d}",
        "name": str(name).strip(),
        "slug": _slug(name),
        "status": "draft",
        "current_stage": stages[0]["id"] if stages else None,
        "repository": repository,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "crawl": {
            "task_id": None,
            "task_root": None,
            "evidence_index": EVIDENCE_DIR,
            "reuse_policy": "reuse-within-project",
        },
        "stages": stages,
        "policies": {
            "html_generated": True,
            "require_user_approval": True,
            "secret_values_in_artifacts": False,
            "production_data_in_project": False,
        },
    }
    _write_json(folder / "project.json", manifest)
    _write_json(folder / "MANIFEST.json", manifest)
    _write_json(folder / "data" / "project.json", manifest)
    _write_json(folder / "APPROVALS.json", {"schema_version": "1.0", "approvals": []})
    _write_json(folder / "data" / "artifacts.json", [])
    _write_json(folder / "data" / "ops" / "checks.json", [])
    _write_json(folder / "data" / "changes.json", {"schema_version": "1.0", "changes": []})
    _write_json(folder / "config" / "documents.json", {"theme": None, "note": "客户文档主题：按本项目行业和受众从 Luz-Design references/themes.json 选择，运行 project.py client theme 设置"})
    _write_initial_file(folder / ".gitignore", "\n".join(GITIGNORE_LINES) + "\n")
    _write_initial_file(folder / ".env.example", "# Set values locally; never commit the real .env.\nAPP_ENV=local\nAPI_BASE_URL=\nSERVICE_API_KEY=\n")
    # Only the config the tools use from the start: where things live, the document theme (above) and the list of key references. project, environments,
    # urls, features and validation.json are written by the stage that has something to put in them (technical-plan, implementation), never as empty files.
    config_files = {
        "keys.example.json": {"api_key_env": "", "secret_ref": ""},
        "paths.json": {"src": "src", "frontend": "src/frontend", "backend": "src/backend", "shared": "src/shared", "test": "test", "unit": "test/unit", "integration": "test/integration", "e2e": "test/e2e", "docs": "docs", "raw": "raw", "crawl": EVIDENCE_DIR, "assets": "assets", "infra": "infra", "migrations": "infra/migrations"},
    }
    for filename, payload in config_files.items():
        _write_json(folder / "config" / filename, payload)
    # The first render makes a newly created project immediately reviewable.
    render_project(folder)
    return folder


def _artifacts_path(project: Path) -> Path:
    return project / "data" / "artifacts.json"


def _load_artifacts(project: Path) -> list[dict[str, Any]]:
    value = _read_json(_artifacts_path(project), [])
    if not isinstance(value, list):
        raise ProjectError(f"artifacts.json 必须是数组: {_artifacts_path(project)}")
    return value


def _save_artifacts(project: Path, artifacts: list[dict[str, Any]]) -> None:
    _write_json(_artifacts_path(project), artifacts)


def _next_id(items: Iterable[dict[str, Any]], prefix: str) -> str:
    highest = 0
    for item in items:
        value = str(item.get("id") or item.get("artifact_id") or "")
        match = re.search(r"(\d+)$", value)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def artifact_id_errors(manifest: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[str]:
    """An artifact number names exactly one registered file: no number twice in the register, none twice in a stage's list, none in two stages."""
    errors: list[str] = []
    for artifact_id, count in Counter(str(a.get("id")) for a in artifacts).items():
        if count > 1:
            errors.append(f"产物编号重复: {artifact_id} 在 data/artifacts.json 里登记了 {count} 次")
    owners: dict[str, list[str]] = {}
    for stage in manifest.get("stages", []):
        for artifact_id, count in Counter(str(i) for i in stage.get("artifact_ids") or []).items():
            owners.setdefault(artifact_id, []).append(str(stage.get("id")))
            if count > 1:
                errors.append(f"产物编号重复: 阶段 {stage.get('id')} 的 artifact_ids 里 {artifact_id} 登记了 {count} 次（project.py migrate 去掉重复的编号）")
    for artifact_id, stages in owners.items():
        if len(stages) > 1:
            errors.append(f"产物编号重复: {artifact_id} 同时属于阶段 {'、'.join(stages)}")
    return errors


def _next_artifact_id(root: Path, manifest: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    """The next ART number. A number an approval, a stage or the register has ever used is not handed out again, even after its file was removed."""
    used: list[dict[str, Any]] = [{"id": str(a.get("id"))} for a in artifacts]
    for stage in manifest.get("stages", []):
        used += [{"id": str(i)} for i in [*(stage.get("artifact_ids") or []), *((stage.get("approved_hashes") or {}).keys())]]
    for approval in _read_json(root / "APPROVALS.json", {}).get("approvals", []) if isinstance(_read_json(root / "APPROVALS.json", {}), dict) else []:
        used += [{"id": str(i)} for i in (approval.get("artifact_hashes") or {}).keys()]
    return _next_id(used, "ART")


def _safe_relative(root: Path, path: Path | str) -> tuple[Path, str]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ProjectError(f"产物必须位于项目目录内: {candidate}") from exc
    return candidate, relative.as_posix()


def stage_document_path(stage: str) -> str:
    """The relative path of the developer document of a stage, from its deliverable in the matrix."""
    for item in _load_matrix()["stages"]:
        if item["id"] == stage:
            pages = [d for d in item.get("deliverables", []) if d.get("format") == "html"]
            pages.sort(key=lambda d: d.get("audience") != "dev")               # the developer document first, then Luz-Ops' page
            if pages:
                return str(pages[0]["path"])
    raise ProjectError(f"阶段 {stage} 在开发矩阵里没有开发文档")


def _stage_page(stage: str) -> str | None:
    """The first HTML deliverable of a stage (developer document, or Luz-Ops' report page), if the matrix names one."""
    for item in _load_matrix()["stages"]:
        if item["id"] == stage:
            for d in item.get("deliverables", []):
                if d.get("format") == "html":
                    return str(d["path"])
    return None


def require_crawl(project: Path | str, stage: str) -> None:
    """A document of a stage is generated only after that stage's Crawl preflight is complete: real search and body reading,
    then the supplement (sources, conclusions, where each is used, adoption decision, uncovered scope) and ``check``."""
    root = _project_root(project)
    manifest = load_project(root)
    from crawl_gate import crawl_errors
    errors = crawl_errors(root, stage, caller=_stage_record(manifest, stage)["owner"])
    if errors:
        raise ProjectError(f"生成 {stage} 阶段的文档前必须先用 Luz-Crawl 取得足够的信息（run → 读正文 → conclude → check）: " + "; ".join(errors))


def _stage_record(manifest: dict[str, Any], stage: str) -> dict[str, Any]:
    for item in manifest.get("stages", []):
        if item.get("id") == stage:
            return item
    raise ProjectError(f"未知开发阶段: {stage}")


def _invalidate_downstream(manifest: dict[str, Any], stage: str) -> None:
    ids = [item["id"] for item in _load_matrix()["stages"]]
    try:
        position = ids.index(stage)
    except ValueError:
        return
    for downstream in ids[position + 1 :]:
        record = _stage_record(manifest, downstream)
        if record.get("artifact_ids") or record.get("approval_id"):
            record["status"] = "superseded"
        elif record.get("status") not in {"blocked", "rejected"}:
            record["status"] = "pending"
        record["approval_id"] = None
        record["approved_hashes"] = {}
        record["approved_sources"] = {}
        record["updated_at"] = now_iso()
    current = _stage_record(manifest, stage)
    current["status"] = "pending-review"
    current["approval_id"] = None
    current["approved_hashes"] = {}
    current["approved_sources"] = {}
    current["updated_at"] = now_iso()
    manifest["current_stage"] = stage
    manifest["status"] = "active"


def register_artifact(
    project: Path | str,
    stage: str,
    artifact: Path | str,
    kind: str,
    source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Register an artifact and invalidate approvals when its content changes."""
    root = _project_root(project)
    manifest = load_project(root)
    stage_record = _stage_record(manifest, stage)
    path, relative = _safe_relative(root, artifact)
    if not path.is_file():
        raise ProjectError(f"产物不存在: {path}")
    source_list = list(dict.fromkeys(str(item) for item in (source_ids or []) if str(item).strip()))
    artifacts = _load_artifacts(root)
    clashes = artifact_id_errors(manifest, artifacts)
    if clashes:
        raise ProjectError("产物登记表里有重复的编号，先修复再登记（" + "；".join(clashes[:3]) + "）")
    digest = sha256_file(path)
    existing = next((item for item in artifacts if item.get("stage") == stage and item.get("path") == relative), None)
    changed = existing is None or existing.get("sha256") != digest
    if existing is None:
        record = {
            "id": _next_artifact_id(root, manifest, artifacts),
            "project_id": manifest["project_id"],
            "stage": stage,
            "path": relative,
            "kind": str(kind),
            "source_ids": source_list,
            "sha256": digest,
            "version": 1,
            "registered_at": now_iso(),
            "updated_at": now_iso(),
        }
        artifacts.append(record)
        stage_record.setdefault("artifact_ids", []).append(record["id"])
    else:
        record = existing
        if changed:
            record["version"] = int(record.get("version", 1)) + 1
        record.update({"kind": str(kind), "source_ids": source_list, "sha256": digest, "updated_at": now_iso()})
    _save_artifacts(root, artifacts)
    if changed and (stage_record.get("status") in {"approved", "completed"} or stage_record.get("approval_id")):
        _invalidate_downstream(manifest, stage)
    elif stage_record.get("status") == "pending":
        stage_record["status"] = "pending-review"
        manifest["status"] = "active"
        # Preparing a later artifact must not skip the current user's gate.
        if not manifest.get("current_stage"):
            manifest["current_stage"] = stage
    stage_record["updated_at"] = now_iso()
    _save_manifest(root, manifest)
    return dict(record)


def unregister_artifacts(project: Path | str, kinds: Iterable[str], *, delete_files: bool = True) -> list[str]:
    """Drop registered artifacts of the given kinds (and their files); used when a deliverable is retired."""
    root = _project_root(project)
    manifest = load_project(root)
    kinds = set(kinds)
    artifacts = _load_artifacts(root)
    gone = [a for a in artifacts if a.get("kind") in kinds]
    if not gone:
        return []
    keep = [a for a in artifacts if a.get("kind") not in kinds]
    _save_artifacts(root, keep)
    ids = {a["id"] for a in gone}
    for stage in manifest.get("stages", []):
        stage["artifact_ids"] = [i for i in stage.get("artifact_ids", []) if i not in ids]
        stage["approved_hashes"] = {k: v for k, v in (stage.get("approved_hashes") or {}).items() if k not in ids}
    _save_manifest(root, manifest)
    removed = []
    for a in gone:
        path = root / a["path"]
        if delete_files and path.is_file():
            path.unlink()
        removed.append(a["path"])
    return removed


def _load_approvals(project: Path) -> dict[str, Any]:
    value = _read_json(project / "APPROVALS.json", {"schema_version": "1.0", "approvals": []})
    if not isinstance(value, dict) or not isinstance(value.get("approvals"), list):
        raise ProjectError("APPROVALS.json 格式无效")
    return value


def approve_stage(project: Path | str, stage: str, note: str, approver: str) -> dict[str, Any]:
    root = _project_root(project)
    manifest = load_project(root)
    stage_record = _stage_record(manifest, stage)
    if not str(note).strip() or not str(approver).strip():
        raise ProjectError("审批说明和审批人不能为空")
    stage_ids = [str(item["id"]) for item in _load_matrix()["stages"]]
    current_index = stage_ids.index(stage)
    prior = {str(item.get("id")): item for item in manifest.get("stages", [])}
    incomplete = [item_id for item_id in stage_ids[:current_index] if prior.get(item_id, {}).get("status") not in {"approved", "completed"}]
    if incomplete:
        raise ProjectError(f"阶段 {stage} 的前置审批尚未完成: {', '.join(incomplete)}")
    from crawl_gate import crawl_errors
    research_errors = crawl_errors(root, stage, caller=stage_record["owner"])
    if research_errors:
        raise ProjectError("; ".join(research_errors))
    preflight = root / "raw" / "00-crawl" / f'{stage_record["owner"]}-{stage}.json'
    record = _read_json(preflight)
    task_root = str(Path(record["task_root"]).resolve())
    bound_task = manifest["crawl"].get("task_root")
    if bound_task and str(Path(bound_task).resolve()) != task_root:
        raise ProjectError("同一项目必须复用绑定的 Crawl 任务，不能换成另一项需求的记录")
    manifest["crawl"]["task_root"] = task_root
    _save_manifest(root, manifest)
    for path in (preflight, preflight.with_suffix(".html")):
        if not path.is_file():
            raise ProjectError("缺少前置检索结论 HTML，请先 conclude")
        register_artifact(root, stage, path, "research-evidence")
    manifest = load_project(root)
    stage_record = _stage_record(manifest, stage)
    errors = gate_stage(root, stage)
    if errors:
        raise ProjectError("阶段门禁未通过: " + "; ".join(errors))
    artifacts = _load_artifacts(root)
    current = [item for item in artifacts if item.get("stage") == stage]
    if not current:
        raise ProjectError(f"阶段 {stage} 尚无可审批产物")
    if not any(str(item.get("path", "")).endswith(".html") and item.get("kind") != "research-evidence" for item in current):
        raise ProjectError("阶段缺少可审阅的 HTML，不能只审批数据文件")
    import dev_documents
    if dev_documents.has_standard(stage):
        spec = _read_json(root / "data" / "stages" / f"{stage}.json", {})
        errors = dev_documents.validate(stage, spec, root)
        if errors or not any(a.get("kind") in {"architecture-spec", "stage-spec"} for a in current):
            raise ProjectError("这份开发文档没有通过 references/dev-documents.md 的标准，不能审批: " + "; ".join(errors or ["没有登记文档数据"]))
    if schema_at_least(manifest, "1.1"):
        import client_flow
        problems = client_flow.stage_checks(root, stage)
        if problems:
            raise ProjectError("客户文档/变更门禁未通过: " + "; ".join(problems))
    hashes: dict[str, str] = {}
    for item in current:
        path = root / str(item["path"])
        if not path.is_file():
            raise ProjectError(f"阶段产物不存在: {path}")
        digest = sha256_file(path)
        if digest != item.get("sha256"):
            raise ProjectError(f"阶段产物已变化，请重新登记: {item['path']}")
        hashes[str(item["id"])] = digest
    ledger = _load_approvals(root)
    approval = {
        "id": _next_id(ledger["approvals"], "APPROVAL"),
        "project_id": manifest["project_id"],
        "stage": stage,
        "status": "approved",
        "note": str(note).strip(),
        "approver": str(approver).strip(),
        "approved_at": now_iso(),
        "artifact_hashes": hashes,
    }
    ledger["approvals"].append(approval)
    _write_json(root / "APPROVALS.json", ledger)
    stage_record["status"] = "approved"
    stage_record["approval_id"] = approval["id"]
    stage_record["approved_hashes"] = hashes
    if schema_at_least(manifest, "1.1"):
        import client_flow
        stage_record["approved_sources"] = client_flow.tracked_hashes(root, stage)
    stage_record["updated_at"] = now_iso()
    next_stage = _stage_record(manifest, stage).get("next")
    if next_stage:
        manifest["current_stage"] = next_stage
        next_record = _stage_record(manifest, next_stage)
        if next_record.get("status") in {"pending", "superseded"}:
            next_record["status"] = "in-progress"
            next_record["updated_at"] = now_iso()
        manifest["status"] = "active"
    else:
        manifest["current_stage"] = stage
        manifest["status"] = "completed"
        stage_record["status"] = "completed"
    _save_manifest(root, manifest)
    return dict(approval)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (list, tuple)):
        return "、".join(_display(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


STATUS_LABELS = {"pending": "待开始", "pending-review": "待审阅", "in-progress": "进行中", "approved": "已批准", "blocked": "已阻断", "rejected": "已退回",
                 "superseded": "已失效", "completed": "已完成", "draft": "草稿", "active": "进行中", "archived": "已归档"}
STAGE_ICONS = {"requirements": "flag", "research": "search", "proposal": "file", "client-intake": "inbox", "architecture": "layers", "design": "pen", "technical-plan": "settings",
               "implementation": "package", "verification": "check", "release": "bolt", "operations": "server", "handover": "book", "project": "grid"}


def doc_theme(project: Path | str | None) -> str:
    """Review pages use the project's document theme; before one is chosen they use the neutral graphite theme."""
    if project is not None:
        value = _read_json(_project_root(project) / "config" / "documents.json", {}) or {}
        if value.get("theme"):
            return str(value["theme"])
    return "b2b-graphite"


def _html_page(
    *,
    project_id: str,
    document_id: str,
    stage: str,
    status: str,
    version: str,
    title: str,
    body: str,
    theme: str = "b2b-graphite",
) -> str:
    """Developer-facing review page, rendered by Luz-Design: icon before the title and each section, theme tokens, one font."""
    attrs = (f'data-project-id="{html.escape(project_id, quote=True)}" data-document-id="{html.escape(document_id, quote=True)}" data-stage="{html.escape(stage, quote=True)}" '
             f'data-status="{html.escape(status, quote=True)}" data-version="{html.escape(version, quote=True)}"')
    import sys

    design = ROOT.parent / "Luz-Design" / "scripts"
    if str(design) not in sys.path:
        sys.path.insert(0, str(design))
    import showcase  # type: ignore

    import reading_style

    return reading_style.apply(showcase.page(title, theme, body, icon=STAGE_ICONS.get(stage, "file"), html_attrs=attrs, formal=True))


def render_project(project: Path | str) -> list[Path]:
    """Render the project index; it links each stage to its developer document (the numbered pages under docs/), none is written per stage."""
    root = _project_root(project)
    manifest = load_project(root)
    artifacts = _load_artifacts(root)
    rendered: list[Path] = []
    stages = manifest.get("stages", [])
    stage_rows = []
    registered_paths = {str(item.get("path", "")).replace(chr(92), chr(47)) for item in artifacts}
    page_links: dict[str, str] = {}
    for item in stages:
        stage_id = str(item["id"])
        docs_dir = root / DOC_DIRS.get(stage_id, "docs")           # only to find pages an older version wrote; the folder is never created here
        for stub in (docs_dir / f"{stage_id}.html", docs_dir / f"stage-{stage_id}.html"):       # pages an older version wrote for every stage
            relative = stub.relative_to(root).as_posix()
            if relative in registered_paths or not stub.is_file():
                continue
            text = stub.read_text(encoding="utf-8", errors="replace")
            if "阶段概况" in text or f'data-document-id="DOC-{manifest["project_id"]}-{stage_id}"' in text:      # a page this tool wrote for the stage itself
                stub.unlink()
        document = _stage_page(stage_id)
        link = document if document and (root / document).is_file() else ""
        page_links[stage_id] = link
        stage_rows.append(
            f'<tr><td>{html.escape(str(item.get("name", stage_id)))}</td>'
            f'<td>{html.escape(stage_id)}</td>'
            f'<td>{html.escape(str(item.get("owner", "—")))}</td>'
            f'<td>{html.escape(STATUS_LABELS.get(str(item.get("status", "pending")), str(item.get("status", "pending"))))}</td>'
            f'<td>{f"<a href={chr(34)}{html.escape(link, quote=True)}{chr(34)}>{html.escape(Path(link).stem)}</a>" if link else "尚未编写"}</td></tr>'
        )
    approvals = _load_approvals(root).get("approvals", [])
    approval_rows = "".join(f'<tr><td>{html.escape(str(a.get("stage")))}</td><td>{html.escape(str(a.get("approver")))}</td><td>{html.escape(str(a.get("approved_at")))}</td><td>{html.escape(str(a.get("note")))}</td></tr>' for a in approvals) or "<tr><td colspan=4>暂无审批</td></tr>"
    contract_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>" for k, v in _load_matrix().get("directory_contract", {}).items())
    requirement_link, architecture_link, verification_link = "docs/01-需求对接", "docs/02-产品开发", "docs/03-验收交付"
    body = f'<h2>项目概况</h2><div class="meta"><span class="chip-s">{html.escape(STATUS_LABELS.get(str(manifest.get("status", "draft")), str(manifest.get("status", "draft"))))}</span><span>项目编号：{html.escape(str(manifest.get("project_id")))}</span><span>当前阶段：{html.escape(next((str(x.get("name")) for x in stages if x.get("id") == manifest.get("current_stage")), str(manifest.get("current_stage"))))}</span></div><p class="notice">项目目录是项目管理和配置边界：config 保存参数与 Key 引用，data 保存开发/测试/脱敏业务数据，生产数据库仍是线上事实源。</p><h2>开发矩阵</h2><table><thead><tr><th>阶段</th><th>稳定 ID</th><th>负责人</th><th>状态</th><th>文档</th></tr></thead><tbody>{"".join(stage_rows)}</tbody></table><h2>审批记录</h2><table><thead><tr><th>阶段</th><th>审批人</th><th>时间</th><th>说明</th></tr></thead><tbody>{approval_rows}</tbody></table><h2>目录入口</h2><ul><li><a href="{html.escape(requirement_link, quote=True)}">需求对接</a></li><li><a href="{html.escape(architecture_link, quote=True)}">产品开发与系统架构</a></li><li><a href="{html.escape(verification_link, quote=True)}">验收交付</a></li></ul><h2>目录约定</h2><table><thead><tr><th>目录</th><th>放什么</th></tr></thead><tbody>{contract_rows}</tbody></table>'
    index = root / "README.html"
    index.write_text(_html_page(project_id=str(manifest["project_id"]), document_id=f'DOC-{manifest["project_id"]}-README', stage="project", status=str(manifest.get("status", "draft")), version=str(manifest.get("updated_at", "")), title=f'{manifest["name"]} · 项目索引', body=body, theme=doc_theme(root)), encoding="utf-8")
    rendered.insert(0, index)
    write_docs_index(root, manifest)
    return rendered


DOCS_INDEX_MARK = "文档导航"
FOLDER_NOTE = {"docs/01-需求对接": "需求对接阶段交给客户的文件，只有 PDF 和 Excel，平铺不建子目录；客户给的原始资料放 raw/uploads，需求、调研、方案、客户信息的评审页放 raw/reviews。",
               "docs/02-产品开发": "开发阶段的 HTML，只有 HTML，平铺不建子目录，一个“两位序号加中文名”的顺序：系统架构、前端界面设计、各前端原型、后端设计规范、实现报告、测试、发布、运维评审（标准见 Luz-Project 的 references/dev-documents.md）。",
               "docs/03-验收交付": "交付给客户的 PDF 和 Excel：使用说明、验收清单、台账快照、测试报告、发布说明、运维手册、用户协议、隐私政策，平铺不建子目录。"}


def write_docs_index(root: Path, manifest: dict[str, Any]) -> Path | None:
    """docs/README.md lists the files that exist, folder by folder; a README somebody wrote by hand is left alone."""
    target = root / "docs" / "README.md"
    if target.is_file() and f"{DOCS_INDEX_MARK}" not in target.read_text(encoding="utf-8", errors="replace").splitlines()[0]:
        return None
    lines = [f"# {manifest['name']} · {DOCS_INDEX_MARK}", "", "目录按阶段划分：需求对接交给客户的文件在 01，开发阶段的 HTML 在 02，交付给客户的文件在 03；每个目录只有一层，给你审批的评审页在 raw/reviews。客户文档由 `data/client/` 里的数据生成，不手改；需求变更先登记到需求变更台账。项目索引见根目录 `README.html`。", ""]
    for folder, note in FOLDER_NOTE.items():
        base = root / folder
        if not base.is_dir():
            continue
        lines += [f"## {Path(folder).name}", "", note, ""]
        files = [f for f in sorted(base.iterdir()) if f.is_file() and not f.name.startswith(".")]
        lines += [f"- [{f.name}]({quote(f.relative_to(root / 'docs').as_posix())})" for f in files] + [""]
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return target


def layout_errors(root: Path) -> list[str]:
    """docs/ keeps three folders, one level each: the files in them are the ones their readers use, and nothing else."""
    errors: list[str] = []
    docs = root / "docs"
    if not docs.is_dir():
        return errors
    for item in sorted(docs.iterdir()):
        name = f"docs/{item.name}"
        if item.is_dir() and name not in DOC_FOLDERS and not item.name.startswith("."):
            errors.append(f"目录约定：docs 里只有 01-需求对接、02-产品开发、03-验收交付三个目录，多出了 {name}/（客户原始资料放 raw/uploads，其他文档放 raw/）")
        elif item.is_file() and item.name != "README.md":
            errors.append(f"目录约定：docs 根目录只放 README.md，{name} 要放进三个目录之一或移出 docs")
    for folder, (suffixes, what) in DOC_FOLDERS.items():
        base = root / folder
        if not base.is_dir():
            continue
        for item in sorted(base.iterdir()):
            relative = f"{folder}/{item.name}"
            if item.name.startswith("."):
                continue
            if item.is_dir():
                errors.append(f"目录约定：{folder} 只有一层，不能有子目录 {item.name}/（里面的文件直接放在 {folder}，不属于这里的移到 raw/）；旧项目运行 project.py migrate")
            elif item.suffix.lower() not in suffixes:
                errors.append(f"目录约定：{folder} 只放{what}（{'、'.join(suffixes)}），{relative} 不属于这里；原始资料和 Word 源文件放 raw/")
    return errors


def placement_errors(artifacts: list[dict[str, Any]]) -> list[str]:
    """A registered document sits in the folder its stage names: a requirement page in 需求对接, a development page in 产品开发."""
    errors: list[str] = []
    for item in artifacts:
        rel = str(item.get("path", "")).replace(chr(92), "/")
        parts = rel.split("/")
        if len(parts) < 3 or parts[0] not in ("docs", "raw") or (parts[0] == "raw" and parts[1] != "reviews"):
            continue
        expected = expected_doc_folder(str(item.get("stage", "")), Path(rel).suffix)
        if expected and f"{parts[0]}/{parts[1]}" != expected:
            errors.append(f"目录约定：{item.get('stage')} 阶段的 {Path(rel).suffix} 文件放 {expected}，不放 {parts[0]}/{parts[1]}：{rel}")
    return errors


def _rewrite_text_paths(root: Path, moves: list[tuple[str, str]]) -> list[str]:
    """Point the project's data files at the new locations of moved files; returns the files that changed."""
    changed: list[str] = []
    candidates = [root / "data" / "artifacts.json", root / "data" / "client" / "build.json", root / "config" / "paths.json"]
    candidates += sorted((root / "data" / "stages").glob("*.json"))
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        new = text
        for old, fresh in moves:
            new = new.replace(old, fresh).replace(old.replace("/", "\\\\"), fresh.replace("/", "\\\\"))
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(path.relative_to(root).as_posix())
    return changed


def migrate_layout(root: Path) -> dict[str, Any]:
    """Move the files of the older docs layouts to the flat one. Only files the standard knows are moved; everything else is reported."""
    import shutil

    moves: list[tuple[str, str]] = []
    for old, fresh in LAYOUT_MOVES:
        source, target = root / old, root / fresh
        if source.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moves.append((old, fresh))
    originals = root / CLIENT_ORIGINALS_DIR
    if originals.is_dir():
        uploads = root / "raw" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        for f in sorted(originals.rglob("*")):
            if f.is_file():
                target = uploads / f.name
                n = 1
                while target.exists():
                    target = uploads / f"{f.stem}-{n}{f.suffix}"
                    n += 1
                shutil.move(str(f), str(target))
                moves.append((f.relative_to(root).as_posix(), target.relative_to(root).as_posix()))
    for old_dir in (_ORIGINAL, f"{_FLAT_V1}/原型", CLIENT_ORIGINALS_DIR):
        folder = root / old_dir
        if folder.is_dir() and not any(folder.rglob("*")):
            shutil.rmtree(folder)
    rewritten = _rewrite_text_paths(root, moves)
    leftovers = layout_errors(root)
    return {"moved": [{"from": a, "to": b} for a, b in moves], "rewritten": rewritten, "leftovers": leftovers}


def _scan_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _validate_links(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    # Only the static markup carries links: a script or style body holds template strings (src="${P(i)}", href='%23s') that are code, not files.
    text = re.sub(r"(<(script|style)\b[^>]*>).*?(</\2\s*>)", r"\1\3", text, flags=re.I | re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for _, raw in re.findall(r"(?:href|src)\s*=\s*([\"'])(.*?)\1", text, flags=re.I):
        raw = html.unescape(raw)
        if raw.startswith("#"):
            continue
        parts = urlsplit(raw)
        if parts.scheme or parts.netloc:
            continue
        target = unquote(parts.path)
        if not target:
            continue
        candidate = (path.parent / target).resolve()
        if not candidate.exists():
            errors.append(f"断开的本地链接: {path.relative_to(path.parents[1])} -> {raw}")
    return errors


def stage_primary_document(stage: dict[str, Any]) -> str | None:
    """The page a stage puts up for review: its first HTML deliverable, the developer document before an Ops page (as stage_document_path)."""
    pages = [d for d in stage.get("deliverables") or [] if isinstance(d, dict) and d.get("format") == "html"]
    pages.sort(key=lambda d: d.get("audience") != "dev")
    return str(pages[0]["path"]).replace(chr(92), "/") if pages else None


def deliverable_errors(root: Path, manifest: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[str]:
    """A stage whose review page is registered has put its work up for review: the other HTML it lists as required (the prototypes of the design stage) exist.

    PDF and XLSX deliverables are not checked here: the client documents are gated by approve and by Luz-Ops, and the agreements depend on the product.
    """
    registered = {str(a.get("path", "")).replace(chr(92), "/") for a in artifacts}
    errors: list[str] = []
    for stage in manifest.get("stages") or []:
        primary = stage_primary_document(stage)
        if not primary or primary not in registered:
            continue
        for d in stage.get("deliverables") or []:
            path = str(d.get("path", "")).replace(chr(92), "/")
            if d.get("format") == "html" and d.get("required", True) and path and path != primary and not (root / path).is_file():
                errors.append(f"交付物不存在: {path}（阶段 {stage.get('id')} 的「{d.get('name', d.get('id'))}」；该阶段的文档已登记，它列出的交付物要一并存在。清单过期时运行 project.py migrate 按设计文档刷新）")
    return errors


def validate_project(project: Path | str, strict: bool = False) -> list[str]:
    """Return actionable validation errors; an empty list means the project is valid."""
    root = _project_root(project)
    errors: list[str] = []
    if not root.is_dir():
        return [f"项目目录不存在: {root}"]
    aliases = _aliases(root)
    for relative in REQUIRED_DIRS:
        target = _alias_target(aliases, relative)
        if target is None:
            continue
        if not (root / target).is_dir():
            errors.append(f"缺少目录: {relative}" + (f"（别名 {target}）" if target != relative else ""))
    for filename in ("project.json", "MANIFEST.json", "APPROVALS.json", "README.html", "data/artifacts.json"):
        if not (root / filename).is_file():
            errors.append(f"缺少文件: {filename}")
    try:
        manifest = load_project(root)
    except ProjectError as exc:
        return errors + [str(exc)]
    definitions = _stage_defs()
    manifest_stages = manifest.get("stages")
    if not isinstance(manifest_stages, list):
        errors.append("project.json 的 stages 必须是数组")
        manifest_stages = []
    ids = [str(item.get("id")) for item in manifest_stages]
    if len(ids) != len(set(ids)):
        errors.append("stages 含重复稳定 ID")
    if set(ids) != set(definitions):
        errors.append("project.json 的 stages 与 development-matrix 不一致（旧项目请运行 project.py migrate <项目>）")
    if schema_at_least(manifest, "1.1"):
        for relative in V11_DIRS:
            if not (root / relative).is_dir():
                errors.append(f"缺少目录: {relative}")
        import client_flow
        errors.extend(client_flow.tracked_drift(root, manifest))
    artifacts = []
    try:
        artifacts = _load_artifacts(root)
    except ProjectError as exc:
        errors.append(str(exc))
    artifact_map = {str(item.get("id")): item for item in artifacts}
    errors.extend(artifact_id_errors(manifest, artifacts))
    errors.extend(deliverable_errors(root, manifest, artifacts))
    for item in artifacts:
        path_value = str(item.get("path", ""))
        try:
            path, relative = _safe_relative(root, path_value)
        except ProjectError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"产物不存在: {relative}")
        elif item.get("sha256") != sha256_file(path):
            errors.append(f"产物哈希漂移: {relative}")
    try:
        approvals = _load_approvals(root).get("approvals", [])
    except ProjectError as exc:
        errors.append(str(exc))
        approvals = []
    if schema_at_least(manifest, "1.1"):
        errors.extend(layout_errors(root))
        errors.extend(placement_errors(artifacts))
    for stage in manifest_stages:
        status = str(stage.get("status", "pending"))
        if status not in STAGE_STATUSES:
            errors.append(f"阶段状态无效: {stage.get('id')}={status}")
        if status in {"approved", "completed"}:
            approval_id = stage.get("approval_id")
            approval = next((a for a in approvals if a.get("id") == approval_id), None)
            if not approval:
                errors.append(f"已批准阶段缺少审批记录: {stage.get('id')}")
            else:
                expected = {a["id"]: a["sha256"] for a in artifacts if a.get("stage") == stage.get("id")}
                if not expected or stage.get("approved_hashes") != expected or approval.get("artifact_hashes") != expected:
                    errors.append(f"审批未覆盖当前阶段全部产物: {stage.get('id')}")
                if approval.get("stage") != stage.get("id") or approval.get("project_id") != manifest.get("project_id") or not approval.get("approver") or not approval.get("note"):
                    errors.append(f"审批身份/阶段/依据无效: {stage.get('id')}")
            from crawl_gate import crawl_errors
            errors.extend(crawl_errors(root, str(stage["id"]), caller=stage.get("owner", "luz-project")))
            for artifact_id, approved_hash in (stage.get("approved_hashes") or {}).items():
                artifact = artifact_map.get(str(artifact_id))
                if not artifact:
                    errors.append(f"审批引用的产物不存在: {artifact_id}")
                elif artifact.get("sha256") != approved_hash:
                    errors.append(f"审批后产物已变化: {artifact.get('path')}")
    for html_path in [root / "README.html", *(root / "docs").rglob("*.html"), *(root / REVIEW_DIR).glob("*.html")]:
        if not html_path.is_file():
            continue
        if any(part in {".git", "__pycache__"} for part in html_path.parts):
            continue
        content = html_path.read_text(encoding="utf-8", errors="replace")
        if _scan_secret(content):
            errors.append(f"HTML 疑似包含秘密值: {html_path.relative_to(root)}")
        errors.extend(_validate_links(html_path))
    if strict:
        if str(manifest.get("project_id", "")).startswith("PROJECT-") is False:
            errors.append("project_id 格式无效")
        if manifest.get("policies", {}).get("secret_values_in_artifacts") is True:
            errors.append("项目策略允许秘密值进入产物")
        # Strict mode still allows future stages to be pending; it validates
        # only the completed/approved portion of the graph.
        for stage in manifest_stages:
            if stage.get("status") == "approved" and not stage.get("artifact_ids"):
                errors.append(f"已批准阶段没有产物: {stage.get('id')}")
    return list(dict.fromkeys(errors))


def set_stage_status(project: Path | str, stage: str, status: str) -> dict[str, Any]:
    root = _project_root(project)
    manifest = load_project(root)
    record = _stage_record(manifest, stage)
    if status not in STAGE_STATUSES:
        raise ProjectError(f"无效阶段状态: {status}")
    if status in {"approved", "completed"} and not record.get("approval_id"):
        raise ProjectError("approved/completed 必须通过 approve_stage 记录用户审批，不能手工绕过门禁")
    if status in {"approved", "completed"}:
        raise ProjectError("审批状态只由 approve 命令设置；stage 用于启动、阻断或重新打开阶段")
    if record.get("approval_id") or record.get("status") in {"approved", "completed"}:
        _invalidate_downstream(manifest, stage)
    record["status"] = status
    record["updated_at"] = now_iso()
    manifest["current_stage"] = stage
    manifest["status"] = "blocked" if status == "blocked" else ("active" if status not in {"completed"} else manifest.get("status", "active"))
    _save_manifest(root, manifest)
    return dict(record)


def _bind_architecture_baseline(root: Path, manifest: dict[str, Any]) -> str | None:
    """An architecture stage approved before data/baseline.json (stack, modules) was tracked gets that tracking now, but only when the approved document
    still agrees with the file (validate checks every row of the document against baseline.json): then the hash recorded is that of what was approved."""
    record = next((s for s in manifest.get("stages", []) if s.get("id") == "architecture"), None)
    if not record or record.get("status") not in {"approved", "completed"} or not schema_at_least(manifest, "1.1"):
        return None
    import client_flow

    wanted = client_flow.tracked_hashes(root, "architecture")
    missing = {k: v for k, v in wanted.items() if k not in (record.get("approved_sources") or {})}
    if not missing:
        return None
    import dev_documents

    try:
        errors = dev_documents.validate("architecture", _read_json(root / "data" / "stages" / "architecture.json", {}), root)
    except Exception as exc:                                                    # a document the current standard cannot even read is not verified
        errors = [f"架构文档无法校验: {exc}"]
    if errors:
        return "架构阶段已批准，但 data/baseline.json 的 stack、modules 与架构文档对不上，没有绑定到审批（先对齐：" + "；".join(errors[:2]) + "）"
    record.setdefault("approved_sources", {}).update(missing)
    return "架构阶段已批准，data/baseline.json 的 stack、modules 两段与架构文档一致，已纳入架构阶段的跟踪（之后改动要走变更台账并重新批准）"


def migrate_project(project: Path | str) -> dict[str, Any]:
    """Bring a project to the current matrix: add new stages as pending, refresh stage names, outputs and deliverables, add the new folders."""
    root = _project_root(project)
    layout = migrate_layout(root)
    manifest = load_project(root)
    existing = {str(item["id"]): item for item in manifest.get("stages", [])}
    stages, added = [], []
    deduped: list[str] = []
    for item in _load_matrix()["stages"]:
        record = existing.get(item["id"])
        if record is None:
            record = _empty_stage(item, root=root)
            added.append(item["id"])
        else:
            record.update({"name": item.get("name", record.get("name")), "docs_dir": item.get("docs_dir", record.get("docs_dir")), "required_inputs": list(item.get("required_inputs", [])), "next": item.get("next"), "failure_route": item.get("failure_route", item["id"]),
                           "client_dir": item.get("client_dir"), "deliverables": stage_deliverables(root, item), "outputs": list(item.get("outputs", [])),
                           "standard": item.get("standard"), "rule_cards": list(item.get("rule_cards", []))})
            record.setdefault("approved_sources", {})
            unique = list(dict.fromkeys(str(i) for i in record.get("artifact_ids") or []))
            if unique != list(record.get("artifact_ids") or []):
                record["artifact_ids"] = unique
                deduped.append(item["id"])
        stages.append(record)
    for old in existing:
        if old not in {s["id"] for s in stages}:
            raise ProjectError(f"项目含矩阵里已不存在的阶段: {old}")
    manifest["stages"] = stages
    manifest["schema_version"] = "1.1"
    last_old = stages[[s["id"] for s in stages].index("operations")]
    if manifest.get("status") == "completed" and "handover" in added:
        manifest["status"] = "active"
        if last_old.get("status") == "completed":
            last_old["status"] = "approved"
        manifest["current_stage"] = "handover"
    for relative in V11_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    if not (root / "data" / "changes.json").is_file():
        _write_json(root / "data" / "changes.json", {"schema_version": "1.0", "changes": []})
    if not (root / "config" / "documents.json").is_file():
        _write_json(root / "config" / "documents.json", {"theme": None})
    notes = []
    crawl = manifest.setdefault("crawl", {})                       # the Crawl records are in raw/00-crawl; an empty raw/crawl/evidence.json was only ever a placeholder
    if crawl.get("evidence_index") in (None, "", "raw/crawl/evidence.json"):
        crawl["evidence_index"] = EVIDENCE_DIR
    paths_file = root / "config" / "paths.json"
    paths = _read_json(paths_file, None)
    if isinstance(paths, dict) and paths.get("crawl") == "raw/crawl":
        paths["crawl"] = EVIDENCE_DIR
        _write_json(paths_file, paths)
    added_ignore = ensure_gitignore(root, GITIGNORE_SAFE)
    if added_ignore:
        notes.append(".gitignore 补上了: " + "、".join(added_ignore))
    if deduped:
        notes.append("去掉了阶段 " + "、".join(deduped) + " 的 artifact_ids 里重复的产物编号")
    bound = _bind_architecture_baseline(root, manifest)
    if bound:
        notes.append(bound)
    _save_manifest(root, manifest)
    render_project(root)
    for relative, empty in (("raw/crawl/evidence.json", lambda v: isinstance(v, dict) and not v.get("sources") and not v.get("coverage") and not v.get("unresolved")),
                            ("data/sources.json", lambda v: v == []), ("data/decisions.json", lambda v: v == [])):
        if (root / relative).is_file() and empty(_read_json(root / relative, None)):
            notes.append(f"{relative} 是空骨架，没有任何工具读取，可以删除")
    approved = [s["id"] for s in stages if s.get("status") in {"approved", "completed"}]
    late = [a for a in added if any(stages_index > [s["id"] for s in stages].index(a) for stages_index in [[s["id"] for s in stages].index(x) for x in approved])]
    if late:
        notes.append(f"新增阶段 {', '.join(late)} 位于已批准阶段之前：补做客户文档后用 project.py stage <阶段> pending-review 重新走审批，或在备注中说明沿用既有批准")
    if layout["moved"]:
        notes.append(f"已把 {len(layout['moved'])} 个文件移到平铺的新目录（docs 只有三个目录，每个一层）；移动过的 HTML 里的相对链接可能失效，对应阶段用 project.py document 重新生成")
    notes += layout["leftovers"]
    return {"added": added, "notes": notes, "layout": {"moved": layout["moved"], "rewritten": layout["rewritten"]}}


def _aliases(root: Path) -> dict[str, str]:
    """Adopted repositories keep their own folder names: config/paths.json ``aliases`` maps a standard folder to the real one."""
    value = _read_json(root / "config" / "paths.json", {}) or {}
    aliases = value.get("aliases") if isinstance(value, dict) else None
    return {str(k): str(v) for k, v in (aliases or {}).items()}


def _alias_target(aliases: dict[str, str], relative: str) -> str | None:
    """The real path to check for a standard folder; None when an aliased ancestor already covers it."""
    for prefix, real in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
        if relative == prefix:
            return real
        if relative.startswith(prefix + "/"):
            return None
    return relative


def _move(root: Path, old: str, new: str, log: list[str], pairs: list[tuple[str, str]] | None = None) -> None:
    import shutil
    import subprocess

    if pairs is not None:
        pairs.append((old, new))

    src, dst = root / old, root / new
    if not src.exists():
        raise ProjectError(f"要移动的路径不存在: {old}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir() and dst.is_dir():
        for child in sorted(src.iterdir()):
            _move(root, f"{old}/{child.name}", f"{new}/{child.name}", log, pairs)
        if not any(src.iterdir()):
            src.rmdir()
        return
    if dst.exists():
        raise ProjectError(f"目标已存在，不覆盖: {new}")
    tracked = (root / ".git").exists() and subprocess.run(["git", "ls-files", "--error-unmatch", old], cwd=root, capture_output=True).returncode == 0
    if tracked and subprocess.run(["git", "mv", old, new], cwd=root, capture_output=True).returncode == 0:
        log.append(f"git mv {old} -> {new}")
        return
    shutil.move(str(src), str(dst))
    log.append(f"move {old} -> {new}")


_SKIP_DIRS = {"node_modules", ".git", "dist", "unpackage", "target", ".claude", "__pycache__"}
_LINK = re.compile(r"(\]\()([^)\s]+)(\))")
_DOC_PATH = re.compile(r"(?<![\w/.-])((?:docs|config|src|data|scripts|tests)/[^\s`'\"<>)\]，。；、]+)")


def _map_path(mapping: list[tuple[str, str]], path: str) -> str:
    """Map an old repository-relative path to its new location (longest moved prefix wins)."""
    for old, new in sorted(mapping, key=lambda pair: -len(pair[0])):
        if path == old:
            return new
        if path.startswith(old + "/"):
            return new + path[len(old):]
    return path


def relink_after_moves(project: Path | str, pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Repair Markdown links and docs/... path mentions after files were moved (relative links are recomputed per file)."""
    from posixpath import dirname, normpath, relpath

    root = _project_root(project)
    mapping = [(a.replace("\\", "/"), b.replace("\\", "/")) for a, b in pairs]
    reverse = [(b, a) for a, b in mapping]
    changed: list[str] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        text = path.read_text(encoding="utf-8")
        old_rel = _map_path(reverse, rel)
        old_dir = dirname(old_rel)
        new_dir = dirname(rel)

        def fix_link(match: re.Match[str]) -> str:
            target = match.group(2)
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|/)", target, re.I):
                return match.group(0)
            raw, _, anchor = target.partition("#")
            decoded = unquote(raw)
            if not decoded:
                return match.group(0)
            old_target = normpath(f"{old_dir}/{decoded}" if old_dir else decoded)
            new_target = _map_path(mapping, old_target)
            if new_target == old_target and old_dir == new_dir:
                return match.group(0)
            if not (root / new_target).exists():
                return match.group(0)
            fixed = relpath(new_target, new_dir or ".")
            if fixed == decoded:
                return match.group(0)
            from urllib.parse import quote
            fixed = quote(fixed, safe="/()%") if "%" in raw else fixed
            return f"{match.group(1)}{fixed}{'#' + anchor if anchor else ''}{match.group(3)}"

        def fix_mention(match: re.Match[str]) -> str:
            old = match.group(1)
            new = _map_path(mapping, old.rstrip("/"))
            return new + ("/" if old.endswith("/") else "") if new != old.rstrip("/") else old

        updated = _DOC_PATH.sub(fix_mention, _LINK.sub(fix_link, text))
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(rel)
    return {"files_updated": changed}


def ensure_gitignore(root: Path, lines: Iterable[str]) -> list[str]:
    """Append the lines a .gitignore does not have yet (an existing file keeps everything it has); returns what was added."""
    ignore = root / ".gitignore"
    text = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    have = {line.strip() for line in text.splitlines()}
    added = [line for line in lines if line not in have]
    if added:
        ignore.write_text((text.rstrip("\n") + "\n" if text.strip() else "") + "# Luz：密钥、依赖、构建输出与客户文档构建中间件\n" + "\n".join(added) + "\n", encoding="utf-8")
    return added


def adopt_project(project: Path | str, name: str | None = None, *, moves: Iterable[tuple[str, str]] = (), aliases: dict[str, str] | None = None) -> dict[str, Any]:
    """Turn an existing repository into a Luz project in place.

    Code folders are never renamed: ``aliases`` records where a standard folder really lives (for example ``test`` -> ``tests``).
    Document folders are relocated with ``moves`` (git mv when tracked). Nothing is overwritten and no stage is pre-approved.
    """
    root = _project_root(project)
    if not root.is_dir():
        raise ProjectError(f"目录不存在: {root}")
    if (root / "project.json").exists():
        raise ProjectError("已经是 Luz 项目（存在 project.json）")
    log: list[str] = []
    pairs: list[tuple[str, str]] = []
    for old, new in moves:
        _move(root, old.strip("/\\"), new.strip("/\\"), log, pairs)
    for old, _ in moves:                                   # folders a move leaves empty are removed, not kept as clutter
        folder = (root / old.strip("/\\")).parent
        while folder != root and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    aliases = dict(aliases or {})
    for real in aliases.values():
        if not (root / real).is_dir():
            raise ProjectError(f"别名指向的目录不存在: {real}")
    for relative in (*REQUIRED_DIRS, *V11_DIRS):
        target = _alias_target(aliases, relative)
        if target is not None:
            (root / target).mkdir(parents=True, exist_ok=True)
    match = re.match(r"^(\d+)", root.name)
    number = int(match.group(1)) if match else 1
    stages = [_empty_stage(item, current=(index == 0), root=root) for index, item in enumerate(_load_matrix()["stages"])]
    shown = (name or root.name).strip()
    manifest: dict[str, Any] = {
        "schema_version": "1.1", "project_id": f"PROJECT-{number:03d}", "name": shown, "slug": _slug(shown),
        "status": "draft", "current_stage": stages[0]["id"], "repository": str(root), "created_at": now_iso(), "updated_at": now_iso(),
        "adopted": {"at": now_iso(), "aliases": aliases, "moves": log, "note": "既有仓库就地接入：不预设任何阶段为已批准，历史文档只是输入材料"},
        "crawl": {"task_id": None, "task_root": None, "evidence_index": EVIDENCE_DIR, "reuse_policy": "reuse-within-project"},
        "stages": stages,
        "policies": {"html_generated": True, "require_user_approval": True, "secret_values_in_artifacts": False, "production_data_in_project": False},
    }
    _write_json(root / "project.json", manifest)
    _write_json(root / "MANIFEST.json", manifest)
    _write_json(root / "data" / "project.json", manifest)
    for path, payload in (
        (root / "APPROVALS.json", {"schema_version": "1.0", "approvals": []}),
        (root / "data" / "artifacts.json", []),
        (root / "data" / "ops" / "checks.json", []),
        (root / "data" / "changes.json", {"schema_version": "1.0", "changes": []}),
        (root / "config" / "documents.json", {"theme": None, "note": "客户文档主题：从 Luz-Design themes.json 选择，运行 project.py client theme 设置"}),
    ):
        if not path.exists():
            _write_json(path, payload)
    paths_file = root / "config" / "paths.json"
    paths = _read_json(paths_file, {}) or {}
    paths.setdefault("docs", "docs")
    paths["aliases"] = aliases
    _write_json(paths_file, paths)
    added = ensure_gitignore(root, GITIGNORE_SAFE)
    relinked = relink_after_moves(root, pairs) if pairs else {"files_updated": []}
    manifest["adopted"]["pairs"] = [list(p) for p in pairs]
    _save_manifest(root, manifest)
    render_project(root)
    return {"project": str(root), "moves": log, "aliases": aliases, "gitignore_added": added, **relinked}


def project_status(project: Path | str) -> dict[str, Any]:
    manifest = load_project(project)
    return {
        "project_id": manifest.get("project_id"),
        "name": manifest.get("name"),
        "status": manifest.get("status"),
        "current_stage": manifest.get("current_stage"),
        "stages": [{"id": s.get("id"), "status": s.get("status"), "approval_id": s.get("approval_id")} for s in manifest.get("stages", [])],
    }


def stage_route(project: Path | str, stage: str | None = None) -> dict[str, Any]:
    """Describe the specialist, inputs, outputs, and next gate for a stage."""
    manifest = load_project(project)
    selected = stage or manifest.get("current_stage")
    record = _stage_record(manifest, str(selected))
    return {
        "project_id": manifest.get("project_id"),
        "stage": record.get("id"),
        "name": record.get("name"),
        "owner": record.get("owner"),
        "contributors": record.get("contributors", []),
        "docs_dir": record.get("docs_dir"),
        "required_inputs": record.get("required_inputs", []),
        "outputs": record.get("outputs", []),
        "crawl_focus": record.get("crawl_focus"),
        "approval": record.get("approval"),
        "next": record.get("next"),
        "failure_route": record.get("failure_route"),
        "status": record.get("status"),
        "standard": record.get("standard"),
        "rule_cards": record.get("rule_cards", []),
        "document": next((str(x["path"]) for x in record.get("deliverables", []) if x.get("format") == "html"), None),
    }


def gate_stage(project: Path | str, stage: str, *, specialist_checks: bool = True) -> list[str]:
    """Check upstream user approvals and immutable artifact snapshots."""
    root = _project_root(project)
    manifest = load_project(root)
    _stage_record(manifest, stage)
    errors = validate_project(root, strict=True)
    from crawl_gate import crawl_errors
    owner = _stage_record(manifest, stage)["owner"]
    errors.extend(crawl_errors(root, stage, caller=owner))
    ordered = [s["id"] for s in _load_matrix()["stages"]]
    stages = {s["id"]: s for s in manifest["stages"]}
    for earlier in ordered[:ordered.index(stage)]:
        if stages[earlier].get("status") not in {"approved", "completed"}:
            errors.append(f"前置审批未完成: {earlier}")
    if specialist_checks and stage in {"verification", "release", "operations"}:
        import sys
        sys.path.insert(0, str(ROOT.parent / "Luz-Ops" / "scripts"))
        from ops_core import validate_ops
        errors.extend(validate_ops(root, stage, check_project=False))
    return list(dict.fromkeys(errors))


def stage_context(project: Path | str, stage: str, skill: str | None = None) -> dict[str, Any]:
    """Return concrete approved handoff files; never initialize an implicit project."""
    root = _project_root(project)
    manifest = load_project(root)
    record = _stage_record(manifest, stage)
    if skill and skill != record["owner"] and skill not in record.get("contributors", []):
        raise ProjectError(f"{skill} 不是 {stage} 的执行者或协作者")
    ordered = [s["id"] for s in manifest["stages"]]
    predecessors = ordered[:ordered.index(stage)]
    inputs = [{**a, "absolute_path": str(root / a["path"])} for a in _load_artifacts(root) if a["stage"] in predecessors]
    result = {**stage_route(root, stage), "project_root": str(root), "mode": "project", "inputs": inputs, "crawl": manifest["crawl"], "blockers": gate_stage(root, stage), "output_root": str(root / record["docs_dir"])}
    if schema_at_least(manifest, "1.1"):
        import client_flow
        result["client"] = client_flow.client_context(root, stage)
        result["client_dir"] = record.get("client_dir")
    return result

