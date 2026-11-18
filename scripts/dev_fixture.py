"""Minimal valid developer documents for the offline rehearsals: just enough to satisfy references/dev-documents.md (never real content)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import dev_documents as dd

SOURCES = [
    {"id": "SRC-001", "url": "https://example.org/a", "finding": "离线夹具中的补充信息", "applies_to": "测试场景的方案输入"},
    {"id": "SRC-002", "url": "https://example.org/b", "finding": "离线夹具中的补充信息", "applies_to": "测试场景的方案输入"},
]
# Broad offline evidence for the mandatory research floor; never real research.
SOURCES += [{"id": f"SRC-{i + 3:03d}", "url": f"https://publisher{i % 3}.example/document-{i}",
             "finding": "离线夹具中的补充信息", "applies_to": "测试场景的方案输入"} for i in range(8)]


def figure(caption: str) -> dict[str, Any]:
    return {"type": "figure", "kind": "layers", "caption": caption, "rows": [{"label": "使用端", "nodes": [{"name": "小程序", "note": "员工"}]}, {"label": "服务端", "nodes": [{"name": "后端", "note": "业务规则"}]}],
            "links": [{"after": 0, "label": "接口调用"}]}


def table(caption: str) -> dict[str, Any]:
    return {"type": "table", "caption": caption, "columns": ["项", "内容"], "rows": [["甲", "乙"]]}


def prototype(root: Path, title: str, name: str, kind: str = "phone") -> dict[str, Any]:
    """Shape-only placeholder; it cannot pass the real source/output gate.

    Tests that actually write the design document must call ``install_source``.
    No marker file, size padding or claimed component library is fabricated.
    """
    digits = "".join(c for c in name if c.isdigit()) or "0"
    rel = f"docs/02-产品开发/{int(digits) + 2:02d}-{name}.html"                  # prototypes of a project sit in docs/02-产品开发 with a two-digit number
    return {"type": "prototype", "file": rel, "title": title, "kind": kind,
            "source": {"session": "OFFLINE-SHAPE-ONLY-NOT-A-SESSION",
                       "package": "OFFLINE-SHAPE-ONLY-NOT-A-PACKAGE", "entry": "index.html"}}


def install_source(root: Path, spec: dict[str, Any]) -> dict[str, str]:
    """Attach an actually built, sealed and reviewed Luz-Design frontend package (tests only).

    Crawl inputs and the review evidence are explicitly synthetic; the package bytes, the seal, the review binding and the
    package check are the public Design implementation without a gate mock. Both preview sizes reuse one responsive web
    package; this fixture does not claim native mini-program behavior, business integration or acceptance.
    """
    import json
    import subprocess
    import sys

    from project_core import _load_artifacts
    from project_crawl_gate import crawl_errors
    from project_summary import register_session
    from project_paths import locate

    root = Path(root).resolve()
    errors = crawl_errors(root, "design", caller="luz-design")
    if errors:
        raise ValueError("The explicit offline design-stage Crawl fixture is required: " + "; ".join(errors))
    blocks = [block for tab in spec.get("tabs", []) for section in tab.get("sections", [])
              for block in section.get("blocks", []) if block.get("type") == "prototype"]
    import template_library
    for block in blocks:
        template_library.select(root, "luz-project", "design", "reading-html", str(locate(root, block["file"])))
    # A frontend package of a project is sealed against the behaviour contract its architecture stage registered.
    contract = next((locate(root, str(a["path"])) for a in _load_artifacts(root)
                     if a.get("stage") == "architecture" and a.get("kind") == "ui-requirements"), None)
    if contract is None:
        raise ValueError("The architecture stage has to be approved with its ui-requirements.json registered first (frontend_handover)")
    design_scripts = Path(__file__).resolve().parents[2] / "Luz-Design/scripts"
    # A separate interpreter avoids collisions among the skills' historical
    # context/new_session/crawl_gate module names in a full routing rehearsal.
    worker = r"""
import json, sys
from pathlib import Path
import new_session, frontend as f, ui_package

root = Path(sys.argv[1]).resolve()
cache = root / "00-design" / "fixture-source.json"
if cache.is_file():
    source = json.loads(cache.read_text(encoding="utf-8"))
    ui_package.verify_package(Path(source["package"]), session=Path(source["session"]))
