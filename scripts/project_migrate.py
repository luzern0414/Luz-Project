"""``project.py migrate``: bring an older project to the current layout and the current matrix.

Without ``--apply`` nothing is touched: the result lists what would move and what would change. With ``--apply``:

* a project of the first layout (project.json in the project directory, tool folders under ``raw/``) gets its Luz-Project session and state root; the
  state and process files move there (project.json, MANIFEST.json, APPROVALS.json, README.html, ``raw/*``, the tool files of ``config/`` and of
  ``data/``), the project directory keeps results only, and the paths in the registers are rewritten;
* the files of the older docs layouts move to the flat folders (the numbers in front of the handover files included);
* new stages and deliverables of the matrix are added, the folders of the new schema are made.

Files whose hash an approval binds (the registered data and review files, the tracked client data) are never rewritten: a path inside them that starts
with ``raw/`` still resolves (project_paths.locate reads it as the state root's folder).
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import project_core as pc
from project_paths import STATE_CONFIG, STATE_DATA, ProjectError, deliver_root, is_legacy

DOCS_INDEX_MARK = "文档导航"          # the first line of the docs/README.md that older versions generated
SKELETONS = (("crawl/evidence.json", lambda v: isinstance(v, dict) and not v.get("sources") and not v.get("coverage") and not v.get("unresolved")),
             ("data/sources.json", lambda v: v == []), ("data/decisions.json", lambda v: v == []))


class _Plan:
    """Moves (source, destination, destination root, reason) and what they mean for the paths written in the registers."""

    def __init__(self, deliver: Path, state: Path) -> None:
        self.deliver, self.state = deliver, state
        self.moves: list[dict[str, Any]] = []
        self.pairs: list[tuple[str, str]] = []          # old project-relative path -> new one (prefix match), for the registers

    def occupied(self, dst: Path) -> bool:
        """Whether something is at ``dst`` now or a planned move puts it there."""
        if dst.exists():
            return True
        for move in self.moves:
            target = move["dst"]
            if target == dst:
                return True
            if target in dst.parents and (move["src"] / dst.relative_to(target)).exists():
                return True
        return False

    def add(self, src: Path, dst: Path, root: str, rel_from: str, rel_to: str, why: str = "") -> None:
        self.moves.append({"src": src, "dst": dst, "root": root, "from": rel_from, "to": rel_to, "why": why})

    def listing(self) -> list[str]:
        return [f"{m['from']}  →  {'[状态根] ' if m['root'] == 'state' else '[项目目录] '}{m['to']}" + (f"（{m['why']}）" if m["why"] else "") for m in self.moves]


def _first_line(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return ""


def _plan_roots(plan: _Plan, root: Path) -> list[str]:
    """The move from the first layout to the two roots; ``root`` is the old project root, ``plan.state`` the new state root."""
    notes: list[str] = []
    state = plan.state
    for name in ("project.json", "MANIFEST.json", "APPROVALS.json"):
        if (root / name).is_file():
            plan.add(root / name, state / name, "state", name, name)
    if (root / "README.html").is_file():
        plan.add(root / "README.html", state / "backup" / "README.html", "state", "README.html", "backup/README.html", "旧索引页，由会话的汇总页取代")
    docs_index = root / "docs" / "README.md"
    if docs_index.is_file():
        if DOCS_INDEX_MARK in _first_line(docs_index):
            plan.add(docs_index, state / "backup" / "docs-README.md", "state", "docs/README.md", "backup/docs-README.md", "工具生成的文档导航，由汇总页取代")
        else:
            notes.append("docs/README.md 是手写的，没有移动；docs 根目录只放三个目录，请把它移出 docs")
    raw = root / "raw"
    if raw.is_dir():
        for child in sorted(raw.iterdir()):
            if child.name != ".gitkeep":
                plan.add(child, state / child.name, "state", f"raw/{child.name}", child.name)
    for name in STATE_CONFIG:
        if (root / "config" / name).is_file():
            plan.add(root / "config" / name, state / "config" / name, "state", f"config/{name}", f"config/{name}")
    if (root / "data").is_dir():
        for child in sorted((root / "data").iterdir()):
            if child.name in STATE_DATA:
                plan.add(child, state / "data" / child.name, "state", f"data/{child.name}", f"data/{child.name}")
    seen: dict[Path, str] = {}
    for move in plan.moves:
        if move["dst"] in seen:
            raise ProjectError(f"迁移有两个来源指向同一个位置 {move['dst']}: {seen[move['dst']]} 与 {move['from']}")
        seen[move["dst"]] = move["from"]
    plan.pairs += [(m["from"], m["to"]) for m in plan.moves if m["from"].startswith("raw/")]
    return notes


def _plan_layout(plan: _Plan) -> None:
    """The files of the older docs layouts go to the flat folders; a client's original files go to uploads/."""
    root = plan.deliver
    for old, fresh in pc.LAYOUT_MOVES:
        source = root / old
        if not source.is_file():
            continue
        into_state = pc.kind_of(fresh) == "state"
        target = (plan.state if into_state else plan.deliver) / fresh
        if plan.occupied(target):
            continue
        plan.add(source, target, "state" if into_state else "deliver", old, fresh)
        plan.pairs.append((old, fresh))
    originals = root / pc.CLIENT_ORIGINALS_DIR
    if originals.is_dir():
        for file in sorted(originals.rglob("*")):
            if not file.is_file():
                continue
            target, n = plan.state / pc.UPLOADS_DIR / file.name, 1
            while plan.occupied(target):
                target = plan.state / pc.UPLOADS_DIR / f"{file.stem}-{n}{file.suffix}"
                n += 1
            rel = file.relative_to(root).as_posix()
            plan.add(file, target, "state", rel, f"{pc.UPLOADS_DIR}/{target.name}")
            plan.pairs.append((rel, f"{pc.UPLOADS_DIR}/{target.name}"))


