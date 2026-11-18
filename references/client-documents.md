# 客户文档规范（需求 → 方案 → 逻辑确认 → 变更 → 使用说明与验收）

Project 维护文件的用途、内容结构、生成入口、目录、阶段和审批关系。实际路径与交付顺序来自 [开发矩阵](development-matrix.json) 的 `documents`。目录规则见 [项目目录](project-structure.md)。文档内容由相应技能提供，版式与成品检查按 [Luz-Design 文件设计](../../Luz-Design/references/file-design.html) 执行。

## 1. 需求对接文件的职责

| 文件 | 解决的问题 | 输入与生成 |
|---|---|---|
| 需求说明书 | 确认客户现状、本期范围、具体要求和验收标准 | Writing 整理用户材料，System 核对需求、功能和约束。客户已经提供需求文档时，登记状态根 `uploads/` 中的原件。需要代写时，由 `requirements.json` 通过 `client requirements` 生成。 |
| 方案说明书 | 在已确认需求上解释拟交付范围、解决方式与结果 | Writing 使用 System 的功能和流程事实，Project 通过 `client proposal` 生成。 |
| 系统架构图 | 让客户理解角色、模块、依赖和数据怎样贯通 | System 维护 `architecture.json` 与功能清单，随方案阶段生成。 |
| 功能清单 | 核对每个使用端、角色与模块的交付功能及基本或可选范围 | System 维护 `features.json`，随方案阶段生成。估算与人工报价按第 6 节的开关。 |
| 业务逻辑确认表 | 让客户核对既定功能的具体规则，并提交只有客户掌握的资料 | System 提供 `features.json` 与 `intake-extra.json`。`client intake-form` 生成，`client intake-import` 回收。 |
| 需求变更台账 | 追踪客户确认的需求与规则变化 | Project 从 `data/changes.json` 更新可见台账，交付时冻结快照。见 [变更规则](change-control.md)。 |

每份文档独立回答表中的问题。保留正文必需的事实与来源，内部功能编号按用途放在状态数据、变更和验收记录。交付阶段的使用说明和验收清单沿用开发矩阵中各自的负责人和事实输入。

## 2. 从一句需求到交付（顺序固定）

每份正式文档先按 [阶段依据合同](../../Luz-Crawl/references/evidence-policy.md) 核对资料的适用范围，再生成。阶段记录方式见 [操作手册](runbook.md)。

1. **requirements**：**先有需求文档**。客户没有需求文档时，先写 `data/client/requirements.json`（`project.py client requirements-draft` 生成草稿；读 `luz-writing` 的 `client-document` 规则卡和 `luz-design` 的 `docx` 规则卡；项目背景要有按使用方的现状问题表，需求清单写清每条需求的具体要求和业务规则，规范见第 3b 节），填完后 `project.py client requirements` 用 Word 排版导出 `01-需求说明书.pdf`；客户有自己的需求文档时放进状态根的 `uploads/` 并在 `requirements.json` 的 `client_document` 里登记。没有需求文档，需求阶段不能批准，方案也生成不了。再把一句话需求补成需求评审页：目标、用户、范围、成功标准、待决项。
2. **research**：Crawl 前置检索 + 调研结论页（同类方案书结构、行业规则、平台前置条件）。
3. **proposal**：
   - 读 `luz-system` 的 `function-list` 规则卡，写 `data/client/features.json`（模块、功能、基础/可选、规则、使用端、角色、标签）。**先确认 `config/documents.json` 的 `estimate` 开关**：默认都关，不写人日、不写预算和报价，只给功能清单。用户或客户明确要求才打开（`project.py client <项目> estimate …`，要带谁要求、何时、原话）：开人日时每个功能再写 `hours` 与 `hours_basis`，人日是估算，用户批准前标“拟定”；开报价要等人工报价（`client <项目> quote …`），数字只来自人工，agent 不得自拟，详见第 6 节。
   - 读 `luz-design` 的 `docx` 规则卡和 `luz-writing` 的 `general` 规则卡写 `proposal.json`（`format: word`）：先分析客户的需求（现状、痛点、各使用方的核心需求），再给出解决方案。`client proposal-draft` 生成含“待补充”的草稿，**草稿不能构建**。
   - `architecture.json` 由 `proposal-draft` 按功能清单先推一版，再改成客户能看懂的节点名和作用。
   - `client proposal` 经 Design 构建：方案说明书 PDF、系统架构图 PDF、功能清单 Excel（默认一张功能表；按开关加工时列、报价清单；开了报价而没有人工报价单，三个文件都不生成，项目等待人工报价）。
   - `project.py document <项目> proposal --file …` 生成开发版评审页。
   - 三份文件由同一条命令一次构建，用户仍然一个一个审（02 → 03 → 04）：每个用 `approve <项目> proposal --doc <路径> …` 记录用户的原话；通过后再交给客户。