else:
    session = new_session.create_session(root / "00-design" / "source-fixtures",
        "TEST ONLY complete source", ["document"], cards=["interface-visual"], project=root)
    package = Path(f.init("app-task", session, "design", requirements=sys.argv[2])["package"])
    # Synthetic review evidence, the same shape Design's own unit fixture uses: never visual acceptance.
    from PIL import Image
    raw = session / "raw"
    image = raw / "fixture.png"; Image.new("RGB", (240, 300), "white").save(image)
    log = raw / "fixture.txt"; log.write_text("TEST ONLY synthetic fixture; not product acceptance.", encoding="utf-8")
    receipt = f.read(package / f.RECEIPT)
    browser = raw / "browser-fixture.json"
    f.write(browser, {"bundle_sha256": receipt["bundle_sha256"], "observations": ["TEST ONLY contract fixture"], "limitations": ["Not product evidence"]})
    q = f.quality_module()
    assessment = q.plan(q.read(q.CATALOG), q.digest(q.CATALOG), "luz-design", "design")
    assessment.update(receipt_sha256=f.digest(package / f.RECEIPT), browser_report_sha256=f.digest(browser))
    for row in assessment["rows"]:
        row.update(status="not-applicable", reason="TEST ONLY validator fixture; no product claim", reviewer="unit-test-fixture")
    quality = raw / "quality-fixture.json"; f.write(quality, assessment)
    evidence = {"path": str(log), "sha256": f.digest(log)}
    contract = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    covers = {"page_ids": [x["id"] for x in contract["pages"]], "action_ids": [x["id"] for x in contract["actions"]],
              "journey_ids": [x["id"] for x in contract["journeys"]]}
    review = {"bundle_sha256": receipt["bundle_sha256"], "reviewer": "unit-test-fixture",
              "browser_report": {"path": str(browser), "sha256": f.digest(browser)},
              "quality_assessment": {"path": str(quality), "sha256": f.digest(quality)},
              "blocking_findings": [], "component_usage": ["fixture"], "limitations": ["synthetic fixture"],
              "hard_rules": {"sha256": f.digest(f.HARD_RULES), "violations": [], "reviewed": sorted(f.REVIEW_RULES)},
              "loaded_assets": ["artwork/list.webp", "artwork/pattern.webp"],
              "experience_axes": {axis: {"status": "verified", "observed": "TEST ONLY contract fixture", "limitations": ["Not product evidence"], "evidence": [evidence]} for axis in ("UX", "AX", "DX")},
              "observations": [{"viewport": "fixture", "finding": "fixture only", "screenshot": {"path": str(image), "sha256": f.digest(image)}}],
              "interactions": [{"action": "fixture", "result": "fixture", "evidence": evidence, "covers": covers}]}
    review_input = raw / "review-input.json"; f.write(review_input, review)
    f.review(package, session, review_input)
    ui_package.verify_package(package, session=session)
    source = {"session": str(session), "package": str(package), "entry": receipt["entries"][0]}
    cache.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
print(json.dumps(source, ensure_ascii=False))
"""
    process = subprocess.run([sys.executable, "-X", "utf8", "-c", worker, str(root), str(contract)],
                             cwd=design_scripts, text=True, encoding="utf-8", errors="replace",
                             capture_output=True, timeout=1800, shell=False)
    if process.returncode:
        raise ValueError("Real Design source fixture failed: " + (process.stdout + process.stderr).strip())
    source = json.loads(process.stdout.splitlines()[-1])
    register_session(root, "luz-design", source["session"], "design",
                     "TEST ONLY: real package seal and check, synthetic review; responsive web preview, not native or product acceptance")
    for block in blocks:
        block["source"] = dict(source)
    spec["conclusion"] += " 本夹具复用同一个响应式 Web 界面包，只核验封存、审阅绑定和来源链，不是原生小程序或业务验收。"
    return source


def paths_blocks(prototypes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """前端规范 › 页面与路径 for the rehearsal: for each front end its prototype file, a navigation table and a page list with a 路径 column."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": "页面与路径的演练内容，只验证文档标准与门禁。"}]
    for title, proto in prototypes.items():
        blocks += [{"type": "sub", "text": title}, {"type": "text", "text": f"原型文件：`{proto['file']}`"},
                   {"type": "table", "caption": f"{title}的导航结构", "columns": ["菜单", "入口", "角色"], "rows": [["首页", "底部标签", "全部"]]},
                   {"type": "table", "caption": f"{title}的页面清单", "columns": ["路径", "页面", "作用"], "rows": [["/home", "首页", "演练页面"]]}]
    return blocks


def baseline_block(kind: str, scope: str, surfaces: Any = None) -> dict[str, Any]:
    """A baseline table that keeps every item (the rehearsal does not care what a project really chooses)."""
    import baseline as bl

    if kind == "module":
        ids = [m["id"] for m in bl.functions()["modules"]]
    else:
        ids = bl.mandatory_ids(kind, scope, surfaces)
    return {"type": "baseline", "kind": kind, "scope": scope, "caption": f"底座对照 {scope or '基础功能'}", "rows": [{"id": i, "status": "沿用"} for i in ids]}


