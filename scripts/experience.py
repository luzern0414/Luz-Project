#!/usr/bin/env python3
"""Small, public-safe experience store for luz-project."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "experience" / "notes.json"
KINDS = {"preference", "lesson", "fact"}
# A note applies to every task unless it is marked as one project's requirement or as upkeep of this skill.
SCOPES = ("project", "maintenance")
PRIVATE = re.compile(r"(?i)(?:sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|password\s*[:=]|cookie\s*[:=]|token\s*[:=])")


def load() -> list[dict]:
    if not STORE.is_file():
        return []
    return json.loads(STORE.read_text(encoding="utf-8"))


def save(items: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def note(kind: str, key: str, text: str, why: str | None = None, scope: str | None = None, codified: str | None = None) -> dict:
    """Add a note, or update the one with this key: the same text confirms it, a new text replaces it and the old one is kept as
    ``previous``. scope: "project" (one project only; the text names it), "maintenance" (about maintaining this skill), "global"
    clears it. codified: the rule page that now states the note; an empty string clears it."""
    if kind not in KINDS or not key.strip() or not text.strip():
        raise ValueError("kind、key、text 不能为空，kind 必须为 preference、lesson 或 fact")
    if scope is not None and scope != "global" and scope not in SCOPES:
        raise ValueError("scope 只能是 global、project 或 maintenance")
    if PRIVATE.search(f"{key} {text} {why or ''} {codified or ''}"):
        raise ValueError("经验记录疑似包含私密值")
    items = load()
    today = date.today().isoformat()
    existing = next((item for item in items if item.get("key") == key), None)
    if existing:
        if str(existing.get("text", "")).strip() != text.strip():
            existing["previous"] = {"text": existing.get("text", ""), "replaced_at": today}
        existing.update({"kind": kind, "text": text.strip(), "uses": int(existing.get("uses", 0)) + 1, "last_confirmed": today})
        if why:
            existing["why"] = why
        result = existing
    else:
        result = {"key": key.strip(), "kind": kind, "text": text.strip(), "why": why, "uses": 1, "first_seen": today, "last_confirmed": today}
        items.append(result)
    if scope is not None:
        result.pop("scope", None)
        if scope != "global":
            result["scope"] = scope
    if codified is not None:
        result.pop("codified", None)
        if codified.strip():
            result["codified"] = codified.strip()
    save(items)
    return result


def check() -> list[str]:
    errors = []
    items = load()
    keys = [str(item.get("key", "")) for item in items]
    if len(keys) != len(set(keys)):
        errors.append("经验 key 重复")
    for item in items:
        if item.get("kind") not in KINDS:
            errors.append(f"经验 kind 无效: {item.get('key')}")
        if not str(item.get("text", "")).strip():
            errors.append(f"经验内容为空: {item.get('key')}")
        if item.get("scope") is not None and item["scope"] not in SCOPES:
            errors.append(f"经验 scope 无效: {item.get('key')}")
        if PRIVATE.search(json.dumps(item, ensure_ascii=False)):
            errors.append(f"经验疑似包含私密值: {item.get('key')}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Luz Project 经验记录")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("note")
    add.add_argument("--kind", required=True, choices=sorted(KINDS))
    add.add_argument("--key", required=True)
    add.add_argument("--text", required=True)
    add.add_argument("--why")
    add.add_argument("--scope", choices=("global", *SCOPES), help="project：只属于某个项目（正文写明项目）；maintenance：只在维护本技能时用；global：每次都适用（缺省）")
    add.add_argument("--codified", help="规则已经写进的规范页和小节；传空字符串取消")
    search = sub.add_parser("search")
    search.add_argument("query", nargs="+", help="一个或多个词，全部命中才返回")
    sub.add_parser("list")
    sub.add_parser("check")
    args = parser.parse_args(argv)
    if args.command == "note":
        print(json.dumps(note(args.kind, args.key, args.text, args.why, args.scope, args.codified), ensure_ascii=False, indent=2))
        return 0
    items = load()
    if args.command == "list":
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    if args.command == "search":
        words = [word.lower() for word in args.query]
        print(json.dumps([item for item in items if all(word in json.dumps(item, ensure_ascii=False).lower() for word in words)], ensure_ascii=False, indent=2))
        return 0
    errors = check()
    print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
