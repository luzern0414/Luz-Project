"""Synthetic client data for offline tests of the client-facing flow (never a real project)."""
from __future__ import annotations

from pathlib import Path

import client_data as cd


def features() -> dict:
    modules = [
        {"id": "M01", "name": "会员与积分", "summary": "顾客注册成为会员，消费累计积分并抵扣"},
        {"id": "M02", "name": "预约服务", "summary": "顾客在线预约时段，门店核销到店"},
        {"id": "M03", "name": "后台管理", "summary": "店长维护商品、会员与订单，查看经营报表"},
        {"id": "M04", "name": "智能助手", "summary": "员工用对话方式查询经营数据并核算绩效"},
    ]
    def f(i, module, name, surface, roles, tier, summary, rules, **extra):
        return {"id": f"FN-{i:03d}", "module": module, "name": name, "surface": surface, "roles": roles, "tier": tier, "summary": summary, "rules": rules, **extra}
    return {"schema_version": "1.0", "modules": modules, "features": [
        f(1, "M01", "会员注册与登录", "miniprogram", ["顾客"], "基础", "微信授权后创建会员档案", "同一微信只能对应一个会员；手机号需验证", tags=["会员"]),
        f(2, "M01", "积分获取与抵扣", "miniprogram", ["顾客"], "基础", "消费按比例累计积分并在下单时抵扣", "1 元累计 1 分；100 分抵 1 元；积分 12 个月有效", tags=["积分", "会员"]),
        f(3, "M01", "会员等级", "miniprogram", ["顾客"], "可选", "按累计消费划分等级并享受折扣", "三级会员，升级即时生效，降级每年核算一次", tags=["会员"]),
        f(4, "M02", "在线预约", "miniprogram", ["顾客"], "基础", "选择服务与时段完成预约", "最晚提前 2 小时取消；爽约三次限制预约", tags=["预约"]),
        f(5, "M02", "到店核销", "web-admin", ["店员"], "基础", "店员扫码核销预约", "每个预约只能核销一次；超时自动失效", tags=["预约", "核销"]),
        f(6, "M03", "商品与套餐管理", "web-admin", ["店长"], "基础", "维护商品、价格、库存与上下架", "下架商品不出现在小程序；价格修改留痕", tags=["商品"]),
        f(7, "M03", "经营报表", "web-admin", ["店长", "老板"], "基础", "按日、周、月查看营业额与订单数", "门店数据权限隔离；口径以支付成功订单为准"),
        f(8, "M04", "对话式经营查询", "agent", ["店长"], "可选", "用自然语言查询营业额与会员数据", "只读数据；越权字段自动脱敏", tags=["知识库"]),
        f(9, "M04", "绩效核算", "agent", ["店长"], "可选", "按后台配置的规则核算员工绩效并复核", "规则由后台配置；结果记录所用规则版本", tags=["绩效核算", "规则引擎"], acceptance=[
            {"steps": "在后台把提成比例改为 5% 后，让智能助手核算上月某员工绩效", "expected": "结果按 5% 计算，并显示所用规则版本号", "evidence_checks": ["rules_calc", "agent_eval"]},
            {"steps": "用无权限账号让智能助手查询他人绩效", "expected": "被拒绝并说明需要店长权限", "evidence_checks": ["agent_eval"]}]),
    ]}