4. **client-intake**：`client intake-form` 生成业务逻辑确认表（每个功能一行写出拟定的业务逻辑 + 待决定的规则 + 需要客户提供的资料）→ 客户确认或修改 → `client intake-import <回填.xlsx>`。需要提供的必填项未答、选了“需修改”却没写修改后的逻辑，都不能通过；确实要延后的用 `client intake-defer "分类/业务逻辑" --owner --due --note`。客户放弃基础功能、选择可选功能、修改业务逻辑，都会自动写入变更台账。
5. **architecture → design → technical-plan → implementation**：各技能读 `project.py context <项目> <阶段> --skill <技能>`，返回的 `client` 段含客户确认过的 `features.json`、`intake.json` 答案、待确认变更和该阶段的交付物路径。功能在架构、设计、开发里的落点用 `project.py link FN-001 --arch … --design … --dev …` 登记，`trace` 报缺口。
6. **verification → release → operations**：进入验证前先运行 `client acceptance-plan` 生成 `data/acceptance/checklist.json`（只写数据，不出 Excel）；Luz-Ops 读它的 `evidence_checks`，把每个验收项映射到测试证据，并分别在三个阶段出验收测试报告、发布说明、运维手册（PDF）。客户在交付阶段才签字，所以 operations 只验证映射完整，不要求签字。
7. **handover**：`client acceptance` 刷新验收清单数据（保留已有结果）并生成 Excel，其“测试证据”列写 Ops 的中文检查名；写 `manual.json` 后 `client manual` 生成使用说明；客户逐项选“通过/不通过”并签名签日期，`client acceptance-import` 回收；`change snapshot` 冻结台账；三个文件（01 使用说明 → 02 验收清单 → 03 台账快照）由用户逐个审批，客户签字回收后，用户明确授权动作门 `final-acceptance`（`project.py action`）。

任何阶段发生客户新增需求、修改规则、补充细节：先按 [change-control.md](change-control.md) 登记，再动手。

## 3. 选择文档生成器

客户正式文档、架构图册和工作簿的模板分别以 Design 的 `docx-paginated`、`showcase`、`xlsx` 为入口。模板文件与适用范围见 [Design 模板库](../../Luz-Design/references/template-library.json)，版式、导出与成品核验按 [文件设计](../../Luz-Design/references/file-design.html) 和实际调用的转换器执行。Project 绑定最终项目相对路径并登记产物。

## 3b. 需求说明书怎么写

`data/client/requirements.json`（`format: word`）：`title`、`subtitle`、`hero.info`、`toc: true`、`sections[{key, title, blocks}]`。`project.py client requirements-draft` 写出带 `待补充` 的草稿，填完后 `project.py client requirements` 用 Word 排版并导出 `01-需求说明书.pdf`；草稿和缺章的资料生成不了。**必有七章**（按 `section.key` 检查）：

