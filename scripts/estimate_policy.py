"""预算、人日与报价政策（用户 2026-11-05）：默认只给功能清单，不写人日、不写预算和报价。

两个互相独立的开关写在状态根的 ``config/documents.json`` 的 ``estimate`` 段：

* ``workdays``：功能清单加“工时（人天）”列；features.json 每个在范围内的功能要有 ``hours``（0.5 的倍数）和 ``hours_basis``（估算依据）。
* ``quote``：功能清单加“报价清单”工作表；单价、折扣、金额这些数字只来自人工提供的报价单（``data/client/quote.json``，带提供人和出处）。``quote`` 打开必须同时打开 ``workdays``。

打开任何一个开关都要有证据：``requested_by``（谁要求的，具体的人）、``requested_at``（何时）、``request_note``（原话）。缺一项，或要求的人是智能体、技能、工具、
系统、示例这类，开关等于没打开，并且校验报错。旧的 ``amounts`` 开关没有证据：``amounts: false`` 等价于两个开关都关，``amounts: true`` 同样按关闭处理并给提醒。

本模块只放规则（读开关、校验证据、校验报价单与人日），不碰客户文件；渲染在 client_render.py，命令在 client_flow.py。技能里不内置任何默认单价或示例金额：
报价单的每个数字来自 ``project.py client <项目> quote`` 记录下的、用户或客户提供的原话或文件。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# 词表的单一来源是 Luz-Design/scripts/estimate_terms.py；本目录的 estimate_terms.py 是它的整文件拷贝（Design 的 sync 脚本写，不手改；摘要必须与母本一致，test_estimate 比对）。
import estimate_terms as et
from project_paths import locate

SWITCHES = ("workdays", "quote")
SWITCH_EVIDENCE = ("requested_by", "requested_at", "request_note")
QUOTE_EVIDENCE = ("provided_by", "provided_at", "request_note", "evidence")
EVIDENCE_LABELS = {"requested_by": "谁要求的", "requested_at": "何时要求的", "request_note": "要求的原话",
                   "provided_by": "谁提供的数字", "provided_at": "何时提供的", "evidence": "提供数字的原话或来源文件"}


def not_evidence(text: object) -> bool:
    """Not words or a source a person gave: empty or only placeholder words (``et.is_not_evidence``), or the text itself says the figure is a 暂估, 自拟, 默认值 or 占位 (``et.says_made_up``,
    wherever the word stands, even with other words after it). Both come from the shared vocabulary."""
    value = str(text or "").strip()
    return et.is_not_evidence(value) or et.says_made_up(value)


UPLOADS_PATH = re.compile(r"^(?:raw/)?uploads/\S.*$")
HOURS_STEP = 0.5


def not_a_person(text: object) -> bool:
    """True when ``text`` (a requested_by, a provided_by) is empty or names the agent, a skill, a tool, the system, an example or an estimate instead of someone."""
    return et.not_a_person(str(text or "").strip())


def default_estimate() -> dict[str, Any]:
    return {"workdays": False, "quote": False, "requested_by": "", "requested_at": "", "request_note": ""}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def is_date(value: Any) -> bool:
    text = _text(value)
    try:
        date.fromisoformat(text[:10])
    except ValueError:
        return False
    return len(text) >= 10 and re.match(r"\d{4}-\d{2}-\d{2}", text) is not None


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def documents_config(root: Path) -> dict[str, Any]:
    value = read_json(Path(root) / "config" / "documents.json", {})
    return value if isinstance(value, dict) else {}


# --- the switches ---------------------------------------------------------------------------------------------------

def evidence_errors(request: dict[str, Any]) -> list[str]:
    """What is wrong with the evidence of an opened switch: a missing item, a requester that is not a person, a date that is not a date, words too short to be words."""
    missing = [k for k in SWITCH_EVIDENCE if not _text(request.get(k))]
    if missing:
        return ["estimate 开关已打开但缺 " + "、".join(f"{k}（{EVIDENCE_LABELS[k]}）" for k in missing) + "：打开人日或报价必须有谁、何时、用什么原话要求的证据，没有证据的开关打不开"]
    errors: list[str] = []
    if not_a_person(request["requested_by"]):
        errors.append(f"estimate.requested_by“{request['requested_by']}”不是具体的人：写要求的用户或客户的姓名或角色，不能是智能体、技能、工具、系统、示例")
    if not is_date(request["requested_at"]):
        errors.append(f"estimate.requested_at“{request['requested_at']}”不是日期（写 YYYY-MM-DD）")
    note = _text(request["request_note"])
    if len(note) < et.MIN_NOTE or not_evidence(note):
        errors.append(f"estimate.request_note 要写要求的原话（不是示例、默认、暂估，不少于 {et.MIN_NOTE} 个字）")
    return errors


def switch_errors(estimate: dict[str, Any]) -> list[str]:
    """The ``estimate`` object must be well formed: booleans, quote only with workdays, evidence for whatever is on."""
    errors: list[str] = []
    for key in SWITCHES:
        if key in estimate and not isinstance(estimate[key], bool):
            errors.append(f"estimate.{key} 须是 true 或 false")
    workdays, quote = estimate.get("workdays") is True, estimate.get("quote") is True
    if quote and not workdays:
        errors.append("estimate.quote 为 true 时 estimate.workdays 必须同时为 true（报价基于人日）")
    if workdays or quote:
        errors += evidence_errors(estimate)
    return errors


def stored_estimate(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The ``estimate`` object of a documents config, filled with the defaults, and the remarks about the old ``amounts`` switch (which has no evidence and counts as both off)."""
    notes: list[str] = []
    raw = config.get("estimate")
    estimate = {**default_estimate(), **{k: v for k, v in raw.items() if k in default_estimate()}} if isinstance(raw, dict) else default_estimate()
    if raw is not None and not isinstance(raw, dict):
        notes.append("config/documents.json 的 estimate 须是对象")
    if not isinstance(raw, dict):
        if config.get("amounts") is True:
            notes.append("config/documents.json 里是旧的 amounts: true：它没有谁要求、何时、什么原话的证据，按人日与报价都关闭处理。"
                         "确实要写人日或报价，请用户明确要求后用 project.py client <项目> estimate 打开")
        elif config.get("amounts") is False:
            notes.append("config/documents.json 里是旧的 amounts: false，等价于 estimate 两个开关都关；project.py migrate 会补上 estimate 默认值")
        else:
            notes.append("config/documents.json 没有 estimate 段，按人日与报价都关闭处理；project.py migrate 会补上默认值")
    return estimate, notes


