"""The words of the 预算、人日与报价政策 as data, one copy for every script of the Luz skills that has to recognise them.

Policy (user, 2026-11-05): a client file lists functions only. Workdays, unit prices, amounts, totals and a quotation exist only when the user or client asked for
them in words, and a price, a discount or an amount is only ever a number a person supplied (a quotation, with who gave it and where it is written down); an agent
never fills one in, never as an example, never as an estimate.

What lives here, and nowhere else:

* ``NOT_A_PERSON_*``      who cannot be ``provided_by`` of a price: the agent, a skill, a tool, an example, an estimate. ``not_a_person(text)``.
* ``WORKDAY_WORDS``       header or label words of a workday column or row.
* ``MONEY_WORDS``         words that are money wherever they stand (金额, 单价, 总价, 报价, 预算, 折扣).
* ``TOTAL_WORDS``         合计, 小计, 总计: money only when the figures beside them are money, not a sum of amperes, devices or metres.
* ``CURRENCY_UNITS``      what makes a figure money; ``OTHER_UNITS`` what makes a total something else (a current, a power, a count, a length).
* ``EVIDENCE_PREFIX``     how a workbook carries the evidence of its quote switch (``write_evidence`` / ``read_evidence``), so a checker that only sees the file can ask for it.

Luz-System (features_check, hw_export), Luz-Writing (09-text_check) and Luz-Project may import this module or copy it verbatim; a copy keeps ``TERMS`` identical
(``terms_digest()`` of the copies must equal this one, tests in each skill compare them).
"""
from __future__ import annotations

import hashlib
import json
import re

# ----------------------------------------------------------------------------------------------------------------------------------------------
# provided_by / requested_by is a person: a name or a role of someone who gave the figures or asked for them. These are not.
#
# Read as a person's identifier, not as prose: the value is stripped of blanks and punctuation, cut at separators (blank, 、 ， , ; ； / ( ) （ ） - and the like) into
# tokens, and it is "not a person" when the whole value or one token EQUALS a word below (case-insensitive, the same for ASCII and CJK), or equals a word followed by a
# generated-by suffix ("系统生成", "模板填写", "示例代填"), or when it contains one of the few unambiguous long words (智能体, claude, assistant …). A short word that is
# also part of a real name or role (系统管理员, 空调公司张工, 无锡客户采购, 程序员王工, Na) is never matched inside a longer token.
# ----------------------------------------------------------------------------------------------------------------------------------------------
NOT_A_PERSON_ASCII = ["agent", "claude", "gpt", "chatgpt", "llm", "skill", "luz", "tool", "bot", "model", "assistant", "codex", "copilot", "gemini", "system", "auto",
                      "automatic", "default", "example", "sample", "demo", "placeholder", "estimate", "estimated", "assumed", "todo", "tbd", "n/a", "none", "unknown", "null",
                      "template"]
NOT_A_PERSON_CJK = ["智能体", "助手", "系统", "技能", "工具", "模型", "机器人", "自动", "脚本", "程序", "示例", "样例", "范例", "默认", "暂估", "估算", "估价", "估计", "拟定",
                    "假设", "待定", "待补", "占位", "未知", "无", "空", "模板", "自拟"]
NOT_A_PERSON_WHOLE_ONLY = ["ai"]          # a whole value only ("AI"); as a token it can be a given name (Ai): "AI 助手" is caught by 助手. "Na" is a name and is not listed at all
NOT_A_PERSON_SUBSTRING_ASCII = ["agent", "assistant", "chatgpt", "claude", "codex", "copilot", "gemini"]       # matched as words inside a longer value ("Claude（自动生成）", "assistant-generated")
NOT_A_PERSON_SUBSTRING_CJK = ["智能体", "机器人", "大模型", "语言模型", "占位符", "示例数据", "样例数据", "暂估值", "默认值"]
GENERATED_SUFFIXES = ["生成", "自动", "拟定", "填写", "代填", "默认"]
NOT_EVIDENCE = ["暂估", "暂估值", "示例", "示例数据", "样例数据", "默认值", "假设", "估算", "拟定", "待定", "占位", "占位符", "未知", "无", "空", "样例", "默认", "模板", "placeholder", "example", "sample", "default",
                "tbd", "todo", "n/a", "none", "unknown", "null", "estimate", "estimated", "assumed"]          # an evidence made of these words alone is no evidence
SEPARATORS = r"[\s、，,;；/／\|｜()（）\[\]【】{}<>《》:：·+&＆\-—–_.。!！?？\"“”'‘’]+"