def requirements() -> dict:
    """The requirements document we write when the client has none (the quick HTML route keeps the tests fast; Word is the standard)."""
    t = lambda text: {"type": "text", "text": text}
    def sec(key, title, icon, *blocks):
        return {"key": key, "title": title, "icon": icon, "blocks": list(blocks)}
    return {"title": "示例健身预约与会员小程序需求说明书", "icon": "list", "orientation": "portrait", "format": "showcase",
            "hero": {"stats": [{"value": "9 项", "label": "需求", "icon": "list"}, {"value": "3 端", "label": "使用端", "icon": "phone"}], "scene": ["user", "calendar", "scan", "check"]},
            "sections": [
                sec("background", "项目背景", "flag", {"type": "sub", "text": "业务现状"}, t("门店目前依靠微信群和纸质登记管理预约与会员，每天约 60 个预约，高峰期容易漏记。"),
                    {"type": "sub", "text": "问题与痛点"}, {"type": "table", "columns": ["使用方", "现状问题", "具体表现", "带来的后果"], "caption": "按使用方的现状问题",
                                                       "rows": [["顾客", "预约靠群消息", "高峰期消息被刷掉", "到店发现没有登记，投诉增多"], ["店员", "纸质登记", "核销要翻本子", "每单耗时约 1 分钟"]]}),
                sec("goals", "建设目标", "target", t("预约转化为到店不低于 80%，前台登记耗时降低一半以上。")),
                sec("scope", "范围与使用者", "users", {"type": "sub", "text": "本期范围"}, t("预约、核销、会员与积分、经营报表。"), {"type": "sub", "text": "不在本期范围"}, t("在线支付与退款。"),
                    {"type": "table", "columns": ["使用者", "使用端", "主要做什么"], "caption": "使用者与使用端", "rows": [["顾客", "小程序", "注册、预约、积分"], ["店员", "网页后台", "扫码核销"]]}),
                sec("requirements", "需求清单", "list", {"type": "auto", "what": "requirement_list"}),
                sec("rules", "业务规则与约束", "shield", t("预约最晚提前 2 小时取消；爽约三次限制预约；价格修改留痕。")),
                sec("acceptance", "验收标准", "check", t("每项需求按功能清单逐项演示，由客户验收人签字确认。")),
                sec("open", "需要客户确认的事项", "info", {"type": "table", "columns": ["事项", "为什么需要确认", "建议的做法"], "caption": "需要客户确认的事项", "rows": [["积分有效期", "影响积分清零规则", "按 12 个月有效"]]}),
            ]}


def requirements_provided(root: Path) -> None:
    """The client brought its own requirements document: it sits under raw/uploads and requirements.json registers it."""
    uploads = root / "raw" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / "客户需求说明.docx").write_text("客户自己的需求文档", encoding="utf-8")
    cd.save(root, {"client_document": {"file": "raw/uploads/客户需求说明.docx", "note": "客户提供的需求文档"}}, "client", "requirements.json")


def proposal() -> dict:
    t = lambda text: {"type": "text", "text": text}
    def sec(key, title, icon, *blocks):
        return {"key": key, "title": title, "icon": icon, "blocks": list(blocks)}
    return {"title": "示例健身预约与会员小程序建设方案", "icon": "calendar", "orientation": "portrait", "format": "showcase",   # the quick HTML route keeps the tests fast; "word" is the standard
            "hero": {"stats": [{"value": "9 项", "label": "功能", "icon": "list"}, {"value": "3 端", "label": "使用端", "icon": "phone"}], "scene": ["user", "calendar", "scan", "check"]},
            "sections": [
                sec("background", "项目背景与现状", "flag", t("门店目前依靠微信群和纸质登记管理预约与会员，高峰期容易漏记，会员积分无法自动累计。")),
                sec("goals", "建设目标与成功标准", "target", {"type": "table", "columns": ["指标", "目标"], "rows": [["预约转化为到店", "不低于 80%"], ["前台登记耗时", "降低一半以上"]]}),
                sec("roles", "使用角色与权限", "users", {"type": "table", "columns": ["角色", "可以做什么"], "rows": [["顾客", "注册会员、预约、积分抵扣"], ["店员", "扫码核销预约"], ["店长", "管理商品、会员与报表"]]}),
                sec("solution", "解决方案", "flow", {"type": "steps", "cols": 3, "items": [{"title": "预约", "text": "顾客选择服务与时段"}, {"title": "核销", "text": "店员扫码核销"}, {"title": "积分", "text": "消费后自动累计"}]}),
                sec("scope", "功能范围", "list", {"type": "auto", "what": "feature_overview"}),
                sec("deliverables", "交付内容", "package", {"type": "bullets", "items": ["微信小程序（顾客端）", "网页管理后台", "智能经营助手", "使用说明与验收清单"]}),
                sec("plan", "实施计划与里程碑", "calendar", {"type": "gantt", "total": 10, "unit": "周", "rows": [{"label": "方案确认", "start": 1, "end": 1, "note": "确认"}, {"label": "设计开发", "start": 2, "end": 7, "note": "开发"}, {"label": "测试上线", "start": 8, "end": 10, "note": "验收"}]}),
                sec("responsibilities", "双方职责与客户需提供的资料", "handshake", {"type": "bullets", "items": ["我方：设计、开发、测试、上线与培训", "贵方：提供营业规则、商品资料、小程序主体资质并指定验收人"]}),
                sec("assumptions", "假设、约束与风险", "warning", t("贵方按《业务逻辑确认表》在约定时间内提供资料；新增需求按变更流程评估后实施。")),
                sec("acceptance", "验收方式", "check", t("按《验收清单》逐项验收，每项由贵方验收人签字确认。")),
                sec("change_policy", "需求变更约定", "refresh", t("需求变更先登记《需求变更台账》，经双方确认后实施，必要时调整周期与费用。")),
            ]}


