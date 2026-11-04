"""Render substantive stage facts; the project index is never an architecture deliverable."""
from __future__ import annotations
import html
import math
from pathlib import Path
import dev_documents
from project_core import ProjectError, _html_page, _load_artifacts, _save_artifacts, doc_theme, _write_json, load_project, register_artifact, now_iso, require_crawl, stage_document_path, DOC_DIRS


def esc(value):
    if isinstance(value, (list, tuple)):
        return "<br>".join(esc(v) for v in value)
    if isinstance(value, dict):
        return "<br>".join(esc(k) + "：" + esc(v) for k, v in value.items())
    return html.escape(str(value), quote=True)


def table(rows, columns, widths=None):
    """Review tables: one alignment per column (Luz-Design), long lists of ids and sentences left, short values centred."""
    import sys
    from project_core import ROOT

    design = ROOT.parent / "Luz-Design" / "scripts"
    if str(design) not in sys.path:
        sys.path.insert(0, str(design))
    import showcase  # type: ignore

    cells = [[(", ".join(map(str, v)) if isinstance(v, (list, tuple)) else (str(v) if v not in (None, "") else "—")) if not isinstance(v, dict) else "；".join(f"{k}：{x}" for k, x in v.items()) for v in (row.get(key, "—") for key, label in columns)] for row in rows]
    return showcase.table_html([label for key, label in columns], cells, first_key=False, widths=widths)


def write_document(project, stage, spec):
    root = Path(project).resolve()
    manifest = load_project(root)
    if stage not in DOC_DIRS:
        raise ProjectError("未知阶段")
    require_crawl(root, stage)
    if not isinstance(spec, dict) or not str(spec.get("title", "")).strip() or not str(spec.get("conclusion", "")).strip():
        raise ProjectError("阶段文档需要实际标题与结论")
    if dev_documents.has_standard(stage):
        errors = dev_documents.validate(stage, spec, root)
        if errors:
            raise ProjectError(f"{stage} 文档未通过 dev-documents 标准: " + "; ".join(errors))
        body = dev_documents.render_body(spec, root, (root / stage_document_path(stage)).parent)
    else:
        sections = spec.get("sections", [])
        if not sections or any(not s.get("title") or not s.get("content") for s in sections):
            raise ProjectError("阶段文档需要实质 sections（title/content）")
        body = "".join("<h2>" + esc(s["title"]) + "</h2><p>" + esc(s["content"]) + "</p>" for s in sections)
    if not dev_documents.has_standard(stage):
        body = "<h2>结论</h2><p>" + esc(spec["conclusion"]) + "</p>" + body             # the reading-page rule: an h2 follows the h1
    if stage in {"proposal", "client-intake", "handover"}:
        import client_flow
        body += "".join("<h2>" + esc(x["title"]) + "</h2><ul>" + "".join("<li>" + esc(i) + "</li>" for i in x["content"]) + "</ul>" for x in client_flow.review_extras(root, stage))
    sources = spec.get("sources", [])
    if sources and not dev_documents.has_standard(stage):
        body += "<h2>来源与依据</h2>" + table(sources, [("id", "来源"), ("url", "网址"), ("finding", "补充信息"), ("applies_to", "采用位置")], widths=[1.3, 3.2, 4, 3])
    data = root / "data" / "stages" / f"{stage}.json"
    relative = stage_document_path(stage)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(data, spec)
    page = _html_page(project_id=manifest["project_id"], document_id=f'DOC-{manifest["project_id"]}-{stage}-review', stage=stage, status="pending-review", version=now_iso(), title=spec["title"], body=body, theme=doc_theme(root))
    path.write_text(page, encoding="utf-8")
    register_artifact(root, stage, data, "architecture-spec" if stage == "architecture" else "stage-spec", [s["id"] for s in sources])
    register_artifact(root, stage, path, "html", [s["id"] for s in sources])
    _retire_old_pages(root, stage, relative)
    if stage == "design":
        _register_prototypes(root, spec)
    return path


def _register_prototypes(root, spec):
    """The prototypes the design document embeds are deliverables of the stage: register each file (kind html) and list them, named after their front end,
    in the stage's deliverables, so that an approval covers them and a check can tell when one is missing."""
    from project_core import _design_prototypes, _save_manifest, stage_deliverables, _stage_defs
    seen = set()
    for proto in _design_prototypes(root):
        if proto["path"] in seen:
            continue
        seen.add(proto["path"])
        register_artifact(root, "design", root / proto["path"], "html")
    manifest = load_project(root)
    for record in manifest["stages"]:
        if record["id"] == "design":
            record["deliverables"] = stage_deliverables(root, _stage_defs()["design"])
    _save_manifest(root, manifest)


def _retire_old_pages(root, stage, keep):
    """A project written before the numbered names has ``<stage>-review.html``: the renamed document replaces it."""
    artifacts = _load_artifacts(root)
    old = [a for a in artifacts if a.get("stage") == stage and a.get("kind") == "html" and str(a.get("path", "")).replace(chr(92), "/") != keep
           and str(a.get("path", "")).endswith("-review.html")]
    if not old:
        return
    gone = {a["id"] for a in old}
    for a in old:
        (root / str(a["path"])).unlink(missing_ok=True)
    _save_artifacts(root, [a for a in artifacts if a["id"] not in gone])
    manifest = load_project(root)
    for record in manifest["stages"]:
        if record["id"] == stage:
            record["artifact_ids"] = [i for i in record.get("artifact_ids", []) if i not in gone]
    from project_core import _save_manifest
    _save_manifest(root, manifest)