# ----------------------------------------------------------------------------------------------------------------------------------------------
# Words in a spreadsheet.
# ----------------------------------------------------------------------------------------------------------------------------------------------
WORKDAY_WORDS = ["工时", "人天", "人日", "人月", "工日"]
MONEY_WORDS = ["金额", "单价", "总价", "报价", "预算", "折扣", "价款", "费用合计", "造价"]
TOTAL_WORDS = ["合计", "小计", "总计"]
CURRENCY_UNITS = ["元", "万元", "¥", "￥", "RMB", "CNY", "人民币", "元/人天", "元每人天", "元/人日"]
OTHER_UNITS = ["A", "mA", "V", "kV", "W", "kW", "VA", "kVA", "kWh", "Hz", "Ω", "dB", "台", "个", "套", "只", "块", "件", "路", "口", "米", "m", "mm", "cm", "km", "㎡", "m²",
               "kg", "g", "t", "L", "个月", "天", "小时", "分钟", "秒", "%", "TB", "GB", "MB"]

# What an evidence may not say about itself: a figure that the text itself calls an estimate, a draft by the agent, a default or a placeholder. Unlike NOT_EVIDENCE (the
# whole text is only such words), these are looked for anywhere in the text, so "暂估，先按这个算" and "按默认值 800" are caught, "客户邮件确认单价（见附件）" is not.
MADE_UP_CJK = ["暂估", "自拟", "默认值", "占位", "示例数据", "样例数据"]
MADE_UP_ASCII = ["placeholder", "assumed", "estimated", "tbd"]
MIN_NOTE = 4              # characters: the shortest words of a person who asked for an estimate or a quote that still count as their words (Luz-Project documents.json request_note)
EVIDENCE_MIN = 6          # characters: the shortest evidence text a workbook description carries after EVIDENCE_PREFIX (read_evidence)
EVIDENCE_PREFIX = "报价依据："        # in the workbook's description; the text after it is "要求人：…；原话：…；提供人：…；来源：…"

# Customer documents are self-contained. Quoted titles of laws and other external
# sources remain valid citations.
INTERNAL_DOCUMENT_REFERENCES = re.compile(
    r"《(?:需求说明书|方案说明书|系统架构图册?|功能清单|报价清单|业务逻辑确认表|需求变更台账|使用说明书?|验收清单|客户信息收集表|业务规则收集表)》"
    r"|配套文件|见功能清单|见系统架构图|见业务逻辑确认表"
)

TERMS = {
    "not_a_person_ascii": NOT_A_PERSON_ASCII, "not_a_person_cjk": NOT_A_PERSON_CJK, "not_a_person_whole_only": NOT_A_PERSON_WHOLE_ONLY,
    "not_a_person_substring_ascii": NOT_A_PERSON_SUBSTRING_ASCII, "not_a_person_substring_cjk": NOT_A_PERSON_SUBSTRING_CJK,
    "generated_suffixes": GENERATED_SUFFIXES, "not_evidence": NOT_EVIDENCE, "separators": SEPARATORS, "made_up_cjk": MADE_UP_CJK, "made_up_ascii": MADE_UP_ASCII, "min_note": MIN_NOTE, "evidence_min": EVIDENCE_MIN,
    "workday_words": WORKDAY_WORDS, "money_words": MONEY_WORDS, "total_words": TOTAL_WORDS,
    "currency_units": CURRENCY_UNITS, "other_units": OTHER_UNITS, "evidence_prefix": EVIDENCE_PREFIX,
    "internal_document_references": INTERNAL_DOCUMENT_REFERENCES.pattern,
}


def is_blank(value) -> bool:
    """A missing value or empty text/container; zero and false are explicit values."""
    if isinstance(value, str):
        return not value.strip()
    return value is None or isinstance(value, (list, dict)) and not value


