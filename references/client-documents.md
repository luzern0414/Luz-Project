# 客户文档规范（需求 → 方案 → 逻辑确认 → 变更 → 使用说明与验收）

交给客户的文件固定为：需求说明书、方案说明书、系统架构图、功能清单（含报价）、业务逻辑确认表、需求变更台账；交付阶段再加使用说明和验收清单。**先有需求文档，再有方案**：客户没有需求文档时，先写需求说明书（背景和具体需求写清楚），方案、功能清单等都以它为前提；客户有自己的需求文档时，把它放进 `raw/uploads/` 并在 `data/client/requirements.json` 的 `client_document` 里登记，不再另写。**每份文件把自己的内容写完整，文件里不提及其他文件**（不写“详见《功能清单》”“配套文件”）。事实都在 `data/client/` 的数据文件里，文件是它的派生物，不手改成品。

## 1. 每份文件写什么

| 文件 | 回答什么 | 格式 | 内容 |
|---|---|---|---|
| 01-需求说明书 | 客户的业务现状是什么、具体要什么 | PDF（用 Word 排版后导出，版式取 Luz-Design 的客户正式文档标准：封面、可点击目录、表题与续表、黑白） | 项目背景（业务现状、按使用方的现状问题表）、建设目标、范围与使用者（本期范围、不在本期范围、使用者与使用端）、需求清单（每条需求：编号、需求、具体要求、业务规则、类型）、业务规则与约束、验收标准、需要客户确认的事项；只写需求，不写解决方案、技术细节和价格 |
| 02-方案说明书 | 客户要什么、我们怎么解决、交付什么 | PDF（用 Word 排版后导出，Word 源文件留在 `raw/client-docs/`，不交给客户） | 项目背景与需求分析、建设目标、解决方案（系统构成、角色与权限、业务流程、各系统的功能与业务逻辑、统一业务规则）、交付内容 |
| 03-系统架构图 | 系统长什么样、怎么运转 | PDF（图加表） | 总体架构（分层图与数据流向）、功能模块与逻辑、模块依赖关系、数据链路与流转、关键流程、状态、数据隔离与权限、部署、各端功能分布 |
| 04-功能清单 | 具体做哪些功能、多少钱 | Excel，两个工作表 | 功能清单：使用端 → 使用角色 → 功能模块 → 功能、功能说明、类型；报价清单：同一份清单加工时（人天）、报价（元），表下方基础功能小计、可选功能小计、报价合计 |
| 05-业务逻辑确认表 | 每个功能和业务规则这样定对不对 | Excel，两个工作表 | “业务逻辑确认”：每个功能一行，拟定的业务逻辑逐条写出，客户选确认或需修改并写出修改后的逻辑；其后是待决定的规则（取消规则、爽约处理、积分有效期……）。“需要提供的资料”：只有客户才有的定制信息（小程序 AppID、域名、首批会员名单与套餐……）。每行写说明与理由 |
| 06-需求变更台账 | 需求和规则改过什么 | Excel | 客户新增需求、修改规则的逐条记录；自动重排 |
| 使用说明（交付阶段） | 怎么用 | PDF（Word 排版导出） | 角色、每个功能的入口、步骤、规则、状态、常见问题 |
| 验收清单（交付阶段） | 逐项验收 | Excel | 每个功能至少一项，客户逐项签字 |

功能的稳定编号（FN-001…）只在数据文件、变更台账和验收清单里使用；客户看的功能清单不带编号。

