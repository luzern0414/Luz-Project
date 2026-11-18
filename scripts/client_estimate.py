"""The two commands of the 预算、人日与报价政策: ``client <项目> estimate`` (the switches) and ``client <项目> quote`` (the quote a person gave).

The rules are in estimate_policy.py; the checks of what the client reads are ``client_flow.estimate_errors``. Here is what changes state: the ``estimate`` section of the state
root's ``config/documents.json`` and ``data/client/quote.json``. Neither command invents a number or a reason: the switch needs who asked, when and in what words; the quote
needs who gave it and the words or the file that carry it. A switch or a quote that changes after the proposal files were approved is a change: it is logged in the change ledger
and reopens the proposal, so every file that depends on it is looked at again.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

import client_data as cd
import client_flow as cf
import estimate_policy as ep
from project_core import UPLOADS_DIR, ProjectError, _stage_record, _write_json, load_project, locate, now_iso, sha256_file, state_name

LABELS = {(False, False): "不写人日与报价", (True, False): "写人日、不写报价", (True, True): "写人日与报价"}
# The same three states in the words of a ledger entry the client may read: none of the words the policy keeps out of a client's text (人天、工时、报价、金额…).
LEDGER_LABELS = {(False, False): "只列功能", (True, False): "列功能和工作量", (True, True): "列功能、工作量和价格"}


def status(root: Path) -> dict[str, Any]:
    state = cd.estimate_state(root)
    quote = state.quote_data if state.quote and state.quote_data and not state.quote_errors else None
    return {"现在": LABELS[(state.workdays, state.quote)], "workdays": state.workdays, "quote": state.quote, "request": state.request if (state.workdays or state.quote) else {},
            "waiting_for_quote": state.waiting_for_quote, "errors": state.errors, "notes": state.notes, "quote_errors": state.quote_errors,
            "quote_from": {k: quote.get(k) for k in ("provided_by", "provided_at", "evidence")} if quote else None, "user_todos": ep.user_todos(root)}


def _register_change(root: Path, *, title: str, detail: str, requester: str, note: str, source: str) -> str | None:
    """A switch or the quote changed after the proposal files were approved: that is a change. Log it (the ledger decides who sees it: the client's own scope changes are
    visible, an internal decision is not), confirm it, and let it reopen the stage so the approvals of its files are void and each file is looked at again. None when nothing
    of the proposal had been approved yet (the files are simply regenerated)."""
    manifest = load_project(root)
    record = _stage_record(manifest, "proposal")
    if not (record.get("status") in {"approved", "completed"} or record.get("approval_id") or cf._approved_files(root, "proposal")):
        return None
    entry = cf.add_change(root, type="修改", category="范围", title=title, detail=detail, source=source, requester=requester or "用户", affects=["proposal"], status="已确认",
                          confirmed_by=requester or "用户", note=note)
    return str(entry["id"])


def set_estimate(root: Path, *, workdays: bool | None = None, quote: bool | None = None, requested_by: str = "", requested_at: str = "", request_note: str = "",
                 note: str = "", source: str = "内部") -> dict[str, Any]:
    """Turn the person-day column and the quote of the function list on or off (``estimate`` in config/documents.json). Both are off by default.

    Turning one on needs who asked, when, and in what words (the three items of evidence): no evidence, no switch. ``quote`` needs ``workdays``. Turning one off needs ``note``
    (why). With the quote switched on and no quote that a person gave, the command succeeds and the project waits for a human quote. When the proposal files were already
    approved, a change is logged and reopens them."""
    if workdays is None and quote is None:
        raise ProjectError("estimate 需要 --workdays on|off 或 --quote on|off（至少一个）")
    config = cd.documents_config(root)
    before = cd.estimate_state(root)
    new_w = before.workdays if workdays is None else workdays
    new_q = before.quote if quote is None else quote
    if new_q and not new_w:
        raise ProjectError("报价基于人日：quote on 需要 workdays 同时 on" + ("；要关掉人日，同时加 --quote off" if before.quote and workdays is False else ""))
    turning_on = (new_w and not before.workdays) or (new_q and not before.quote)
    turning_off = (before.workdays and not new_w) or (before.quote and not new_q)
    given = {"requested_by": requested_by.strip(), "requested_at": requested_at.strip(), "request_note": request_note.strip()}
    if turning_on or (new_w and any(given.values())):
        problems = ep.evidence_errors(given)
        if problems:
            raise ProjectError("打开人日或报价必须带要求的证据（--requested-by 谁要求的，具体的人；--requested-at 何时，YYYY-MM-DD；--request-note 要求的原话）: " + "；".join(problems))
        request = given
    else:
        request = before.request
    if turning_off and not note.strip():
        raise ProjectError("关闭需要 --note 写明为什么不再写人日或报价")
    if not turning_on and not turning_off and request == before.request:
        raise ProjectError("开关没有变化：现在是" + LABELS[(before.workdays, before.quote)])
    if not (new_w or new_q):
        request = {k: "" for k in ep.SWITCH_EVIDENCE}                           # nothing is on: the last request is history, not evidence
    history = config.get("estimate_history") if isinstance(config.get("estimate_history"), list) else []
    history = history + [{"at": now_iso(), "workdays": new_w, "quote": new_q, "requested_by": given["requested_by"] or before.request["requested_by"],
                          "request_note": given["request_note"] or before.request["request_note"], "note": note.strip()}]
    config.pop("amounts", None)                                                  # the old switch had no evidence and never meant anything but off
    config["estimate"] = {"workdays": new_w, "quote": new_q, **request}
    config["estimate_history"] = history[-20:]
    _write_json(root / "config" / "documents.json", config)
    after = cd.estimate_state(root)
    old, new = LABELS[(before.workdays, before.quote)], LABELS[(after.workdays, after.quote)]
    who = given["requested_by"] or before.request["requested_by"] or "用户"
    when = given["requested_at"] or before.request["requested_at"] or cf.today_cn()
    change = _register_change(root, title="功能清单的工作量与价格写法调整", note=f"{note.strip()} {given['request_note']}".strip() or "估算开关变更", requester=who, source=source,
                              detail=f"按{who}的要求（{when}），功能清单的写法由「{LEDGER_LABELS[(before.workdays, before.quote)]}」改为「{LEDGER_LABELS[(after.workdays, after.quote)]}」；功能清单随之重新生成并重新审批。")
    result: dict[str, Any] = {"estimate": {"workdays": after.workdays, "quote": after.quote, **after.request}, "was": old, "now": new, "change": change,
                              "waiting_for_quote": after.waiting_for_quote, "message": f"功能清单现在{new}。" + ("功能清单的批准已因变更作废，重新生成后逐个重审。" if change else "")}
    if after.workdays:
        result["next"] = "features.json 每个在范围内的功能要有 hours（0.5 的倍数）和 hours_basis（估算依据）；人日是拟定值，用户批准功能清单之前一律标“拟定”"
    if after.waiting_for_quote:
        result["todo"] = ep.quote_wait_message()
    return result


# --- the quote -----------------------------------------------------------------------------------------------------------

PRICE_LABEL = re.compile(r"单价|unit[_ ]?price|元\s*[/每]\s*人[天日]", re.I)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.fullmatch(r"[¥￥\s]*(\d[\d,]*(?:\.\d+)?)\s*(?:元(?:\s*[/每]\s*人[天日])?)?", value.strip())
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def read_unit_price(path: Path) -> float:
    """The person-day unit price written in a quote sheet a person supplied (xlsx, json or csv): the number next to (or under) the cell that says 单价 or unit_price.
    No such cell, or several different numbers, is an error: the person is asked, the code never picks one."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ProjectError(f"{path.name} 里没有写明单价的对象（unit_price）")
        grid: list[list[Any]] = [[k, v] for k, v in data.items()]
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            grid = [list(row) for row in csv.reader(handle)]
    elif suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        grid = [list(row) for ws in load_workbook(path, data_only=True).worksheets for row in ws.iter_rows(values_only=True)]
    else:
        raise ProjectError(f"报价单支持 xlsx、json、csv，{path.name} 不是；也可以直接 --unit-price 并写明出处")
    found: list[float] = []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if isinstance(cell, str) and PRICE_LABEL.search(cell):
                value = next((n for n in (_number(x) for x in row[c + 1:]) if n is not None), None)
                if value is None:
                    value = next((n for n in (_number(grid[k][c]) for k in range(r + 1, len(grid)) if c < len(grid[k])) if n is not None), None)
                if value is not None:
                    found.append(value)
    distinct = sorted(set(found))
    if not distinct:
        raise ProjectError(f"{path.name} 里找不到人天单价（写着“单价”或 unit_price 的格子旁边的数）：请让提供报价的人指出是哪一格，再用 --unit-price 和 --evidence 记录")
    if len(distinct) > 1:
        raise ProjectError(f"{path.name} 里有几个不同的单价 {distinct}：请让提供报价的人确认人天单价是哪一个，再用 --unit-price 和 --evidence 记录")
    return distinct[0]


