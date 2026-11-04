"""Tabs, baseline tables and function cards for the developer documents (references/dev-documents.md, references/tech-baseline.md).

Blocks added here:

* ``baseline``  ``{"type": "baseline", "kind": "stack|frontend|module", "scope": "<layer or category id>", "caption": …, "rows": [{"id", "status", "value", "reason"}]}``
                 a table that puts the baseline item next to what this project does: 项 | 底座规定 | 本项目 | 状态 | 理由
* ``function``  ``{"type": "function", "id": "FN-001", "name", "system", "module", "summary", "frontend", "backend", "database", "tech",
                 "rules": […], "exceptions": […], "tests": […], "code": […], "deviation": […], "inherits": "BF-LOGIN-01", "status": "沿用|调整|新增", "change": …}``
                 one card per function: what the user sees, what the backend does, what the database keeps, how it is built

The page uses top tabs (and sub tabs) so that one document stays one page: ARIA tablist, arrow keys, ``#tab=1.2`` deep links, every
panel visible when printed or when scripts are off. Prototype frames load when their tab is first shown.
"""
from __future__ import annotations

import html
import re
from typing import Any

import baseline as bl

E = html.escape
PLACEHOLDER = bl.PLACEHOLDER
FUNCTION_TEXT = ("frontend", "backend", "database", "tech")
FUNCTION_LABEL = {"frontend": "前端逻辑", "backend": "后端逻辑", "database": "数据库", "tech": "技术方案"}
KIND_SCOPE = {"stack": {l: l for l in bl.STACK_LAYERS}, "frontend": {c: c for c in bl.FRONTEND_CATEGORIES}}


def _inline(text: Any) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", E(str(text)))


# --- validation ---------------------------------------------------------------------------------------------------------


def baseline_block_errors(where: str, b: dict[str, Any], surfaces: Any = None) -> list[str]:
    out: list[str] = []
    kind, scope = b.get("kind"), str(b.get("scope", ""))
    if not str(b.get("caption", "")).strip():
        out.append(f"{where}有没有表题的底座对照表")
    rows = b.get("rows")
    if kind not in {"stack", "frontend", "module"} or not isinstance(rows, list) or not rows:
        return out + [f"{where}的底座对照表要写 kind（stack、frontend、module）和 rows"]
    scopes = [s for s in scope.split(",") if s]
    if kind != "module" and (not scopes or any(s not in KIND_SCOPE[kind] for s in scopes)):
        return out + [f"{where}的底座对照表 scope 不在底座里: {scope}"]
    known = ({i["id"] for s in scopes for i in (bl.stack_items(s) if kind == "stack" else bl.frontend_items(s))} if kind != "module"
             else {m["id"] for m in bl.functions()["modules"]})
    live = known if kind == "module" else {i["id"] for s in scopes for i in (bl.stack_items(s, surfaces) if kind == "stack" else bl.frontend_items(s, surfaces))}
    seen: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            out.append(f"{where}的底座对照表有不是对象的行")
            continue
        iid = str(r.get("id", ""))
        if iid in seen:
            out.append(f"{where}的底座对照表里 {iid} 出现了两次")
        seen.add(iid)
        if iid.startswith("X-"):
            if r.get("status") != "新增":
                out.append(f"{where}的 {iid}：底座没有的项状态只能是 新增")
            out += bl._row_errors(iid, r)
            continue
        if iid not in known:
            out.append(f"{where}的底座对照表里 {iid} 不属于范围 {scope}")
            continue
        if iid not in live:
            out.append(f"{where}的底座对照表里 {iid} 是小程序的项，本项目没有小程序，不写这一项")
            continue
        out += bl._row_errors(iid, r)
    if kind == "module":
        need = {m["id"] for m in bl.functions()["modules"]}
    else:
        need = {i["id"] for s in scopes for i in (bl.stack_items(s, surfaces) if kind == "stack" else bl.frontend_items(s, surfaces)) if i.get("mandatory", True)}
    for iid in sorted(need - seen):
        item = bl.item(iid) or next((m for m in bl.functions()["modules"] if m["id"] == iid), {})
        out.append(f"{where}的底座对照表漏了 {iid}（{item.get('name', '')}）：必有项要说明沿用、调整还是不用")
    return out