| key | 章 | 写什么 |
|---|---|---|
| `background` | 项目背景 | 业务现状（客户是做什么的、现在怎么做、规模多大）和按使用方的现状问题表：使用方 / 现状问题 / 具体表现 / 带来的后果 |
| `goals` | 建设目标 | 三到四个可检验的目标，各写衡量方法 |
| `scope` | 范围与使用者 | 本期范围、不在本期范围、使用者与使用端表 |
| `requirements` | 需求清单 | 每条需求：编号、需求、具体要求、业务规则、类型。功能清单已有时用 `{"type": "auto", "what": "requirement_list"}` 生成，需求与功能清单不会不一致：按模块分表，编号是全文连续的序号（1、2、3……，不出现功能编号 FN-001），只列客户仍然要的功能（在业务逻辑确认里选“不需要”的不列，它要在“不在本期范围”里写明）；功能清单或客户的功能选择变了，需求说明书即“已过期”，重新生成 |
| `rules` | 业务规则与约束 | 业务规则、时间与金额口径、数据范围、合规与平台约束，写边界和数字 |
| `acceptance` | 验收标准 | 怎样算做好了：可观察的结果和验收方式 |
| `open` | 需要客户确认的事项 | 事项 / 为什么需要确认 / 建议的做法 |

- 只写需求，不写解决方案、技术细节和价格；块只用文段、小标题、列点和带表题的表；标题不加括号；不提及其他文件（`《方案说明书》` 等，校验会拦截）。
- 需求来自客户的原始资料（状态根的 `uploads/`）、与客户的沟通和对同类系统的调研，调研按 Luz-Crawl 前置检索，写进需求阶段的来源。
- 客户有自己的需求文档时：文件放状态根的 `uploads/`，`requirements.json` 写 `{"client_document": {"file": "uploads/<文件名>", "note": "<说明>"}}`，不再生成需求说明书。两种情况下，需求阶段都要有需求文档才能批准，方案阶段也不能在没有需求文档时生成。
- 需求说明书的来源（`requirements.json` 和用到的 `features.json`）改了，PDF 即“已过期”，重新生成后才能再批准。

## 4. 方案说明书怎么写

`data/client/proposal.json`（`format: word`）：`title`、`subtitle`、`hero.info`（封面：项目名称、版本、日期）、`toc: true`、`sections[{key, title, blocks}]`。**必有三章**（按 `section.key` 检查）：`background` 项目背景与需求分析、`solution` 解决方案、`deliverables` 交付内容；常加 `goals` 建设目标。

- **先分析，再给方案**：`background` 写业务现状（现状问题表：现状问题 / 具体表现 / 带来的后果）、需求分析（按使用方：使用方 / 现状与痛点 / 核心需求 / 解决方式）和本期需求边界（试点规模、不做什么）。需求来自需求说明书（或客户自己的需求文档）和对同类系统的调研，不凭空写；客户原始资料放 `raw/uploads/`。
- **解决方案要让客户看懂系统**：`solution` 先写一段总体思路，再分小节：系统构成（系统 / 使用者 / 解决什么问题 / 主要功能模块）、角色与权限、业务流程（环节表加一天的运转）、各系统的功能与业务逻辑（每个系统一张表：功能模块 / 主要功能 / 业务逻辑，业务逻辑写边界和数字）、统一业务规则。
- **块只有这些**：`text` 文段、`sub` 二级标题、`bullets` 列点、`table`（必须有 `caption`，长文本列用 `widths` 给相对宽度）、`matrix`。不用卡片、指标卡、图标。
- **标题精简**：标题不加括号说明（“一天的运转”，不是“一天的运转（以预约为例）”），说明放进正文或表题。
- **不提及其他文件**：不写本项目文件的名字（《功能清单》《系统架构图》《业务逻辑确认表》等）、配套文件、见某某表，校验会拦截；法规、标准的名称照 GB/T 15834 用书名号，不受限。**不写人日、预算和价格**：这些只在用户明确要求并开了开关的功能清单里出现（工时列、报价清单），方案正文哪里都不写数字（`check` 会拦；系统自身的业务概念如“工时统计”功能，在数据文件的 `allow_terms` 里列出）；方案里写“第三方费用由客户承担”这类约定即可。
- **用客户的词**：写“顾客预约时段”，不写“调用预约服务接口”；不出现技术栈、库表、内部编号；每个数字有依据。
- 完整示例见 `references/examples/proposal.example.json`。

## 5. 系统架构图册怎么画

