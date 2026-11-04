"""The Word route of the client documents: what the proposal may contain, the quote sheet, the rule form and the Word build itself."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
        data = fx.features()
        for i, f in enumerate(data["features"]):
            f["hours"] = 2 if f["tier"] == "基础" else 1
        return data

    def test_feature_list_has_no_code_or_rules_and_the_quote_sheet_totals(self):
        data = self.features()
        spec = cr.feature_list_xlsx_spec(data, "示例", "japanese-sushi", {"unit_price": 500})
        listing, pricing = spec["sheets"]
        self.assertEqual([c["name"] for c in listing["columns"]], ["使用端", "使用角色", "功能模块", "功能", "功能说明", "类型"])
        self.assertEqual([c["name"] for c in pricing["columns"]][-2:], ["工时（人天）", "报价（元）"])
        basic = sum(f["hours"] for f in cd.active_features(data) if f["tier"] == "基础")
        self.assertEqual(pricing["footer"][0]["values"], {"工时（人天）": basic, "报价（元）": basic * 500})
        self.assertEqual(pricing["footer"][-1]["values"], {"报价（元）": basic * 500})
        self.assertTrue(all(len(r) == len(pricing["columns"]) for r in pricing["rows"]))

    def test_every_function_needs_hours_for_a_quote(self):
        data = fx.features()
        self.assertIn("工时", "；".join(cd.validate_quote(data, {"unit_price": 500})))
        self.assertEqual(cd.validate_quote(self.features(), {"unit_price": 500}), [])

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
            root = Path(tmp)
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


if __name__ == "__main__":
    unittest.main()
