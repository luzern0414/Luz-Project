import unittest

import baseline as bl


class BaselineFilesTests(unittest.TestCase):
    def test_the_baseline_files_are_complete_and_clean(self):
        self.assertEqual(bl.baseline_errors(), [])

    def test_every_layer_category_and_module_is_present_with_substance(self):
        self.assertEqual([l["id"] for l in bl.stack()["layers"]], list(bl.STACK_LAYERS))
        self.assertEqual([c["id"] for c in bl.frontend()["categories"]], list(bl.FRONTEND_CATEGORIES))
        self.assertGreaterEqual(len(bl.stack_items()), 50)
        self.assertGreaterEqual(len(bl.frontend_items()), 80)
        self.assertGreaterEqual(len(bl.function_items()), 70)
        for fn in bl.function_items():
            for k in bl.FUNCTION_FIELDS:
                self.assertGreaterEqual(len(fn[k]), 30, (fn["id"], k))

    def test_the_six_layouts_and_the_ui_kit_are_in_the_frontend_baseline(self):
        names = {i["name"] for i in bl.frontend_items("layout")}
        for name in ("主次布局", "横带分层", "主区加右侧窄栏", "全幅画布加浮动面板", "看板分列", "时间轴泳道"):
            self.assertIn(name, names)
        self.assertTrue(any("ui-kit" in i["source"] for i in bl.frontend_items("stack")))

    def test_ids_resolve_across_the_three_files(self):
        for i in bl.stack_items()[:3] + bl.frontend_items()[:3] + bl.function_items()[:3]:
            self.assertEqual(bl.item(i["id"])["id"], i["id"])
        self.assertIsNone(bl.item("STK-ZZ-99"))


class ProjectStatementTests(unittest.TestCase):
    def keep_everything(self):
        return {"stack": {i["id"]: {"status": "沿用"} for i in bl.stack_items()}, "frontend": {i["id"]: {"status": "沿用"} for i in bl.frontend_items()},
                "modules": {m["id"]: {"status": "沿用"} for m in bl.functions()["modules"]}}

    def test_keeping_everything_is_a_valid_statement(self):
        self.assertEqual(bl.project_baseline_errors(self.keep_everything()), [])

    def test_a_mandatory_item_cannot_be_left_out(self):
        s = self.keep_everything()
        gone = next(i for i in bl.stack_items() if i.get("mandatory", True))["id"]
        del s["stack"][gone]
        self.assertTrue(any(gone in e and "必有项" in e for e in bl.project_baseline_errors(s)))

    def test_a_change_needs_a_reason_and_a_value_and_an_omission_needs_a_reason(self):
        s = self.keep_everything()
        a, b, c = [i["id"] for i in bl.stack_items()[:3]]
        s["stack"][a] = {"status": "调整", "value": "Java 21"}
        s["stack"][b] = {"status": "不用", "reason": "没有"}
        s["stack"][c] = {"status": "调整", "reason": "客户的运维团队只维护这一种"}
        errors = bl.project_baseline_errors(s)
        self.assertTrue(any(a in e and "理由" in e for e in errors), errors)
        self.assertTrue(any(b in e and "理由" in e for e in errors), errors)
        self.assertTrue(any(c in e and "取值" in e for e in errors), errors)
        s["stack"][a] = {"status": "调整", "value": "Java 21", "reason": "客户的运维团队只维护 Java 服务"}
        s["stack"][b] = {"status": "不用", "reason": "本项目没有缓存需求，数据量很小"}
        s["stack"][c] = {"status": "调整", "value": "另一种", "reason": "客户的运维团队只维护这一种"}
        self.assertEqual(bl.project_baseline_errors(s), [])

    def test_every_basic_function_module_needs_a_statement(self):
        s = self.keep_everything()
        gone = next(iter(s["modules"]))
        del s["modules"][gone]
        self.assertTrue(any(gone in e and "基础功能模块" in e for e in bl.project_baseline_errors(s)))
        s["modules"][gone] = {"status": "不用", "reason": "项目没有这类业务"}
        self.assertEqual(bl.project_baseline_errors(s), [])
        s["modules"]["nosuch"] = {"status": "沿用"}
        self.assertTrue(any("nosuch" in e for e in bl.project_baseline_errors(s)))

    def test_unknown_ids_and_added_items_follow_the_prefix_rule(self):
        s = self.keep_everything()
        s["stack"]["STK-ZZ-99"] = {"status": "沿用"}
        self.assertTrue(any("STK-ZZ-99" in e for e in bl.project_baseline_errors(s)))
        del s["stack"]["STK-ZZ-99"]
        s["stack"]["X-自建"] = {"status": "沿用"}
        self.assertTrue(any("新增" in e for e in bl.project_baseline_errors(s)))
        s["stack"]["X-自建"] = {"status": "新增", "value": "项目自己的做法"}
        self.assertEqual(bl.project_baseline_errors(s), [])