`data/client/architecture.json`（`style: atlas`）。图册的排版按 Design 模板。**必有四章**（`section.key`）：`layers` 总体架构、`modules` 功能模块与逻辑、`dependencies` 模块依赖关系、`dataflow` 数据链路与流转；再按项目加关键流程（泳道图加校验表）、状态、数据隔离与权限、部署、各端功能分布。

1. **总体架构**（`figure: arch_layers`）：3–4 层——使用端、业务模块（按业务分组）、基础保障；每层 ≤ 6 个节点；`flows` 画 6–9 条编号数据流，说明写在图下表，再加“各层职责与运行方式”表。
2. **功能模块与逻辑**：表（模块 / 输入 / 处理逻辑 / 输出 / 数据保存在）。
3. **模块依赖关系**：矩阵（行模块依赖列对象，“是”标注）+ 表（被依赖的对象 / 被谁使用 / 不可用时的影响）。
4. **数据链路与流转**：表（数据 / 产生于 / 经过 / 保存在 / 被谁使用）。
5. **关键流程**：泳道图（泳道是角色，列是阶段，步骤只连相邻阶段，**连线不写标签**）+ 校验表。
6. 状态表、数据隔离与权限表、部署图（`figure: deployment`）、各端功能分布（`auto: role_module_matrix`）。

每个节点和流向都来自功能清单与客户确认的规则，不凭空画；每张表有表题；排版后每页占满率 ≥ 70%，不满就调整章节与块的顺序，不加空白页。

## 6. 功能清单、人日与报价

**默认只给功能清单。**用户的话：「有一些项目是不需要写预算的，只有明确要求写人日和报价，才写，否则只需要给出清单即可，且报价必须人工报价，不允许 agent 随便填」。没有明确要求时，所有客户文件（需求说明书、方案说明书、系统架构图、功能清单、业务逻辑确认表、变更台账、使用说明、验收清单）和给用户审批的 docs 文件里都不出现人日、工时、预算、单价、金额、小计、合计、报价，只有功能清单（模块、功能、说明、使用角色、基础/可选、业务逻辑）。“基础/可选”是功能分级，不是价格，保留。

两个互相独立的开关写在状态根的 `config/documents.json` 的 `estimate`（`init`、`adopt`、`migrate` 都写出默认值）：

```json
"estimate": {"workdays": false, "quote": false, "requested_by": "", "requested_at": "", "request_note": ""}
```

- `workdays`：功能清单加“工时（人天）”列。`quote`：功能清单加“报价清单”工作表，**必须同时打开 `workdays`**（报价基于人日）。
- 打开任何一个都要有三项证据：`requested_by`（谁要求的：具体的用户或客户，姓名或角色，不能是智能体、技能、工具、系统、示例）、`requested_at`（YYYY-MM-DD）、`request_note`（要求的原话）。缺一项，或要求的人不是具体的人，开关等于没打开，`check` 报错。要求的原话可以只有几个字但不少于 4 个字（`estimate_terms.MIN_NOTE`，如“请给出报价”），报价单的 `evidence` 要写具体来源，不少于 6 个字（`estimate_terms.EVIDENCE_MIN`，与工作簿描述里证据的最短长度一致），原话或证据里自己说“暂估”“自拟”“默认值”“占位”一律拒绝（`says_made_up`）。命令 `project.py client <项目> estimate --workdays on|off --quote on|off --requested-by … --requested-at … --request-note …` 在证据不全时拒绝，关闭不要证据但要 `--note` 写原因，不带开关参数运行就显示现状。
- 旧的 `amounts` 开关没有证据：`amounts: false` 等价于两个开关都关，`amounts: true` 同样按关闭处理并给提醒（`check` 输出的 notes）。`project.py migrate` 补上 `estimate` 默认值并去掉 `amounts`。
- `estimate` 这一段是方案阶段所有文件的来源（`config/documents.json#estimate`）：改开关，02、03、04 都过期，已有的批准按文件作废，重新生成、逐个重审。已有批准文件时 `estimate` 命令自动登记一条变更（范围类、已确认，客户可见与否按台账默认规则；客户提出的加 `--source 客户`）并重开方案阶段，见 [change-control.md](change-control.md)。

