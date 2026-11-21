"""Require the final bytes of every approvable document to match its template.

The writer performs the pre-check. This separate read-only gate runs before
presentation and approval, so registering an arbitrary file or changing its
bytes cannot stand in for the writer's post-check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import project_core as pc


def output_contract(root: Path, stage: str, document: dict[str, Any]) -> tuple[str, str]:
    """Return the real writer's caller and template, including both PDF routes."""
    import client_data as cd

    path = str(document["path"]).replace(chr(92), "/")
    for kind, (folder, name, _) in pc.client_document_files(root).items():
        if path != f"{folder}/{name}":
            continue
        if kind in {"intake-response", "change-ledger"}:
            raise ValueError("客户输入与活台账不属于逐文件审批")
        if Path(path).suffix == ".xlsx":
            return "luz-project", "xlsx"
        if kind == "architecture-pdf":
            return "luz-project", "showcase"
        if kind in {"requirements-pdf", "proposal-pdf"} and (cd.load(root, "client", "requirements.json" if kind == "requirements-pdf" else "proposal.json") or {}).get("format", "word") != "word":
            return "luz-project", "showcase"
        return "luz-project", "docx-paginated"
    if path == pc.stage_document_path(stage, root).replace(chr(92), "/"):
        return "luz-project", "showcase"
    if stage == "design" and Path(path).suffix.lower() == ".html":
        return "luz-project", "reading-html"
    if stage in {"verification", "release", "operations"} and Path(path).suffix.lower() == ".pdf":
        return "luz-ops", "docx-paginated"
    if stage == "implementation" and Path(path).suffix.lower() == ".pdf":
        return "luz-dev", "docx-paginated"
    raise ValueError(f"没有正式文档的模板契约：{stage}/{path}")


def output_errors(root: Path, stage: str, document: dict[str, Any]) -> list[str]:
    """Check a Project writer or an explicitly linked specialist session."""
    target = pc.locate(root, document["path"])
    if not target.is_file():
        return []  # the ordinary build check reports the missing document
    try:
        caller, identifier = output_contract(root, stage, document)
        design_scripts = str(pc.ROOT.parent / "Luz-Design" / "scripts")
        if design_scripts not in sys.path:
            sys.path.insert(0, design_scripts)
        from template_library import require_selected
        from project_summary import sessions

        reasons = []
        contracts = [(caller, identifier, False)]
        if stage in {"verification", "release", "operations"} and str(document["path"]).replace(chr(92), "/") == pc.stage_document_path(stage, root).replace(chr(92), "/"):
            # Ops' public report writer owns the same three precise HTML
            # targets.  It uses the same showcase template under luz-ops and
            # records its own writer index; arbitrary HTMLs gain no fallback.
            contracts.append(("luz-ops", "showcase", True))
        for candidate, template, ops_report in contracts:
            contexts = [Path(root)]
            if ops_report:
                try:
                    index = json.loads((Path(root) / "data/ops/template-outputs.json").read_text(encoding="utf-8"))
                    binding = index.get(str(target.resolve())) if isinstance(index, dict) else None
                    if not isinstance(binding, dict) or binding.get("stage") != stage or binding.get("id") != template:
                        raise ValueError("Ops 正式评审页缺少本项目准确阶段与路径的 writer 记录")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    reasons.append(str(exc))
                    continue
            else:
                for item in sessions(root):
                    if item.get("stage") != stage or str(item.get("skill", "")).lower() != candidate:
                        continue
                    path = Path(str(item.get("path", ""))).resolve()
                    if path not in contexts:
                        contexts.append(path)
            for context in contexts:
                try:
                    require_selected(context, candidate, stage, target, template, phase="post")
                    if stage == "design" and str(document["path"]).replace(chr(92), "/") != pc.stage_document_path(stage, root).replace(chr(92), "/"):
                        from project_ui_source import output_errors as ui_output_errors
                        return ui_output_errors(root, document["path"])
                    return []
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    reasons.append(str(exc))
        return [f"{document['path']}：Luz-Design 模板最终输出未通过（{caller}/{stage}/{identifier}）：" + "；".join(reasons)]
    except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
        return [f"{document['path']}：Luz-Design 模板最终输出无法核验：{exc}"]