def function_block_errors(where: str, b: dict[str, Any]) -> list[str]:
    out: list[str] = []
    fid = str(b.get("id", ""))
    if not re.fullmatch(r"FN-\d{3}", fid):
        out.append(f"{where}的功能卡编号不合格式 FN-001: {fid}")
    for k in ("name", "system", "module", "summary"):
        if len(str(b.get(k, "")).strip()) < 2:
            out.append(f"{where}的功能卡 {fid} 缺 {k}")
    for k in FUNCTION_TEXT:
        text = str(b.get(k, "")).strip()
        if len(text) < 60:
            out.append(f"{where}的功能卡 {fid} 的{FUNCTION_LABEL[k]}太短（至少 60 个字，要写到真实的页面、接口、表和数字）")
    for k, label in (("rules", "业务规则"), ("exceptions", "异常与提示"), ("tests", "测试")):
        v = b.get(k)
        if not isinstance(v, list) or not v or any(len(str(t).strip()) < 6 for t in v):
            out.append(f"{where}的功能卡 {fid} 的{label}至少一条，每条至少 6 个字")
    status, inherits = b.get("status"), str(b.get("inherits", "") or "")
    if status not in ("沿用", "调整", "新增"):
        out.append(f"{where}的功能卡 {fid} 的状态要写 沿用、调整 或 新增")
    elif status == "新增" and inherits:
        out.append(f"{where}的功能卡 {fid} 是新增，不写 inherits")
    elif status != "新增":
        if not inherits or not bl.item(inherits):
            out.append(f"{where}的功能卡 {fid} 的 inherits 要写底座里存在的基础功能编号（现在是“{inherits}”）")
        if status == "调整" and len(str(b.get("change", "")).strip()) < 8:
            out.append(f"{where}的功能卡 {fid} 是调整，要用 change 写清和底座哪里不同、为什么")
    for k in ("rules", "exceptions", "tests", "code", "deviation"):
        v = b.get(k, [])
        if not isinstance(v, list):
            out.append(f"{where}的功能卡 {fid} 的 {k} 要是列表")
    text = " ".join(str(b.get(k, "")) for k in FUNCTION_TEXT + ("summary", "change")) + " ".join(map(str, b.get("rules", []) + b.get("exceptions", []) + b.get("tests", [])))
    if PLACEHOLDER.search(text):
        out.append(f"{where}的功能卡 {fid} 含占位字样")
    return out


# --- rendering ----------------------------------------------------------------------------------------------------------

STATUS_CLASS = {"沿用": "st-keep", "调整": "st-change", "新增": "st-add", "不用": "st-off"}


def _cell_table(table: dict[str, Any]) -> str:
    head = "".join(f"<th>{E(str(c))}</th>" for c in table["columns"])
    body = "".join("<tr>" + "".join(f"<td>{E(str(c))}</td>" for c in row) + "</tr>" for row in table["rows"])
    return f'<table class="mini"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def render_baseline(b: dict[str, Any], table_no: int, surfaces: Any = None) -> str:
    """The comparison table of a baseline block: what the baseline says, what this project does, and why they differ.
    The baseline text is the neutral text plus what it says only for the front ends this project has (``surfaces``)."""
    kind = b["kind"]
    rows_html, extra = [], []
    for r in b["rows"]:
        iid, status = str(r["id"]), r["status"]
        if iid.startswith("X-"):
            name, base_text, detail = str(r.get("name", iid)), "—（底座没有这一项）", ""
            item = None
        elif kind == "module":
            m = next(x for x in bl.functions()["modules"] if x["id"] == iid)
            name = m["name"]
            base_text = f"{m['summary']}（{len(m['functions'])} 个基础功能：{'、'.join(f['name'] for f in m['functions'])}）"
            detail, item = "", None
        else:
            item = bl.item(iid)
            name, base_text, detail = item["name"], bl.text(item, "baseline", surfaces), bl.text(item, "detail", surfaces)
        value = str(r.get("value") or ("同底座" if status == "沿用" else "—"))
        reason = str(r.get("reason") or "—")
        base_cell = _inline(base_text) + (f'<details class="more"><summary>详细规定</summary><p>{_inline(detail)}</p></details>' if detail else "")
        rows_html.append(f'<tr><th scope="row">{E(name)}<span class="bid">{E(iid)}</span></th><td>{base_cell}</td><td>{_inline(value)}</td>'
                         f'<td><span class="st {STATUS_CLASS[status]}">{E(status)}</span></td><td>{_inline(reason)}</td></tr>')
        if kind == "frontend" and item:
            tbl = r.get("table") or item.get("table")
            if tbl:
                extra.append(f'<div class="tcap">{E(name)}：{"本项目取值" if r.get("table") else "底座取值"}</div>' + _cell_table(tbl))
            if item.get("values") and not r.get("table") and status == "沿用":
                extra.append("<ul class=\"vals\">" + "".join(f"<li><strong>{E(str(k))}</strong>　{_inline(v)}</li>" for k, v in item["values"].items()) + "</ul>")
    head = "<tr><th>项</th><th>底座规定</th><th>本项目</th><th>状态</th><th>理由</th></tr>"
    summary = {s: sum(1 for r in b["rows"] if r["status"] == s) for s in bl.STATUSES}
    stats = "　".join(f"{s} {n}" for s, n in summary.items() if n)
    return (f'<div class="tcap">表 {table_no}　{E(b["caption"])}<span class="stats">{E(stats)}</span></div>'
            f'<table class="base"><thead>{head}</thead><tbody>{"".join(rows_html)}</tbody></table>' + "".join(extra))