**人日（`workdays`）**：features.json 每个在范围内的功能要有 `hours`（人天，0.5 的倍数）和 `hours_basis`（估算依据：功能复杂度、涉及的页面与接口数、参照的同类功能，不能只有数字）。人日是 agent 的估算，**用户批准功能清单之前一律标“拟定”**：`next`、`checklist`、汇总页出示这个文件时写明“工时（人天）是拟定值，估算依据在 features.json 每个功能的 hours_basis，你批准之后才作数”（文件一经批准就是定稿，改文件会让批准作废，所以“拟定”标在出示的说明里，不写进文件）。列合计用公式。未开启时 features.json 里的 `hours`、`hours_basis` 只是历史字段，不进任何客户文件。

**报价（`quote`）**：单价、折扣、金额、总价这些数字**只能来自人工提供的报价单**，agent 不得自拟、不得套用示例值、不得“暂估”，技能和模板里没有任何默认单价。人工数字用命令记录：

- `project.py client <项目> quote --unit-price <数> --provided-by <提供的人> --evidence "<提供数字的原话或来源>"`，或 `--from-file <报价单.xlsx|json|csv> --provided-by <提供的人>`：从报价单里读“单价”那一格，文件留在状态根的 `uploads/` 并记哈希；找不到、或有几个不同的数就拒绝，不替人挑。
- 写出 `data/client/quote.json`：`unit_price`（元每人天，大于 0）、`provided_by`（提供数字的人）、`provided_at`、`request_note`（要求报价的原话，缺省取 `estimate.request_note`）、`evidence`（原话或来源文件路径；来源文件另有 `evidence_file`、`evidence_sha256`）。缺字段、`provided_by` 是智能体/技能/工具/系统/示例/暂估、`evidence` 是暂估/示例/默认值、单价不大于 0：命令拒绝记录，渲染和 `approve` 也拒绝（旧的只有 `unit_price` 的 quote.json 同样，不会静默通过）。`quote` 没开时 quote.json 不读，只提醒。
- 开了 `quote` 而没有合格的 quote.json：`estimate` 命令照样成功，项目进入**等待人工报价**：`next`、`checklist`、汇总页把它列为用户待办（一句话说明要提供人天单价或报价单文件），`client proposal` 不生成（三个文件同一条命令构建），也不出示；收到数字、记录之后再继续。

**其余文件同步**：未开启时，方案、需求说明书、架构图册、确认表的项目专属问题、使用说明里不出现人天、人日、人月、工日、“12 工时”，也不出现报价、单价、小计、元每人天、合计加金额、`¥` 加数字；变更台账里客户可见的条目和两页评审页（03、04）同样（`project.py check`、`gate`、`approve` 会报，`change add` 会拒绝；只是顺带提到钱的业务规则，如“100 分抵 1 元”，不算）。开启后这些词也只在功能清单的工时列、报价清单里出现，正文不写数字；系统自身的业务概念（如“员工工时统计”）在数据文件的 `allow_terms` 里列出才放行。判断用的词（谁不算具体的人、人日词、金额词）是 `scripts/estimate_terms.py`，Luz-Design 母本的整文件拷贝，由 Design 的 sync 脚本写，不手改，`test_estimate.py` 比对摘要。文件版本取方案封面的“版本”（或 `documents.json` 的 `version`），台账、确认表中的日期都是北京时间。

`data/client/features.json`：`modules[{id,name,summary,icon?}]`，`features[{id: FN-001…, module, name, surface, roles[], tier(基础|可选), summary, rules, tags[], depends_on[], acceptance[]}]`，开启人日时每个在范围内的功能再加 `hours`、`hours_basis`。成品 `04-功能清单.xlsx`：