def architecture() -> dict:
    def table(columns, rows, caption):
        return {"type": "table", "columns": columns, "rows": rows, "caption": caption}
    return {"title": "示例健身系统架构图册", "icon": "layers", "orientation": "landscape", "min_fill": 0.3, "style": "atlas", "sections": [
        {"title": "功能模块与逻辑", "key": "modules", "blocks": [table(["模块", "输入", "处理", "输出"], [["预约与核销", "顾客选择的时段", "校验库存并生成预约", "预约单与核销码"]], "模块的输入、处理与输出")]},
        {"title": "模块依赖关系", "key": "dependencies", "blocks": [table(["被依赖的对象", "被谁使用", "不可用时的影响"], [["会员与积分服务", "预约与核销服务", "无法按会员价预约"]], "被依赖对象与影响")]},
        {"title": "数据链路与流转", "key": "dataflow", "blocks": [table(["数据", "产生于", "保存在"], [["预约单", "顾客小程序", "数据库"]], "主要数据的来源与去向")]},
        {"title": "总体架构", "key": "layers", "icon": "layers", "blocks": [{"type": "figure", "figure": "arch_layers", "caption": "总体架构图", "data": {"layers": [
            {"name": "使用端", "icon": "phone", "nodes": [{"id": "U1", "name": "顾客小程序", "role": "预约、会员与积分", "icon": "phone"}, {"id": "U2", "name": "管理后台", "role": "商品、核销与报表", "icon": "monitor"}, {"id": "U3", "name": "经营助手", "role": "对话查询与绩效核算", "icon": "bolt"}]},
            {"name": "业务服务", "icon": "layers", "nodes": [{"id": "S1", "name": "会员与积分服务", "role": "会员档案、积分账户", "icon": "users"}, {"id": "S2", "name": "预约与核销服务", "role": "时段库存、核销记录", "icon": "calendar"}, {"id": "S3", "name": "规则与核算服务", "role": "读取后台规则并核算", "icon": "sliders"}]},
            {"name": "基础设施", "icon": "server", "nodes": [{"id": "B1", "name": "数据库与备份", "role": "业务数据保存与恢复", "icon": "database"}, {"id": "B2", "name": "消息通知", "role": "订阅消息提醒", "icon": "bell"}]}],
            "flows": [{"from": "U1", "to": "S1", "n": 1}, {"from": "U2", "to": "S2", "n": 2}, {"from": "U3", "to": "S3", "n": 3}, {"from": "S1", "to": "B1", "n": 4}, {"from": "S2", "to": "B2", "n": 5}]}}]}]}


def manual(chapter_features: dict[str, list[str]]) -> dict:
    chapters = []
    for index, (heading, ids) in enumerate(chapter_features.items(), 1):
        chapters.append({"id": f"CH-{index:02d}", "heading": heading, "features": ids, "entry": "小程序首页 > 对应入口", "steps": [f"打开「{heading}」入口", "按页面提示填写并提交", "在结果页确认状态"], "rules": ["以功能清单中的业务规则为准", "操作后可在记录中查看结果"],
                         "states": [{"name": "处理中", "meaning": "系统正在处理", "next": "等待结果"}], "faq": [{"q": f"{heading}失败怎么办？", "a": "按页面提示重试，仍失败请联系门店客服"}]})
    return {"title": "示例健身使用说明", "intro": {"paragraphs": ["本说明介绍各角色如何使用系统完成日常工作。"], "bullets": ["首次使用请先完成登录"]}, "roles": [{"name": "顾客", "desc": "预约与积分"}, {"name": "店长", "desc": "管理与报表"}], "chapters": chapters, "glossary": [{"term": "核销", "meaning": "到店后确认预约已使用"}], "support": {"联系电话": "门店前台", "服务时间": "每日 9:00–21:00"}}