def _remap(pairs: list[tuple[str, str]], rel: str) -> str:
    """Where a path written in a register points after the moves (the longest moved prefix wins)."""
    text = rel.replace("\\", "/")
    name, hashmark, fragment = text.partition("#")
    for old, fresh in sorted(pairs, key=lambda pair: -len(pair[0])):
        if name == old:
            return fresh + hashmark + fragment
        if name.startswith(old + "/"):
            return fresh + name[len(old):] + hashmark + fragment
    return rel


def _rewrite_registers(state: Path, pairs: list[tuple[str, str]], apply: bool) -> list[str]:
    """Point the registers at the new locations; returns what changed. artifacts.json and the build ledger are rewritten by key; the stage data
    files and paths.json only get the renamed docs paths (text replacement); files an approval binds are not touched here."""
    changed: list[str] = []
    artifacts_file = state / "data" / "artifacts.json"
    artifacts = pc._read_json(artifacts_file, [])
    count = 0
    for item in artifacts if isinstance(artifacts, list) else []:
        fresh = _remap(pairs, str(item.get("path", "")))
        if fresh != item.get("path"):
            item["path"], count = fresh, count + 1
    if count:
        changed.append(f"data/artifacts.json（{count} 个产物的路径）")
        if apply:
            pc._write_json(artifacts_file, artifacts)
    build_file = state / "data" / "client" / "build.json"
    build = pc._read_json(build_file, {})
    count = 0
    for entry in build.values() if isinstance(build, dict) else []:
        for field in ("sources", "outputs"):
            if isinstance(entry.get(field), dict):
                remapped = {_remap(pairs, k): v for k, v in entry[field].items()}
                count += sum(1 for k in entry[field] if _remap(pairs, k) != k)
                entry[field] = remapped
    if count:
        changed.append(f"data/client/build.json（{count} 个来源或成品的路径）")
        if apply:
            pc._write_json(build_file, build)
    docs_pairs = [(a, b) for a, b in pairs if not a.startswith("raw/")]
    candidates = sorted((state / "data" / "stages").glob("*.json")) if (state / "data" / "stages").is_dir() else []
    for path in candidates:
        text = path.read_text(encoding="utf-8-sig")
        new = text
        for old, fresh in docs_pairs:
            new = new.replace(old, fresh).replace(old.replace("/", "\\\\"), fresh.replace("/", "\\\\"))
        if new != text:
            changed.append(path.relative_to(state).as_posix())
            if apply:
                path.write_text(new, encoding="utf-8")
    return changed


