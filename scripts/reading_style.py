"""The type of every reading page this skill writes (the developer documents, the project index, the stage review pages).

Reading pages are Markdown-shaped (Luz-Design file-design.html 网页文件 › 排版参数): one body size, six heading levels, lists, tables,
captions and code, in two size sets, phone (under 768 px) and desktop (768 px and up, body 18). ``MD_TYPE`` is a byte-for-byte copy of the block
in Luz-Design/references/md-type.css (``scripts/sync_md_type.py --write`` keeps it equal; edit the master, never this copy).

Every page goes through ``project_core._html_page`` and Luz-Design's ``showcase.page``, whose own style sheet still carries older sizes
(``.sh``, ``main.doc h3``, ``.tbl td``). ``apply`` adds the block and ``PAGE_FIX`` to the page head, after the page's own sheet: PAGE_FIX
puts those rules back on the md tokens with the same selectors, and it can go once ``showcase.page`` carries the block itself. Component
styles (tabs, cards, figures) live next to their renderers (dev_tabs.TAB_CSS, dev_documents.CSS) and only use ``var(--md-*)``.
"""
from __future__ import annotations

import re

MD_TYPE = r"""/* luz-md-type:start
   阅读型网页的 Markdown 层级（母本：Luz-Design/references/md-type.css）。其他技能的样式文件里夹着同一段，
   改这里之后运行 py -X utf8 scripts/sync_md_type.py --write 同步，不要在别处手改（不带参数运行只报告 SAME 或 DIFF）。
   规则见 file-design.html 网页文件 › 排版参数（逐级数值表）与 visual-design.html 一 › 字体与字号 › 字阶表的阅读型网页一行：手机（小于 768）与桌面（768 及以上）各一套字号，
   桌面正文 18，手机 16；每一级的字号、字重、行高、上下留白固定，页面只取这些级别，不另造样式。
   只管文字层级，不管容器宽度、颜色主题与组件：颜色取页面已有的变量，缺省用下面的回退值。 */
:root {
  --md-body: 16px;  --md-body-lh: 1.75;
  --md-h1: 28px;  --md-h2: 24px;  --md-h3: 20px;  --md-h4: 16px;  --md-h5: 14px;  --md-h6: 14px;
  --md-table: 14px;  --md-aux: 14px;  --md-code: 14px;
  --md-measure: 42em;
}
@media (min-width: 768px) {
  :root {
    --md-body: 18px;  --md-body-lh: 1.8;
    --md-h1: 36px;  --md-h2: 28px;  --md-h3: 22px;  --md-h4: 18px;  --md-h5: 16px;  --md-h6: 14px;
    --md-table: 16px;  --md-aux: 14px;  --md-code: 16px;
  }
}
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
body { font-size: var(--md-body); line-height: var(--md-body-lh); font-weight: 400; font-kerning: normal; text-rendering: optimizeLegibility; overflow-wrap: break-word; }
h1, h2, h3, h4, h5, h6 { font-family: inherit; font-style: normal; letter-spacing: 0; text-wrap: balance; }
h1 { margin: 0 0 24px; font-size: var(--md-h1); line-height: 1.25; font-weight: 700; }
h2 { margin: 56px 0 16px; padding-bottom: 12px; border-bottom: 1px solid var(--line, #d7e0e8); font-size: var(--md-h2); line-height: 1.3; font-weight: 700; }
h3 { margin: 40px 0 12px; font-size: var(--md-h3); line-height: 1.4; font-weight: 600; }
h4 { margin: 28px 0 8px; font-size: var(--md-h4); line-height: 1.5; font-weight: 600; }
h5 { margin: 24px 0 8px; font-size: var(--md-h5); line-height: 1.5; font-weight: 600; color: var(--muted, var(--ink-2, #526071)); }
h6 { margin: 20px 0 8px; font-size: var(--md-h6); line-height: 1.5; font-weight: 600; color: var(--muted, var(--ink-2, #526071)); }
p { margin: 0 0 16px; }
p, ul, ol, dl, blockquote { max-width: var(--md-measure); }
ul, ol { margin: 0 0 16px; padding-left: 1.6em; }
li { margin: 0; }
li + li { margin-top: 6px; }
li > ul, li > ol { margin: 6px 0 0; }
ul { list-style: disc; }
ul ul { list-style: circle; }
ul ul ul { list-style: square; }
li::marker { color: var(--muted, var(--ink-2, #526071)); }
dt { font-weight: 600; }
dd { margin: 2px 0 12px; padding-left: 1em; }
strong, b { font-weight: 600; }
em, i, cite, address { font-style: normal; font-weight: 600; }
blockquote { margin: 0 0 16px; padding: 4px 0 4px 16px; border-left: 4px solid var(--line, #d7e0e8); color: var(--muted, var(--ink-2, #526071)); }
blockquote > :last-child { margin-bottom: 0; }
hr { margin: 40px 0; border: 0; border-top: 1px solid var(--line, #d7e0e8); }
small, figcaption, caption, time, .aux, .src { font-size: var(--md-aux); line-height: 1.6; }
caption, figcaption { margin: 0; padding: 0 0 10px; color: var(--muted, var(--ink-2, #526071)); text-align: center; }
caption { caption-side: top; }
table { font-size: var(--md-table); line-height: 1.65; font-variant-numeric: tabular-nums; }
th { font-weight: 600; }
td > :last-child, th > :last-child { margin-bottom: 0; }
code, kbd, samp, pre { font-family: "Cascadia Mono", "Consolas", "Microsoft YaHei", monospace; font-size: var(--md-code); line-height: 1.6; }
code, kbd, samp { padding: 2px 6px; border-radius: 8px; background: var(--surface-soft, var(--surface-2, #edf3f7)); overflow-wrap: anywhere; }
pre { margin: 0 0 16px; padding: 16px 20px; overflow: auto; border: 1px solid var(--line, #d7e0e8); border-radius: 8px; background: var(--surface, #f7f9fc); }
pre code { padding: 0; border-radius: 0; background: none; font-size: inherit; }
@media print {
  :root { --md-body: 11pt; --md-body-lh: 1.7; --md-h1: 22pt; --md-h2: 17pt; --md-h3: 14pt; --md-h4: 12pt; --md-h5: 11pt; --md-h6: 10.5pt; --md-table: 10.5pt; --md-aux: 10.5pt; --md-code: 10.5pt; }
}
/* luz-md-type:end */"""

_H3 = re.search(r"^h3 \{([^}]*)\}", MD_TYPE, re.M)
PAGE_FIX = """
:root{--muted:var(--ink2);--surface:var(--tint1);--surface-soft:var(--tint1)}
main.doc .hero h1{margin:0}
main.doc h3{""" + (_H3.group(1).strip().rstrip(";") if _H3 else "font-size:var(--md-h3)") + """;color:var(--ink)}
main.doc table:not(.tbl) th,main.doc table:not(.tbl) td,.tbl th,.tbl td{font-size:var(--md-table);line-height:1.65}
.tcap,.cap,.chip,.chip-s,.meta{font-size:var(--md-aux);line-height:1.6}
.notice{font-size:var(--md-body)}
"""


def style() -> str:
    """The ``<style>`` element of a reading page: the md block, then the compatibility rules."""
    return "<style>" + MD_TYPE + PAGE_FIX + "</style>"


def apply(page: str) -> str:
    """Put the reading type into a finished page: headings lose the wrapper's ``sh`` class (the md h2 rule styles them), the style goes in the head."""
    page = page.replace('<h2 class="sh">', "<h2>")
    return page.replace("</head>", style() + "</head>", 1) if "</head>" in page else style() + page
