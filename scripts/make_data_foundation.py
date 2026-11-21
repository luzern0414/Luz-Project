"""Build a self-contained data-foundation HTML from the Project 03 template."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT.parent / "Luz-Design"
TEMPLATE = ROOT / "templates" / "03-开发资料" / "Agent数据底座.html"
VENDOR = DESIGN / "kit" / "vendor" / "three"
TEMPLATE_ID = "data-foundation-html"
DATA_SCRIPT = re.compile(r'(<script type="application/json" id="foundation-data">)\s*(.*?)\s*(</script>)', re.S)
RENDERER_TAG = '<script src="../../../Luz-Design/kit/vendor/three/three.min.js" data-inline-renderer></script>'

def text(node, key):
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 需要填写文字")
    return value

def records(node, key):
    values = node.get(key)
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError(f"{key} 需要一组记录")
    return values

def unique(items, key):
    result = {}
    for item in items:
        name = text(item, key)
        if name in result:
            raise ValueError(f"{key} 重复：{name}")
        result[name] = item
    return result

def validate(model):
    if not isinstance(model, dict):
        raise ValueError("数据底座需要一个对象")
    text(model, "title")
    database = model.get("database")
    if not isinstance(database, dict) or not text(database, "name").isidentifier():
        raise ValueError("database.name 需要实际库名或查询名")
    text(database, "label")
    groups = unique(records(model, "groups"), "id")
    for group in groups.values():
        text(group, "label")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text(group, "color")):
            raise ValueError("业务分组颜色须用六位十六进制值")
    tables = unique(records(model, "tables"), "name")
    if not tables:
        raise ValueError("至少需要一张业务表")
    table_fields = {}
    for name, table in tables.items():
        if not name.isidentifier() or text(table, "group") not in groups:
            raise ValueError(f"表名或业务分组无效：{name}")
        text(table, "label")
        text(table, "grain")
        sources = table.get("sources")
        if not isinstance(sources, list) or any(not isinstance(s, str) or not s.strip() for s in sources):
            raise ValueError(f"填写 {name} 的来源库表清单")
        fields = unique(records(table, "fields"), "name")
        if not fields:
            raise ValueError(f"填写 {name} 的字段")
        for field_name, field in fields.items():
            if not field_name.isidentifier():
                raise ValueError(f"字段名无效：{name}.{field_name}")
            for key in ("label", "type", "description"):
                text(field, key)
            if any(key in field and not isinstance(field[key], str) for key in ("unit", "key")):
                raise ValueError(f"字段单位和键标注需要文字：{name}.{field_name}")
            if "featured" in field and not isinstance(field["featured"], bool):
                raise ValueError(f"featured 需要布尔值：{name}.{field_name}")
        table_fields[name] = fields

    def check_ref(ref):
        if not isinstance(ref, dict):
            raise ValueError("关联和问数引用须给出 table 与 field")
        table, field = text(ref, "table"), text(ref, "field")
        if field not in table_fields.get(table, {}):
            raise ValueError(f"引用了未登记字段：{table}.{field}")

    for link in records(model, "links"):
        for side in ("from", "to"):
            check_ref(link.get(side))
        text(link, "label")
        text(link, "rule")
        if link.get("kind") not in {"foreign-key", "rule"}:
            raise ValueError("关联类型请标明 foreign-key 或 rule")
    for question in unique(records(model, "questions"), "id").values():
        for key in ("label", "question", "formula", "status"):
            text(question, key)
        steps = records(question, "steps")
        if not steps:
            raise ValueError("问数路径至少要有一个处理步骤")
        for step in steps:
            text(step, "title")
            text(step, "text")
            for ref in records(step, "fields"):
                check_ref(ref)
        for key in ("example", "pending"):
            if key in question:
                text(question, key)

def render(data=None):
    template = TEMPLATE.read_text(encoding="utf-8-sig")
    found = DATA_SCRIPT.search(template)
    if found is None or template.count(RENDERER_TAG) != 1:
        raise ValueError("数据底座模板缺少数据区或三维渲染位")
    if data is None:
        data = json.loads(found.group(2))
    validate(data)
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("<", r"\u003c")
    source = DATA_SCRIPT.sub(lambda m: m.group(1) + "\n" + payload + "\n" + m.group(3), template, count=1)
    title = html.escape(data["title"])
    source = re.sub(r"<title>[^<]*</title>", lambda _: f"<title>{title}</title>", source, count=1)
    source = re.sub(r'(<h1 id="page-title">)[^<]*(</h1>)', lambda m: m.group(1) + title + m.group(2), source, count=1)
    vendor = (VENDOR / "three.min.js").read_text(encoding="utf-8")
    vendor = re.sub(r"</script", lambda _: r"<\/script", vendor, flags=re.I)
    license_text = (VENDOR / "LICENSE").read_text(encoding="utf-8").replace("--", "- -")
    return source.replace(RENDERER_TAG, "<!--\n" + license_text + "\n-->\n<script>\n" + vendor + "\n</script>")

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--data", type=Path, help="项目的数据描述。省略时生成模板内置的示例。")
    args = parser.parse_args(argv)
    sys.path.append(str(DESIGN / "scripts"))
    from crawl_gate import require_session_preflight, record_template_output
    try:
        context = require_session_preflight(args.session, args.output, template_id=TEMPLATE_ID)
        if args.output.suffix.lower() != ".html" or not args.output.resolve().is_relative_to(context["raw"].resolve()):
            raise ValueError("HTML 构建写入当前会话的 raw 目录")
        data = json.loads(args.data.read_text(encoding="utf-8-sig")) if args.data else None
        content = render(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        record_template_output(context, args.output, TEMPLATE_ID, generator="Luz-Project/scripts/make_data_foundation.py")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(args.output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