def write_quote(root: Path, *, unit_price: float | None = None, from_file: Path | str | None = None, provided_by: str = "", evidence: str = "", provided_at: str = "",
                request_note: str = "", note: str = "") -> dict[str, Any]:
    """Record the quote a person gave (data/client/quote.json). The number is the person's: a unit price typed with the words that carry it, or read from the quote sheet the
    person sent (the sheet is kept in uploads/ and its hash recorded). Refused: no provider, or a provider that is the agent, a skill, a tool, an example or an estimate; no
    evidence or evidence that is a placeholder; a price at or below zero. An agent never invents the number: when nobody gave one, nothing is recorded."""
    if (unit_price is None) == (from_file is None):
        raise ProjectError("quote 要么 --unit-price <数>（配 --evidence 写明提供数字的原话），要么 --from-file <人工提供的报价单>（xlsx、json、csv）；数字必须是用户或客户提供的，agent 不得自拟")
    who = provided_by.strip()
    if not who:
        raise ProjectError("quote 需要 --provided-by（提供这个数字的人：姓名或角色）；agent 不得自拟数字")
    if ep.not_a_person(who):
        raise ProjectError(f"--provided-by“{who}”不是具体的人：报价只能由人工提供，不能是智能体、技能、工具、系统、示例或暂估")
    state = cd.estimate_state(root)
    kept = digest = ""
    if from_file is not None:
        source = Path(from_file).expanduser()
        if not source.is_file():
            raise ProjectError(f"找不到报价单: {source}")
        unit_price = read_unit_price(source)
        uploads = locate(root, state_name(root, UPLOADS_DIR))
        uploads.mkdir(parents=True, exist_ok=True)
        target = uploads / source.name
        if source.resolve() != target.resolve():
            if target.exists() and sha256_file(target) != sha256_file(source):
                target = uploads / f"{source.stem}-{sha256_file(source)[:8]}{source.suffix}"
            shutil.copyfile(source, target)
        kept = f"{state_name(root, UPLOADS_DIR)}/{target.name}"
        digest = sha256_file(target)
        evidence = evidence.strip() or kept
    elif not evidence.strip():
        raise ProjectError("quote --unit-price 需要 --evidence：写明提供这个数字的原话或来源（谁在哪里说的）；没有出处就不能记")
    when = provided_at.strip() or cf.today_cn()
    asked = request_note.strip() or state.request["request_note"]
    quote = {"unit_price": unit_price, "unit": "元每人天", "provided_by": who, "provided_at": when, "request_note": asked, "evidence": evidence.strip(),
             **({"evidence_file": kept, "evidence_sha256": digest} if kept else {})}
    problems = ep.quote_errors(quote, root)
    if problems:
        raise ProjectError("报价单不能记录: " + "；".join(problems) + ("（--request-note 写要求报价的原话，或先 project.py client <项目> estimate 记下要求的原话）" if not asked else ""))
    previous = cd.load_quote(root)
    cd.save(root, quote, "client", "quote.json")
    result: dict[str, Any] = {"path": str(cd.data_path(root, "client", "quote.json")), "quote": quote}
    if not state.quote:
        result["warning"] = "estimate.quote 没有开启：这份报价单不会用于任何客户文件（用户明确要求报价后，用 project.py client <项目> estimate --quote on … 打开）"
    elif previous is not None and previous != quote:
        result["change"] = _register_change(root, title="功能清单的价格依据更新", note=note.strip() or f"{who} 于 {when} 重新提供报价", requester=who, source="内部",
                                            detail=f"价格依据由{who}于{when}重新提供；功能清单随之重新生成并重新审批。")
    return result
