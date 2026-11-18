"""Keep source-locked UI intact and hand its verified entry to project docs.

The docs file is a Design reading page containing the source link. The actual
UI and every asset stay in its linked Design session; no HTML is flattened.
"""
from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote, urlsplit

import project_core as pc

DESIGN = pc.ROOT.parent / "Luz-Design"


def _library():
    spec = importlib.util.spec_from_file_location("_project_ui_templates", DESIGN / "scripts/template_library.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _source_check(session, package):
    """Use the public verifier in its own process, avoiding cross-skill imports."""
    verifier = "ui_package.py"
    try:
        result = subprocess.run([sys.executable, "-X", "utf8", str(DESIGN / "scripts" / verifier), "check",
                                 str(package), "--session", str(session)], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120, shell=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"完整 UI 来源核验进程未完成：{exc}") from exc
    if result.returncode:
        raise ValueError("完整 UI 未通过 " + verifier + " check：" + (result.stdout + result.stderr).strip())
    proof = json.loads(result.stdout)
    if not isinstance(proof, dict) or not proof.get("receipt") or not proof.get("entry_files"):
        raise ValueError("来源核验没有返回真实回执及固定入口")
    return proof


def source_contract(root, source):
    root = Path(root).resolve()
    if not isinstance(source, dict) or set(source) != {"session", "package", "entry"}:
        raise ValueError("原型必须提供 source 的 session、package、entry，不能用文件大小或组件标记代替来源")
    session = Path(str(source["session"])).resolve()
    manifest = _read(session / "raw/99-delivery/MANIFEST.json")
    link = manifest.get("project")
    if not isinstance(link, dict) or link.get("stage", "design") != "design":
        raise ValueError("UI 来源必须来自关联本项目 design 阶段的 Design 会话")
    state = Path(str(link.get("state_root") or "")).resolve()
    if state != root or not (state / "project.json").is_file():
        raise ValueError("UI 来源的项目状态根与当前项目不一致")
    from project_summary import sessions
    if not any(str(item.get("skill", "")).lower() == "luz-design" and item.get("stage") == "design"
               and Path(str(item.get("path", ""))).resolve() == session for item in sessions(root)):
        raise ValueError("先使用 project.py session 登记本项目 design 阶段的真实 Design 会话")
    package = Path(str(source["package"]))
    package = (package if package.is_absolute() else session / package).resolve()
    raw = session / "raw"
    if package == raw or not package.is_relative_to(raw):
        raise ValueError("完整 UI 来源包必须保留在关联 Design 会话 raw 中")
    proof = _source_check(session, package)
    selected = proof.get("mode", "source-locked")
    if selected == 'component-reuse':
        from project_ui_requirements import binding as requirements_binding
        req=proof['requirements'];req_path=(Path(proof['spec']).parent/req['path']).resolve()
        requirements_binding(root,req_path)
    elif selected == 'frontend':
        # A frontend.py package carries the contract it was sealed against as ui-requirements.json and lists its entries in the receipt.
        from project_ui_requirements import binding as requirements_binding
        requirements_binding(root, package / "ui-requirements.json")
        entries = [str(item) for item in (proof["receipt"].get("entries") or [])]
        proof = {**proof, "entrypoints": entries, "entry_files": {item: item for item in entries}}
    entry = str(source["entry"])
    if entry not in proof["entrypoints"] or entry not in proof["entry_files"]:
        raise ValueError("原型 entry 不是本次浏览器核验的来源入口")
    physical = Path(str(proof["entry_files"][entry]))
    target = (package / physical).resolve()
    if physical.is_absolute() or not target.is_relative_to(package) or not target.is_file():
        raise ValueError("原型入口文件不存在或越出完整来源包")
    relative = package.relative_to(raw).as_posix()
    registry, receipt_name = {
        "source-locked": ("source_ui_outputs", "luz-source.json"),
        "component-reuse": ("component_ui_outputs", "luz-component-ui.json"),
        "authorized-project": ("custom_ui_outputs", "luz-custom-ui.json"),
        "frontend": ("frontend_outputs", "luz-frontend.json"),
    }.get(selected, (None, None))
    if registry is None:
        raise ValueError("未知 UI 来源合同模式")
    record = manifest.get(registry, {}).get(relative)
    # frontend packages record the sha of their review.json (frontend.py review); the other modes record a browser audit.
    audit_sha = None
    if isinstance(record, dict):
        audit = record.get("audit")
        audit_sha = record.get("review_sha256") if selected == "frontend" else (audit.get("sha256") if isinstance(audit, dict) else None)
    if not isinstance(record, dict) or not audit_sha:
        raise ValueError("完整 UI 来源缺少登记的浏览器审计")
    binding = {"session": str(session), "package": str(package), "entry": entry,
               "entry_sha256": _digest(target.read_bytes()), "receipt_sha256": _digest((package / receipt_name).read_bytes()),
               "audit_sha256": audit_sha, "template_id": proof["template_id"]}
    return {"entry": target, "fragment": urlsplit(entry).fragment, "binding": binding}


def entry_href(contract, base):
    relative = os.path.relpath(contract["entry"], Path(base)).replace(os.sep, "/")
    return quote(relative, safe="/.-_") + ("#" + quote(contract["fragment"], safe="/.-_") if contract["fragment"] else "")


def prototype_blocks(spec):
    for tab in spec.get("tabs", []):
        for section in tab.get("sections", []):
            for block in section.get("blocks", []):
                if block.get("type") == "prototype":
                    yield block


def render_link(block, contract, target):
    title = str(block["title"])
    href = html.escape(entry_href(contract, Path(target).parent), quote=True)
    body = f'<h2>系统界面</h2><p><a href="{href}">打开{html.escape(title)}</a></p>'
    return _library().render_reading(title, body)


def prepare(root, spec):
    """Precheck all sources and all exact link-page templates before any write."""
    pc.require_crawl(root, "design")
    prepared = []
    for block in prototype_blocks(spec):
        target = pc.locate(root, str(block["file"]))
        if target.parent != pc.locate(root, "docs/02-产品开发") or target.suffix.lower() != ".html":
            raise ValueError("原型访问页必须平铺在项目 docs/02-产品开发 中")
        contract = source_contract(root, block.get("source"))
        _library().require_selected(root, "luz-project", "design", target, "reading-html")
        block["source_binding"] = contract["binding"]
        prepared.append((block, target, render_link(block, contract, target)))
    return prepared


def write_links(root, prepared):
    pc.require_crawl(root, "design")
    for block, target, document in prepared:
        contract = source_contract(root, block.get("source"))
        expected = pc.locate(root, str(block["file"]))
        if (Path(target).resolve() != expected.resolve()
                or document != render_link(block, contract, target)
                or block.get("source_binding") != contract["binding"]):
            raise ValueError("原型访问页的来源、目标或模板内容在写入前发生变化")
        _library().require_selected(root, "luz-project", "design", target, "reading-html")
    for block, target, document in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding="utf-8")
        _library().record_output(root, "luz-project", "design", target, "reading-html",
                                 generator="Luz-Project/scripts/project_ui_source.py:write_links")


def output_errors(root, relative):
    try:
        spec = _read(Path(root) / "data/stages/design.json")
        blocks = [block for block in prototype_blocks(spec) if str(block.get("file", "")).replace(chr(92), "/") == str(relative).replace(chr(92), "/")]
        if len(blocks) != 1:
            raise ValueError("设计文档没有唯一对应的完整 UI 来源记录")
        block = blocks[0]
        contract = source_contract(root, block.get("source"))
        if block.get("source_binding") != contract["binding"]:
            raise ValueError("来源包、入口、回执或浏览器审计与交接时不一致")
        target = pc.locate(root, relative)
        _library().require_selected(root, "luz-project", "design", target, "reading-html", phase="post")
        if target.read_text(encoding="utf-8") != render_link(block, contract, target):
            raise ValueError("项目原型访问页没有保持真实模板与原入口链接")
        return []
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        return [f"{relative}：完整 UI 来源交接未通过：{exc}"]