def _fix_paths_file(state: Path, apply: bool) -> bool:
    """config/paths.json describes the project directory only now: the entries for raw/ and the crawl folder go."""
    path = state / "config" / "paths.json"
    paths = pc._read_json(path, None)
    if not isinstance(paths, dict) or not ({"raw", "crawl"} & set(paths)):
        return False
    if apply:
        for key in ("raw", "crawl"):
            paths.pop(key, None)
        pc._write_json(path, paths)
    return True


def _refresh_manifest(source: Path, state: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The matrix part of a migration, on the manifest in memory: new stages as pending, refreshed names, outputs and deliverables, duplicate artifact
    numbers dropped, the architecture baseline bound when its document still agrees. ``source`` is where the data files are read from."""
    existing = {str(item["id"]): item for item in manifest.get("stages", [])}
    stages, added, notes, deduped = [], [], [], []
    for item in pc._load_matrix()["stages"]:
        record = existing.get(item["id"])
        if record is None:
            record = pc._empty_stage(item, root=state)
            added.append(item["id"])
        else:
            record.update({"name": item.get("name", record.get("name")), "docs_dir": item.get("docs_dir", record.get("docs_dir")), "required_inputs": list(item.get("required_inputs", [])), "next": item.get("next"),
                           "failure_route": item.get("failure_route", item["id"]), "client_dir": item.get("client_dir"), "deliverables": pc.stage_deliverables(state, item),
                           "outputs": list(item.get("outputs", [])), "standard": item.get("standard"), "rule_cards": list(item.get("rule_cards", []))})
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
    manifest["schema_version"] = pc.SCHEMA_VERSION
    last_old = stages[[s["id"] for s in stages].index("operations")]
    if manifest.get("status") == "completed" and "handover" in added:
        manifest["status"] = "active"
        if last_old.get("status") == "completed":
            last_old["status"] = "approved"
        manifest["current_stage"] = "handover"
    crawl = manifest.setdefault("crawl", {})
    if crawl.get("evidence_index") in (None, "", "raw/crawl/evidence.json", "raw/00-crawl"):
        crawl["evidence_index"] = pc.EVIDENCE_DIR
    if deduped:
        notes.append("去掉了阶段 " + "、".join(deduped) + " 的 artifact_ids 里重复的产物编号")
    bound = pc._bind_architecture_baseline(source, manifest)
    if bound:
        notes.append(bound)
    approved = [s["id"] for s in stages if s.get("status") in {"approved", "completed"}]
    order = [s["id"] for s in stages]
    late = [a for a in added if any(order.index(x) > order.index(a) for x in approved)]
    if late:
        notes.append(f"新增阶段 {', '.join(late)} 位于已批准阶段之前：补做客户文档后用 project.py stage <阶段> pending-review 重新走审批，或在备注中说明沿用既有批准")
    return added, notes


def migrate_project(project: Path | str, *, apply: bool = False, output: Path | str | None = None) -> dict[str, Any]:
    """Preview (default) or carry out the migration of a project; ``output`` is the Luz-Project output root (default: project_paths.output_root())."""
    root = pc._project_root(project)
    legacy = is_legacy(root)
    manifest = pc.load_project(root)
    notes: list[str] = []
    if legacy:
        from project_paths import output_root

        state = pc._session_for(root, output if output is not None else output_root()) / "raw"
        if state.exists() and any(state.iterdir()):
            raise ProjectError(f"新的状态根已存在且不是空的: {state}（这个项目可能已经迁移过）")
        deliver = root
    else:
        state, deliver = root, deliver_root(root)
    plan = _Plan(deliver, state)
    if legacy:
        notes += _plan_roots(plan, root)
    _plan_layout(plan)

    active = copy.deepcopy(manifest)
    if legacy:
        active["deliver_root"] = str(deliver)
    added, refresh_notes = _refresh_manifest(root, state, active)
    notes += refresh_notes
    ignored = {x.strip() for x in (deliver / ".gitignore").read_text(encoding="utf-8").splitlines()} if (deliver / ".gitignore").is_file() else set()
    missing = [line for line in pc.GITIGNORE_SAFE if line not in ignored]
    if missing:
        notes.append(".gitignore 补上: " + "、".join(missing))
    if any(m["from"].startswith("docs/") and m["from"].endswith(".html") and m["root"] == "state" for m in plan.moves):
        notes.append("移动过的 HTML 里的相对链接可能失效，对应阶段用 project.py document 重新生成")
    for relative, empty in SKELETONS:
        for base in ({root / "raw", deliver} if legacy else {deliver, state}):
            candidate = base / relative
            if candidate.is_file() and empty(pc._read_json(candidate, None)):
                notes.append(f"{candidate.relative_to(base).as_posix()} 是空骨架，没有任何工具读取，可以删除")

    result: dict[str, Any] = {"mode": "已执行" if apply else "预演（没有改动任何文件，加 --apply 执行）", "layout": "旧布局：状态与过程文件搬到状态根，项目目录只留成果" if legacy else "两个根已分开",
                              "state_root": str(state), "deliver_root": str(deliver), "move": plan.listing(), "added": added, "notes": notes}
    if not apply:
        result["rewrite"] = (["project.json、MANIFEST.json、data/project.json（deliver_root、阶段的交付物路径、crawl.evidence_index）"] if legacy else []) + _preview_registers(root, plan.pairs)
        return result

    for move in plan.moves:
        if move["dst"].exists():
            raise ProjectError(f"目标已存在，不覆盖: {move['dst']}")
    for move in plan.moves:                                                     # the moves out of raw/ first: the flat docs moves may land in the folders they create
        move["dst"].parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(move["src"]), str(move["dst"]))
    if legacy:
        for folder in (root / "raw", root / "config"):                         # what the moves left behind
            if folder.is_dir() and not any(p.is_file() and p.name != ".gitkeep" for p in folder.rglob("*")):
                shutil.rmtree(folder)
    for old_dir in (pc._ORIGINAL, f"{pc._FLAT_V1}/原型", pc.CLIENT_ORIGINALS_DIR):
        folder = deliver / old_dir
        if folder.is_dir() and not any(folder.rglob("*")):
            shutil.rmtree(folder)
    for relative in (*pc.STATE_DIRS, *pc.V11_DIRS):
        (state / relative).mkdir(parents=True, exist_ok=True)
    for relative in pc.DELIVER_MADE:
        (deliver / relative).mkdir(parents=True, exist_ok=True)
    result["rewrite"] = _rewrite_registers(state, plan.pairs, True)
    if _fix_paths_file(state, True):
        result["rewrite"].append("config/paths.json（去掉 raw、crawl 两项）")
    if not (state / "data" / "changes.json").is_file():
        pc._write_json(state / "data" / "changes.json", {"schema_version": "1.0", "changes": []})
    if not (state / "config" / "documents.json").is_file():
        pc._write_json(state / "config" / "documents.json", {"theme": None})
    manifest = pc._read_json(state / "project.json", {})
    if legacy:
        manifest["deliver_root"] = str(deliver)                                # from here on the project is read as one of the new layout
        pc._save_manifest(state, manifest)
    _refresh_manifest(state, state, manifest)
    pc._save_manifest(state, manifest)
    pc.ensure_gitignore(deliver, pc.GITIGNORE_SAFE)
    pc.render_project(state)
    result["leftovers"] = pc.layout_errors(state)
    result["notes"] = notes + result["leftovers"]
    return result


def _preview_registers(root: Path, pairs: list[tuple[str, str]]) -> list[str]:
    """What _rewrite_registers would change in a project that has not moved yet (read from the old locations, nothing written)."""
    out: list[str] = []
    artifacts = pc._read_json(root / "data" / "artifacts.json", [])
    count = sum(1 for item in artifacts if isinstance(item, dict) and _remap(pairs, str(item.get("path", ""))) != item.get("path"))
    if count:
        out.append(f"data/artifacts.json（{count} 个产物的路径）")
    build = pc._read_json(root / "data" / "client" / "build.json", {})
    count = sum(1 for entry in build.values() if isinstance(entry, dict) for field in ("sources", "outputs") for key in (entry.get(field) or {}) if _remap(pairs, key) != key)
    if count:
        out.append(f"data/client/build.json（{count} 个来源或成品的路径）")
    paths = pc._read_json(root / "config" / "paths.json", None)
    if isinstance(paths, dict) and {"raw", "crawl"} & set(paths):
        out.append("config/paths.json（去掉 raw、crawl 两项）")
    return out
