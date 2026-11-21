# Project HTML contract

项目汇总、开发说明与文档评审使用本页的阅读版式，由项目清单、状态根事实、已登记成果和阶段证据生成。商业项目的开发说明放在 `docs/03-开发资料/`，旧流程沿用 `docs/02-产品开发/`，需求阶段评审页放在状态根的 `reviews/`。

商业项目的 `docs/03-开发资料/05-交互原型.html` 使用应用界面模板。它按 [Design 成品要求](../../Luz-Design/references/design/hard-rules.md) 呈现和操作业务页面，按[原型验收](commercial-project.md#原型验收)登记浏览器证据。

Every document has UTF-8 encoding, `lang="zh-CN"`, one visible title, a stable `data-document-id`, `data-project-id`, `data-stage`, `data-status`, and `data-version`. The first content block is the conclusion or current state. Details follow in semantic sections with stable IDs.

Use tabs only for parallel views with the same subject, such as the tabs of the development documents. Tab controls must use `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, `aria-controls`, keyboard focus, and a no-script fallback.

The page may show source IDs, decisions, risks, approvals, and links to evidence. It must redact secrets, access tokens, cookies, private keys, and unapproved personal data. Paths and source metadata belong in the document data attributes or `MANIFEST.json` when they do not help the reader.

The canonical source is JSON. Edit source data or the skill artifact and rerender; do not hand-edit the generated HTML. A generated document is registered with its SHA-256 and upstream artifact hashes.

## The summary page

The overview of a project is the page `NNN-项目名.html` at the root of its Luz-Project session (written by `project.py render`, frame by `make_summary.py`, checked by `check_output_layout.py session`): `lang="zh-CN"`, light, one font family, the Markdown type scale (desktop body 18, phone 16), zoom not disabled, a tab icon, the main title `h1` first and only once with no subtitle, timestamp or hash, then one `h2` per section with one captioned table — results (paths relative to the project directory), stages with their approvals, sessions of the other skills, the files the tools keep. A section without content is not written. No README.html or other index is generated inside the project directory.

## Look of the pages

Review pages share the look of the client documents (Luz-Design `showcase.page(..., formal=True)`): no icon block before the title or any section title, one ink for titles, table heads and text, one regular weight, a pale table head with hairlines, table heads over their own left-aligned column, no parenthetical explanation in a title (write it in the text below), a browser-tab icon only. Page titles name the document (`方案文档评审`, `调研结论`), not its audience.