class SurfaceTests(unittest.TestCase):
    WEB = {"web-admin"}
    BOTH = {"miniprogram", "web-admin"}

    def keep(self, surfaces):
        return {"stack": {i["id"]: {"status": "沿用"} for i in bl.stack_items(surfaces=surfaces)},
                "frontend": {i["id"]: {"status": "沿用"} for i in bl.frontend_items(surfaces=surfaces)},
                "modules": {m["id"]: {"status": "沿用"} for m in bl.functions()["modules"]}}

    def test_the_mini_program_layer_and_its_items_are_only_for_projects_that_have_a_mini_program(self):
        mini = {i["id"] for i in bl.stack_items("frontend-miniapp")}
        self.assertEqual(len(mini), 7)
        self.assertFalse(mini & {i["id"] for i in bl.stack_items(surfaces=self.WEB)})
        self.assertTrue(mini <= {i["id"] for i in bl.stack_items(surfaces=self.BOTH)})
        self.assertTrue(mini <= {i["id"] for i in bl.stack_items()})          # no function list yet: every item applies
        self.assertEqual(bl.stack_items("frontend-miniapp", self.WEB), [])
        self.assertTrue(bl.stack_items("frontend-admin", {"website"}))        # the admin web stack stays in every project

    def test_a_frontend_item_for_the_mini_program_only_follows_the_same_rule(self):
        only = [i for i in bl.frontend_items() if i.get("surfaces") == ["miniapp"]]
        self.assertGreaterEqual(len(only), 6)
        ids = {i["id"] for i in bl.frontend_items(surfaces=self.WEB)}
        self.assertFalse({i["id"] for i in only} & ids)
        self.assertTrue(all(i["id"] in {j["id"] for j in bl.frontend_items(surfaces=self.BOTH)} for i in only))
        self.assertTrue(all(i["id"] in ids for i in bl.frontend_items() if "both" in i.get("surfaces", [])))

    def test_a_project_without_a_mini_program_does_not_account_for_it_and_may_not_state_it(self):
        s = self.keep(self.WEB)
        self.assertEqual(bl.project_baseline_errors(s, self.WEB), [])
        self.assertTrue(any("STK-MP-01" in e and "必有项" in e for e in bl.project_baseline_errors(s, self.BOTH)))
        s["stack"]["STK-MP-01"] = {"status": "不用", "reason": "项目没有小程序，只做后台"}
        errors = bl.project_baseline_errors(s, self.WEB)
        self.assertTrue(any("STK-MP-01" in e and "没有这一端" in e for e in errors), errors)
        self.assertFalse(any("没有这一端" in e for e in bl.project_baseline_errors(s)))   # surfaces unknown: no front end is absent
        self.assertEqual(bl.project_baseline_errors(self.keep(self.BOTH), self.BOTH), [])

    def test_the_text_says_what_is_true_for_the_mini_program_only_where_the_project_has_one(self):
        item = bl.item("STK-DP-04")
        neutral = bl.text(item, "detail", self.WEB)
        self.assertNotIn("小程序", neutral)
        self.assertEqual(neutral, item["detail"])
        with_mini = bl.text(item, "detail", self.BOTH)
        self.assertTrue(with_mini.startswith(item["detail"]) and "小程序备案在小程序后台办理" in with_mini)
        self.assertEqual(bl.text(item, "detail"), with_mini)                  # no function list yet: nothing is left out
        self.assertEqual(bl.text({"detail": "只有正文的一项"}, "detail", self.BOTH), "只有正文的一项")

    def test_the_neutral_text_of_an_item_outside_the_mini_program_layer_does_not_name_the_mini_program(self):
        for layer in bl.stack()["layers"]:
            for i in layer["items"]:
                if layer["id"] in bl.LAYER_SURFACE:
                    continue
                for field in ("name",) + bl.SURFACE_TEXT_FIELDS:
                    self.assertIsNone(bl.SURFACE_ONLY_WORDS.search(str(i.get(field) or "")), (i["id"], field))
        base = {"id": "STK-ZZ-01", "name": "某一项", "detail": "小程序请求只发往合法域名并带版本头。"}
        self.assertTrue(any("小程序" in e and "by_surface" in e for e in bl._by_surface_errors("w", base, in_surface_layer=False)))
        fixed = {"id": "STK-ZZ-01", "name": "某一项", "detail": "请求只发往合法域名并带版本头。", "by_surface": {"miniprogram": {"detail": "小程序请求域名要配成合法域名。"}}}
        self.assertEqual(bl._by_surface_errors("w", fixed, in_surface_layer=False), [])
        for bad in ({"web-admin": {"detail": "后台写的一句话很长很长"}}, {"miniprogram": {"nosuch": "字段不存在的一句话"}}, {"miniprogram": {"detail": "短"}}):
            self.assertTrue(bl._by_surface_errors("w", dict(fixed, by_surface=bad), in_surface_layer=False), bad)
        self.assertTrue(bl._by_surface_errors("w", fixed, in_surface_layer=True))   # the layer is already only for the mini program


if __name__ == "__main__":
    unittest.main()
