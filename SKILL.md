---
name: luz-project
description: Use when a user explicitly asks to create, manage, or run a complete Luz project across requirements, client-facing proposal documents, client information collection, system architecture, visual design, development, testing, release, operations, and final handover; also owns the global requirement-change ledger.
metadata:
  short-description: Orchestrate a complete Luz project lifecycle and client documents
---

# Luz Project

`luz-project` is the project control plane. It creates the project workspace, owns the stage matrix, approvals and the change ledger, routes work to the specialist Luz skills, keeps one source of truth in `data/`, and renders two audiences' documents: **client PDF/Excel** (方案、架构图、功能清单、业务逻辑确认表、使用说明、验收清单) and **developer HTML** (评审页).

## Invocation boundary

This skill is explicit project mode. Do not create a project directory or activate the full chain when a user calls `luz-system`, `luz-design`, `luz-dev`, `luz-writing`, or `luz-crawl` alone. Existing skills keep their standalone output and checks unless `LUZ_PROJECT_ROOT` or an explicit project context is supplied by this skill.

## 调用协议（完整项目显式启用）

1. Run `python -X utf8 scripts/project.py matrix`, then read this card, `references/project-mode.md`, `references/client-documents.md`, `references/dev-documents.md` (the standard of the developer HTML), `references/tech-baseline.md` (the technical baseline: stack, frontend and basic functions fixed once, every project states keep / change / add / drop against it), `references/change-control.md` and `experience/catalog.md`. Only an explicit Project request or supplied project context authorizes `init`. An older project: `project.py migrate <项目>`. An existing repository: `project.py adopt` (moves docs with git, keeps code folders, records aliases; see project-mode.md).
2. Every stage must complete the [Crawl preflight](../Luz-Crawl/references/preflight.md): actual search/capture, verified body evidence, adopted supplements, and conclusion HTML. Reuse one project task but record each caller/stage separately. Missing or stale information determines research scope, never whether research happens. **A document is written only after its stage has crawled enough**: stage review pages, the proposal and architecture PDFs, the feature list, the logic confirmation form, the manual and the acceptance checklist are refused (`project.py` raises, nothing is written) until that stage's preflight is concluded and `check` passes; the same holds for Luz-Ops' three client PDFs and Luz-Dev's agreement PDFs. Only the change ledger, imports of what the client filled in and the project index page are exempt.
3. Create one project root with `scripts/project.py init`. The root contains `config/`, `data/`, `docs/`, `src/`, `test/`, `assets/`, `infra/`, `scripts/` and `raw/`, first level only (folders below them are made when something is written there). Choose a document theme once: `project.py client <项目> theme <主题>` (Luz-Design `themes.json`, by industry and audience).
4. **Baseline first.** Technical choices, frontend rules and basic functions come from `references/baseline/` (written once, in the skills' words, with the contradictions between source standards listed in `references/baseline/CONFLICTS.md`). A project neither copies nor edits them: it states for every item 沿用 / 调整 / 新增 / 不用 with a reason in `data/baseline.json`, and a gap or error found in the baseline goes back to `references/baseline/`. `python -X utf8 scripts/baseline.py` validates the baseline files.
   **One source of truth.** Facts live in `data/` JSON (`client/features.json` with stable `FN-` IDs, `changes.json`, `acceptance/checklist.json`, `stages/*.json`); PDF, Excel and HTML are rendered from them and carry source hashes. Never hand-edit a rendered file; a stale file blocks approval.
5. **Before any specialist starts a stage** run `project.py context <项目> <阶段> --skill <技能>`. Its `client` section carries the data files, deliverable paths, open and recent changes, and the rule-card commands that stage must run. A context with `blockers` is not permission to proceed.
6. **Client documents go through the specialists**: function content from `luz-system` (`function-list`), text from `luz-writing` (`general` for proposals, `academic-professional` for manuals), layout and checks from `luz-design` (`docx` for the proposal and the manual: the formal client-document layout of `references/client-documents.md` §3, typeset in Word, only the exported PDF delivered; `showcase` with `style: atlas` for the architecture atlas; `xlsx` for the feature list with its quote sheet, the rule collection sheet, ledger and checklist), evidence from `luz-ops`. Project only wires them: `project.py client <项目> proposal | intake-form | intake-import | acceptance | manual`. Drafts that still contain “待补充” cannot be built.
7. **Change ledger first.** When the user says a client added a requirement, changed a rule, supplemented a detail or dropped a function, ask for any missing logic, then `project.py change <项目> add …` **before** doing the work ([change-control.md](references/change-control.md)). A confirmed change updates the feature list, reopens the earliest approved stage it touches, and re-renders `06-需求变更台账.xlsx`, which carries only the entries the client may read (`--client-visible`: by default the client's own requirement, rule and scope changes; internal, technical and interface changes stay in `data/changes.json`), with process notes in `--note` and Beijing dates. A pending change blocks approval of the stages it names.
8. Stop at every user gate: requirements, research, proposal (client confirms the three PDFs), client information, system architecture, UI design, technical plan, implementation milestone, release candidate, production release, operations handoff, final acceptance. Store the approval quote, artifact path, SHA-256, time, and approver. Silence is not approval; signatures come only from the client's own filled sheet.
9. A changed approved artifact invalidates downstream stages. Route the change back to the owning skill, revise the project record, and wait for approval before continuing. Tracked sources (requirements, features, proposal, architecture, intake, manual, checklist, changes, and the `stack` and `modules` sections of `data/baseline.json` for the architecture stage) cannot drift after approval without a recorded change; `check` also reports an artifact number registered twice and a required HTML deliverable that is missing once its stage's page is registered.
10. Call `luz-ops` for verification, release, operations and the evidence behind the acceptance checklist. Do not implement feature code in `luz-project`.
11. Before finishing, run `project.py trace` (feature → architecture → manual → acceptance → changes), render the project index and write or confirm an experience note. Run `scripts/project.py check <project> --strict`.

## Specialist routing

- Requirements, function list, function logic, frontend structure, backend intent, prototypes, hardware: `luz-system`.
- Palette, type, icons, layout, PDF/Excel layout, assets, and visual UI handoff: `luz-design`.
- APIs, database, services, queues and schedulers, rule engines, workflow engine, knowledge base, integration, deployment: `luz-dev`.
- Proposal text, user manual, copy, agreements, source-backed prose: `luz-writing`.
- Browser research and source evidence: `luz-crawl`.
- Browser automation, load tests, mini-program tests, agent evaluation, release, monitoring, backup, rollback, handoff evidence: `luz-ops`.

## Directory contract

- `docs/01-需求对接/`: **what the requirement stages hand to the client, PDF and XLSX only, flat, no sub folders** — 01-需求说明书.pdf (the requirements document: background and the specific needs; **written first when the client has no requirements document**, otherwise the client's own is registered from `raw/uploads/`), 02-方案说明书.pdf (typeset in Word, only the exported PDF is delivered), 03-系统架构图.pdf, 04-功能清单.xlsx (sheet 1 the functions, sheet 2 the quote), 05-业务逻辑确认表.xlsx (+回填), 06-需求变更台账.xlsx. Each file is complete in itself and mentions no other file (references/client-documents.md §1); the Word typesetting follows Luz-Design's formal client-document standard (`context.py docx`). **No HTML in this folder**: the review pages of the requirement stages (for your approval and for developers, internal) live in `raw/reviews/` — 01-需求评审, 02-调研结论, 03-方案评审, 04-业务逻辑确认评审, 05-交付评审.
- `docs/02-产品开发/`: **the HTML of the development stages only, flat, no sub folders**, numbered Chinese names in one sequence — 01-系统架构, 02-前端界面设计, then one prototype per front end named 序号 + 前端名称 + 原型 from 03 on (a phone page and a back office are 03-手机原型 and 04-后台原型; a mini program and a back office are 03-小程序原型 and 04-后台原型; the design stage's deliverable list is read from the prototype blocks of `data/stages/design.json` by `init`, `migrate`, `context` and `document`, and falls back to the matrix default only before a design document exists), 05-后端设计规范, 06-实现报告, 07-验收测试评审, 08-发布评审, 09-运维评审 (the last three are Luz-Ops' test, release and operations evidence). Requirement-stage review pages never go here (they are in `raw/reviews/`). Their tabs, sub tabs, baseline tables, function cards, front end tabs (one prototype each, every path in 前端规范) and sources are fixed by `references/dev-documents.md`; the project's own statement against the baseline is `data/baseline.json` (`stack`, `frontend`, `modules`) and the documents must agree with it; `scripts/dev_documents.py` validates and renders them, `project.py document` refuses a document that fails the standard or whose stage has not crawled.
- `docs/03-验收交付/`: what the handover gives the client, PDF and XLSX only, flat — 使用说明.pdf, 验收清单.xlsx, 需求变更台账-交付快照.xlsx, and the client PDFs of the development stages (验收测试报告, 发布说明, 运维手册, 用户协议, 隐私政策). The 交付评审 page is internal and lives in `raw/reviews/`.
- `data/`: `client/` (features, proposal, architecture, intake, manual, trace links, build ledger), `changes.json`, `acceptance/checklist.json`, `stages/`, `ops/`, and domain data. `config/`: parameters, URLs, flags, `documents.json` (theme), key references; secret values stay outside generated artifacts. `src/ test/ infra/ assets/ raw/` as before (`raw/uploads/` holds the client's original material, `raw/client-docs/` the Word sources, build intermediates and page overview images). `project.py check` names every extra folder, misplaced file and wrong-stage file; `project.py migrate` moves an older project.

## Validation

```powershell
python -X utf8 scripts/project.py matrix
python -X utf8 scripts/project.py route "<project>"
python -X utf8 scripts/project.py trace "<project>"
python -X utf8 scripts/project.py check "<project>" --strict
python -X utf8 scripts/validate_project.py "<project>" --strict
python -X utf8 scripts/experience.py check
python -X utf8 -m pytest -q scripts
```

The complete schemas and stage rules are in `references/`. Standalone validators keep their original sessions; project-mode entry checks and specialist content checks are described in `references/project-mode.md`. After producing a PDF, read the rendered page images in `raw/client-docs/` page by page.