def write_all(root: Path, theme: str = "fitness-gym") -> None:
    requirements_provided(root)
    cd.save(root, features(), "client", "features.json")
    cd.save(root, proposal(), "client", "proposal.json")
    cd.save(root, architecture(), "client", "architecture.json")
    cd.save(root, {"questions": [
        {"category": "预约规则 · 取消", "item": "预约取消", "kind": "logic", "example": "开课前 2 小时可取消，之后不能取消", "why": "决定顾客能否取消和何时截止"},
        {"category": "预约规则 · 爽约", "item": "爽约处理", "kind": "logic", "example": "爽约 3 次限制预约 7 天", "why": "防止占位不到"},
        {"category": "上线资料 · 小程序", "item": "小程序 AppID", "example": "wx1234567890abcdef", "why": "绑定开发和发布的账号"}]}, "client", "intake-extra.json")
    import client_flow
    client_flow.set_theme(root, theme)


def fill_intake(path: Path, root: Path | None = None) -> Path:
    """Fill the form the way a client would: pass the proposed logic (or decline a function), answer what is required (test helper)."""
    from openpyxl import load_workbook

    wb = load_workbook(path)
    for ws in wb.worksheets:
        header_row = next(r for r in range(1, 8) if any(c.value in ("业务逻辑", "需要提供的内容") for c in ws[r]))
        idx = {c.value: c.column for c in ws[header_row]}
        item_col = idx.get("业务逻辑") or idx["需要提供的内容"]
        for r in range(header_row + 1, ws.max_row + 1):
            item = str(ws.cell(r, item_col).value or "")
            if "审核结果" in idx:
                if item.endswith("会员等级"):
                    ws.cell(r, idx["审核结果"]).value = "需要"
                elif item.endswith(("绩效核算", "对话式经营查询")):
                    ws.cell(r, idx["审核结果"]).value = "不需要"
            elif ws.cell(r, idx["必填"]).value == "必填":
                ws.cell(r, idx["客户填写"]).value = "已填写（测试）"
    out = path.with_name("filled.xlsx")
    wb.save(out)
    return out


def crawled(root: Path, *stages: str) -> None:
    """Offline Crawl preflight fixtures for the stages whose documents a test generates (never a live search)."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Luz-Crawl" / "scripts"))
    from test_crawl_preflight import complete_fixture
    from project_core import _stage_record, load_project

    for stage in stages:
        complete_fixture(root, _stage_record(load_project(root), stage)["owner"], stage)


def prepare(root: Path, stage: str) -> None:
    """Produce the real client deliverables a stage needs before approval (offline rehearsal only)."""
    import client_flow as cf

    if stage == "requirements":
        requirements_provided(root)
    elif stage == "proposal":
        write_all(root)
        cf.build_proposal(root)
    elif stage == "client-intake":
        cf.import_intake(root, fill_intake(cf.build_intake_form(root)))
    elif stage == "handover":
        features = cd.load_features(root)
        checklist = cf.generate_acceptance(root)
        for item in checklist["items"]:
            if item["status"] != "waived":
                item.update({"status": "passed", "signed_by": "验收人（测试）", "signed_at": "2026-11-02"})
        cd.save(root, checklist, "acceptance", "checklist.json")
        cf.build_acceptance_xlsx(root)
        scoped = cf.effective_features(root, features)
        names = {m["name"]: [f["id"] for f in scoped if f["module"] == m["id"]] for m in features["modules"]}
        cd.save(root, manual({k: v for k, v in names.items() if v}), "client", "manual.json")
        cf.build_manual(root)
        for c in cf._ledger(root)["changes"]:
            if c["status"] == "已确认":
                cf.update_change(root, c["id"], status="已实施")
        cf.snapshot_ledger(root)
