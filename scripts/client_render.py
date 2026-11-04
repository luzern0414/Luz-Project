"""Render client-facing documents through Luz-Design: Word-typeset PDFs (proposal, manual), the architecture atlas PDF, and XLSX.

Luz-Project owns *what* goes into a client document (facts in ``data/client``); Luz-Design owns how it looks: the Word route
(make_docx_paginated.py, file-design.html 客户正式文档), the atlas figures and tables (make_showcase.py, 系统架构图册) and the
spreadsheet builder with its no-clipping checks. Everything is built into ``raw/client-docs/`` first, so a document that
fails a check never reaches ``docs/``.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from project_core import ProjectError

DESIGN_SCRIPTS = Path(__file__).resolve().parents[2] / "Luz-Design" / "scripts"


def design_modules():
    if not DESIGN_SCRIPTS.is_dir():
        raise ProjectError(f"找不到 Luz-Design 脚本目录: {DESIGN_SCRIPTS}（客户文档必须由 Design 的版式与检查生成）")
    if str(DESIGN_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(DESIGN_SCRIPTS))
    import check_document  # type: ignore
    import make_showcase  # type: ignore
    import make_table_pdf  # type: ignore
    import make_xlsx  # type: ignore
    import showcase  # type: ignore

    return showcase, make_showcase, make_table_pdf, make_xlsx, check_document


def staging(root: Path) -> Path:
    path = root / "raw" / "client-docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- showcase documents -----------------------------------------------------------------------------------------

def build_showcase(root: Path, name: str, spec: dict[str, Any], *, min_fill: float = 0.75) -> tuple[Path, Path]:
    """Validate the spec, write the display HTML, run Design's document check, export the packed PDF, check it."""
    showcase, make_showcase, make_table_pdf, _, check_document = design_modules()
    errors = showcase.validate_spec(spec)
    if errors:
        raise ProjectError(f"{name}: 文档数据未通过: " + "; ".join(errors[:8]))
    work = staging(root)
    html_path, pdf_path = work / f"{name}.html", work / f"{name}.pdf"
    html_path.write_text(showcase.build(spec), encoding="utf-8")
    if check_document.main([str(html_path), "--allow", "showcase"]) != 0:
        raise ProjectError(f"{name}: Luz-Design check_document 未通过，见上方 ERROR（源文件 {html_path}）")
    page_errors, warnings, report = make_showcase.export_pdf(html_path, pdf_path, spec.get("orientation", "portrait"), spec.get("min_fill", min_fill),
                                                             spec["title"] if spec.get("style") in ("formal", "atlas") else "", bool(spec.get("cover")),
                                                             header=spec.get("style") != "atlas")
    page_errors += make_table_pdf.check_pdf(pdf_path, spec.get("max_pages"))
    print(f"{name}: page fill " + ", ".join(f"{p['page']}:{p['fill']:.0%}" for p in report["pages"]))
    for w in warnings:
        print("WARN", w)
    if page_errors:
        raise ProjectError(f"{name}: PDF 检查未通过: " + "; ".join(page_errors))
    return pdf_path, html_path


# --- project data -> showcase specs -------------------------------------------------------------------------------

def _module_icon(module: dict[str, Any]) -> str:
    import showcase_icons as I  # type: ignore

    design_modules()
    return module.get("icon") or I.pick(module["name"] + module.get("summary", ""), "grid")