| 文件 | 目录 | 阶段 | 来源数据 | 生成命令 |
|---|---|---|---|---|
| 01-需求说明书.pdf | docs/01-需求对接 | requirements | requirements（需求清单可由 features 生成） | `client requirements-draft` / `client requirements` |
| 02-方案说明书.pdf | docs/01-需求对接 | proposal | features / proposal | `client proposal` |
| 03-系统架构图.pdf | docs/01-需求对接 | proposal | architecture / features | `client proposal` |
| 04-功能清单.xlsx | docs/01-需求对接 | proposal | features（含 `hours`）/ quote | `client proposal` |
| 05-业务逻辑确认表.xlsx（及 -回填） | docs/01-需求对接 | client-intake | features + intake-extra | `client intake-form` / `client intake-import` |
| 06-需求变更台账.xlsx | docs/01-需求对接 | 全程 | data/changes.json | `change add/update` 自动重排 |
| 需求、调研、方案、客户信息、交付阶段的评审 HTML（01 需求评审、02 调研结论、03 方案评审、04 业务逻辑确认评审、05 交付评审，内部页，给你审批、给开发看） | raw/reviews（不进 docs，不交给客户） | requirements / research / proposal / client-intake / handover | 同阶段数据 | `document` / `render` |
| 开发阶段的 HTML（系统架构、前端界面设计、各前端原型、后端设计规范、实现报告；验收测试、发布、运维评审页由 Luz-Ops 生成，只给开发看） | docs/02-产品开发（平铺，一个序号顺序，不建子目录） | architecture … operations | 同阶段数据 / data/ops | `document` / `render` |
| 验收测试报告.pdf / 发布说明.pdf / 运维手册.pdf | docs/03-验收交付 | verification / release / operations | data/ops | `ops.py client-doc <项目> test-report｜release-notes｜operations-manual`（Word 排版，只交 PDF） |
| 用户协议.pdf / 隐私政策.pdf | docs/03-验收交付 | implementation | 功能清单 + 技术方案里的个人信息处理 | Luz-Dev 的 `formal_doc.py build`（Word 排版，只交 PDF），再 `project.py artifact <项目> implementation <PDF> --kind legal-pdf` 登记；无账号、不收集个人信息的产品在实现报告页写明不适用 |
| 使用说明.pdf | docs/03-验收交付 | handover | manual / features | `client manual` |
| 验收清单.xlsx | docs/03-验收交付 | handover | data/acceptance/checklist.json | `client acceptance` |
| 需求变更台账-交付快照.xlsx | docs/03-验收交付 | handover | data/changes.json | `change snapshot` |

交付前对 PDF 跑 `py -X utf8 D:\Codes\Luz-Design\scripts\check_pdf.py <文件> --fonts any`：字体嵌入、文字层、书签、文档标题和语言应零错误（Word 版的标题和语言由构建自动补；WPS 不产生结构标签，只提示，不得声称已满足无障碍标签）。

目录约定由 `validate_project` 检查：**给客户的只有 PDF 和 XLSX**，HTML 只给开发看，只放 02（开发评审页）和 03 的 Ops 证据页；01 目录出现 HTML 是错误。

## 2. 从一句需求到交付（顺序固定）

**每一份文档都先走 Crawl，取到足够的信息才能写**：下面每个阶段先 `crawl_preflight.py run`、读正文、`conclude`、`check`，再写数据、再生成文件；构建命令在没有该阶段通过的前置检索时直接拒绝，不会写出任何文件。补充信息里的来源、结论、采用位置、采用决定和未覆盖范围要真的进入文档内容，不是走个形式。

1. **requirements**：**先有需求文档**。客户没有需求文档时，先写 `data/client/requirements.json`（`project.py client requirements-draft` 生成草稿；读 `luz-writing` 的 `client-document` 规则卡和 `luz-design` 的 `docx` 规则卡；项目背景要有按使用方的现状问题表，需求清单写清每条需求的具体要求和业务规则，规范见第 3b 节），填完后 `project.py client requirements` 用 Word 排版导出 `01-需求说明书.pdf`；客户有自己的需求文档时放进 `raw/uploads/` 并在 `requirements.json` 的 `client_document` 里登记。没有需求文档，需求阶段不能批准，方案也生成不了。再把一句话需求补成需求评审页：目标、用户、范围、成功标准、待决项。
2. **research**：Crawl 前置检索 + 调研结论页（同类方案书结构、行业规则、平台前置条件）。
3. **proposal**：
   - 读 `luz-system` 的 `function-list` 规则卡，写 `data/client/features.json`（模块、功能、基础/可选、规则、使用端、角色、标签、**工时 `hours`**）；写 `quote.json`（`{"unit_price": 500}`，元每人天）；工时是估算，须请用户确认。
   - 读 `luz-design` 的 `docx` 规则卡和 `luz-writing` 的 `general` 规则卡写 `proposal.json`（`format: word`）：先分析客户的需求（现状、痛点、各使用方的核心需求），再给出解决方案。`client proposal-draft` 生成含“待补充”的草稿，**草稿不能构建**。
   - `architecture.json` 由 `proposal-draft` 按功能清单先推一版，再改成客户能看懂的节点名和作用。
   - `client proposal` 经 Design 构建：方案说明书 PDF、系统架构图 PDF、功能清单 Excel（含报价清单）。
   - `project.py document <项目> proposal --file …` 生成开发版评审页。
   - 用户把三份文件交给客户确认后，`approve proposal` 记录确认依据。
