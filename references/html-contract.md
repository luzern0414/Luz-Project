# Project HTML contract

Project HTML is a review artifact, not a runtime product screen. It is rendered from `project.json`, `data/`, registered artifacts, and stage evidence.

Every document has UTF-8 encoding, `lang="zh-CN"`, one visible title, a stable `data-document-id`, `data-project-id`, `data-stage`, `data-status`, and `data-version`. The first content block is the conclusion or current state. Details follow in semantic sections with stable IDs.

Use tabs only for parallel views with the same subject, such as the tabs of the development documents. Tab controls must use `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, `aria-controls`, keyboard focus, and a no-script fallback.

The page may show source IDs, decisions, risks, approvals, and links to evidence. It must redact secrets, access tokens, cookies, private keys, and unapproved personal data. Paths and source metadata belong in the document data attributes or `MANIFEST.json` when they do not help the reader.

The canonical source is JSON. Edit source data or the skill artifact and rerender; do not hand-edit the generated HTML. A generated document is registered with its SHA-256 and upstream artifact hashes.

## Look of the pages

Review pages share the look of the client documents (Luz-Design `showcase.page(..., formal=True)`): no icon block before the title or any section title, one ink for titles, table heads and text, one regular weight, a pale table head with hairlines, table heads over their own left-aligned column, no parenthetical explanation in a title (write it in the text below), a browser-tab icon only. Page titles name the document (`方案文档评审`, `调研结论`), not its audience.
