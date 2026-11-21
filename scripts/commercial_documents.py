"""Render each commercial review package from its specialists' project facts."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile

import client_data as cd
import client_render as cr
import estimate_policy as ep
from project_paths import ProjectError


TEMPLATES = {"scope": {".pdf": "docx-paginated"}, "design": {".html": "reading-html"},
             "demo": {".html": "frontend-existing"}, "baseline": {".pdf": "showcase", ".xlsx": "xlsx"}}
CHAPTERS = {
    "requirements": ("context", "roles", "scope", "acceptance"),
    "solution": ("journey", "modules", "delivery", "risks"),
    "functional": ("journey", "permissions", "states", "exceptions"),
    "technical": ("architecture", "data", "integrations", "quality"),
    "frontend": ("entries", "pages", "actions", "recovery"),
    "backend": ("contracts", "authorization", "consistency", "operations"),
}
WRITER = "luz-project"
UI_STATE_RULES = cr.DESIGN_SCRIPTS / "application_state_rules.js"
DEMO_WALKTHROUGH = "data/commercial/demo-walkthrough.json"
EDITOR_SECTIONS = {"思考过程", "编辑备注", "制作备注", "修改说明话术", "过渡话术", "模板填写说明", "撰写思路"}
EDITOR_INTRO = re.compile(r"^(?:(?:好的[，。！ ]*)?(?:下面|以下)(?:是|为)(?:我(?:为你|帮你)?)?(?:重新|已经)?(?:修改|优化|整理|补充|调整)后的(?:内容|版本|正文|方案)[：:，。！\s]*|(?:备注|编者按|温馨提示|需要说明的是|值得注意的是|抱歉|对不起)[：:，。！\s]+|我(?:已经|已|刚刚)?(?:帮你|为你)(?:删掉|删除|修改|补充|整理|优化)了?[^，,。！？；;]*(?:[，,。！？；;]|$))")


def _design():
    if str(cr.DESIGN_SCRIPTS) not in sys.path:
        sys.path.append(str(cr.DESIGN_SCRIPTS))
    import template_library
    return template_library


def _targets(project, batch):
    from commercial_workflow import paths
    if batch not in TEMPLATES:
        raise ProjectError(f"未知项目批次 {batch}")
    root = Path(project).resolve()
    for rel in paths(batch):
        target = (root / rel).resolve()
        if not target.is_relative_to(root):
            raise ProjectError(f"项目交付路径越界：{rel}")
        yield target, TEMPLATES[batch][target.suffix]


def select_templates(project_dir, state_root, batch_id):
    """Return the actual template uses for a Crawl supplement before conclusion."""
    library = _design()
    uses = []
    for target, template in _targets(project_dir, batch_id):
        try:
            use = library.require_selected(state_root, WRITER, batch_id, target, template)
        except (OSError, ValueError):
            library.select(state_root, WRITER, batch_id, template, str(target))
            use = library.require_selected(state_root, WRITER, batch_id, target, template)
        uses.append(use)
    return uses


def output_errors(project_dir, state_root, batch_id):
    errors = []
    for target, template in _targets(project_dir, batch_id):
        try:
            _design().require_selected(state_root, WRITER, batch_id, target, template, phase="post")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(f"{target.name}：{exc}")
    return errors


def _read(path):
    with Path(path).open(encoding="utf-8-sig") as source:
        result = json.load(source)
    if not isinstance(result, dict):
        raise ProjectError(f"{path} 应为 JSON 对象")
    return result


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"请填写 {field}")
    return value.strip()


def _reader_paragraph(value, field):
    parts = re.split(r"(?<=[。！？])", _text(value, field))
    clean = [EDITOR_INTRO.sub("", part.strip()) for part in parts]
    return "".join(clean)


def _list(value, field):
    if not isinstance(value, list) or not value:
        raise ProjectError(f"{field} 应有至少一条实际记录")
    return value


def _feature_data(value):
    errors = cd.validate_features(value)
    if errors:
        raise ProjectError("；".join(errors))
    return value


def _acceptance(feature):
    cases = feature.get("acceptance", [])
    if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
        raise ProjectError(f"{feature['id']} 的验收场景应是记录数组")
    return [(_text(case.get("steps"), "验收场景"), _text(case.get("expected"), "可见结果")) for case in cases]


def _agreed_rules(design, baseline=None):
    facts = design.get("business_rules")
    if baseline is not None and "rules" in baseline and facts is not None and baseline["rules"] != facts:
        raise ProjectError("定稿时的规则与第二次确认不一致；请先登记设计变更并重新走查")
    records = facts if facts is not None else (baseline or {}).get("rules")
    rows = _sheet_rows({"rules": records}, "rules", ("feature", "condition", "decision", "exception", "owner"))
    active = {f["id"] for f in cd.active_features(design["features"])}
    if {row[0] for row in rows} != active:
        raise ProjectError("规则确认表应覆盖设计范围中的每个功能，使用原功能编号")
    return rows


def _sections(data, key):
    """Use the same section/table representation in working HTML and Word."""
    sections = []
    keys = []
    for source in _list(data.get(key), key):
        sec = copy.deepcopy(source)
        if not isinstance(sec, dict):
            raise ProjectError(f"{key} 的章节应是对象")
        title = _text(sec.get("title"), f"{key}.title")
        if title in EDITOR_SECTIONS:
            continue
        keys.append(_text(sec.get("key"), f"{key}.key"))
        paragraphs = sec.get("paragraphs", [])
        if not isinstance(paragraphs, list):
            raise ProjectError(f"{title} 的 paragraphs 须是段落列表")
        paragraphs = [clean for para in paragraphs if (clean := _reader_paragraph(para, title))]
        sec["paragraphs"] = paragraphs
        tbl = sec.get("table")
        if tbl is not None:
            if not isinstance(tbl, dict):
                raise ProjectError(f"{title} 的 table 须是对象")
            cols = _list(tbl.get("columns"), title + "表头")
            for col in cols:
                _text(col, title + "列名")
            _text(tbl.get("caption"), title + "表题")
            for row in _list(tbl.get("rows"), title + "数据行"):
                if not isinstance(row, list) or len(row) != len(cols):
                    raise ProjectError(f"{title} 表格行与列数不符")
                for cell in row:
                    _text(cell, title + "单元格")
        if not paragraphs and not tbl:
            raise ProjectError(f"{title} 缺少实际内容")
        sections.append(sec)
    missing = set(CHAPTERS[key]) - set(keys)
    if missing or len(keys) != len(set(keys)):
        raise ProjectError(f"{key} 章节重复或缺少 {', '.join(sorted(missing))}")
    return sections


def _sources(data):
    rows = []
    for src in _list(data.get("sources"), "项目资料或采用的原文"):
        if not isinstance(src, dict):
            raise ProjectError("来源须包含名称、出处和采用位置")
        rows.append([_text(src.get(k), k) for k in ("name", "reference", "use")])
    return {"title": "采用依据", "table": {"caption": "材料与采用位置", "columns": ["资料", "出处", "用途"], "rows": rows}}


def _check_scope_estimates(state, sections, business_terms):
    """Apply the existing client estimate policy to the visible first-batch content."""
    if not isinstance(business_terms, list) or not all(isinstance(term, str) for term in business_terms):
        raise ProjectError("allow_terms 应为项目实际使用的业务术语列表")
    estimate = cd.estimate_state(state)
    allowed = (*ep.project_allowed_terms(state), *business_terms)
    content = json.dumps(sections, ensure_ascii=False)
    issues = list(estimate.errors)
    money = cd.money_issues(content, allow=allowed)
    if money and (not estimate.quote or estimate.waiting_for_quote):
        issues.append("首批文件含尚无人工报价依据的用词或金额：" + "、".join(money))
    workdays = ep.workday_issues(content, allowed)
    if workdays and not estimate.workdays:
        issues.append("首批文件含未经要求的人日估算：" + "、".join(workdays))
    if issues:
        raise ProjectError("；".join(issues))


def _scope_pdf(title, sections, dest, context):
    import make_docx_paginated
    from check_document import main as check_document
    chapters = []
    for sec in sections:
        blocks = [{"p": para} for para in sec.get("paragraphs", [])]
        if "table" in sec:
            tab = sec["table"]
            blocks.append({"table": {"caption": tab["caption"], "header": tab["columns"], "rows": tab["rows"]}})
        chapters.append({"heading": sec["title"], "blocks": blocks})
    source = dest.with_suffix(".docx")
    spec = {"type": "proposal", "style": "paper", "mono": True, "title": title,
            "cover": {"subtitle": "", "info": []}, "toc": True, "sections": chapters}
    make_docx_paginated.build(spec, source, context=context)
    if check_document([str(source), "--allow", "cover", "--allow", "paper", "--allow", "header"]):
        raise ProjectError(f"{source.name} 正式文档检查失败")


def _workbook(plan, target, work, ctx):
    import make_xlsx
    make_xlsx.build(plan, work, context=ctx)
    if make_xlsx.verify_output(work, "xlsx", multi=bool(plan.get("sheets")), allow=make_xlsx.estimate_allow(plan)):
        raise ProjectError(f"{target.name} 表格检查失败")


def _atlas(spec, work):
    import showcase
    import make_showcase
    import make_table_pdf
    errors = cd.validate_architecture(spec, spec.get("theme"))
    if errors:
        raise ProjectError("架构图册：" + "；".join(errors))
    source = work.with_suffix(".html")
    source.write_text(showcase.build(spec), encoding="utf-8")
    errors, _, _ = make_showcase.export_pdf(source, work, spec.get("orientation", "landscape"),
                                            spec.get("min_fill", 0.75), spec["title"], header=False)
    errors += make_table_pdf.check_pdf(work, spec.get("max_pages"))
    if errors:
        raise ProjectError("；".join(errors))


def _demo_scope(features):
    exercisable = set()
    for feature in cd.active_features(features):
        if "prototype_exclusion" in feature:
            _text(feature["prototype_exclusion"], feature["id"] + " 的实际环境验收安排")
        else:
            exercisable.add(feature["id"])
    return exercisable


def _walk_demo(source_path, record, feature_ids):
    """Exercise the portable HTML on an isolated local origin. Store observations."""
    from playwright.sync_api import sync_playwright
    name = _text(record.get("html"), "Design 单文件 Demo")
    src = (source_path.parent / name).resolve()
    if (Path(name).is_absolute() or not src.is_relative_to(source_path.parent.resolve())
            or src.suffix.lower() != ".html" or not src.is_file()):
        raise ProjectError("html 应是事实文件同目录或子目录内的单文件 HTML")
    content = src.read_bytes()
    rule_bytes = UI_STATE_RULES.read_bytes()
    inspect_state = """async () => {
        await new Promise(requestAnimationFrame);
        await new Promise(requestAnimationFrame);
        return (%s)();
    }""" % rule_bytes.decode("utf-8-sig").strip().rstrip(";")
    rule_hash = hashlib.sha256(rule_bytes).hexdigest()
    html_hash = hashlib.sha256(content).hexdigest()
    journeys = _list(record.get("journeys"), "Demo 走查场景")
    url = "http://luz-demo.test/"
    results = []
    covered = set()
    with sync_playwright() as runtime:
        from playwright.sync_api import Error as BrowserError, expect
        try:
            browser = runtime.chromium.launch(channel="msedge")
        except BrowserError:
            browser = runtime.chromium.launch()
        for journey in journeys:
            if not isinstance(journey, dict):
                raise ProjectError("每条 Demo 走查场景须含关联功能、操作和预期结果")
            feature = journey.get("feature")
            if feature not in feature_ids:
                raise ProjectError(f"Demo 引用了未设计的功能 {feature}")
            title = _text(journey.get("name"), "Demo 场景名称")
            observed_steps = []
            width = journey.get("width", 1280)
            if not isinstance(width, int) or not 240 <= width <= 3840:
                raise ProjectError("Demo 走查应使用实际终端宽度")
            context = browser.new_context(viewport={"width": width, "height": 850}, service_workers="block")
            requests, errors = [], []
            def serve(route):
                if route.request.url == url and route.request.is_navigation_request():
                    route.fulfill(content_type="text/html; charset=utf-8", body=content)
                else:
                    requests.append(route.request.url)
                    route.abort()
            context.route("**/*", serve)
            page = context.new_page()
            page.set_default_timeout(4500)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("dialog", lambda dialog: dialog.dismiss())
            audited = []

            def check_state(action):
                issues = page.evaluate(inspect_state)
                if not isinstance(issues, list):
                    raise ProjectError("Design 成品检查未返回规则结果")
                if issues:
                    details = "；".join(f"{i['rule']} {i['element']} {i['detail']}" for i in issues[:8])
                    raise ProjectError(f"{title}（{width}px，{action}）未通过 Design 成品检查：{details}")
                audited.append(action)

            page.goto(url)
            check_state("打开页面")
            result = page.locator(_text(journey.get("result"), "结果选择器"))
            expected = _text(journey.get("expected"), "用户应看到的结果")
            if result.count() == 1 and result.is_visible() and expected in result.inner_text():
                raise ProjectError(f"{title}：预期结果在操作前已经显示，请指定实际变化")
            for step in _list(journey.get("steps"), title + "操作"):
                if not isinstance(step, dict):
                    raise ProjectError(f"{title}：操作步骤应写明动作和控件")
                if step.get("action") == "reload":
                    page.reload()
                    check_state("reload")
                    continue
                selector = _text(step.get("selector"), "控件选择器")
                loc = page.locator(selector)
                action = step.get("action")
                try:
                    if action == "click":
                        loc.click()
                    elif action == "focus":
                        loc.focus()
                    elif action == "hover":
                        loc.hover()
                    elif action in ("fill", "select"):
                        if "value" not in step:
                            raise ProjectError(f"{title}：{action} 缺少控件 {selector} 的输入值")
                        if action == "fill":
                            loc.fill(str(step["value"]))
                        else:
                            loc.select_option(str(step["value"]))
                    elif action == "press":
                        loc.press(_text(step.get("value"), "按键"))
                    elif action == "check":
                        checkpoint = _text(step.get("expected"), title + "中间结果")
                        linked = step.get("feature", feature)
                        if linked not in feature_ids:
                            raise ProjectError(f"{title}：查验引用的功能 {linked} 超出原型范围")
                        expect(loc).to_be_visible()
                        expect(loc).to_contain_text(checkpoint)
                        observed_steps.append({"feature": linked, "selector": selector, "observed": loc.inner_text()})
                    else:
                        raise ProjectError(f"{title}：未知 Demo 操作 {action}")
                except (AssertionError, BrowserError) as exc:
                    raise ProjectError(f"{title}：无法在控件 {selector} 执行 {action}，{exc}") from exc
                check_state(f"{action} {selector}")
            try:
                expect(result).to_be_visible()
                expect(result).to_contain_text(expected)
            except (AssertionError, BrowserError) as exc:
                raise ProjectError(f"{title}：操作后未看到预期结果「{expected}」，{exc}") from exc
            check_state("结果可见")
            if errors or requests:
                raise ProjectError(f"{title}：页面异常或依赖未内嵌资源 {errors + requests}")
            verified = {feature, *(step["feature"] for step in observed_steps)}
            claimed = journey.get("covers", [])
            if not isinstance(claimed, list) or any(fid not in verified for fid in claimed):
                raise ProjectError(f"{title}：关联功能须有对应的页面查验结果")
            covered.update(verified)
            results.append({"name": title, "feature": feature, "width": width, "observed": result.inner_text(),
                            "checks": observed_steps, "verified": sorted(verified), "ui_states": audited,
                            "html_sha256": html_hash, "design_rules_sha256": rule_hash})
            context.close()
        browser.close()
    missing = feature_ids - covered
    if missing:
        raise ProjectError("待补原型操作与查验：" + "、".join(sorted(missing)))
    return content, results


def _sheet(title, columns, rows):
    return {"title": title, "sheet": title, "columns": [{"name": col} for col in columns], "rows": rows}


def _add_acceptance_criteria(spec, features):
    ordered = cr.ordered_features(features)
    cases = [_acceptance(feature) for feature in ordered]
    if any(cases):
        # Append to the function list only. Existing hour and quotation column positions stay valid.
        listing = spec["sheets"][0] if "sheets" in spec else spec
        listing["columns"].append({"name": "验收场景与预期", "type": "longtext"})
        for row, feature, scenarios in zip(listing["rows"], ordered, cases):
            row.append("\n".join(steps + " → " + expected for steps, expected in scenarios) or feature["rules"])


def _sheet_rows(data, key, fields):
    rows = []
    for row in _list(data.get(key), key):
        if not isinstance(row, dict):
            raise ProjectError(f"{key} 的每行须为对象")
        rows.append([_text(row.get(field), key + "." + field) for field in fields])
    return rows


def _replace(source, target):
    """Atomic file replacement also when the state and project roots are on different disks."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        tmp = Path(handle.name)
    try:
        shutil.copyfile(source, tmp)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def build(project_dir, state_root, batch_id, data_path):
    """Called under the workflow's project write lock after predecessor checks."""
    project = Path(project_dir).resolve()
    state = Path(state_root).resolve()
    facts = Path(data_path).resolve()
    data = _read(facts)
    title = _text(_read(state / "project.json").get("name"), "项目名称")
    raw = state / "data" / "commercial"
    raw.mkdir(parents=True, exist_ok=True)
    targets = list(_targets(project, batch_id))
    library = _design()
    from design_output_gate import verified_output_context
    import make_summary
    select_templates(project, state, batch_id)
    with TemporaryDirectory(dir=raw, prefix="build-") as directory:
        staged = Path(directory)
        artifacts = []
        generated = []
        features = None
        if batch_id == "design":
            features = _feature_data(data.get("features"))
        if batch_id in ("baseline", "demo"):
            approved_design = _read(raw / "design.json")
            features = _feature_data(approved_design.get("features"))
        for index, (target, template) in enumerate(targets):
            work = staged / target.name
            working = work.with_suffix(".docx") if template == "docx-paginated" else work
            ctx = verified_output_context(state, WRITER, batch_id, target, template, working_output=working)
            if batch_id in ("scope", "design"):
                key = (("requirements", "solution") if batch_id == "scope" else
                       ("functional", "technical", "frontend", "backend"))[index]
                sections = list(_sections(data, key)) + [_sources(data)]
                if key == "functional":
                    sections.insert(-1, {"title": "功能与规则", "table": {"caption": "角色、动作与规则",
                        "columns": ["功能编号", "功能", "使用端", "角色", "业务规则", "范围"],
                        "rows": [[f["id"], f["name"], cd.SURFACES[f["surface"]], "、".join(f["roles"]), f["rules"],
                                  {"in-scope": "本期", "out-of-scope": "本期以外", "removed": "已移除"}[f.get("status", "in-scope")]]
                                 for f in features["features"]]}})
                    _demo_scope(features)
                    environment_cases = [[f["id"], f["name"], f["prototype_exclusion"]] for f in cd.active_features(features)
                                         if "prototype_exclusion" in f]
                    if environment_cases:
                        sections.insert(-1, {"title": "目标环境验证", "table": {"caption": "联机与实物验收安排",
                            "columns": ["功能编号", "功能", "验证条件与预期结果"], "rows": environment_cases}})
                    if "business_rules" in data:
                        sections.insert(-1, {"title": "业务决定与责任", "table": {"caption": "条件、结果和异常处理",
                            "columns": ["功能编号", "条件", "处理规则", "异常", "确认责任方"], "rows": _agreed_rules(data)}})
                    cases = [[f["id"], steps, expected] for f in cd.active_features(features) for steps, expected in _acceptance(f)]
                    if cases:
                        sections.insert(-1, {"title": "业务验收", "table": {"caption": "角色操作与预期结果",
                            "columns": ["功能编号", "场景与操作", "预期结果"], "rows": cases}})
                document_title = title + target.stem.split("-", 1)[1]
                if batch_id == "scope":
                    _check_scope_estimates(state, sections, data.get("allow_terms", []))
                    _scope_pdf(document_title, sections, work, ctx)
                    generated.append((working, raw / "sources" / working.name))
                else:
                    work.write_text(make_summary.render({"title": document_title, "sections": sections}), encoding="utf-8")
            elif batch_id == "demo":
                content, results = _walk_demo(facts, data, _demo_scope(features))
                work.write_bytes(content)
                generated.append((_json(staged / "walkthrough.json", results), raw / "demo-walkthrough.json"))
            elif index == 0:
                spec = copy.deepcopy(data.get("architecture", {}))
                _text(spec.get("theme"), "架构图册主题")
                _atlas(spec, work)
                generated.append((_json(staged / "atlas.json", spec), state / "data/client/architecture.json"))
            elif index == 1:
                from client_flow import estimate_build_errors
                estimate = cd.estimate_state(state)
                issues = estimate_build_errors(state, estimate, features)
                if issues:
                    raise ProjectError("；".join(issues))
                spec = cr.feature_list_xlsx_spec(features, title, data["architecture"]["theme"],
                    quote=cd.load_quote(state) if estimate.quote else None, estimate=estimate.render_block())
                _add_acceptance_criteria(spec, features)
                _workbook(spec, target, work, ctx)
            elif index == 2:
                active = {f["id"]: f for f in cd.active_features(features)}
                rules = _agreed_rules(approved_design, data)
                rows = [[active[fid]["name"], *rest, ""] for fid, *rest in rules]
                _workbook(_sheet("业务规则确认表", ["功能", "条件", "处理规则", "例外与恢复", "确认责任方", "客户意见"], rows), target, work, ctx)
            else:
                rows = _sheet_rows(data, "plan", ("milestone", "prerequisite", "schedule", "owner", "deliverable", "acceptance"))
                _workbook(_sheet("项目实施计划表", ["里程碑", "前提", "时间或启动条件", "负责人", "交付物", "验收条件"], rows), target, work, ctx)
            artifacts.append((work, target, template))
        generated.append((_json(staged / "facts.json", data), raw / (batch_id + ".json")))
        if batch_id == "baseline":
            old_links = cd.load(state, "client", "trace-links.json", default={}) or {}
            links = {f["id"]: {**old_links.get(f["id"], {}), "arch": [f["module"]]} for f in features["features"]}
            for file, value in (("client/features.json", features), ("client/trace-links.json", links),
                                ("stages/architecture.json", {"logic": {"modules": features["modules"]}})):
                generated.append((_json(staged / file, value), state / "data" / file))
        # Protect the previous batch and template receipts if a publication fails partway.
        receipt = state / "00-design" / f"{WRITER}-{batch_id}.json"
        writes = [(work, target) for work, target, _ in artifacts] + generated
        previous = {}
        for i, target in enumerate([p for _, p in writes] + [receipt]):
            backup = staged / f"before-{i}" if target.is_file() else None
            if backup is not None:
                shutil.copyfile(target, backup)
            previous[target] = backup
        touched = []
        try:
            for work, target in writes:
                _replace(work, target)
                touched.append(target)
            touched.append(receipt)
            for work, target, template in artifacts:
                library.record_output(state, WRITER, batch_id, target, template,
                                      generator=f"Luz-Project/scripts/commercial_documents.py:{template}")
        except BaseException:
            for target in reversed(touched):
                if previous[target] is None:
                    target.unlink(missing_ok=True)
                else:
                    _replace(previous[target], target)
            raise
    return [str(path) for path, _ in targets]