4. **client-intake**：`client intake-form` 生成业务逻辑确认表（每个功能一行写出拟定的业务逻辑 + 待决定的规则 + 需要客户提供的资料）→ 客户确认或修改 → `client intake-import <回填.xlsx>`。需要提供的必填项未答、选了“需修改”却没写修改后的逻辑，都不能通过；确实要延后的用 `client intake-defer "分类/业务逻辑" --owner --due --note`。客户放弃基础功能、选择可选功能、修改业务逻辑，都会自动写入变更台账。
5. **architecture → design → technical-plan → implementation**：各技能读 `project.py context <项目> <阶段> --skill <技能>`，返回的 `client` 段含客户确认过的 `features.json`、`intake.json` 答案、待确认变更和该阶段的交付物路径。功能在架构、设计、开发里的落点用 `project.py link FN-001 --arch … --design … --dev …` 登记，`trace` 报缺口。
6. **verification → release → operations**：进入验证前先运行 `client acceptance-plan` 生成 `data/acceptance/checklist.json`（只写数据，不出 Excel）；Luz-Ops 读它的 `evidence_checks`，把每个验收项映射到测试证据，并分别在三个阶段出验收测试报告、发布说明、运维手册（PDF）。客户在交付阶段才签字，所以 operations 只验证映射完整，不要求签字。
7. **handover**：`client acceptance` 刷新验收清单数据（保留已有结果）并生成 Excel，其“测试证据”列写 Ops 的中文检查名；写 `manual.json` 后 `client manual` 生成使用说明；客户逐项选“通过/不通过”并签名签日期，`client acceptance-import` 回收；`change snapshot` 冻结台账；`approve handover`。

任何阶段发生客户新增需求、修改规则、补充细节：先按 [change-control.md](change-control.md) 登记，再动手。

## 3. 版式标准（版式由 Luz-Design 保证，这里只写怎么选）

| 文件 | 版式 | 规范位置 |
|---|---|---|
| 方案说明书、使用说明 | **客户正式文档**：封面（无页码）→ 目录（每条可点击跳转，罗马页码）→ 正文（页码从 1，居中）；页眉写文档标题；全文黑白，表格也不上色；一级标题“一、”，二级“（一）”，三级“1.”，Word 自动编号；标题不写括号说明；每张表有表题（在表上方）、跨页写“续表 N”并重复表头；宋体小四、1.5 倍行距；只交付导出的 PDF | Design 规范页：文字文档 › 客户正式文档；规则卡 `docx` |
| 系统架构图册 | **atlas 样式**：标题前不加图标；标题、表题、表头、正文同一种墨色、同一种常规字重；表头浅底、行间发丝线，没有黑线黑框；表头与本列同向（文字列左对齐，标记列居中）；不设页眉标题，第一页也不写大标题，从第一章开始（`show_title: false`），页脚页码居中；只有图和表，不写段落 | Design 规范页：系统架构图册；规则卡 `showcase` |
| 功能清单、业务逻辑确认表、验收清单、台账 | Excel：宋体 12 磅，标题 16 磅粗体居中，文字一律黑色，颜色只做底色（功能清单按功能模块用六种淡色区分，可选功能黄色高亮，副标题写明颜色含义），表头蓝灰底，分组名居中，数字右对齐，细黑边框，关闭网格线，横向 A4 一页宽、重复表头、页脚页码；分组列由大到小纵向合并；汇总行用 `footer` | Design 规范页：表格文件；规则卡 `xlsx` |