def terms_digest() -> str:
    """A short fingerprint of all the data above: a copy of this module in another skill must give the same string."""
    return hashlib.sha256(json.dumps(TERMS, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _alt(words: list[str]) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


WORKDAY = re.compile(_alt(WORKDAY_WORDS))
MONEY = re.compile(_alt(MONEY_WORDS))
TOTAL = re.compile(_alt(TOTAL_WORDS))
CURRENCY = re.compile(_alt(CURRENCY_UNITS), re.I)
# a unit that follows a figure: "6.5 A", "12 台", "3.2 kW", "40 m" (a figure, optional space, the unit, then a non-letter); a currency word beats it
OTHER_UNIT_AFTER_NUMBER = re.compile(r"[\d.,]\s*(?:%s)(?![A-Za-z])" % _alt(OTHER_UNITS))


_SEP = re.compile(SEPARATORS)
_SUBSTRING_ASCII = re.compile(r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % _alt(NOT_A_PERSON_SUBSTRING_ASCII), re.I)
_EDGE_PUNCT = " \t\r\n.,;:!?。，；：！？、'\"“”‘’()（）[]【】{}<>《》"


def _tokens(text: str) -> list[str]:
    return [t for t in _SEP.split((text or "").strip(_EDGE_PUNCT)) if t]


def _is_word(token: str, words: list[str]) -> bool:
    """The token equals a word, or a word followed by a generated-by suffix (系统生成, 模板填写)."""
    low = token.lower()
    for word in words:
        w = word.lower()
        if low == w or (low.startswith(w) and low[len(w):] in GENERATED_SUFFIXES):
            return True
    return False


def not_a_person(text: str) -> bool:
    """True when ``text`` (a provided_by, a requested_by) names the agent, a skill, a tool, an example or an estimate instead of someone who gave a price or asked for one.

    The whole value or one token must EQUAL a word of the lists (or word + 生成, 自动, 拟定, 填写, 代填, 默认); only the unambiguous long words (智能体, 机器人, 大模型, 语言模型, 占位符,
    示例数据, 样例数据, 暂估值, 默认值, agent, assistant, chatgpt, claude, codex, copilot, gemini) match inside a longer value. 系统管理员, 空调公司张工, 无锡客户采购, 程序员王工
    and a name such as Na are people."""
    value = (text or "").strip(_EDGE_PUNCT)
    if not value:
        return True
    if value.lower() in NOT_A_PERSON_WHOLE_ONLY or _is_word(value, NOT_A_PERSON_ASCII + NOT_A_PERSON_CJK):
        return True
    if _SUBSTRING_ASCII.search(value) or any(word in value for word in NOT_A_PERSON_SUBSTRING_CJK):
        return True
    return any(_is_word(token, NOT_A_PERSON_ASCII + NOT_A_PERSON_CJK) for token in _tokens(value))


_MADE_UP_ASCII = re.compile(r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % _alt(MADE_UP_ASCII), re.I)


def says_made_up(text: str) -> bool:
    """True when the text itself says its figures are an estimate, made up by the agent, a default or a placeholder (暂估, 自拟, 默认值, 占位, 示例数据, 样例数据, placeholder, assumed,
    estimated, tbd), wherever the word stands, even when other words follow. Evidence must not say that; is_not_evidence is the separate case of a text made only of such words."""
    value = text or ""
    return any(word in value for word in MADE_UP_CJK) or bool(_MADE_UP_ASCII.search(value))


def is_not_evidence(text: str) -> bool:
    """True when an evidence (the words someone said, a source file or link) is empty or made of nothing but placeholder words (暂估, 示例, 默认值, TBD …).
    A long real quotation is evidence even if it mentions one of those words."""
    value = (text or "").strip(_EDGE_PUNCT)
    if not value or _is_word(value, NOT_EVIDENCE):
        return True
    return all(_is_word(token, NOT_EVIDENCE) for token in _tokens(value))


def has_currency(text: str) -> bool:
    return bool(CURRENCY.search(text or ""))


def is_workday_text(text: str) -> bool:
    return bool(WORKDAY.search(text or ""))


def is_money_text(text: str, *, row_text: str = "", column_text: str = "") -> bool:
    """Whether a header or a short label cell speaks of money.

    ``MONEY_WORDS`` are money wherever they stand. A ``TOTAL_WORDS`` word (合计, 小计, 总计) is money only when the cell itself, the row it sums up (``row_text``: the
    other cells of the row, joined) or the column's header (``column_text``) carries a currency; a total of amperes or devices ("合计约 6.5 A", "合计 12 台") is not."""
    text = text or ""
    if MONEY.search(text):
        return True
    if not TOTAL.search(text):
        return False
    if has_currency(text):
        return True
    if OTHER_UNIT_AFTER_NUMBER.search(text) or OTHER_UNIT_AFTER_NUMBER.search(row_text or ""):
        return has_currency(row_text) or has_currency(column_text)
    return has_currency(row_text) or has_currency(column_text) or bool(MONEY.search(row_text or "")) or bool(MONEY.search(column_text or ""))


def evidence_text(requested_by: str, request_note: str, provided_by: str = "", evidence: str = "") -> str:
    """The description a workbook carries when its quote switch is on."""
    parts = [f"要求人：{requested_by}", f"原话：{request_note}"]
    if provided_by:
        parts += [f"提供人：{provided_by}", f"来源：{evidence}"]
    return EVIDENCE_PREFIX + "；".join(parts)


def read_evidence(description: str | None) -> str:
    """The evidence text of a workbook description ('' when it carries none or too little)."""
    value = description or ""
    if EVIDENCE_PREFIX not in value:
        return ""
    body = value.split(EVIDENCE_PREFIX, 1)[1].strip()
    return body if len(body) >= EVIDENCE_MIN else ""


if __name__ == "__main__":
    print(json.dumps({"digest": terms_digest(), **TERMS}, ensure_ascii=False, indent=1))