def render_function(b: dict[str, Any]) -> str:
    inherits = str(b.get("inherits") or "")
    base = bl.item(inherits) if inherits else None
    tag = f'<span class="st {STATUS_CLASS[b["status"]]}">{E(b["status"])}{(" " + inherits) if inherits else ""}</span>'
    cols = "".join(f'<div class="fn-col"><h5>{FUNCTION_LABEL[k]}</h5><p>{_inline(b[k])}</p></div>' for k in FUNCTION_TEXT)
    lists = "".join(f'<div class="fn-list"><h5>{label}</h5><ul>{"".join(f"<li>{_inline(x)}</li>" for x in b[k])}</ul></div>'
                    for k, label in (("rules", "业务规则"), ("exceptions", "异常与提示"), ("tests", "测试")) if b.get(k))
    notes = ""
    if b.get("change"):
        notes += f'<p class="fn-note"><strong>与底座的差异</strong>　{_inline(b["change"])}</p>'
    elif base and b["status"] == "沿用":
        notes += f'<p class="fn-note"><strong>底座做法</strong>　{_inline(base["summary"])}</p>'
    if b.get("deviation"):
        notes += '<p class="fn-note warn"><strong>与功能清单不一致</strong>　' + "；".join(_inline(x) for x in b["deviation"]) + "</p>"
    code = f'<p class="fn-code"><strong>代码落点</strong>　{"　".join(f"<code>{E(str(c))}</code>" for c in b["code"])}</p>' if b.get("code") else ""
    return (f'<article class="fn" id="{E(b["id"])}"><header><span class="fid">{E(b["id"])}</span><h4>{E(b["name"])}</h4>'
            f'<span class="fsys">{E(b["system"])}</span>{tag}</header><p class="fn-sum">{_inline(b["summary"])}</p>'
            f'<div class="fn-grid">{cols}</div><div class="fn-lists">{lists}</div>{notes}{code}</article>')


def tab_nav(labels: list[str], prefix: str, sub: bool = False) -> str:
    cls = "subtabs" if sub else "tabs"
    buttons = "".join(f'<button type="button" role="tab" id="{prefix}-t{i}" aria-controls="{prefix}-p{i}" aria-selected="{"true" if i == 0 else "false"}" tabindex="{0 if i == 0 else -1}">{E(l)}</button>'
                      for i, l in enumerate(labels))
    return f'<div class="{cls}" role="tablist" aria-label="{"子分类" if sub else "文档分类"}">{buttons}</div>'


def tab_panel(prefix: str, i: int, inner: str) -> str:
    return f'<div role="tabpanel" id="{prefix}-p{i}" aria-labelledby="{prefix}-t{i}"{"" if i == 0 else " hidden"} class="tabpanel">{inner}</div>'