## 3b. 需求说明书怎么写

`data/client/requirements.json`（`format: word`）：`title`、`subtitle`、`hero.info`、`toc: true`、`sections[{key, title, blocks}]`。`project.py client requirements-draft` 写出带 `待补充` 的草稿，填完后 `project.py client requirements` 用 Word 排版并导出 `01-需求说明书.pdf`；草稿和缺章的资料生成不了。**必有七章**（按 `section.key` 检查）：

| key | 章 | 写什么 |
|---|---|---|
| `background` | 项目背景 | 业务现状（客户是做什么的、现在怎么做、规模多大）和按使用方的现状问题表：使用方 / 现状问题 / 具体表现 / 带来的后果 |
| `goals` | 建设目标 | 三到四个可检验的目标，各写衡量方法 |
| `scope` | 范围与使用者 | 本期范围、不在本期范围、使用者与使用端表 |
| `requirements` | 需求清单 | 每条需求：编号、需求、具体要求、业务规则、类型。功能清单已有时用 `{"type": "auto", "what": "requirement_list"}` 生成，需求与功能清单不会不一致 |
| `rules` | 业务规则与约束 | 业务规则、时间与金额口径、数据范围、合规与平台约束，写边界和数字 |
| `acceptance` | 验收标准 | 怎样算做好了：可观察的结果和验收方式 |
| `open` | 需要客户确认的事项 | 事项 / 为什么需要确认 / 建议的做法 |

- 只写需求，不写解决方案、技术细节和价格；块只用文段、小标题、列点和带表题的表；标题不加括号；不提及其他文件（`《方案说明书》` 等，校验会拦截）。
- 需求来自客户的原始资料（`raw/uploads/`）、与客户的沟通和对同类系统的调研，调研按 Luz-Crawl 前置检索，写进需求阶段的来源。
- 客户有自己的需求文档时：文件放 `raw/uploads/`，`requirements.json` 写 `{"client_document": {"file": "raw/uploads/<文件名>", "note": "<说明>"}}`，不再生成需求说明书。两种情况下，需求阶段都要有需求文档才能批准，方案阶段也不能在没有需求文档时生成。
- 需求说明书的来源（`requirements.json` 和用到的 `features.json`）改了，PDF 即“已过期”，重新生成后才能再批准。

## 4. 方案说明书怎么写

`data/client/proposal.json`（`format: word`）：`title`、`subtitle`、`hero.info`（封面：项目名称、版本、日期）、`toc: true`、`sections[{key, title, blocks}]`。**必有三章**（按 `section.key` 检查）：`background` 项目背景与需求分析、`solution` 解决方案、`deliverables` 交付内容；常加 `goals` 建设目标。

- **先分析，再给方案**：`background` 写业务现状（现状问题表：现状问题 / 具体表现 / 带来的后果）、需求分析（按使用方：使用方 / 现状与痛点 / 核心需求 / 解决方式）和本期需求边界（试点规模、不做什么）。需求来自需求说明书（或客户自己的需求文档）和对同类系统的调研，不凭空写；客户原始资料放 `raw/uploads/`。
- **解决方案要让客户看懂系统**：`solution` 先写一段总体思路，再分小节：系统构成（系统 / 使用者 / 解决什么问题 / 主要功能模块）、角色与权限、业务流程（环节表加一天的运转）、各系统的功能与业务逻辑（每个系统一张表：功能模块 / 主要功能 / 业务逻辑，业务逻辑写边界和数字）、统一业务规则。
- **块只有这些**：`text` 文段、`sub` 二级标题、`bullets` 列点、`table`（必须有 `caption`，长文本列用 `widths` 给相对宽度）、`matrix`。不用卡片、指标卡、图标。
- **标题精简**：标题不加括号说明（“一天的运转”，不是“一天的运转（以预约为例）”），说明放进正文或表题。
- **不提及其他文件**：不写本项目文件的名字（《功能清单》《系统架构图》《业务逻辑确认表》等）、配套文件、见某某表，校验会拦截；法规、标准的名称照 GB/T 15834 用书名号，不受限。**不写价格**：价格只在功能清单的报价清单里；方案里写“第三方费用由客户承担”这类约定即可。
- **用客户的词**：写“顾客预约时段”，不写“调用预约服务接口”；不出现技术栈、库表、内部编号；每个数字有依据。
- 完整示例见 `references/examples/proposal.example.json`。

