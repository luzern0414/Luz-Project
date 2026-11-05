# Luz Project workflow

`luz-project` owns the project lifecycle, the handoff ledger and the change ledger. It does not replace the specialist skills. A project has a session `D:\Codes\skill输出\Luz-Project\NNN-项目名\` (the summary page and `raw\`, the state root) and a project directory `D:\Codes\NNN-项目名` that holds results only; each specialist keeps its own session in its output root and hands the result to Luz-Project, which registers it and writes it into the project directory.

## 0. Project context and Crawl handshake

Read the project rule card and experience first. Before each stage, run the Luz-Crawl handshake. Reuse the same project Crawl task and evidence index; create a new task only for a separate user request. Every stage records source IDs, access dates, coverage, and unresolved evidence. A stage may state that no fresh capture is required only after checking the existing evidence.

## 1. Create the project

`project.py init <名称> --project-dir <项目目录>` creates the state root (`project.json` with `deliver_root`, `MANIFEST.json`, `APPROVALS.json`, `data/`, `config/`) and the summary page in the session, and in the project directory the three documentation folders (需求对接 and 验收交付 for client files, 产品开发 for developer HTML; the review pages of the requirement stages go to the state root's `reviews/`); `src/`, `test/` and the other implementation folders appear when something is written there. Choose the document theme with `client theme` before the first client document.

## 2. Requirements and research

A one-line request becomes a requirements page (goal, users, scope, success criteria, open questions). Research produces a reviewable conclusion and an evidence index. The user confirms scope and research coverage before the proposal.

## 3. Proposal documents for the client

**The requirements document comes first**: when the client has none, `luz-writing` and `luz-design` write `01-需求说明书.pdf` (`project.py client requirements-draft`, then `project.py client requirements`; chapters in `references/client-documents.md` §3b); a client who brings its own document registers it from the state root's `uploads/` instead. No proposal is written before one of the two exists. `luz-system` writes the function list (`data/client/features.json`, stable `FN-` IDs, 基础/可选, rules, surface, roles, tags). `luz-writing` writes the proposal text. `project.py client proposal` renders through Luz-Design the **方案说明书** (PDF), the **系统架构图** (PDF) and the **功能清单** (Excel: functions, and on sheet 2 the quote; with `"amounts": false` in `config/documents.json` one sheet of functions and person-days, no money); what each file says is in `references/client-documents.md` §1. The developer review HTML is rendered separately into the state root's `reviews/`. The client confirms the three files; the user records that approval.

## 4. Client information collection

`client intake-form` builds the Excel sheet from the question library (filtered by surfaces and feature tags) plus a per-feature selection block. The client fills it in (mini-program account facts, business hours, packages, membership and points rules, notification and payment facts, acceptance contacts, agent-specific facts such as knowledge sources, approvers, queue expectations, scheduled jobs and risk thresholds). `client intake-import` structures the answers; required gaps block the next stage unless deferred with owner and due date. Feature choices that differ from the baseline enter the change ledger automatically.

## 5. System architecture

`luz-system` receives the approved requirements, features and client answers and produces the system architecture document (`01-系统架构.html`; its tabs are fixed by `references/dev-documents.md`). Each feature's landing points are recorded with `project.py link`. The page is approved before Design or Dev proceeds.

## 6. UI design

`luz-design` reads the approved frontend view and client brand facts, calls Luz-Crawl for visual and component evidence, runs adaptive style matching, and produces a UI handoff with tokens, assets, component states, breakpoints and page/action bindings. It stops for visual approval.

## 7. Technical plan and implementation

`luz-dev` reads the approved system, design artifacts and client rule answers, calls Luz-Crawl for technical evidence, writes the executable technical plan, and stops for approval. Rule and calculation features become versioned configurations with regression samples. After the gate it binds actions to contracts, implements vertical slices, and records tests and deviations. User-visible changes return to System or Design through a revised stage.

## 8. Verification, release and operations

`luz-ops` reads the manifest, design bindings, technical plan, implementation evidence and `data/acceptance/checklist.json`. It selects checks by product surface, records evidence bound to file hashes, blocks release on missing or failed required checks, and produces the runbook and handoff package.

## 9. Handover

`client acceptance` creates the acceptance checklist from the in-scope features (steps, expected result, evidence checks). `client manual` renders the user manual from `manual.json`, which must cover every in-scope feature. The client fills in 验收结果, 签字 and 日期 per item; `client acceptance-import` loads them. `change snapshot` freezes the ledger. Final approval requires every item passed (or waived with owner and reason), no unimplemented changes, and fresh documents.

## 10. Change loop (all stages)

Any client addition, rule change, detail or deletion is written to the change ledger first. A confirmed change updates the feature list, marks the earliest affected approved stage `pending-review`, supersedes its downstream approvals and flags stale client documents. A pending change blocks approval of the stages it names. Silence never counts as approval. Specialists re-read `project.py context` after every change.