def function_card(fid: str, module: str, name: str) -> dict[str, Any]:
    import baseline as bl

    text = "演练内容，只验证文档标准与门禁：写到页面、接口、表和数字才是真实的功能卡。" * 2
    return {"type": "function", "id": fid, "name": name, "system": "小程序", "module": module, "summary": "演练功能卡，验证标准", "frontend": text, "backend": text, "database": text, "tech": text,
            "rules": ["演练规则一条，条件与结果"], "exceptions": ["演练异常一条，界面提示"], "tests": ["演练测试一条"], "code": ["src/演练.java"], "deviation": [],
            "inherits": bl.function_items()[0]["id"], "status": "沿用"}


def sample_spec(stage: str, root: Path, frontends: list[tuple[str, str, str]] | None = None) -> dict[str, Any]:
    """``frontends`` (title, surface, prototype kind) overrides the front end tabs of a design document (default: one per surface of the project)."""
    import dev_documents as dd

    std = dd.STANDARDS[stage]
    ctx = dd.project_context(Path(root))

    def blocks_for(title: str, req: dict[str, Any]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [{"type": "text", "text": f"{title}的演练内容，只验证文档标准与门禁。"}]
        if req.get("baseline"):
            blocks.append(baseline_block(*req["baseline"], surfaces=ctx["surfaces"] if ctx else None))
        for n in range(req.get("tables", 0)):
            blocks.append(table(f"{title}表{n + 1}"))
        for n in range(req.get("figures", 0)):
            blocks.append(figure(f"{title}图{n + 1}"))
        return blocks

    if "tabs" in std:
        tabs = []
        want = dd.expected_tabs(stage, ctx)
        if frontends:
            mids = [{"title": n, "layout": "frontend", "frontend": True, "surface": sf, "kind": k} for n, sf, k in frontends]
            want = [x for t in want for x in (mids if t.get("frontend") else [t])]
        prototypes = {t["title"]: prototype(Path(root), f"{t['title']}原型", f"proto{n}", t.get("kind") or dd.UI_SURFACES[t["surface"]][1]) for n, t in enumerate((t for t in want if t.get("frontend")), 1)}
        for tab in want:
            if tab.get("frontend"):
                tabs.append({"title": tab["title"], "layout": tab["layout"], "surface": tab["surface"], "sections": [{"title": tab["title"], "blocks": [prototypes[tab["title"]]]}]})
                continue
            if tab.get("dynamic") == "modules":
                mods = [(str(m["id"]), str(m["name"])) for m in ctx["modules"]] if ctx and ctx["modules"] else [("M01", "模块甲"), ("M02", "模块乙")]
                sections = []
                for mid, mname in mods:
                    blocks = blocks_for(mname, {"tables": tab.get("module_tables", 0)})
                    if tab.get("functions"):
                        feats = [f for f in ctx["features"] if str(f["module"]) == mid] if ctx and ctx["features"] else [{"id": f"FN-{len(sections) + 1:03d}", "name": "演练功能"}]
                        blocks += [function_card(f["id"], mname, f["name"]) for f in feats]
                    sections.append({"title": mname, "blocks": blocks})
            else:
                sections = [{"title": s["title"], "blocks": paths_blocks(prototypes) if s.get("paths") else blocks_for(s["title"], s)} for s in tab["sections"]]
            tabs.append({"title": tab["title"], "layout": tab["layout"], "sections": sections})
        spec: dict[str, Any] = {"title": f"{stage} 离线演练", "conclusion": "只验证路由、门禁和文档标准，不构成真实的开发文档，也不是产品验收。", "tabs": tabs, "sources": SOURCES}
        have = sum(1 for t in tabs for sec in t["sections"] for b in sec["blocks"] if b["type"] in ("figure", "image"))
        for n in range(max(0, std.get("min_figures", 0) - have)):
            tabs[0]["sections"][0]["blocks"].append(figure(f"补充图{n + 1}"))
        return spec
    sections = []
    for title in std["sections"]:
        sections.append({"title": title, "blocks": blocks_for(title, {"tables": std.get("tables", {}).get(title, 0), "figures": std.get("figures", {}).get(title, 0)})})
    return {"title": f"{stage} 离线演练", "conclusion": "只验证路由、门禁和文档标准，不构成真实的开发文档，也不是产品验收。", "sections": sections, "sources": SOURCES}

def ui_requirements(ids: list[str]) -> dict[str, Any]:
    """The behaviour contract Luz-System's ui_requirements.py checks, for a rehearsal: one page, one component, one action and
    one journey that answer for the given functions. TEST ONLY wording, never real requirements."""
    states = ("default", "loading", "empty", "success", "error", "disabled", "permission_denied", "offline")
    return {
        "schema": "luz-ui-requirements/2",
        "action_groups": [{"id": "rehearsal", "owner_page_id": "P-001", "feature_ids": list(ids)}],
        "features": [{"id": i, "need": "演练需求", "acceptance": "演练验收条件", "basis": {"kind": "user", "ref": "TEST ONLY 演练夹具"}} for i in ids],
        "pages": [{"id": "P-001", "route": "/home", "goal": "演练页面目标", "entry": "演练入口", "exit": "演练离开方式", "feature_ids": list(ids),
                   "component_ids": ["C-001"], "states": {state: "演练状态说明" for state in states}, "primary_action": "A-001"}],
        "actions": [{"id": "A-001", "name": "演练动作", "precondition": "演练前置条件", "result": "演练结果", "error": "演练错误提示", "recovery": "演练恢复方式",
                     "permission": "演练权限", "feature_id": ids[0], "page_id": "P-001", "component_id": "C-001"}],
        "components": [{"id": "C-001", "purpose": "演练用途", "behavior": "演练行为", "data_contract": "演练数据", "acceptance": "演练验收",
                        "page_ids": ["P-001"], "feature_ids": list(ids), "states": ["default"]}],
        "journeys": [{"id": "J-001", "expected": "演练预期", "recovery": "演练恢复", "page_ids": ["P-001"], "action_ids": ["A-001"]}],
        "non_ui_features": [],
    }


def frontend_handover(root: Path) -> None:
    """The 界面功能说明 and entrance table an architecture stage of a project with screens hands over (references/dev-documents.md): minimal files that
    answer for every function of the function list, registered as artifacts of the stage (never real content)."""
    import json

    import client_data as cd
    from project_core import locate, register_artifact, state_name

    root = Path(root)
    folder = locate(root, state_name(root, "architecture/frontend-spec"))
    folder.mkdir(parents=True, exist_ok=True)
    ids = [f["id"] for f in cd.active_features(cd.load_features(root))]
    (folder / "frontend-spec.json").write_text(json.dumps({"fn_homes": [{"fn": i} for i in ids]}, ensure_ascii=False), encoding="utf-8")
    (folder / "界面功能说明.html").write_text("<!doctype html><title>界面功能说明（演练）</title><h1>界面功能说明</h1>", encoding="utf-8")
    (folder / "entrances.json").write_text(json.dumps({"entrances": [{"fn": i} for i in ids], "no_entrance": []}, ensure_ascii=False), encoding="utf-8")
    # A component-reuse project (the default) also registers the behaviour contract of its screens: exactly the functions
    # the client kept, which the intake form may have narrowed.
    from client_flow import effective_features
    scope = [f["id"] for f in effective_features(root, cd.load_features(root))]
    (folder / "ui-requirements.json").write_text(json.dumps(ui_requirements(scope), ensure_ascii=False), encoding="utf-8")
    for name, kind in (("frontend-spec.json", "frontend-spec"), ("界面功能说明.html", "frontend-spec-page"), ("entrances.json", "entrances"),
                       ("ui-requirements.json", "ui-requirements")):
        register_artifact(root, "architecture", folder / name, kind)


def approved_frontend_handover(root: Path) -> None:
    """Supply an isolated stage-approval fixture to tests of design rendering and source tampering."""
    import client_fixture
    import project_core as pc

    client_fixture.crawled(root, "architecture")
    frontend_handover(root)
    manifest = pc.load_project(root)
    architecture = pc._stage_record(manifest, "architecture")
    artifacts = {item["id"]: item["sha256"] for item in pc._load_artifacts(root) if item["stage"] == "architecture"}
    approvals = pc._load_approvals(root)
    record = {
        "id": pc._next_id(approvals["approvals"], "APPROVAL"),
        "project_id": manifest["project_id"],
        "stage": "architecture",
        "status": "approved",
        "approver": "TEST FIXTURE",
        "note": "TEST ONLY: isolated setup for design document tests",
        "approved_at": pc.now_iso(),
        "artifact_hashes": artifacts,
    }
    approvals["approvals"].append(record)
    architecture.update(status="approved", approval_id=record["id"], approved_hashes=artifacts)
    pc._write_json(root / "APPROVALS.json", approvals)
    pc._save_manifest(root, manifest)