def normalized_section(config: dict[str, Any]) -> dict[str, Any]:
    """What a document built from the estimate depends on: the switches that are effectively on and the evidence they rest on. Two switches off give the same section
    whatever else is written (a missing section, the defaults, the last request's leftovers), so adding the defaults to an old project does not make its files stale."""
    estimate, _ = stored_estimate(config)
    if switch_errors(estimate):
        return {"workdays": False, "quote": False, "invalid": True}
    workdays, quote = estimate["workdays"] is True, estimate["quote"] is True
    if not (workdays or quote):
        return {"workdays": False, "quote": False}
    return {"workdays": workdays, "quote": quote, **{k: _text(estimate[k]) for k in SWITCH_EVIDENCE}}


# --- the quote -------------------------------------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quote_errors(quote: Any, root: Path | None = None) -> list[str]:
    """quote.json when the quote switch is on: a unit price above zero that a person gave, with who, when, the words that asked for it and the words or file that carry the number."""
    if not isinstance(quote, dict):
        return ["quote.json 须是对象"]
    errors: list[str] = []
    price = quote.get("unit_price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        errors.append("quote.json 需含大于 0 的 unit_price（元每人天），且只能来自人工提供的报价单")
    missing = [k for k in QUOTE_EVIDENCE if not _text(quote.get(k))]
    if missing:
        errors.append("quote.json 缺人工证据字段 " + "、".join(f"{k}（{EVIDENCE_LABELS[k]}）" for k in missing) + "：缺它们不能渲染，也不能批准；补人工证据请用 project.py client <项目> quote")
        return errors
    if not_a_person(quote["provided_by"]):
        errors.append(f"quote.json 的 provided_by“{quote['provided_by']}”不是具体的人：报价只能由人工提供，不能是智能体、技能、工具、系统、示例或暂估")
    if not is_date(quote["provided_at"]):
        errors.append(f"quote.json 的 provided_at“{quote['provided_at']}”不是日期（写 YYYY-MM-DD）")
    evidence = _text(quote["evidence"])
    # A request may be as short as a person's few words (et.MIN_NOTE); the evidence of a number must name a concrete source (a quotation, a file path): at least et.EVIDENCE_MIN characters,
    # the same length the workbook description needs to carry it (et.read_evidence).
    if len(evidence) < et.EVIDENCE_MIN or not_evidence(evidence):
        errors.append(f"quote.json 的 evidence 太短（少于 {et.EVIDENCE_MIN} 个字）或看起来是示例、暂估、默认值：写提供数字的原话或具体的来源文件路径（如 uploads/客户报价单.xlsx）")
    request_words = _text(quote["request_note"])
    if len(request_words) < et.MIN_NOTE or not_evidence(request_words):
        errors.append(f"quote.json 的 request_note 看起来是示例、暂估或默认值，或少于 {et.MIN_NOTE} 个字：写要求报价的原话")
    source = _text(quote.get("evidence_file")) or (evidence if UPLOADS_PATH.match(evidence) else "")
    if source and root is not None:
        path = locate(Path(root), source)
        if not path.is_file():
            errors.append(f"quote.json 的来源文件不存在: {source}（报价单放在状态根的 uploads/，用 project.py client <项目> quote --from-file 记录）")
        elif _text(quote.get("evidence_sha256")) and _text(quote["evidence_sha256"]) != sha256_of(path):
            errors.append(f"来源文件 {source} 的内容与记录报价时不一致：报价单被改过，请让提供人确认后重新记录")
    return errors


def quote_wait_message(project: str = "<项目>") -> str:
    return ("等待人工报价：请提供人天单价（元每人天）或客户给的报价单文件（xlsx、json、csv），并说明是谁提供的、出处是什么。agent 不得自拟、暂估或套用示例数字；"
            f"收到后运行 project.py client {project} quote --unit-price <数> --provided-by <提供的人> --evidence \"<原话>\"，或 --from-file <报价单>")


# --- the hours -------------------------------------------------------------------------------------------------------

def hours_errors(features: dict[str, Any]) -> list[str]:
    """With workdays on every function in scope has ``hours`` (above zero, in steps of 0.5) and the ``hours_basis`` the estimate rests on (more than a number)."""
    bad_hours: list[str] = []
    bad_basis: list[str] = []
    for f in features.get("features", []):
        if f.get("status", "in-scope") != "in-scope":
            continue
        hours = f.get("hours")
        if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0 or (hours / HOURS_STEP) % 1:
            bad_hours.append(str(f.get("id")))
        basis = f.get("hours_basis")
        if not isinstance(basis, str) or not basis.strip() or re.fullmatch(r"[\d\s.,，。人天日hH工时]*", basis.strip()) or re.search(r"待补充|TODO|TBD|占位|xxx", basis, re.I):
            bad_basis.append(str(f.get("id")))
    out: list[str] = []
    if bad_hours:
        out.append("已开启 estimate.workdays，这些功能的 hours 缺失或不是 0.5 的倍数（features.json，人天，最小 0.5）: " + "、".join(bad_hours[:8]) + ("…" if len(bad_hours) > 8 else ""))
    if bad_basis:
        out.append("已开启 estimate.workdays，这些功能没有 hours_basis（估算依据：功能复杂度、涉及的页面与接口数、参照的同类功能，不能只有数字）: " + "、".join(bad_basis[:8]) + ("…" if len(bad_basis) > 8 else ""))
    return out


def workday_issues(text: str, allow: tuple[str, ...] = ()) -> list[str]:
    """The person-day words (``estimate_terms.WORKDAY_WORDS``: 工时, 人天, 人日, 人月, 工日) in a text a client reads. Only a function list that was asked to carry them may. A word that
    is a business concept of the system itself (a 工时统计 function) is released by ``allow_terms`` (the data files list it, as Luz-System's features_check asks)."""
    for term in sorted((a for a in allow if a), key=len, reverse=True):
        text = text.replace(term, " ")                                         # the business words are out of the text before it is read
    return sorted({m.group(0) for m in et.WORKDAY.finditer(text)})


def project_allowed_terms(root: Path) -> tuple[str, ...]:
    """The words the project declared as business concepts: ``allow_terms`` of modules and functions in features.json and at the top of the other client data files."""
    found: list[str] = []
    for name in ("features.json", "requirements.json", "proposal.json", "architecture.json", "intake-extra.json", "manual.json"):
        data = read_json(Path(root) / "data" / "client" / name, None)
        if isinstance(data, dict):
            found += [str(w) for w in data.get("allow_terms") or [] if isinstance(w, str)]
            for item in [*(data.get("modules") or []), *(data.get("features") or [])]:
                if isinstance(item, dict):
                    found += [str(w) for w in item.get("allow_terms") or [] if isinstance(w, str)]
    return tuple(dict.fromkeys(found))


# --- the state ---------------------------------------------------------------------------------------------------------

@dataclass
class State:
    """What the project's switches say now. ``workdays`` and ``quote`` are the *effective* switches: on in the config, with valid evidence (and, for the quote, with workdays)."""
    workdays: bool = False
    quote: bool = False
    stored: dict[str, Any] = field(default_factory=default_estimate)
    errors: list[str] = field(default_factory=list)            # the switches are malformed or lack evidence: the project does not pass ``check``
    notes: list[str] = field(default_factory=list)             # remarks (old switch, no section yet)
    quote_data: dict[str, Any] | None = None
    quote_errors: list[str] = field(default_factory=list)      # quote on and quote.json present but not acceptable
    quote_missing: bool = False                                # quote on and no quote.json: the project waits for a person's quote

    @property
    def waiting_for_quote(self) -> bool:
        return self.quote and (self.quote_missing or bool(self.quote_errors))

    @property
    def request(self) -> dict[str, str]:
        return {k: _text(self.stored.get(k)) for k in SWITCH_EVIDENCE}

    def render_block(self) -> dict[str, Any] | None:
        """The ``estimate`` block of a Luz-Design spreadsheet spec (make_xlsx writes the evidence into the workbook); None when both switches are off."""
        if not self.workdays:
            return None
        block: dict[str, Any] = {"workdays": True, "quote": self.quote, "requested_by": self.request["requested_by"], "request_note": self.request["request_note"]}
        if self.quote and self.quote_data:
            block.update({"provided_by": _text(self.quote_data.get("provided_by")), "evidence": _text(self.quote_data.get("evidence"))})
        return block


def read_state(root: Path) -> State:
    root = Path(root)
    config = documents_config(root)
    stored, notes = stored_estimate(config)
    errors = switch_errors(stored)
    workdays = stored["workdays"] is True and not errors
    quote = stored["quote"] is True and workdays and not errors
    state = State(workdays=workdays, quote=quote, stored=stored, errors=errors, notes=notes)
    if quote:
        data = read_json(root / "data" / "client" / "quote.json", None)
        state.quote_data = data if isinstance(data, dict) else None
        if data is None:
            state.quote_missing = True
        else:
            state.quote_errors = quote_errors(data, root)
    return state


def user_todos(root: Path, project: str = "<项目>") -> list[str]:
    """What only a person can do for the estimate, in one sentence each: the first is the quote nobody has given yet."""
    state = read_state(root)
    todos: list[str] = []
    if state.errors:
        todos.append("估算开关配置有误，请用户确认谁在何时、用什么原话要求了人日或报价（project.py client " + project + " estimate …）：" + "；".join(state.errors[:2]))
    if state.waiting_for_quote:
        todos.append(quote_wait_message(project) + ("。现有 quote.json 不合格：" + "；".join(state.quote_errors[:2]) if state.quote_errors else ""))
    return todos