- **功能清单**（默认就是这一张表）：使用端 → 使用角色 → 功能模块（三级分组，由大到小，纵向合并）、功能、功能说明、类型；没有编号，没有业务规则，没有工时、金额、小计、合计。
- **开启人日**：同一张表在类型后加“工时（人天）”（取 `hours`），表下方“基础功能小计”“可选功能小计，选用后另计”“工时合计”，三行都是公式。
- **开启报价**：另有“报价清单”工作表：同一份清单加“工时（人天）”“单价（元每人天）”（取 quote.json）“报价（元）”（每行 = 工时 × 单价，公式），表下方基础、可选小计和报价合计也是公式；单价由谁提供记在 quote.json，不写在表头。表里没有一个数字是代码或 agent 敲进去的：要么是人给的单价，要么是功能的 `hours`，要么是公式。
- 开了人日或报价的工作簿，描述里带着证据（“报价依据：要求人…；原话…；提供人…；来源…”），Luz-Design 的 `check_document` 凭它放行（`--allow workdays|quote`）；没有这条证据，检查把工时、金额列当错误。

规则：ID 一经发布永不复用，删除功能用变更把 status 置为 `removed`；`rules` 写边界和数字（“最晚提前 2 小时取消”），不写“支持灵活配置”；`surface`：miniprogram / web-admin / agent / website / mobile-app / api / hardware；`tags` 驱动验收证据，用词表（会员、积分、储值、优惠券、商品、套餐、订单、门店、预约、核销、配送、退款、支付、通知、发票、售后、分销、拉新、抽奖、活动、排队、并发、定时任务、风险预警、规则引擎、绩效核算、单据核算、知识库、流程编排、对接）；智能体平台类功能（排队、定时任务、风险预警、规则配置、知识库、流程编排）按 Luz-System 的 platform-console 规则写成独立功能。

## 7. 业务逻辑确认表怎么用

**先给出方案，再由客户确认或修改**；只让客户填只有他们才有的定制信息，不问每个项目都一样的通用内容（企业名称、联系人邮箱、云厂商、操作系统……）。

- **业务逻辑确认**（第一张表）七列：分类、子类、业务逻辑、拟定逻辑、说明与理由、审核结果、修改后的逻辑。第一块是**每个功能一行**（分类 = 使用角色，子类 = 功能模块）：“拟定逻辑”把 `features.json` 的 `rules` 拆成 1、2、3… 逐条写出，“说明与理由”写功能说明；“审核结果”下拉：基础功能 `确认 / 需修改 / 不需要`（默认确认），可选功能 `需要 / 不需要 / 待定`；选“需修改”就在“修改后的逻辑”写出要的逻辑。第二块是待决定的规则（`kind: logic` 的项目专属问题）：拟定的逻辑写成可直接确认的一句话（“团课预约：开课前 7 天 10:00 开放预约，开课前 2 小时截止取消”），说明与理由写它决定什么。
- **需要提供的资料**（第二张表）七列：分类、子类、需要提供的内容、示例、为什么需要、客户填写、必填。只放定制信息，示例写成真实可抄的样子（`wx1234567890abcdef`、`gym.example.com`、`周一至周五 6:30–22:30`）。密钥、密码、证书私钥一律不进表格，只问“已通过安全渠道发送 / 尚未发送”。
- 业务逻辑项写清楚，不写缩略词：“团课的预约和取消时间”，不是“团课”。每一行都写说明与理由（缺少会拒绝生成）。
- 问题来源：① 每个功能一行由功能清单自动生成；② 项目专属问题 `data/client/intake-extra.json`（`{category: "大类 · 子类", item, kind: "logic"|"info", example, why, options?}`）；③ 通用问题库 `references/intake-library.json` 只在 `intake-extra.json` 的 `library` 写 `all`、`tagged` 或列表时借用，默认不用。
- 客户选“需修改”并写出新逻辑，导入时自动在变更台账登记一条待确认的“修改规则”；写了“需修改”却没写新逻辑，算未回答。放弃基础功能、选择可选功能同样自动登记。
- 会员名单、套餐、课程表这类成批数据写成“上传文件”类问题并指向导入模板。平台规则（小程序备案、类目资质、支付商户开通材料）只作为向客户确认的问题，具体要求以平台官方最新说明为准，由 Crawl 前置检索核对后再写给客户。
- 回填表被改动结构（缺列、多出问题）时拒绝导入，要求使用系统生成的原表。
- 确认表不问价格，也不写人日：`intake-extra.json` 的问题里出现报价、人天（未开启时）会被 `check` 拦下；谁出钱、付款节点这类商务事项不在这张表里，由用户直接与客户谈。