def expand_auto(spec: dict[str, Any], features: dict[str, Any], theme: str) -> dict[str, Any]:
    """Resolve ``{"type": "auto", "what": ...}`` blocks from the single feature list, so documents cannot disagree with it."""
    from client_data import SURFACES, active_features

    items = active_features(features)
    modules = features["modules"]
    out = json.loads(json.dumps(spec, ensure_ascii=False))
    out.setdefault("theme", theme)
    for sec in out.get("sections", []):
        blocks = []
        for b in sec["blocks"]:
            if b.get("type") != "auto":
                blocks.append(b)
                continue
            what = b["what"]
            if what == "feature_overview":
                basic = sum(1 for f in items if f["tier"] == "基础")
                if out.get("style") == "formal":
                    blocks.append({"type": "text", "text": f"共 {len(modules)} 个功能模块、{len(items)} 项功能，其中基础功能 {basic} 项（本期交付），可选功能 {len(items) - basic} 项（客户选择后实施）。"})
                else:
                    blocks.append({"type": "stats", "items": [
                        {"value": f"{len(modules)} 个", "label": "功能模块", "icon": "grid"},
                        {"value": f"{len(items)} 项", "label": "功能总数", "icon": "list"},
                        {"value": f"{basic} 项", "label": "基础功能（本期交付）", "icon": "check"},
                        {"value": f"{len(items) - basic} 项", "label": "可选功能（客户选择）", "icon": "star"}]})
                rows = []
                for m in modules:
                    fs = [f for f in items if f["module"] == m["id"]]
                    if fs:
                        rows.append([m["name"], m["summary"], "、".join(sorted({SURFACES.get(f["surface"], f["surface"]) for f in fs})), f"{len(fs)} 项"])
                blocks.append({"type": "table", "columns": ["模块", "说明", "使用端", "功能"], "rows": rows, "widths": [2.2, 5, 2.4, 1], "caption": "功能模块总览"})
            elif what == "role_module_matrix":
                roles = []
                for f in items:
                    for r in f["roles"]:
                        if r != "全部角色" and r not in roles:
                            roles.append(r)
                rows = []
                for m in modules:
                    fs = [f for f in items if f["module"] == m["id"]]
                    if fs:
                        rows.append([m["name"]] + [("✓" if any(r in f["roles"] or "全部角色" in f["roles"] for f in fs) else "—") for r in roles])
                blocks.append({"type": "matrix", "columns": ["功能模块"] + roles, "rows": rows, "widths": [3] + [1.3] * len(roles), "caption": "各角色可使用的功能模块"})
            elif what == "requirement_list":          # the needs, module by module, taken from the feature list so the two cannot disagree
                for m in modules:
                    fs = [f for f in items if f["module"] == m["id"]]
                    if fs:
                        blocks.append({"type": "sub", "text": m["name"]})
                        blocks.append({"type": "table", "columns": ["编号", "需求", "具体要求", "业务规则", "类型"], "widths": [1.9, 2.2, 4, 4, 1.2],
                                       "rows": [[f["id"], f["name"], f["summary"], f.get("rules") or "—", f["tier"]] for f in fs], "caption": f"{m['name']}的需求"})
            else:
                raise ProjectError(f"未知 auto 块: {what}")
        sec["blocks"] = blocks
    return out