TAB_CSS = """<style>
.tabs,.subtabs{display:flex;gap:4px;flex-wrap:wrap}
.tabs{position:sticky;top:0;z-index:5;margin:28px 0 0;padding:0;background:var(--bg,#fff);border-bottom:1px solid var(--line)}
.tabs button{min-height:44px;padding:0 18px;border:0;border-bottom:3px solid transparent;background:none;color:var(--ink);font:inherit;font-size:var(--md-body);cursor:pointer}
.tabs button[aria-selected=true]{border-bottom-color:var(--brand,#2f6b4f);font-weight:600}
.tabs button:hover{background:var(--tint1)}
.subtabs{margin:18px 0 6px}
.subtabs button{min-height:36px;padding:0 14px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font:inherit;font-size:var(--md-table);cursor:pointer}
.subtabs button[aria-selected=true]{background:var(--tint1);border-color:var(--ink);font-weight:600}
.subtabs button:hover{background:var(--tint1)}
.tabs button:focus-visible,.subtabs button:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.tabpanel{padding-top:8px}
.tabpanel[hidden]{display:none}
@media print{.tabs,.subtabs{display:none}.tabpanel[hidden]{display:block!important}}
table.base{width:100%;border-collapse:collapse;margin:6px 0 18px}
table.base th,table.base td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
table.base thead th{background:var(--tint1);font-weight:600;white-space:nowrap}
table.base tbody th{font-weight:600}
table.base td:nth-child(4){white-space:nowrap}
@media(min-width:701px){table.base tbody th{width:14%}table.base td:nth-child(2){width:34%}table.base td:nth-child(3){width:24%}table.base td:nth-child(4){width:7%}}
.bid{display:block;color:var(--ink);font-size:var(--md-aux);font-weight:400;opacity:.75}
.st{display:inline-block;padding:2px 10px;border:1px solid var(--line);border-radius:4px;font-size:var(--md-aux);white-space:nowrap}
.st-keep{background:#fff}.st-change{background:var(--tint1);font-weight:600}.st-add{background:var(--tint1);font-weight:600}.st-off{background:#fff;text-decoration:line-through}
.stats{margin-left:16px;opacity:.8}
details.more{margin-top:6px}details.more summary{cursor:pointer;opacity:.8}details.more p{margin:6px 0 0}
table.mini{border-collapse:collapse;margin:4px 0 14px}table.mini th,table.mini td{padding:6px 12px;border:1px solid var(--line);text-align:left}
article.fn{margin:16px 0;padding:16px 20px;border:1px solid var(--line);border-radius:12px;background:#fff}
article.fn header{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
article.fn h4{margin:0}
.fid{font-weight:600;font-variant-numeric:tabular-nums}
.fsys{padding:2px 10px;border-radius:4px;background:var(--tint1);font-size:var(--md-aux)}
.fn-sum{margin:8px 0 12px}
.fn-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px}
.fn-col h5,.fn-list h5{margin:0 0 4px}
.fn-col p{margin:0}
.fn-lists{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px 24px;margin-top:12px}
.fn-list ul{margin:0}
.fn-note,.fn-code{margin:12px 0 0}
.fn-note.warn{border-left:3px solid var(--ink);padding-left:12px}
.fn-col,.fn-list{min-width:0}
.fn-sum,.fn-col p,.fn-list li,.fn-note,.fn-code,table.base td,table.base th{overflow-wrap:anywhere}
@media(max-width:900px){.fn-grid,.fn-lists{grid-template-columns:minmax(0,1fr)}}
@media(max-width:700px){table.base{display:block;overflow-x:auto}table.base th,table.base td{min-width:9em}table.base tbody th{min-width:7em}table.base td:nth-child(4){min-width:4.5em}article.fn{padding:14px}}
</style>"""

TAB_JS = """<script>
(function(){
  function activate(list,i,focus){
    var tabs=list.querySelectorAll('[role=tab]');
    tabs.forEach(function(t,k){var on=k===i;t.setAttribute('aria-selected',on?'true':'false');t.tabIndex=on?0:-1;var p=document.getElementById(t.getAttribute('aria-controls'));if(p){p.hidden=!on;if(on)p.querySelectorAll('iframe[data-src]').forEach(function(f){f.src=f.dataset.src;f.removeAttribute('data-src');});}});
    if(focus)tabs[i].focus();
    return tabs[i];
  }
  function sync(){var m=/#tab=(\\d+)(?:\\.(\\d+))?/.exec(location.hash);if(!m)return;var top=document.querySelector('.tabs');if(top&&top.querySelectorAll('[role=tab]')[+m[1]]){var t=activate(top,+m[1]);if(m[2]!==undefined){var p=document.getElementById(t.getAttribute('aria-controls')),s=p&&p.querySelector(':scope>.subtabs');if(s)activate(s,+m[2]);}}}
  document.addEventListener('click',function(e){var t=e.target.closest('[role=tab]');if(!t)return;var list=t.parentElement,tabs=[].slice.call(list.querySelectorAll('[role=tab]')),i=tabs.indexOf(t);activate(list,i);
    var top=document.querySelector('.tabs'),h;if(list===top)h='#tab='+i;else{var pn=list.closest('.tabpanel'),ti=pn?[].slice.call(top.querySelectorAll('[role=tab]')).findIndex(function(x){return x.getAttribute('aria-controls')===pn.id;}):0;h='#tab='+ti+'.'+i;}
    try{history.replaceState(null,'',h);}catch(_){}});
  document.addEventListener('keydown',function(e){var t=e.target.closest&&e.target.closest('[role=tab]');if(!t)return;var list=t.parentElement,tabs=[].slice.call(list.querySelectorAll('[role=tab]')),i=tabs.indexOf(t),n=null;
    if(e.key==='ArrowRight')n=(i+1)%tabs.length;else if(e.key==='ArrowLeft')n=(i-1+tabs.length)%tabs.length;else if(e.key==='Home')n=0;else if(e.key==='End')n=tabs.length-1;
    if(n!==null){e.preventDefault();activate(list,n,true);}});
  window.addEventListener('hashchange',sync);
  window.addEventListener('beforeprint',function(){document.querySelectorAll('iframe[data-src]').forEach(function(f){f.src=f.dataset.src;f.removeAttribute('data-src');});});
  document.querySelectorAll('.tabpanel:not([hidden]) iframe[data-src]').forEach(function(f){f.src=f.dataset.src;f.removeAttribute('data-src');});
  sync();
})();
</script>"""