## 5. 系统架构图册怎么画

`data/client/architecture.json`（`style: atlas`，横版），只有图和表，不写段落。**必有四章**（`section.key`）：`layers` 总体架构、`modules` 功能模块与逻辑、`dependencies` 模块依赖关系、`dataflow` 数据链路与流转；再按项目加关键流程（泳道图加校验表）、状态、数据隔离与权限、部署、各端功能分布。

1. **总体架构**（`figure: arch_layers`）：3–4 层——使用端、业务模块（按业务分组）、基础保障；每层 ≤ 6 个节点；`flows` 画 6–9 条编号数据流，说明写在图下表，再加“各层职责与运行方式”表。
2. **功能模块与逻辑**：表（模块 / 输入 / 处理逻辑 / 输出 / 数据保存在）。
3. **模块依赖关系**：矩阵（行模块依赖列对象，“是”标注）+ 表（被依赖的对象 / 被谁使用 / 不可用时的影响）。
4. **数据链路与流转**：表（数据 / 产生于 / 经过 / 保存在 / 被谁使用）。
5. **关键流程**：泳道图（泳道是角色，列是阶段，步骤只连相邻阶段，**连线不写标签**）+ 校验表。
6. 状态表、数据隔离与权限表、部署图（`figure: deployment`）、各端功能分布（`auto: role_module_matrix`）。

每个节点和流向都来自功能清单与客户确认的规则，不凭空画；每张表有表题；排版后每页占满率 ≥ 70%，不满就调整章节与块的顺序，不加空白页。

## 6. 功能清单与报价

`data/client/features.json`：`modules[{id,name,summary,icon?}]`，`features[{id: FN-001…, module, name, surface, roles[], tier(基础|可选), summary, rules, hours, tags[], depends_on[], acceptance[]}]`。`hours` 是人天，可到 0.5；`quote.json` 写 `{"unit_price": 500}`。成品 `04-功能清单.xlsx`：

- **功能清单**：使用端 → 使用角色 → 功能模块（三级分组，由大到小，纵向合并）、功能、功能说明、类型；没有编号，也没有业务规则。
- **报价清单**：同一份清单，加“工时（人天）”“报价（元）”，第 2 行灰色副标题写“金额 = 工时 × 人天单价”；表下方“基础功能小计”“可选功能小计，选用后另计”“报价合计，基础功能 N 人天，单价 M 元每人天”。有 `quote.json` 才生成；每个在范围内的功能都必须有 `hours`。

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
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client <项目> proposal          # 方案资料通过后才生成（Word 排版需要本机有 WPS 文字或 Word）
py -X utf8 D:\Codes\Luz-Project\scripts\project.py trace <项目>                    # 功能追溯与缺口
py -X utf8 D:\Codes\Luz-Project\scripts\project.py check <项目> --strict
```

生成后必须逐页看渲染图：方案封面无页码、目录可点击且页码对、续表有“续表 N”；架构图册没有黑线黑框和粗体、标题与表头同一种墨色、表头与列同向；Excel 的标题、表头、分组带、汇总行颜色与第 3 节的版式规范一致。文件被用户在 Excel 或 WPS 里打开时无法覆盖，先请用户关闭。

## 表格里的分组列（所有客户 Excel 通用）

连续重复的列（使用端、使用角色、功能模块、分类、子类）都是分组列：**排在名称前面，按大组到小组排，纵向合并，数据按同样顺序排序**；类型、必填、状态这类描述一行属性的列放在后面，不合并。已按此排列：功能清单与报价清单（使用端 → 使用角色 → 功能模块）、验收清单（使用端 → 功能模块）、确认表（分类 → 子类）；变更台账按时间排，没有分组列。新增任何表格都用 Design 的 `group_by`，不手工排列；`check_document` 会拦截顺序错误。表格下方的汇总行用 `footer`，标签写“合计”“小计”或“总计”。