def proposal_docx_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """The proposal's blocks (text, sub heading, list, table) as a Design make_docx description: formal, black and white, cover and contents."""
    def blocks(section: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for b in section["blocks"]:
            kind = b["type"]
            if kind in ("text", "p", "callout"):
                out.append({"p": b["text"]})
            elif kind in ("bullets", "checks"):
                out.append({"items": b["items"]})
            elif kind == "sub":
                out.append({"sub": b["text"]})
            elif kind == "table":
                out.append({"table": {"header": b["columns"], "rows": b["rows"], "caption": b["caption"], **({"widths": b["widths"]} if b.get("widths") else {})}})
            elif kind == "matrix":
                rows = [[r[0]] + ["是" if v in (True, "✓", "y", "是") else "—" for v in r[1:]] for r in b["rows"]]
                out.append({"table": {"header": b["columns"], "rows": rows, "caption": b["caption"]}})
            else:
                raise ProjectError(f"方案用 Word 排版，不支持 {kind} 块")
        return out

    info = spec.get("hero", {}).get("info") or []
    return {"type": "proposal", "title": spec["title"], "style": "paper", "mono": True, "toc": bool(spec.get("toc", True)),
            "cover": {"subtitle": spec.get("subtitle", ""), "info": info},
            "sections": [{"heading": s["title"], "blocks": blocks(s)} for s in spec["sections"]]}


def build_docx(root: Path, name: str, spec: dict[str, Any]) -> tuple[Path, Path]:
    """Word first: build the .docx, let a Word-compatible application lay it out (contents page numbers, 续表), export the PDF from it."""
    design_modules()
    import check_document  # type: ignore
    import make_docx_paginated  # type: ignore

    out = staging(root) / f"{name}.docx"
    try:
        make_docx_paginated.build(proposal_docx_spec(spec), out)
    except FileNotFoundError as exc:
        raise ProjectError(f"{name}: 找不到排版用的 Word 兼容软件（WPS 文字或 Word）: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - the layout step runs an external application
        raise ProjectError(f"{name}: Word 排版失败: {exc}") from exc
    if check_document.main(["--allow", "paper", "--allow", "cover", "--allow", "header", str(out)]) != 0:
        raise ProjectError(f"{name}.docx 未通过 Luz-Design check_document")
    return out, out.with_suffix(".pdf")


def ordered_features(features: dict[str, Any]) -> list[dict[str, Any]]:
    """Big groups first: 使用端, then 使用角色, then 功能模块, then the function id; every Excel that lists functions uses this order."""
    from client_data import SURFACES, active_features

    items = active_features(features)
    surface_rank = {name: i for i, name in enumerate(SURFACES)}
    role_rank: dict[str, int] = {}
    for f in items:
        role_rank.setdefault("、".join(f["roles"]), len(role_rank))
    module_rank = {m["id"]: i for i, m in enumerate(features["modules"])}
    return sorted(items, key=lambda f: (surface_rank.get(f["surface"], 99), role_rank["、".join(f["roles"])], module_rank.get(f["module"], 99), f["id"]))


def feature_list_xlsx_spec(features: dict[str, Any], project_name: str, theme: str, quote: dict[str, Any] | None = None) -> dict[str, Any]:
    """功能清单: 使用端 → 使用角色 → 功能模块 (merged, big to small), 功能, 功能说明, 类型 — no code column, no business rules (those are in the
    业务逻辑确认表). With a quote there is a second sheet 报价清单: the same list plus 工时（人天） and 报价（元）, and the totals under it."""
    from client_data import SURFACES, quote_totals

    names = {m["id"]: m["name"] for m in features["modules"]}
    ordered = ordered_features(features)
    groups = [{"name": "使用端", "merge": True}, {"name": "使用角色", "merge": True}, {"name": "功能模块", "merge": True}]
    rows = [[SURFACES.get(f["surface"], f["surface"]), "、".join(f["roles"]), names[f["module"]], f["name"], f["summary"], f["tier"]] for f in ordered]
    columns = groups + [{"name": "功能"}, {"name": "功能说明", "type": "longtext"}, {"name": "类型", "tags": ["基础", "可选"]}]
    today = date.today().isoformat()
    look = {"tint_by": "功能模块", "highlight": {"column": "类型", "values": ["可选"]}}          # one pale colour per module, yellow for what the client chooses
    legend = "底色区分功能模块，黄色为可选功能"
    listing = {"sheet": "功能清单", "title": f"{project_name}功能清单", "subtitle": f"{project_name}　·　V1.0　·　{today}　·　{legend}", "columns": columns, "rows": rows, **look}
    if not quote:
        return {"title": listing["title"], "theme": theme, **{k: v for k, v in listing.items() if k != "title"}}
    totals = quote_totals(features, quote)
    price = quote["unit_price"]
    quoted = [r + [f["hours"], f["hours"] * price] for r, f in zip(rows, ordered)]
    unit = f"{price:,.0f}" if float(price).is_integer() else f"{price:,.2f}"
    footer = [{"label": "基础功能小计", "values": {"工时（人天）": totals["basic_hours"], "报价（元）": totals["basic_amount"]}},
              {"label": "可选功能小计，选用后另计", "values": {"工时（人天）": totals["optional_hours"], "报价（元）": totals["optional_amount"]}},
              {"label": f"报价合计，基础功能 {totals['basic_hours']:g} 人天，单价 {unit} 元每人天", "values": {"报价（元）": totals["basic_amount"]}}]
    pricing = {"sheet": "报价清单", "title": f"{project_name}报价清单", "subtitle": f"金额 = 工时 × 人天单价（{unit} 元）　·　{today}　·　{legend}",
               "columns": columns + [{"name": "工时（人天）", "type": "days"}, {"name": "报价（元）", "type": "money"}],
               "rows": quoted, "footer": footer, **look}
    return {"title": f"{project_name}功能清单与报价", "theme": theme, "sheets": [listing, pricing]}


def manual_spec(features: dict[str, Any], manual: dict[str, Any], theme: str) -> dict[str, Any]:
    """User manual as a Word document: one chapter per group of features; steps and rules are lists, states and questions are tables."""
    names = {f["id"]: f["name"] for f in features["features"]}
    sections: list[dict[str, Any]] = []
    if manual.get("intro"):
        blocks: list[dict[str, Any]] = [{"type": "text", "text": p} for p in manual["intro"].get("paragraphs", [])]
        if manual["intro"].get("bullets"):
            blocks.append({"type": "bullets", "items": manual["intro"]["bullets"]})
        sections.append({"title": "使用前须知", "blocks": blocks})
    if manual.get("roles"):
        sections.append({"title": "角色与权限", "blocks": [{"type": "table", "columns": ["角色", "说明"], "rows": [[r["name"], r["desc"]] for r in manual["roles"]], "caption": "使用角色"}]})
    for ch in manual["chapters"]:
        blocks = [{"type": "text", "text": f"入口：{ch['entry']}。涉及功能：{'、'.join(names.get(i, i) for i in ch['features'])}。"},
                  {"type": "sub", "text": "操作步骤"}, {"type": "bullets", "items": ch["steps"]},
                  {"type": "sub", "text": "业务规则"}, {"type": "bullets", "items": ch["rules"]}]
        if ch.get("states"):
            blocks.append({"type": "table", "columns": ["状态", "含义", "下一步"], "rows": [[s["name"], s["meaning"], s.get("next", "—")] for s in ch["states"]], "caption": f"{ch['heading']}的状态"})
        if ch.get("notes"):
            blocks.append({"type": "text", "text": "注意：" + "；".join(ch["notes"])})
        if ch.get("faq"):
            blocks.append({"type": "table", "columns": ["常见问题", "回答"], "rows": [[q["q"], q["a"]] for q in ch["faq"]], "caption": f"{ch['heading']}常见问题"})
        sections.append({"title": ch["heading"], "blocks": blocks})
    if manual.get("glossary"):
        sections.append({"title": "名词解释", "blocks": [{"type": "table", "columns": ["名词", "含义"], "rows": [[g["term"], g["meaning"]] for g in manual["glossary"]], "caption": "名词解释"}]})
    if manual.get("support"):
        sections.append({"title": "联系与支持", "blocks": [{"type": "table", "columns": ["项目", "内容"], "rows": [[k, v] for k, v in manual["support"].items()], "caption": "联系与支持"}]})
    return {"title": manual["title"], "subtitle": "使用说明", "format": "word", "toc": True, "hero": {"info": []}, "sections": sections}


# --- XLSX ------------------------------------------------------------------------------------------------------

def build_xlsx(root: Path, name: str, spec: dict[str, Any], *, pick_column: str | list[str] | None = None, row_lists: dict[str, dict[int, list[str]]] | dict[int, list[str]] | None = None) -> Path:
    """Build through Design's make_xlsx (its check_document gate included); then tint a fill-in column and add per-row pick-lists.

    With ``spec["sheets"]`` the workbook has several sheets and ``row_lists`` maps sheet name -> {data-row index -> options};
    for one sheet it maps data-row index -> options directly.
    """
    _, _, _, make_xlsx, check_document = design_modules()
    out = staging(root) / f"{name}.xlsx"
    spec_path = staging(root) / f"{name}.spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    make_xlsx.build(spec, out)
    if pick_column:
        from openpyxl import load_workbook
        from openpyxl.styles import Alignment, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation

        tint = "FFF8E1"   # one pale cream for every fill-in cell of every client sheet, whatever the theme
        wb = load_workbook(out)
        multi = bool(spec.get("sheets"))
        for ws in wb.worksheets:
            lists = (row_lists or {}).get(ws.title, {}) if multi else (row_lists or {})
            wanted = [pick_column] if isinstance(pick_column, str) else list(pick_column)
            header_row = next((r for r in range(1, 8) if any(c.value in wanted for c in ws[r])), None)
            if header_row is None:
                continue
            letters = [c.column_letter for c in ws[header_row] if c.value in wanted]
            for letter in letters:
                last = next((c for c in ws[header_row] if c.column_letter == letter), None)
                ws.column_dimensions[letter].width = max(ws.column_dimensions[letter].width or 0, 34 if last and last.value != "审核结果" else 16)   # the columns the client writes in stay roomy
                for r in range(header_row + 1, ws.max_row + 1):  # pale tint marks every cell the client fills in
                    cell = ws[f"{letter}{r}"]
                    cell.fill = PatternFill("solid", fgColor=tint)
                    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1)
            for i, options in lists.items():
                dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True, showErrorMessage=False)
                ws.add_data_validation(dv)
                dv.add(f"{letters[0]}{header_row + 1 + i}")           # the pick list sits on the first answer column
        wb.save(out)
    if check_document.main([str(out), "--allow", "multi-sheet"] if spec.get("sheets") else [str(out)]) != 0:
        raise ProjectError(f"{name}.xlsx 未通过 Luz-Design check_document")
    return out
