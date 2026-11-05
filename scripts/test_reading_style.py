import re
import tempfile
import unittest
from pathlib import Path

import client_fixture as fx
import dev_documents
import dev_fixture
import dev_tabs
import reading_style
from client_fixture import new_project
from project_core import create_project
from stage_documents import write_document

MASTER = Path(__file__).resolve().parents[2] / "Luz-Design" / "references" / "md-type.css"
START, END = "/* luz-md-type:start", "/* luz-md-type:end */"


class ReadingStyleTests(unittest.TestCase):
    def test_the_block_is_a_byte_for_byte_copy_of_the_luz_design_master(self):
        if not MASTER.is_file():
            self.skipTest("Luz-Design is not next to this skill")
        text = MASTER.read_text(encoding="utf-8")
        self.assertEqual(reading_style.MD_TYPE, text[text.index(START):text.index(END) + len(END)])

    def test_a_page_has_the_markdown_type_and_the_component_styles_only_use_its_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_project("阅读排版", tmp)
            fx.crawled(root, "architecture")
            page = write_document(root, "architecture", dev_fixture.sample_spec("architecture", root)).read_text(encoding="utf-8")
        head = page[:page.index("</head>")]
        self.assertIn(START, head)
        self.assertIn("--md-body: 18px", head)                                  # 桌面正文 18
        self.assertIn("--md-body: 16px", head)                                  # 手机正文 16
        self.assertNotIn('class="sh"', page)                                    # 二级标题由 md 的 h2 规则排版，不再走外壳的旧字号
        for name, css in (("dev_documents.CSS", dev_documents.CSS), ("dev_tabs.TAB_CSS", dev_tabs.TAB_CSS)):
            self.assertEqual(re.findall(r"font-size:\s*\d+px", css), [], f"{name} 的字号要取 var(--md-*)，不写像素值")

    def test_the_wrapper_overrides_use_the_token_of_their_own_level(self):
        self.assertRegex(reading_style.PAGE_FIX, r"main\.doc h3\{[^}]*font-size: var\(--md-h3\)")
        self.assertIn("font-size:var(--md-table)", reading_style.PAGE_FIX)
        self.assertIn("font-size:var(--md-aux)", reading_style.PAGE_FIX)


if __name__ == "__main__":
    unittest.main()
