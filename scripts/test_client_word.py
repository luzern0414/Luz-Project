"""The Word route of the client documents: what the proposal may contain, the quote sheet, the rule form and the Word build itself."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from client_fixture import new_project
import client_data as cd
import client_fixture as fx
import client_flow as cf
import client_render as cr


def word_proposal() -> dict:
    table = {"type": "table", "columns": ["项", "内容"], "rows": [["甲", "乙"]], "caption": "示例表"}
    return {"title": "示例建设方案", "subtitle": "建设方案", "format": "word", "toc": True, "hero": {"info": [["项目名称", "示例"], ["版本", "V1.0"]]},
            "sections": [{"key": "background", "title": "项目背景与需求分析", "blocks": [{"type": "text", "text": "现状。"}, {"type": "sub", "text": "需求分析"}, table]},
                         {"key": "solution", "title": "解决方案", "blocks": [{"type": "sub", "text": "系统构成"}, table, {"type": "sub", "text": "业务流程"}, table]},
                         {"key": "deliverables", "title": "交付内容", "blocks": [{"type": "bullets", "items": ["源代码", "部署"]}]}]}


class WordProposalRules(unittest.TestCase):
    def test_a_proper_proposal_passes(self):
        self.assertEqual(cd.validate_proposal(word_proposal()), [])

    def test_headings_carry_no_parentheses(self):
        spec = word_proposal()
        spec["sections"][1]["blocks"][0]["text"] = "总体流程（以午餐为例）"
        spec["sections"][0]["title"] = "项目背景（现状）"
        errors = "；".join(cd.validate_proposal(spec))
        self.assertIn("括号", errors)
        self.assertGreaterEqual(errors.count("括号"), 2)

    def test_tables_need_titles_and_duplicates_are_refused(self):
        spec = word_proposal()
        del spec["sections"][0]["blocks"][2]["caption"]
        spec["sections"][2]["blocks"] = [{"type": "auto", "what": "feature_overview"}, {"type": "cards", "items": [{"title": "a", "text": "b"}]}]
        errors = "；".join(cd.validate_proposal(spec))
        self.assertIn("表题", errors)
        self.assertIn("auto", errors)
        self.assertIn("cards", errors)

    def test_a_proposal_names_no_other_file(self):
        spec = word_proposal()
        spec["sections"][0]["blocks"][0]["text"] = "具体功能和报价见《功能清单》。"
        spec["hero"]["info"].append(["配套文件", "系统架构图"])
        self.assertIn("不提及其他文件", "；".join(cd.validate_proposal(spec)))

    def test_cover_and_contents_are_required(self):
        spec = word_proposal()
        spec["toc"] = False
        spec["hero"] = {}
        errors = "；".join(cd.validate_proposal(spec))
        self.assertIn("目录", errors)
        self.assertIn("封面", errors)

    def test_the_proposal_needs_the_analysis_the_solution_and_what_is_delivered(self):
        spec = word_proposal()
        spec["sections"] = spec["sections"][:1]
        errors = "；".join(cd.validate_proposal(spec))
        self.assertIn("解决方案", errors)
        self.assertIn("交付内容", errors)


class QuoteAndRules(unittest.TestCase):
    def features(self):
        return fx.with_hours(fx.features())

    def estimate(self, quote: bool = True) -> dict:
        block = {"workdays": True, "quote": quote, "requested_by": fx.REQUESTED_BY, "request_note": fx.REQUEST_NOTE}
        if quote:
            block.update({"provided_by": fx.QUOTE_BY, "evidence": fx.QUOTE_EVIDENCE})
        return block

    def human_quote(self) -> dict:
        return {"unit_price": 800, "provided_by": fx.QUOTE_BY, "provided_at": "2026-11-05", "request_note": fx.REQUEST_NOTE, "evidence": fx.QUOTE_EVIDENCE}

    def test_feature_list_lists_functions_only_by_default(self):
        spec = cr.feature_list_xlsx_spec(fx.features(), "示例", "japanese-sushi")
        self.assertEqual([c["name"] for c in spec["columns"]], ["使用端", "使用角色", "功能模块", "功能", "功能说明", "类型"])
        self.assertNotIn("sheets", spec)
        self.assertNotIn("footer", spec)
        self.assertNotIn("estimate", spec)

    def test_feature_list_has_no_code_or_rules_and_the_quote_sheet_totals_are_formulas_of_the_persons_numbers(self):
        data = self.features()
        spec = cr.feature_list_xlsx_spec(data, "示例", "japanese-sushi", self.human_quote(), estimate=self.estimate())
        listing, pricing = spec["sheets"]
        self.assertEqual([c["name"] for c in listing["columns"]], ["使用端", "使用角色", "功能模块", "功能", "功能说明", "类型", "工时（人天）"])
        self.assertEqual([c["name"] for c in pricing["columns"]][-3:], ["工时（人天）", "单价（元每人天）", "报价（元）"])
        self.assertTrue(all(r[-2] == 800 and str(r[-1]).startswith("=") for r in pricing["rows"]), "the unit price is the person's; the amount is a formula, not a typed number")
        self.assertTrue(all(isinstance(v, str) and v.startswith("=") for item in pricing["footer"] for v in item["values"].values()), "every total is a formula")
        self.assertTrue(all(len(r) == len(pricing["columns"]) for r in pricing["rows"]))
        self.assertEqual(spec["estimate"]["provided_by"], fx.QUOTE_BY)

    def test_a_quote_cannot_reach_the_sheet_without_its_switch_or_without_workdays(self):
        data = self.features()
        with self.assertRaises(ValueError):
            cr.feature_list_xlsx_spec(data, "示例", "japanese-sushi", self.human_quote())
        with self.assertRaises(ValueError):
            cr.feature_list_xlsx_spec(data, "示例", "japanese-sushi", self.human_quote(), estimate={**self.estimate(), "workdays": False})
        with self.assertRaises(ValueError):
            cr.feature_list_xlsx_spec(data, "示例", "japanese-sushi", None, estimate=self.estimate())

    def test_every_function_needs_hours_and_its_basis_when_workdays_is_on(self):
        data = fx.features()
        self.assertIn("hours", "；".join(cd.validate_hours(data)))
        self.assertEqual(cd.validate_hours(self.features()), [])
        data = self.features()
        data["features"][0]["hours_basis"] = "3"
        self.assertIn("hours_basis", "；".join(cd.validate_hours(data)))

    def test_the_rule_form_has_one_row_per_function_with_numbered_rules_and_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.features()
            questions = cf.intake_questions(Path(tmp), data, include_all=False)
            rows = [q for q in questions if q.get("feature_id")]
            self.assertEqual(len(rows), len(cd.active_features(data)))
            self.assertTrue(all(q["example"].startswith("1. ") and q["why"] for q in rows))
            self.assertTrue(all(q["why"] for q in questions), "every question says why it is asked")


class WordBuild(unittest.TestCase):
    def test_the_word_document_and_its_pdf_are_built_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("文档构建", tmp)
            fx.crawled(root, "proposal")
            spec = cr.expand_auto(word_proposal(), fx.features(), "japanese-sushi")
            docx, pdf = cr.build_docx(root, "proposal", spec)
            self.assertTrue(docx.is_file() and pdf.is_file())
            import fitz
            with fitz.open(str(pdf)) as doc:
                text = "".join(page.get_text() for page in doc).replace(" ", "").replace(chr(10), "")
                links = len(doc[1].get_links())
            self.assertIn("一、项目背景", text)
            self.assertIn("目录", text)
            self.assertGreaterEqual(links, 4, "each contents entry jumps to its heading")
            sheets = sorted(pdf.parent.glob("proposal-pages-*.png"))
            self.assertTrue(sheets and all(p.stat().st_size > 2000 for p in sheets), "overview images of the pages are written next to the PDF for the page-by-page reading")

    def test_the_architecture_atlas_gets_its_overview_images_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("文档构建", tmp)
            fx.crawled(root, "proposal")
            spec = cr.expand_auto({**fx.architecture(), "orientation": "landscape"}, fx.features(), "japanese-sushi")
            pdf, _html = cr.build_showcase(root, "architecture", spec)
            sheets = sorted(pdf.parent.glob("architecture-pages-*.png"))
            self.assertTrue(sheets and all(p.stat().st_size > 2000 for p in sheets), "the atlas is read page by page like the Word documents")


if __name__ == "__main__":
    unittest.main()
