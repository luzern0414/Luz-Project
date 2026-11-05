import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import client_fixture as fx
import dev_documents as dd
import dev_fixture
from client_fixture import new_project
from project_paths import locate
from project_core import create_project, ProjectError
from stage_documents import write_document


def architecture_spec(root):
    return dev_fixture.sample_spec("architecture", root)


def find_tab(spec, title):
    return next(t for t in spec["tabs"] if t["title"] == title)


def find_block(spec, kind):
    return next(b for t in spec["tabs"] for s in t["sections"] for b in s["blocks"] if b["type"] == kind)


class DocumentTests(unittest.TestCase):
    def test_a_stage_page_is_not_written_before_the_stage_has_crawled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("先检索", tmp)
            with self.assertRaises(ProjectError) as refused:
                write_document(root, "architecture", architecture_spec(root))
            self.assertIn("Crawl", str(refused.exception))
            self.assertFalse((locate(root, "docs") / "02-产品开发" / "01-系统架构.html").exists())
            self.assertFalse((root / "data" / "stages" / "architecture.json").exists())

    def test_a_tabbed_document_is_one_page_with_top_tabs_baseline_tables_and_function_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("架构", tmp)
            fx.crawled(root, "architecture")
            path = write_document(root, "architecture", architecture_spec(root))
            self.assertEqual(path.name, "01-系统架构.html")
            page = path.read_text(encoding="utf-8")
            import re
            self.assertTrue(re.search(r"<h2[^>]*>结论</h2>", page).start() < page.index('<div class="tabs" role="tablist"'))        # 结论在最前，标签栏在它后面
            self.assertEqual(page.count('class="tabs"'), 1)
            for name in ("技术栈", "总体架构", "功能与技术方案", "决策与质量"):
                self.assertIn(f">{name}</button>", page)
            self.assertIn('class="base"', page)                                              # 底座对照表
            self.assertIn("article class=\"fn\"", page)                                      # 功能卡
            self.assertIn("沿用", page)
            self.assertIn("aria-selected", page)
            self.assertIn("hidden", page)                                                    # 非当前标签页的面板在页面里，但先隐藏
            self.assertIn("@media print", page)                                              # 打印时全部展开
            self.assertGreaterEqual(page.count('role="img"'), 3)
            self.assertIn("检索来源与采用位置", page)
            data = json.loads((root / "data" / "artifacts.json").read_text(encoding="utf-8"))
            self.assertTrue(any(a["kind"] == "architecture-spec" for a in data))

    def test_the_standard_refuses_what_it_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = dev_fixture.sample_spec("technical-plan", root)
            self.assertEqual(dd.validate("technical-plan", good, root), [])

            def drop_tab(s):
                s["tabs"].pop(2)

            def swap_tabs(s):
                s["tabs"][0], s["tabs"][1] = s["tabs"][1], s["tabs"][0]

            def drop_table(s):
                find_tab(s, "接口")["sections"][1]["blocks"].pop(1)

            def placeholder(s):
                find_tab(s, "技术架构")["sections"][0]["blocks"].append({"type": "text", "text": "这里待补充"})

            def no_caption(s):
                find_tab(s, "接口")["sections"][0]["blocks"][1].pop("caption")

            def wrong_layout(s):
                find_tab(s, "接口")["layout"] = "subtabs"

            def short_conclusion(s):
                s["conclusion"] = "太短"

            cases = {"标签页必须依次是": drop_tab, "标签页必须依次是 ": swap_tabs, "至少要有": drop_table, "占位": placeholder, "没有表题": no_caption, "layout 必须是": wrong_layout, "结论至少": short_conclusion}
            for needle, mutate in cases.items():
                spec = copy.deepcopy(good)
                mutate(spec)
                errors = dd.validate("technical-plan", spec, root)
                self.assertTrue(any(needle.strip() in e for e in errors), (needle, errors))

    def test_a_baseline_table_must_account_for_every_mandatory_item_and_explain_every_change(self):
        import baseline as bl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = dev_fixture.sample_spec("architecture", root)
            self.assertEqual(dd.validate("architecture", good, root), [])
            block = find_block(good, "baseline")
            first = block["rows"][0]["id"]

            spec = copy.deepcopy(good)
            find_block(spec, "baseline")["rows"].pop(0)
            self.assertTrue(any(first in e and "漏了" in e for e in dd.validate("architecture", spec, root)))

            spec = copy.deepcopy(good)
            find_block(spec, "baseline")["rows"][0].update({"status": "调整", "value": "另一个取值"})
            self.assertTrue(any("理由" in e for e in dd.validate("architecture", spec, root)))     # 调整没有理由

            spec = copy.deepcopy(good)
            find_block(spec, "baseline")["rows"][0].update({"status": "调整", "value": "另一个取值", "reason": "客户的运维团队只维护这一种"})
            self.assertEqual(dd.validate("architecture", spec, root), [])

            spec = copy.deepcopy(good)
            find_block(spec, "baseline")["rows"].append({"id": "STK-ZZ-99", "status": "沿用"})
            self.assertTrue(any("STK-ZZ-99" in e for e in dd.validate("architecture", spec, root)))

            spec = copy.deepcopy(good)
            find_block(spec, "baseline")["rows"].append({"id": "X-自有项", "name": "自有项", "status": "新增", "value": "项目自己加的做法", "reason": "客户要求"})
            self.assertEqual(dd.validate("architecture", spec, root), [])
            self.assertTrue(bl.item(first))

    def test_the_document_agrees_with_the_projects_own_baseline_statement(self):
        import baseline as bl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = dev_fixture.sample_spec("architecture", root)
            self.assertEqual(dd.validate("architecture", spec, root), [])       # no statement file: nothing to compare with
            statement = {"stack": {}, "frontend": {}, "modules": {m["id"]: {"status": "沿用"} for m in bl.functions()["modules"]}}
            for kind, getter in (("stack", bl.stack_items), ("frontend", bl.frontend_items)):
                statement[kind] = {i["id"]: {"status": "沿用"} for i in getter()}
            (root / "data").mkdir(exist_ok=True)
            path = root / "data" / "baseline.json"
            path.write_text(json.dumps(statement, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(dd.validate("architecture", spec, root), [])
            row = find_block(spec, "baseline")["rows"][0]
            statement["stack"][row["id"]] = {"status": "不用", "reason": "项目里没有这个能力，数据量很小"}
            path.write_text(json.dumps(statement, ensure_ascii=False), encoding="utf-8")
            errors = dd.validate("architecture", spec, root)
            self.assertTrue(any(row["id"] in e and "data/baseline.json" in e for e in errors), errors)
            del statement["modules"][next(iter(statement["modules"]))]           # the statement itself is incomplete
            path.write_text(json.dumps(statement, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(any("基础功能模块" in e for e in dd.validate("architecture", spec, root)))

    def test_every_function_of_the_project_has_one_card_in_the_sub_tab_of_its_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("功能", tmp)
            data = {"modules": [{"id": "M01", "name": "登录"}, {"id": "M02", "name": "订单"}],
                    "features": [{"id": "FN-001", "module": "M01", "name": "微信登录", "surface": "miniprogram"}, {"id": "FN-002", "module": "M02", "name": "下单", "surface": "miniprogram"}]}
            (root / "data" / "client").mkdir(parents=True, exist_ok=True)
            (root / "data" / "client" / "features.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            good = dev_fixture.sample_spec("architecture", root)
            self.assertEqual(dd.validate("architecture", good, root), [])
            spec = copy.deepcopy(good)
            tab = find_tab(spec, "功能与技术方案")
            tab["sections"][1]["blocks"] = [b for b in tab["sections"][1]["blocks"] if b["type"] != "function"]
            errors = dd.validate("architecture", spec, root)
            self.assertTrue(any("FN-002" in e for e in errors), errors)
            spec = copy.deepcopy(good)
            tab = find_tab(spec, "功能与技术方案")
            moved = [b for b in tab["sections"][0]["blocks"] if b["type"] == "function"][0]
            tab["sections"][1]["blocks"].append(copy.deepcopy(moved))
            errors = dd.validate("architecture", spec, root)
            self.assertTrue(any("出现了两次" in e or "放在了子标签" in e for e in errors), errors)
            spec = copy.deepcopy(good)
            find_tab(spec, "功能与技术方案")["sections"][0]["title"] = "别的名字"
            self.assertTrue(any("features.json 的模块" in e for e in dd.validate("architecture", spec, root)))

    def test_a_removed_function_needs_no_card_and_its_module_and_surface_drop_out_with_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("拿掉的功能", tmp)
            data = {"modules": [{"id": "M01", "name": "登录"}, {"id": "M02", "name": "订单"}, {"id": "M03", "name": "小程序提醒"}],
                    "features": [{"id": "FN-001", "module": "M01", "name": "账号登录", "surface": "web-admin"}, {"id": "FN-002", "module": "M02", "name": "下单", "surface": "web-admin"},
                                 {"id": "FN-003", "module": "M02", "name": "查看登录记录", "surface": "web-admin", "status": "removed"},
                                 {"id": "FN-004", "module": "M03", "name": "订阅提醒", "surface": "miniprogram", "status": "removed"}]}
            (root / "data" / "client").mkdir(parents=True, exist_ok=True)
            (root / "data" / "client" / "features.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            ctx = dd.project_context(root)
            self.assertEqual([f["id"] for f in ctx["features"]], ["FN-001", "FN-002"])
            self.assertEqual([m["id"] for m in ctx["modules"]], ["M01", "M02"], "没有一个在用功能的模块不再要子标签")
            self.assertEqual(ctx["surfaces"], {"web-admin"}, "只有被拿掉的功能用的使用端，不要求这个端的页签和底座层")
            spec = dev_fixture.sample_spec("architecture", root)
            self.assertEqual([s["title"] for s in find_tab(spec, "功能与技术方案")["sections"]], ["登录", "订单"])
            self.assertEqual(dd.validate("architecture", spec, root), [])
            card = {"type": "function", "id": "FN-003", "name": "查看登录记录", "system": "电脑浏览器", "module": "订单", "summary": "不再做的功能"}
            find_tab(spec, "功能与技术方案")["sections"][1]["blocks"].append(dict(next(b for b in find_tab(spec, "功能与技术方案")["sections"][1]["blocks"] if b["type"] == "function"), **card))
            self.assertTrue(any("FN-003" in e and "不在 features.json 里" in e for e in dd.validate("architecture", spec, root)), "拿掉的功能不应再有卡")

    def test_a_function_card_needs_real_text_and_a_valid_baseline_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = dev_fixture.sample_spec("architecture", root)
            cases = {
                "太短": lambda b: b.update({"backend": "太短"}),
                "inherits": lambda b: b.update({"inherits": "BF-NOPE-01"}),
                "change": lambda b: b.update({"status": "调整"}),
                "新增": lambda b: b.update({"status": "新增"}),
                "占位": lambda b: b.update({"tech": b["tech"] + "待补充"}),
                "测试": lambda b: b.update({"tests": []}),
            }
            for needle, mutate in cases.items():
                spec = copy.deepcopy(good)
                mutate(find_block(spec, "function"))
                errors = dd.validate("architecture", spec, root)
                self.assertTrue(any(needle in e for e in errors), (needle, errors))
            spec = copy.deepcopy(good)
            find_block(spec, "function").update({"status": "新增", "inherits": ""})
            self.assertEqual(dd.validate("architecture", spec, root), [])

    def test_every_figure_kind_draws_readable_text_inside_its_canvas(self):
        import re
        figures = {
            "layers": {"caption": "分层", "rows": [{"label": "使用端", "nodes": [{"name": "小程序", "note": "员工在微信里打开"}, {"name": "后台", "note": "网页"}]},
                                                {"label": "后端", "nodes": [{"name": "服务", "note": "业务规则与鉴权，带一段比较长的说明文字用来换行"}]}], "links": [{"after": 0, "label": "HTTPS"}]},
            "steps": {"caption": "步骤", "per_row": 3, "steps": [{"name": f"第{i}步", "note": "做一件事并说明结果"} for i in range(1, 6)]},
            "sequence": {"caption": "时序", "actors": ["甲", "乙", "丙"], "messages": [{"from": 0, "to": 1, "label": "请求"}, {"from": 1, "to": 1, "label": "校验"}, {"from": 2, "to": 0, "label": "回复"}]},
            "grid": {"caption": "关系", "nodes": [{"id": "a", "name": "表甲", "note": "说明", "col": 0, "row": 0}, {"id": "b", "name": "表乙", "note": "说明", "col": 1, "row": 0}], "links": [{"from": "a", "to": "b", "label": "属于"}]},
        }
        for kind, spec in figures.items():
            with self.subTest(kind=kind):
                svg = dd.FIGURE_FUNCS[kind]({"kind": kind, **spec})
                self.assertIn('role="img"', svg)
                self.assertEqual(dd._figure_errors("x", {"kind": kind, **spec}), [])
                sizes = [int(s) for s in re.findall(r'font-size="(\d+)"', svg)]
                self.assertTrue(sizes and min(sizes) >= 14, sizes)
                width, height = [float(v) for v in re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups()]
                for x, y in re.findall(r'<text[^>]* x="([\d.]+)" y="([\d.]+)"', svg):
                    self.assertTrue(0 <= float(x) <= width and 0 <= float(y) <= height, (x, y, width, height))

    def test_a_document_that_fails_the_standard_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("缺失", tmp)
            fx.crawled(root, "architecture")
            spec = architecture_spec(root)
            spec["tabs"] = spec["tabs"][:2]
            with self.assertRaises(ProjectError):
                write_document(root, "architecture", spec)
            self.assertFalse((locate(root, "docs") / "02-产品开发" / "01-系统架构.html").exists())

    def test_the_design_document_has_the_frontend_foundation_first_then_one_tab_per_frontend_with_only_its_prototype(self):
        std = dd.STANDARDS["design"]["tabs"]
        self.assertEqual([t["title"] for t in std], ["前端规范", "前端名称", "检查与差异"])      # 中间一项是模板：每个前端一个页签
        self.assertTrue(std[1]["frontend"])
        self.assertEqual(std[0]["layout"], "subtabs")
        import baseline as bl
        self.assertEqual([s["title"] for s in std[0]["sections"]], list(bl.FRONTEND_CATEGORIES.values()) + ["页面与路径"])     # 十三类底座分类，加一个放所有路径的子标签
        self.assertEqual([t["title"] for t in dd.expected_tabs("design", None)], ["前端规范", "小程序", "管理后台", "检查与差异"])
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("界面", tmp)
            fx.crawled(root, "design")
            spec = dev_fixture.sample_spec("design", root)
            self.assertEqual(dd.validate("design", spec, root), [])
            page = write_document(root, "design", spec).read_text(encoding="utf-8")
            self.assertEqual(page.count("<iframe"), 2)                       # 小程序与后台各一个
            self.assertEqual(page.count("data-src="), 2)                     # 切到那个标签页才加载，隐藏时宽度为零的页面不会画错
            self.assertIn('data-src="03-proto1.html"', page)                 # 相对文档所在目录，文件夹整体搬走也能打开
            self.assertIn("在新窗口打开", page)
            self.assertIn("重新载入", page)
            self.assertLess(page.index(">前端规范<"), page.index(">小程序<"))
            self.assertLess(page.index(">小程序<"), page.index(">管理后台<"))
            for gone in ("<img", "<figure", "<figcaption", "可以这样试", "真实界面"):
                self.assertNotIn(gone, page.split("<h2>来源与依据</h2>")[0], gone)
            for index in (1, 2):                                             # a front end tab holds the prototype frame and nothing else
                panel = re.search(rf'<div role="tabpanel" id="d1-p{index}"[^>]*>(.*?)</div></div>', page, flags=re.S).group(1)
                self.assertEqual(panel.count("<iframe"), 1)
                for gone in ("<h2", "<h3", "<p", "<table", "<ul", "<img", "<figcaption"):
                    self.assertNotIn(gone, panel)
            self.assertIn(">页面与路径<", page)                               # every path is in 前端规范
            self.assertIn("docs/02-产品开发/03-proto1.html", page)
            self.assertIn("docs/02-产品开发/04-proto2.html", page)
            self.assertIn("导航结构", page)
            self.assertIn("检索来源与采用位置", page)                          # 来源与依据 stays at the end of the document, out of the tabs

    def test_a_surface_the_project_does_not_have_gets_no_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "client").mkdir(parents=True)
            (root / "data" / "client" / "features.json").write_text(json.dumps({"modules": [{"id": "M01", "name": "登录"}], "features": [{"id": "FN-001", "module": "M01", "name": "登录", "surface": "miniprogram"}]}, ensure_ascii=False), encoding="utf-8")
            ctx = dd.project_context(root)
            self.assertEqual([t["title"] for t in dd.expected_tabs("design", ctx)], ["前端规范", "小程序", "检查与差异"])
            spec = dev_fixture.sample_spec("design", root)
            self.assertEqual(dd.validate("design", spec, root), [])

    def test_a_prototype_that_is_a_stub_or_a_picture_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = dev_fixture.sample_spec("design", root)
            block = find_block(spec, "prototype")
            file = root / block["file"]
            good = file.read_text(encoding="utf-8")
            cases = {
                "只有框架没有内容": lambda: file.write_text("<title>x</title>", encoding="utf-8"),
                "减少动态效果": lambda: file.write_text(good.replace("prefers-reduced-motion", "x"), encoding="utf-8"),
                "没有对话框": lambda: file.write_text(good.replace("showModal", "x"), encoding="utf-8"),
                "场景配置面板": lambda: file.write_text(good.replace("UI.demo(", "x("), encoding="utf-8"),
                "不写 try": lambda: block.update({"try": ["点一", "点二", "点三"]}),         # 页签里只显示原型本身
                "不写 caption": lambda: block.update({"caption": "图题"}),
                "文件不存在": lambda: file.unlink(),
            }
            for needle, mutate in cases.items():
                file.write_text(good, encoding="utf-8")
                block.pop("try", None)
                block.pop("caption", None)
                mutate()
                errors = dd.validate("design", spec, root)
                self.assertTrue(any(needle in e for e in errors), (needle, errors))
            file.write_text(good, encoding="utf-8")
            self.assertEqual(dd.validate("design", spec, root), [])
            file.write_text(good.replace("showModal", "role: 'dialog'").replace("UI.demo(", "K.panel("), encoding="utf-8")     # 上一代原型的写法同样被接受
            self.assertEqual(dd.validate("design", spec, root), [])

    def test_a_prototype_must_name_its_component_library_and_really_use_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = dev_fixture.sample_spec("design", root)
            block = find_block(spec, "prototype")
            file = root / block["file"]
            good = file.read_text(encoding="utf-8")
            self.assertEqual(block["library"], "vant")
            cases = {
                "要写 library": lambda: block.pop("library"),
                "不在组件库注册表里": lambda: block.update({"library": "my-own-kit"}),         # not in the registry
                "换一个适合这一端的库": lambda: block.update({"library": "element-plus"}),    # a web admin library on a phone prototype
                "种 Vant 的组件": lambda: file.write_text(good.replace("van-", "xx-"), encoding="utf-8"),   # the library's style sheet is not the library
            }
            for needle, mutate in cases.items():
                block["library"] = "vant"
                file.write_text(good, encoding="utf-8")
                mutate()
                errors = dd.validate("design", spec, root)
                self.assertTrue(any(needle in e for e in errors), (needle, errors))
            block["library"] = "vant"
            file.write_text(good, encoding="utf-8")
            self.assertEqual(dd.validate("design", spec, root), [])
            block["kind"] = "wide"                                                         # the same file declared as a web admin prototype
            self.assertTrue(any("换一个适合这一端的库" in e for e in dd.validate("design", spec, root)))

    def test_every_library_of_the_registry_is_complete_and_its_components_are_counted_by_prefix(self):
        libs = dd.component_libraries()
        self.assertGreaterEqual(len(libs), 8)
        for key, lib in libs.items():
            for field in ("name", "stack", "surfaces", "prefix", "theme", "license", "docs", "fit"):
                self.assertTrue(lib.get(field), (key, field))
            self.assertTrue(set(lib["surfaces"]) <= {"admin", "website", "h5", "miniapp"}, key)
            # a library that marks its components with an attribute (luz-kit: data-cid) names root classes such as mpcard, with no hyphen
            self.assertTrue(lib.get("attr") or all(pre.endswith("-") for pre in lib["prefix"]), key)
        self.assertTrue(any("miniapp" in lib["surfaces"] for lib in libs.values()))
        self.assertTrue(any("admin" in lib["surfaces"] for lib in libs.values()))
        found = dd.library_components("<div class='el-card__body el-button--primary'><t-button/><el-x></el-x> my-el-foo el-input__inner", ["el-"])
        self.assertEqual(found, {"el-card", "el-button", "el-x", "el-input"})            # modifiers are cut, a name that merely contains the prefix is not counted

    def test_the_old_review_page_is_replaced_by_the_numbered_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("改名", tmp)
            fx.crawled(root, "requirements")
            from project_core import register_artifact
            old = root / "reviews" / "requirements-review.html"
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text("<html>旧页面</html>", encoding="utf-8")
            register_artifact(root, "requirements", old, "html", [])
            spec = {"title": "需求对接", "conclusion": "客户要一个预约系统，范围与目标已写清楚。", "sections": [{"title": "目标", "content": "预约、排课汇总、扫码核销。"}],
                    "sources": [{"id": "SRC-001", "url": "https://example.org/a", "finding": "示例", "applies_to": "目标"}]}
            path = write_document(root, "requirements", spec)
            self.assertEqual(path.parent.as_posix().endswith("raw/reviews"), True)
            self.assertEqual(path.name, "01-需求评审.html")
            self.assertFalse(old.exists())
            data = json.loads((root / "data" / "artifacts.json").read_text(encoding="utf-8"))
            self.assertFalse(any(str(a.get("path", "")).endswith("requirements-review.html") for a in data))

    def test_a_review_page_section_can_carry_titled_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("评审页表格", tmp)
            fx.crawled(root, "research")
            blocks = [{"type": "text", "text": "三款同类产品都把拜访记录放在客户的时间线上。"},
                      {"type": "table", "caption": "同类产品对比", "columns": ["产品", "记录内容"], "rows": [["甲", "时间、联系人、沟通内容"], ["乙", "时间、结果、备注"]]},
                      {"type": "bullets", "items": ["只看官方帮助页", "不看第三方转述"]}]
            spec = {"title": "调研结论", "conclusion": "同类产品的做法一致，可以照此设计。", "sections": [{"title": "同类产品", "blocks": blocks}, {"title": "其他", "content": "没有其他。"}],
                    "sources": [{"id": "SRC-001", "url": "https://example.org/a", "finding": "示例", "applies_to": "同类产品"}]}
            page = write_document(root, "research", spec).read_text(encoding="utf-8")
            self.assertIn("表 1　同类产品对比", page)
            self.assertIn("表 2　检索来源与采用位置", page)
            self.assertIn("<li>只看官方帮助页</li>", page)
            for bad in ({"type": "table", "caption": "", "columns": ["产品"], "rows": [["甲"]]},
                        {"type": "table", "caption": "空格", "columns": ["产品", "内容"], "rows": [["甲", ""]]},
                        {"type": "image", "file": "x.png"}):
                with self.assertRaises(ProjectError):
                    write_document(root, "research", {**spec, "sections": [{"title": "同类产品", "blocks": [bad]}]})


def design_project(tmp, surfaces):
    """A project folder that only has a function list with the given surfaces (the design document reads nothing else of it)."""
    root = Path(tmp)
    (root / "data" / "client").mkdir(parents=True, exist_ok=True)
    feats = [{"id": f"FN-{n + 1:03d}", "module": "M01", "name": f"功能{n + 1}", "surface": surface} for n, surface in enumerate(surfaces)]
    (root / "data" / "client" / "features.json").write_text(json.dumps({"modules": [{"id": "M01", "name": "登录"}], "features": feats}, ensure_ascii=False), encoding="utf-8")
    return root


class FrontendTabsTests(unittest.TestCase):
    """The design document: 前端规范 + one tab per system or device + 检查与差异; a front end tab is one prototype and nothing else."""

    PHONE_AND_ADMIN = [("手机页", "web-admin", "phone"), ("管理后台", "web-admin", "wide")]

    def titles(self, spec):
        return [t["title"] for t in spec["tabs"]]

    def test_the_tabs_follow_the_front_ends_the_spec_declares_not_only_the_surfaces_of_the_function_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin", "web-admin"])               # a phone page and an admin page are both web-admin
            spec = dev_fixture.sample_spec("design", root, self.PHONE_AND_ADMIN)
            self.assertEqual(self.titles(spec), ["前端规范", "手机页", "管理后台", "检查与差异"])
            self.assertEqual(dd.validate("design", spec, root), [])
            self.assertEqual([t["title"] for t in dd.expected_tabs("design", dd.project_context(root), spec)], self.titles(spec))
            only_admin = dev_fixture.sample_spec("design", root)                 # the default for a project that has only a web admin: three tabs
            self.assertEqual(self.titles(only_admin), ["前端规范", "管理后台", "检查与差异"])
            self.assertEqual(dd.validate("design", only_admin, root), [])
            tablet = dev_fixture.sample_spec("design", root, self.PHONE_AND_ADMIN + [("平板页", "web-admin", "phone")])
            self.assertEqual(self.titles(tablet), ["前端规范", "手机页", "管理后台", "平板页", "检查与差异"])     # a device end gets its own tab
            self.assertEqual(dd.validate("design", tablet, root), [])

    def test_a_project_with_a_mini_program_and_an_admin_has_four_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["miniprogram", "web-admin"])
            spec = dev_fixture.sample_spec("design", root)
            self.assertEqual(self.titles(spec), ["前端规范", "小程序", "管理后台", "检查与差异"])
            self.assertEqual(dd.validate("design", spec, root), [])
            spec["tabs"].pop(1)                                                  # the mini program has functions but no tab
            errors = dd.validate("design", spec, root)
            self.assertTrue(any("miniprogram" in e and "前端页签" in e for e in errors), errors)

    def test_the_classic_tab_names_need_no_surface_but_a_new_name_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin"])
            spec = dev_fixture.sample_spec("design", root)
            del spec["tabs"][1]["surface"]                                       # 管理后台 is inferred as web-admin
            self.assertEqual(dd.validate("design", spec, root), [])
            spec["tabs"][1]["title"] = "后台"
            errors = dd.validate("design", spec, root)
            self.assertTrue(any("要写 surface" in e for e in errors), errors)
            spec["tabs"][1]["surface"] = "kiosk"
            self.assertTrue(any("surface 无效" in e for e in dd.validate("design", spec, root)))
            spec["tabs"][1]["surface"] = "miniprogram"
            self.assertTrue(any("没有这种使用端" in e for e in dd.validate("design", spec, root)))     # the project has no mini program

    def test_a_front_end_tab_holds_one_prototype_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin"])
            tab = lambda spec: spec["tabs"][1]
            blocks = lambda spec: tab(spec)["sections"][0]["blocks"]
            cases = {
                "不放截图": lambda spec: blocks(spec).append({"type": "image", "file": "raw/x.png", "alt": "后台首页截图", "caption": "后台首页"}),
                "不放表": lambda spec: blocks(spec).append(dev_fixture.table("后台导航与页面")),
                "不放说明文字": lambda spec: blocks(spec).insert(0, {"type": "text", "text": "两个端各一个原型"}),
                "不放图": lambda spec: blocks(spec).append(dev_fixture.figure("后台结构")),
                "有 2 个原型": lambda spec: blocks(spec).append(dev_fixture.prototype(root, "另一个", "proto8", "wide")),
                "不同设备端各开一个页签": lambda spec: blocks(spec).append(dev_fixture.prototype(root, "另一个", "proto8", "wide")),
                "只有一个章节": lambda spec: tab(spec)["sections"].append({"title": "后台真实界面", "blocks": [dev_fixture.table("页面清单")]}),
                "缺少可交互原型": lambda spec: blocks(spec).clear(),
                "不写 caption": lambda spec: blocks(spec)[0].update({"caption": "图 1　后台"}),
                "不写 try": lambda spec: blocks(spec)[0].update({"try": ["点一", "点二", "点三"]}),
                "不写 source": lambda spec: blocks(spec)[0].update({"source": "https://example.org"}),
                "layout 必须是 frontend": lambda spec: tab(spec).update({"layout": "sections"}),
            }
            for needle, mutate in cases.items():
                spec = dev_fixture.sample_spec("design", root)
                mutate(spec)
                errors = dd.validate("design", spec, root)
                self.assertTrue(any(needle in e for e in errors), (needle, errors))

    def test_screenshots_and_prototypes_have_no_place_outside_a_front_end_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin"])
            spec = dev_fixture.sample_spec("design", root)
            spec["tabs"][0]["sections"][0]["blocks"].append({"type": "image", "file": "raw/x.png", "alt": "后台首页截图", "caption": "后台首页"})
            self.assertTrue(any("前端界面设计不放截图" in e for e in dd.validate("design", spec, root)))
            spec = dev_fixture.sample_spec("design", root)
            spec["tabs"][0]["sections"][0]["blocks"].append(dev_fixture.prototype(root, "多出的", "proto8", "wide"))
            self.assertTrue(any("原型只放在各自的前端页签" in e for e in dd.validate("design", spec, root)))
            spec = dev_fixture.sample_spec("design", root)
            spec["tabs"][-1]["sections"][0]["blocks"].append({"type": "text", "text": "每页都有真实截图作对照。"})
            self.assertTrue(any("不再写截图" in e for e in dd.validate("design", spec, root)))     # 检查与差异 does not talk about screenshots either
            spec = dev_fixture.sample_spec("design", root)
            spec["tabs"][1]["sections"] = [                                      # the structure of the older standard
                {"title": "后台原型", "blocks": [dev_fixture.prototype(root, "后台", "proto9", "wide")]},
                {"title": "后台导航与页面", "blocks": [dev_fixture.table("按角色的导航"), dev_fixture.table("页面清单")]},
                {"title": "后台真实界面", "blocks": [{"type": "image", "file": "raw/x.png", "alt": "后台首页截图", "caption": "后台首页"}]}]
            errors = dd.validate("design", spec, root)
            self.assertTrue(any("只有一个章节" in e for e in errors) and any("截图" in e and "表" in e for e in errors), errors)

    def test_every_path_is_written_in_the_frontend_standard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin", "web-admin"])
            good = dev_fixture.sample_spec("design", root, self.PHONE_AND_ADMIN)
            paths = lambda spec: next(s for s in spec["tabs"][0]["sections"] if s["title"] == "页面与路径")
            parts = lambda spec: paths(spec)["blocks"]
            cases = {
                "要有一节「手机页」": lambda spec: paths(spec).update({"blocks": [b for b in parts(spec) if b.get("text") != "手机页"]}),
                "至少要有 2 张表": lambda spec: paths(spec).update({"blocks": [b for b in parts(spec) if b.get("caption") != "管理后台的导航结构"]}),
                "要有“路径”列": lambda spec: [b.update({"columns": ["地址", "页面", "作用"]}) for b in parts(spec) if b.get("caption") == "手机页的页面清单"],
                "没有写原型文件路径": lambda spec: [b.update({"text": "原型文件见下"}) for b in parts(spec) if str(b.get("text", "")).startswith("原型文件")],
            }
            for needle, mutate in cases.items():
                spec = copy.deepcopy(good)
                mutate(spec)
                errors = dd.validate("design", spec, root)
                self.assertTrue(any(needle in e for e in errors), (needle, errors))
            spec = copy.deepcopy(good)
            spec["tabs"][0]["sections"] = [s for s in spec["tabs"][0]["sections"] if s["title"] != "页面与路径"]
            self.assertTrue(any("章节必须依次是" in e and "页面与路径" in e for e in dd.validate("design", spec, root)))
            spec = copy.deepcopy(good)
            spec["tabs"][2]["sections"][0]["blocks"][0]["file"] = spec["tabs"][1]["sections"][0]["blocks"][0]["file"]
            self.assertTrue(any("同一个原型文件" in e for e in dd.validate("design", spec, root)))

    def test_the_document_is_refused_without_a_front_end_or_with_the_wrong_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin"])
            spec = dev_fixture.sample_spec("design", root)
            for mutate in (lambda s: s["tabs"].pop(1), lambda s: s["tabs"].reverse(), lambda s: s["tabs"].insert(1, copy.deepcopy(s["tabs"][1]))):
                bad = copy.deepcopy(spec)
                mutate(bad)
                errors = dd.validate("design", bad, root)
                self.assertTrue(any("标签页必须依次是" in e or "不能重复" in e for e in errors), errors)

    def test_the_sources_stay_at_the_end_of_the_document_and_are_still_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = design_project(tmp, ["web-admin"])
            spec = dev_fixture.sample_spec("design", root)
            spec["sources"] = spec["sources"][:1]
            self.assertTrue(any("来源与依据至少 2 条" in e for e in dd.validate("design", spec, root)))
            spec = dev_fixture.sample_spec("design", root)
            page = dd.render_body(spec, root)
            self.assertGreater(page.index("来源与依据"), page.rindex('role="tabpanel"'))


class StackBySurfaceTests(unittest.TestCase):
    def project(self, tmp, name, surfaces):
        root = Path(tmp) / name
        (root / "data" / "client").mkdir(parents=True)
        feats = [{"id": f"FN-{n + 1:03d}", "module": "M01", "name": f"功能{n + 1}", "surface": surface} for n, surface in enumerate(surfaces)]
        (root / "data" / "client" / "features.json").write_text(json.dumps({"modules": [{"id": "M01", "name": "登录"}], "features": feats}, ensure_ascii=False), encoding="utf-8")
        return root

    def layers(self, ctx):
        stack = dd.expected_tabs("architecture", ctx)[0]
        return [s["title"] for s in stack["sections"]]

    def test_the_stack_tab_of_a_project_without_a_mini_program_has_no_mini_program_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = self.project(tmp, "web", ["web-admin"])
            both = self.project(tmp, "both", ["miniprogram", "web-admin"])
            self.assertNotIn("小程序前端", self.layers(dd.project_context(web)))
            self.assertIn("管理后台前端", self.layers(dd.project_context(web)))
            self.assertIn("小程序前端", self.layers(dd.project_context(both)))
            self.assertIn("小程序前端", self.layers(None))                      # no function list yet: the full standard
            spec = dev_fixture.sample_spec("architecture", web)
            self.assertNotIn("小程序前端", [s["title"] for s in find_tab(spec, "技术栈")["sections"]])
            self.assertEqual(dd.validate("architecture", spec, web), [])
            full = dev_fixture.sample_spec("architecture", both)
            self.assertEqual(dd.validate("architecture", full, both), [])
            errors = dd.validate("architecture", full, web)                    # a document that still has the layer is refused
            self.assertTrue(any("小程序前端" in e for e in errors), errors)

    def test_a_baseline_table_may_not_list_the_items_of_a_front_end_the_project_does_not_have(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = self.project(tmp, "web", ["web-admin"])
            spec = dev_fixture.sample_spec("architecture", web)
            section = next(s for s in find_tab(spec, "技术栈")["sections"] if s["title"] == "管理后台前端")
            find = next(b for b in section["blocks"] if b["type"] == "baseline")
            find["rows"].append({"id": "STK-MP-01", "status": "沿用"})
            errors = dd.validate("architecture", spec, web)
            self.assertTrue(any("STK-MP-01" in e for e in errors), errors)

    def test_the_rendered_baseline_says_mini_program_things_only_for_a_project_that_has_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = self.project(tmp, "web", ["web-admin"])
            both = self.project(tmp, "both", ["miniprogram", "web-admin"])
            page_web = dd.render_body(dev_fixture.sample_spec("architecture", web), web)
            page_both = dd.render_body(dev_fixture.sample_spec("architecture", both), both)
            for phrase in ("wx.login", "小程序备案", "miniprogram-automator", "小程序 AppSecret"):
                self.assertNotIn(phrase, page_web, phrase)
                self.assertIn(phrase, page_both, phrase)
            self.assertNotIn("STK-MP-01", page_web)
            self.assertIn("STK-MP-01", page_both)


if __name__ == "__main__":
    unittest.main()