## 8. 使用说明与验收清单

- `manual.json`：`title, intro, roles[], chapters[{id, heading, features[], entry, steps[], rules[], states[], notes[], faq[]}], glossary[], support{}`。每个在范围内的功能 ID 必须出现在某个章节里（`validate_manual` 检查），步骤用祈使句，规则写数字与边界，状态写含义和下一步。使用说明与方案说明书同一套 Word 正式文档版式，只交付 PDF；章节标题不写括号说明。草稿 `client manual-draft` 带占位，不能构建。
- 验收清单由功能清单生成：每个在范围内的功能至少一项；客户未选择或已移除的功能自动“不适用（waived）”并说明原因。
- 签字只能来自客户的回填表（结果、姓名、日期同时存在）；脚本和模型不代签。`acceptance-waive` 需要确认人与理由。
- 交付门禁：全部验收项通过（或有理由的豁免）、使用说明覆盖全部功能、台账无未实施条目且快照与当前台账一致。

## 9. 与其它技能的边界

| 技能 | 在客户文档里负责 | 不负责 |
|---|---|---|
| Luz-System | 功能清单内容、模块分组、基础/可选、端与角色；架构图节点的业务含义 | 版式 |
| Luz-Design | 客户正式文档（Word 版式、封面、目录、页眉页脚、表题与续表、黑白）、架构图册 atlas 样式、Excel 版式与不遮挡检查、检查脚本 | 写什么内容 |
| Luz-Writing | 方案、使用说明、协议类文字的写作规则与自查 | 数据结构与门禁 |
| Luz-Crawl | 前置检索：同类方案结构、行业规则、平台前置条件；来源进入调研页 | 客户文档本身 |
| Luz-Dev | 在技术方案里承接 `features.json` 与 `intake.json`，把规则写进合同与配置 | 改功能清单（走变更） |
| Luz-Ops | 给验收项提供测试证据（`evidence_checks`） | 签字、改清单 |
| Luz-Project | 数据文件、顺序、哈希、过期与缺项阻断、变更台账、目录、文件分工 | 具体写作与版式 |

## 10. 校验清单

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client <项目> estimate          # 人日与报价开关现状（默认都关）；开了报价时有没有人工报价
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client <项目> proposal          # 方案资料通过后才生成（Word 排版需要本机有 WPS 文字或 Word）
py -X utf8 D:\Codes\Luz-Project\scripts\project.py trace <项目>                    # 功能追溯与缺口
py -X utf8 D:\Codes\Luz-Project\scripts\project.py check <项目> --strict
```

生成后必须逐页看渲染图（Word 排版的 PDF 构建时在状态根的 `client-docs/` 写下总览图 `<名>-pages-N.png`，每张六页，不交给客户）：方案封面无页码、目录可点击且页码对、续表有“续表 N”；架构图册没有黑线黑框和粗体、标题与表头同一种墨色、表头与列同向；Excel 的标题、表头、分组带、汇总行颜色与第 3 节的版式规范一致。文件被用户在 Excel 或 WPS 里打开时无法覆盖，先请用户关闭。

## 表格里的分组列（所有客户 Excel 通用）

连续重复的列（使用端、使用角色、功能模块、分类、子类）都是分组列：**排在名称前面，按大组到小组排，纵向合并，数据按同样顺序排序**；类型、必填、状态这类描述一行属性的列放在后面，不合并。已按此排列：功能清单（及开启报价时的报价清单）（使用端 → 使用角色 → 功能模块）、验收清单（使用端 → 功能模块）、确认表（分类 → 子类）；变更台账按时间排，没有分组列。新增任何表格都用 Design 的 `group_by`，不手工排列；`check_document` 会拦截顺序错误。表格下方的汇总行用 `footer`，标签写“合计”“小计”或“总计”。
