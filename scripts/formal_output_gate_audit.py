"""Audit formal-output entry points across the Luz skills.

This is intentionally a small, dependency-free contract audit.  It does not
render a document and it never creates a project/session.  The audit answers
the question that package validators cannot answer: do the reviewed formal
writers call evidence and Design template gates before writing, and do final
UI exports call a source audit? Static results are review signals, not proof
that all conditional execution paths are safe. Offline runtime probes check
the public summary CLIs' observable refusal and success behavior.

Run ``python -X utf8 scripts/formal_output_gate_audit.py`` for a JSON report.
Use ``--strict`` in a release/CI check; it exits non-zero while any blocking
entry point is still missing a contract.  ``--self-check`` exercises the
selection/output-hash contract in a temporary directory without touching a
session or output directory.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESIGN_ROOT = ROOT / "Luz-Design"
TEMPLATE_LIBRARY = DESIGN_ROOT / "scripts" / "template_library.py"


@dataclass(frozen=True)
class EntryPoint:
    skill: str
    file: str
    function: str
    template: str | None = None
    ui: bool = False
    source_audit: bool = False
    # A pure renderer is deliberately outside this audit.  The public CLI or
    # orchestration function that calls it remains in the table.
    formal: bool = True
    exclusion_reason: str = ""
    research_required: bool = True
    research_exemption_reason: str = ""


# This list is the review surface. ``inventory_candidates`` reports additional
# writers for human classification; raw reports, maintenance tools and test
# fixtures are not automatically treated as formal business output.
ENTRY_POINTS: tuple[EntryPoint, ...] = (
    EntryPoint("luz-design", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-design", "scripts/make_docx.py", "main", "docx"),
    EntryPoint("luz-design", "scripts/make_docx.py", "build", "docx"),
    EntryPoint("luz-design", "scripts/make_docx_paginated.py", "main", "docx-paginated"),
    EntryPoint("luz-design", "scripts/make_docx_paginated.py", "build", "docx-paginated"),
    EntryPoint("luz-design", "scripts/make_xlsx.py", "main", "xlsx"),
    EntryPoint("luz-design", "scripts/make_xlsx.py", "build", "xlsx"),
    EntryPoint("luz-design", "scripts/make_table_pdf.py", "main", "table-pdf"),
    EntryPoint("luz-design", "scripts/make_showcase.py", "main", "showcase"),
    EntryPoint("luz-design", "scripts/deliver.py", "deliver"),
    EntryPoint("luz-design", "scripts/publish.py", "publish"),
    EntryPoint("luz-design", "scripts/style_match.py", "main", formal=False,
               exclusion_reason="Crawl-gated research-candidate JSON restricted to session raw; not a formal document or UI"),
    EntryPoint("luz-design", "scripts/new_session.py", "create_session", formal=False,
               exclusion_reason="initial raw template scaffolds and rule cards; no formal researched business content"),
    EntryPoint("luz-design", "scripts/frontend.py", "init", ui=True, formal=False,
               exclusion_reason="provisional raw package inside the session; checks this stage's Crawl record and selects the frontend template before copying"),
    EntryPoint("luz-design", "scripts/frontend.py", "export", ui=True, formal=False,
               exclusion_reason="zips an already sealed package; verify_package re-checks the Crawl record, the selected template's final hash and the current review first"),
    EntryPoint("luz-design", "scripts/ui_package.py", "export_package", ui=True, formal=False,
               exclusion_reason="dispatches to frontend.export or component_ui.export by the package receipt; writes nothing itself"),
    EntryPoint("luz-design", "scripts/component_ui.py", "build", "ui-component-output", ui=True, formal=False,
               exclusion_reason="provisional raw assembly; prechecks requirements, sources, research and exact targets; export requires current audit/review"),
    EntryPoint("luz-design", "scripts/component_ui.py", "export", "ui-component-output", ui=True, source_audit=True),
    EntryPoint("luz-system", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-system", "scripts/hw_build.py", "main", "hardware-plan"),
    EntryPoint("luz-system", "scripts/hw_render_plan.py", "main", "hardware-plan"),
    EntryPoint("luz-system", "scripts/hw_export.py", "main", "xlsx"),
    EntryPoint("luz-system", "scripts/publish.py", "publish"),
    EntryPoint("luz-system", "scripts/publish.py", "publish_ui_source", "ui-component-output 或 frontend-*", ui=True, source_audit=True),
    EntryPoint("luz-dev", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-dev", "scripts/formal_doc.py", "build", "docx-paginated"),
    EntryPoint("luz-dev", "scripts/build_checklist.py", "main", formal=False,
               exclusion_reason="maintains bundled references/dev-checklist.html; not business output"),
    EntryPoint("luz-dev", "scripts/build_function_catalog.py", "main", formal=False,
               exclusion_reason="maintains bundled references/function-catalog.html; not business output"),
    EntryPoint("luz-dev", "scripts/build_standards.py", "main", formal=False,
               exclusion_reason="maintains bundled references/standards.html; not business output"),
    EntryPoint("luz-dev", "scripts/knowledge.py", "main", formal=False,
               exclusion_reason="maintains skill knowledge index; not business output"),
    EntryPoint("luz-dev", "scripts/tech_plan.py", "save_plan", "dev-technical-plan"),
    EntryPoint("luz-dev", "scripts/tech_plan.py", "write_pages", "dev-technical-plan"),
    EntryPoint("luz-writing", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-writing", "scripts/02-article_builder.py", "main", "writing-article"),
    EntryPoint("luz-writing", "scripts/03-session.py", "cmd_summary", "reading-html"),
    EntryPoint("luz-ops", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-ops", "scripts/ops_layout.py", "write_summary_page", "reading-html"),
    EntryPoint("luz-ops", "scripts/ops_docs.py", "client_document", "docx-paginated"),
    EntryPoint("luz-crawl", "scripts/crawl_preflight.py", "_conclude", "reading-html"),
    EntryPoint("luz-crawl", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-project", "scripts/make_summary.py", "main", "reading-html"),
    EntryPoint("luz-project", "scripts/project_summary.py", "render_summary", "reading-html",
               research_required=False,
               research_exemption_reason="reviewed machine-ledger status index only; no new business claims; Design template selection and output hash remain required"),
    EntryPoint("luz-project", "scripts/stage_documents.py", "write_document", "showcase"),
    EntryPoint("luz-project", "scripts/client_render.py", "build_docx", "docx-paginated"),
    EntryPoint("luz-project", "scripts/client_render.py", "build_xlsx", "xlsx"),
    EntryPoint("luz-project", "scripts/client_render.py", "build_showcase", "showcase"),
    EntryPoint("luz-project", "scripts/project_ui_source.py", "write_links", "reading-html"),
)


WRITE_METHODS = {
    "write_text",
    "write_bytes",
    "save",
    "copyfile",
    "copy2",
    "copytree",
    "move",
    "rename",
    "writestr",
}

CRAWL_TOKENS = (
    "require_session_preflight",
    "require_formal_output",
    "crawl_preflight",
    "crawl_errors",
    "generation_errors",
    "require_crawl",
    "project_crawl_gate",
    "require_summary_preflight",
    "validate_preflight",
    "packaging_errors",
    "plan_crawl_errors",
)

TEMPLATE_TOKENS = (
    "require_selected",
    "require_formal_output",
)

UI_AUDIT_TOKENS = (
    "verify_package",
)

# This reviewed wrapper invokes Design source_ui.py check in its own import
# context, rejects a failing exit code and verifies the registered entry URL.
# An unrelated function with the same name is not an audit contract.
REVIEWED_SOURCE_AUDIT_WRAPPERS = {
    ("Luz-System/scripts/publish.py", "verify_ui_source"),
}


def _source_root(skill: str) -> Path:
    return ROOT / ("Luz-" + skill.removeprefix("luz-").title())


def _entry_path(entry: EntryPoint) -> Path:
    return _source_root(entry.skill) / entry.file


def _function_node(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _call_name(node: ast.Call) -> str:
    value = node.func
    return value.id if isinstance(value, ast.Name) else value.attr if isinstance(value, ast.Attribute) else ""


def _calls(node: ast.AST) -> list[ast.Call]:
    """Calls in this function body, excluding deferred nested function bodies."""
    result: list[ast.Call] = []
    class Visitor(ast.NodeVisitor):
        def visit_Call(self, current):
            self.generic_visit(current)
            result.append(current)
        def visit_FunctionDef(self, current):
            if current is node:
                self.generic_visit(current)
        visit_AsyncFunctionDef = visit_FunctionDef
    Visitor().visit(node)
    return result


def _json_payload(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        return _call_name(node) in {"dumps", "canonical"}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (_json_payload(node.left) and isinstance(node.right, ast.Constant)
                and isinstance(node.right.value, (str, bytes)) and not node.right.value.strip())
    return False


class _CallGraph:
    """Read local helpers without importing or executing business code.

    This follows calls in source order. It deliberately makes no claim about
    branch conditions; runtime probes must establish actual refusal behavior.
    """

    def __init__(self):
        self.trees: dict[Path, ast.Module] = {}
        self.functions: dict[Path, dict] = {}
        self.imports: dict[Path, dict] = {}
        self.memo: dict[tuple, list[dict]] = {}
        self.resolutions: dict[tuple, tuple | None] = {}

    def tree(self, path: Path) -> ast.Module:
        if path not in self.trees:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            self.trees[path] = tree
            self.functions[path] = {node.name: node for node in tree.body
                                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            imports = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imports.update({alias.asname or alias.name: (node.module, alias.name) for alias in node.names})
                elif isinstance(node, ast.Import):
                    imports.update({alias.asname or alias.name: (alias.name, None) for alias in node.names})
            self.imports[path] = imports
        return self.trees[path]

    def module(self, path: Path, name: str) -> Path | None:
        relative = Path(*name.split(".")).with_suffix(".py")
        candidates = [path.parent / relative]
        candidates.extend(ROOT / skill / "scripts" / relative for skill in
                          ("Luz-Design", "Luz-System", "Luz-Dev", "Luz-Writing", "Luz-Ops", "Luz-Crawl", "Luz-Project"))
        return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)

    def resolve(self, path: Path, call: ast.Call) -> tuple[Path, str] | None:
        self.tree(path)
        name = _call_name(call)
        if isinstance(call.func, ast.Name) and name in self.functions[path]:
            return path, name
        lookup = call.func.id if isinstance(call.func, ast.Name) else call.func.value.id if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) else ""
        key = (path, lookup, name)
        if key not in self.resolutions:
            imported = self.imports[path].get(lookup)
            module = self.module(path, imported[0]) if imported else None
            self.resolutions[key] = (module, imported[1] or name) if module else None
        return self.resolutions[key]

    def events(self, path: Path, name: str, seen=frozenset()) -> list[dict]:
        key = (path, name)
        if key in seen or len(seen) > 12:
            return []
        if key in self.memo:
            return self.memo[key]
        node = _function_node(self.tree(path), name)
        if node is None:
            return []
        bindings = {target.id: item.value for item in ast.walk(node) if isinstance(item, ast.Assign)
                    for target in item.targets if isinstance(target, ast.Name)}
        result = []
        for call in _calls(node):
            called = _call_name(call)
            kinds = []
            if called in CRAWL_TOKENS:
                kinds.append("crawl")
                if called == "require_session_preflight" and any(item.arg == "template_id" and
                       not (isinstance(item.value, ast.Constant) and item.value.value is None) for item in call.keywords):
                    kinds.append("template")
            if called in TEMPLATE_TOKENS:
                # A post-generation hash check cannot replace selection.
                phase = next((value.value for value in call.keywords if value.arg == "phase"), None)
                if not isinstance(phase, ast.Constant) or phase.value != "post":
                    kinds.append("template")
            if called in UI_AUDIT_TOKENS:
                setting = next((value.value for value in call.keywords if value.arg == "require_audit"), None)
                if setting is None or isinstance(setting, ast.Constant) and setting.value is True:
                    kinds.append("ui-audit")
            resolved = self.resolve(path, call)
            if resolved and (resolved[0].relative_to(ROOT).as_posix(), resolved[1]) in REVIEWED_SOURCE_AUDIT_WRAPPERS:
                kinds.append("ui-audit")
            if called == "reject_legacy_ui_generation":
                kinds.append("disabled")
            if called in WRITE_METHODS and (isinstance(call.func, ast.Attribute) or called in {"copyfile", "copy2", "copytree", "move"}):
                receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
                if isinstance(receiver, ast.Name):
                    receiver = bindings.get(receiver.id, receiver)
                save_target = call.args[0] if call.args else None
                if isinstance(save_target, ast.Name):
                    save_target = bindings.get(save_target.id, save_target)
                in_memory = isinstance(save_target, ast.Call) and _call_name(save_target) in {"BytesIO", "StringIO"}
                json_path = receiver is not None and any(isinstance(part, ast.Constant) and isinstance(part.value, str)
                                                        and part.value.lower().endswith(".json") for part in ast.walk(receiver))
                kinds.append("process-write" if in_memory or json_path or call.args and _json_payload(call.args[0]) else "write")
            if called in {"_write_json", "write_json"} or called in {"atomic_write", "write"} and any(_json_payload(arg) for arg in call.args):
                kinds.append("process-write")
            if called == "open":
                mode = call.args[1] if len(call.args) > 1 else next((item.value for item in call.keywords if item.arg == "mode"), None)
                if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(char in mode.value for char in "wax+"):
                    kinds.append("write")
            if kinds:
                result.extend({"kind": kind, "path": str(path), "line": call.lineno, "call": called} for kind in kinds)
                continue
            resolved = self.resolve(path, call)
            if resolved:
                result.extend(self.events(*resolved, seen=seen | {key}))
        self.memo[key] = result
        return result


def _audit_entry(entry: EntryPoint) -> dict:
    path = _entry_path(entry)
    result = {
        **asdict(entry),
        "path": str(path),
        "exists": path.is_file(),
        "crawl_gate": False,
        "template_gate": False,
        "source_audit_required": entry.source_audit,
        "source_audit_detected": False,
        "disabled": False,
        "write_before_gate": False,
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append("入口文件不存在")
        return result
    source = path.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        result["errors"].append(f"Python 语法错误: {exc}")
        return result
    if _function_node(tree, entry.function) is None:
        result["errors"].append(f"登记的入口函数不存在: {entry.function}")
        return result
    events = _CallGraph().events(path, entry.function)
    result["analysis"] = "static-call-graph signals; conditional paths and dynamic imports require runtime verification"
    result["crawl_gate"] = any(item["kind"] == "crawl" for item in events)
    result["template_gate"] = any(item["kind"] == "template" for item in events)
    result["source_audit_detected"] = any(item["kind"] == "ui-audit" for item in events)
    first_write = next((index for index, item in enumerate(events) if item["kind"] == "write"), len(events))
    result["disabled"] = any(item["kind"] == "disabled" for item in events[:first_write])
    result["gate_events"] = [item for item in events if item["kind"] not in {"write", "process-write"}]
    result["process_writes"] = [item for item in events if item["kind"] == "process-write"]
    result["first_write"] = events[first_write] if first_write < len(events) else None
    if result["disabled"]:
        return result
    if not entry.research_required and not entry.research_exemption_reason:
        result["errors"].append("研究豁免必须记录已复核的明确范围和理由")
    if entry.research_required and not result["crawl_gate"]:
        result["errors"].append("缺少 Crawl 前置检索 gate")
    if not result["template_gate"]:
        result["errors"].append(f"缺少 Luz-Design 模板 gate（应绑定 {entry.template or '模板'}）")
    if entry.source_audit and not result["source_audit_detected"]:
        result["errors"].append("UI 缺少 source_ui verify/audit/check")
    required = {"template"} | ({"crawl"} if entry.research_required else set()) | ({"ui-audit"} if entry.source_audit else set())
    preceding = {item["kind"] for item in events[:first_write]}
    if first_write < len(events) and not required.issubset(preceding):
        result["write_before_gate"] = True
        missing = ", ".join(sorted(required - preceding))
        result["errors"].append(f"在 {missing} gate 前写入（{events[first_write]['path']}:{events[first_write]['line']}）")
    return result


def _inventory_gaps() -> list[str]:
    """Find obvious formal writers not listed in the review surface.

    This is intentionally conservative: a file is only a candidate when it
    contains both a write call and a CLI ``main``/public writer function.  It
    reports candidates for human review rather than silently treating every
    raw fixture writer as a deliverable.
    """
    listed = {(e.skill, e.file) for e in ENTRY_POINTS}
    candidates: list[str] = []
    for skill in ("Luz-Design", "Luz-System", "Luz-Dev", "Luz-Writing", "Luz-Ops", "Luz-Crawl", "Luz-Project"):
        scripts = ROOT / skill / "scripts"
        if not scripts.is_dir():
            continue
        for path in scripts.glob("*.py"):
            if path.name.startswith("test_") or path.name.startswith("0") and skill == "Luz-Writing":
                continue
            text = path.read_text(encoding="utf-8-sig", errors="ignore")
            if not any(f".{method}(" in text for method in WRITE_METHODS):
                continue
            if "def main(" not in text and "def client_document(" not in text and "def write_summary_page(" not in text:
                continue
            key = ("luz-project" if skill == "Luz-Project" else "luz-" + skill.removeprefix("Luz-").lower(), f"scripts/{path.name}")
            if key not in listed:
                candidates.append(f"{skill}/{path.relative_to(ROOT / skill).as_posix()}")
    return sorted(candidates)


def audit() -> dict:
    entries = [_audit_entry(entry) for entry in ENTRY_POINTS if entry.formal]
    errors = [f"{item['skill']}:{item['file']}::{item['function']}: {error}"
              for item in entries for error in item["errors"]]
    return {
        "schema_version": 1,
        "root": str(ROOT),
        "entries": entries,
        "inventory_candidates": _inventory_gaps(),
        "excluded_entry_points": [asdict(entry) for entry in ENTRY_POINTS if not entry.formal],
        "errors": errors,
        "ok": not errors,
    }


def _probe_outcome(condition: str, code, target_written: bool, diagnostic: str) -> dict:
    """An unrelated exception is not evidence that the requested gate works."""
    if condition == "valid_selection":
        return {"passed": code == 0 and target_written, "blocked_before_write": None,
                "diagnostic_matches_gate_reason": None}
    markers = (("crawl 前置", "前置检索", "检索记录") if condition == "missing_crawl" else
               ("luz-design 模板", "模板选择", "template selection"))
    matches = any(marker in diagnostic.casefold() for marker in markers)
    blocked = code not in (0, None) and not target_written and matches
    return {"passed": blocked, "blocked_before_write": blocked,
            "diagnostic_matches_gate_reason": matches}


def runtime_probes() -> list[dict]:
    """Run all seven shared business summary CLIs against offline fixtures.

    No network, Word process, browser or real user session is used.  A probe
    missing-input probe passes only when the public writer returns failure,
    gives the expected gate reason and leaves its exact target absent. The
    positive control must write with valid evidence, exact template selection
    and a registered output hash. These are synthetic test records, never
    claimed as real research or approval.
    """
    skills = ("Luz-Project", "Luz-System", "Luz-Design", "Luz-Dev", "Luz-Ops", "Luz-Writing", "Luz-Crawl")
    saved_path, saved_env = list(sys.path), dict(os.environ)
    results = []
    try:
        sys.path.insert(0, str(ROOT / "Luz-Crawl" / "scripts"))
        for variable in ("LUZ_PROJECT_ROOT", "LUZ_PROJECT_STAGE", "LUZ_DESIGN_SESSION"):
            os.environ.pop(variable, None)
        from test_crawl_preflight import complete_fixture
        from test_summary_entry_gates import design_manifest
        library = _load_library()
        for skill in skills:
            for condition in ("missing_crawl", "missing_template", "valid_selection"):
                with tempfile.TemporaryDirectory(prefix="luz-writer-probe-") as folder:
                    tmp = Path(folder)
                    session = tmp / "001-contract-probe"
                    spec = tmp / "spec.json"
                    spec.write_text(json.dumps({"title": "OFFLINE_GATE_PROBE", "sections": []}), encoding="utf-8")
                    if skill == "Luz-Design":
                        design_manifest(session)
                    if condition != "missing_crawl":
                        complete_fixture(session, skill.lower(), "contract-probe")
                    target = session / f"{session.name}.html"
                    if condition == "valid_selection":
                        library.select(session, skill.lower(), "contract-probe", "reading-html", target.name)
                    path = ROOT / skill / "scripts" / "make_summary.py"
                    modspec = importlib.util.spec_from_file_location("_gate_probe_" + skill.replace("-", "_"), path)
                    module = importlib.util.module_from_spec(modspec)
                    stdout, stderr = io.StringIO(), io.StringIO()
                    code, error = None, ""
                    try:
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                            modspec.loader.exec_module(module)
                            code = module.main([str(spec), str(session), "--stage", "contract-probe"])
                    except (Exception, SystemExit) as exc:  # a refusal may use a CLI exit
                        code = getattr(exc, "code", 1)
                        error = str(exc)
                    diagnostic = (stderr.getvalue() or stdout.getvalue() or error).strip()
                    outcome = _probe_outcome(condition, code, target.exists(), diagnostic)
                    if condition == "valid_selection" and outcome["passed"]:
                        try:
                            library.require_selected(session, skill.lower(), "contract-probe", target, "reading-html", phase="post")
                        except (ValueError, OSError) as exc:
                            diagnostic += "\n" + str(exc)
                            outcome["passed"] = False
                    results.append({"skill": skill.lower(), "entry": str(path), "condition": condition,
                                    "exit_code": code, "target_written": target.exists(), **outcome,
                                    "diagnostic": diagnostic[-1500:]})
    finally:
        sys.path[:] = saved_path
        os.environ.clear()
        os.environ.update(saved_env)
    return results


def _load_library():
    spec = importlib.util.spec_from_file_location("luz_design_template_library_audit", TEMPLATE_LIBRARY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Luz-Design template_library.py: {TEMPLATE_LIBRARY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def self_check() -> dict:
    """Exercise the exact-target and output-hash contract in isolation."""
    library = _load_library()
    with tempfile.TemporaryDirectory(prefix="luz-formal-gate-") as folder:
        root = Path(folder)
        target = root / "raw" / "03-documents" / "report.html"
        target.parent.mkdir(parents=True)
        missing_selection = False
        try:
            library.require_selected(root, "luz-dev", "technical-plan", target, "reading-html")
        except ValueError:
            missing_selection = True
        if target.exists():
            raise AssertionError("缺少模板选择时不应创建目标文件")
        if not missing_selection:
            raise AssertionError("缺少模板选择没有被阻断")
        library.select(root, "luz-dev", "technical-plan", "reading-html", "raw/03-documents/report.html")
        library.require_selected(root, "luz-dev", "technical-plan", target, "reading-html")
        try:
            library.require_selected(root, "luz-dev", "technical-plan", target.with_name("different.html"), "reading-html")
        except ValueError:
            pass
        else:
            raise AssertionError("模板选择没有绑定准确目标")
        target.write_text(library.render_reading("Offline contract fixture", "<p>OFFLINE_FIXTURE</p>"), encoding="utf-8")
        library.record_output(root, "luz-dev", "technical-plan", target, "reading-html", generator="self-check")
        library.require_selected(root, "luz-dev", "technical-plan", target, "reading-html", phase="post")
        target.write_text(target.read_text(encoding="utf-8") + "<!-- changed -->", encoding="utf-8")
        try:
            library.require_selected(root, "luz-dev", "technical-plan", target, "reading-html", phase="post")
        except ValueError:
            pass
        else:
            raise AssertionError("输出改动未触发哈希绑定失败")
    return {"ok": True, "checks": ["missing_selection_blocks", "exact_target_binding", "actual_design_renderer",
                                     "output_hash_binding", "output_tampering_rejected"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="任一正式入口缺 gate 或运行探针失败时返回 1；inventory 候选仅供人工分类")
    parser.add_argument("--self-check", action="store_true", help="运行临时目录中的 selection/output-hash contract smoke test")
    parser.add_argument("--runtime", action="store_true", help="对七个 summary CLI 运行离线缺 Crawl/缺模板/有效选择探针")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON（默认也是 JSON，为兼容保留该选项）")
    args = parser.parse_args(argv)
    payload = audit()
    if args.runtime:
        payload["runtime_probes"] = runtime_probes()
        payload["errors"].extend(f"{item['skill']}:summary:{item['condition']}: 运行契约失败"
                                 for item in payload["runtime_probes"] if not item["passed"])
    if args.self_check:
        try:
            payload["self_check"] = self_check()
        except Exception as exc:  # noqa: BLE001 - report the contract failure
            payload["self_check"] = {"ok": False, "error": str(exc)}
            payload["errors"].append(f"self-check: {exc}")
    payload["ok"] = not payload["errors"]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.strict and (payload["errors"] or not payload.get("self_check", {"ok": True}).get("ok", True)):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
