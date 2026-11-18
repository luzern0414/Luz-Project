# 显式项目上下文与交接

仅用户调用 luz-project、给出 LUZ_PROJECT_ROOT 或提供项目 context 才启用完整目录和矩阵。读取规则卡、运行检查或单独调用专业 skill 不自动 init。LUZ_PROJECT_ROOT 指向已有 project.json 所在的状态根（项目会话的 `raw\`）；缺失时报错，不在附近目录猜测或创建。`project.py` 接收项目路径的命令都接受状态根或项目目录两种写法（规则见 [project-structure.md](project-structure.md)）。

## 逐文件审批（用户只审 docs 里的文件，一次一个）

用户审批的单位是 docs 里的文件（`docs/01-需求对接`、`02-产品开发`、`03-验收交付`）。每个文件由用户单独审批：生成一个、过内部检查、向用户出示这一个（路径、是什么、怎么看，三行以内）、用户说“通过”才记录、再生成下一个；用户提修改意见就登记、修改、重新生成、再出示。**用户不再审批、也不被要求看**评审页（`reviews/`）、Crawl 记录与结论、规则卡采用记录、专家技能自检、trace、`00-design/` 下的过程文件。完整操作手册见 [runbook.md](runbook.md)。

- **顺序**：全局顺序 = 阶段顺序，阶段内按矩阵 `documents` 的顺序（设计阶段：各前端原型 → 02-前端界面设计，因为它内嵌原型）。下一阶段的文件不得在上一阶段的全部文件通过前生成；同一阶段的几个文件可由同一条命令一次构建，但当前待审文件永远只有一个，`approve --doc` 按顺序强制。
- **记录**：`APPROVALS.json` 里 `scope: "document"` 的记录含 `document`、`stage`、`hash`、`source_hashes`、`upstream`（顺序在前的各文件的哈希）、`mode`（`user` 或 `pre-authorized`）、`approver`、`note`、`time`。文件、来源数据或前面任何一个文件变了，记录即失效；已批准的文件被改，它和顺序在它之后的文件（含下游阶段）的批准一并作废。旧的阶段级记录继续有效，`project.py approvals-upgrade <项目>`（预演；`--apply` 才写，写前备份）把它拆成逐文件记录。
- **内部门**：矩阵给每个阶段写了有序的 `steps`，`internal_records` 列出阶段必须有但用户不审的内部记录。所有 `prepare`、`produce` 步骤（上游已通过、规则卡采用记录、Crawl 前置检索、专家产出、文件已生成、内部记录、trace）通过，文件才能出示给用户、才能记录批准；生成命令只要求 `prepare` 步骤。上游阶段的内部记录事后缺了（Crawl 结论、评审页、规则卡记录），即使它的文件都已被用户批准，下游也不放行。**Crawl 记录的七天期限只管正在做的阶段**：上游已批准阶段的记录只核对存在、有效（任务标记、日志哈希）、已 conclude，不因超过七天挡下游（`check`、`gate` 同理，否则项目拖过一周就走不下去，还逼人重跑已批准阶段的调研）；变更重开某阶段后，它的批准作废、重新算作进行中，期限从它的检索时间起重新生效（超过七天要重新检索）。`project.py checklist <项目> [阶段]` 实时显示每一步已完成/未做/被什么阻断以及下一条命令；`project.py step <项目> <阶段> rules|specialist --note …` 记录工具看不到的两步。
- **没有 docs 文件的阶段**（research，或客户自带需求文档时的 requirements）：不设用户审批，内部步骤全部通过后 `project.py approve <项目> <阶段>` 自动完成并留 `scope: "stage"`、`mode: "internal"` 的记录。
- **活文件与客户输入**：`06-需求变更台账.xlsx` 随台账变化，不单独审批，交接阶段以快照审批；客户的 `05-业务逻辑确认表-回填.xlsx` 和验收清单上的签字是客户的输入，不审批，由内部门检查。
- **动作门**：真实生产发布（release 的 `production-release`）和客户最终验收（handover 的 `final-acceptance`）不是文件，仍须用户明确授权：`project.py action <项目> <阶段> <动作> --note <用户原话> --approver <用户>`；不接受整体预先授权的写法。
- **修改意见**：`project.py review <项目> add|done|list`，记在状态根 `data/review-notes.json`；有 open 意见的文件不能批准；`done` 要求文件自登记意见后确有变化。已批准的文件之后又要改，走变更台账。
- **预先授权（旧的整体授权）**：备注以“用户整体预先授权”开头的旧批准升级为 `mode: pre-authorized` 的逐文件记录，**视为待用户复核**：哈希不变、下游不作废，但 `project.py next` 把它们排在最前，存在待复核文件时不得生成新阶段的文件（生成命令和 `gate` 都拒绝并指出是哪个文件），用户逐个复核后用 `approve --doc`（或 `confirm`）记 `mode: user` 的记录。只有用户显式把 `project.json` 的 `approval_policy.mode` 设为 `blanket`，才允许继续生成，并且记录必须在备注里如实标明；这不是默认路径，agent 不得自己设置。

## 接入既有仓库

已有代码和文档的项目不重建目录：`project.py adopt <仓库目录> --name <名称> --move <旧路径>=<新路径> … --alias test=tests --alias infra=config`。仓库成为项目目录（目录名要是 `NNN-项目名`），状态根在新建的会话里。`--move` 的目标是成果位置（docs 的三个目录等）时用 `git mv` 留在仓库里，是源文件或过程文件的位置（如 `uploads/旧文档/…`）时搬进状态根；代码目录不改名，只在状态根 `config/paths.json` 的 `aliases` 记录标准目录与实际目录的对应；留在仓库里的移动之后自动修复 Markdown 相对链接和 `docs/…` 路径提及（`project.py relink` 可重跑）。不预设任何阶段为已批准，历史文档只当输入材料。

## 路由（十二个阶段，每个阶段先做 Crawl 前置检索等内部步骤，再由用户逐个审批 docs 里的文件）

1. **requirements 需求对接**（Project）：客户没有需求文档时先写 `01-需求说明书.pdf`（背景、目标、范围、需求清单、规则与约束、验收标准、待确认事项），内部另有需求评审页；客户自带需求文档时登记后本阶段没有文件。
2. **research 调研结论**（Crawl）：行业、同类产品、平台与技术信息，来源、发现、采用位置、未覆盖范围。
3. **proposal 方案文档**（Project 编排；System 写功能清单，Writing 写方案文字，Design 出版式，Crawl 检索）：产出给客户的两份 PDF（方案说明书：先做需求分析，再给出解决方案；系统架构图册）加一份 Excel（功能清单，**默认只列功能**，不出现人日、预算、单价、金额；用户或客户明确要求才在 `config/documents.json` 的 `estimate` 打开人日（加工时列）和报价（加人工报价清单），开关要带谁要求、何时、原话，报价的数字只来自人工报价单，见 [client-documents.md](client-documents.md) 第 6 节）；同时产出稳定功能 ID `FN-001…`。开发版评审 HTML 放状态根的 `reviews/`。客户确认后才进入下一步。
4. **client-intake 业务逻辑确认**（Project；System、Design 协助）：下发 Excel 业务逻辑确认表：每个功能拟定的业务逻辑和待决定的规则由客户确认或修改，另收只有客户才有的资料（小程序 AppID、域名、首批名单与套餐等）；回收后结构化入库，修改的逻辑进变更台账；必填资料未答、选了需修改却没写新逻辑，不得进入设计。
5. **architecture 系统架构**（System）：读已批准的功能清单与客户答案，产出系统架构文档（`01-系统架构.html`，标签页与必须有的内容见 [dev-documents.md](dev-documents.md)）；在 `project.py link <FN> --arch <模块ID>` 登记每个功能的落点，`project.py trace` 对照系统架构每张功能卡所属的模块：范围内的功能没有登记、登记的模块与功能卡所属模块不一致、引用了不存在的模块，都是缺口（旧版 `logic.modules` 结构仍兼容）。`data/baseline.json` 的 `stack` 与 `modules` 两段属于本阶段，批准时记哈希，之后不能悄悄改（见 [tech-baseline.md](tech-baseline.md)）。架构文档本身不设前端页签；有界面的项目，界面的功能层（页面与路由、入口、标签栏项数与名称、组件清单、按钮动作、状态、数据需求、文案键，不选颜色、字体、图标、圆角阴影、配图与动画，见 Luz-Design `references/ui-ownership.md`）写在**界面功能说明**里，和入口表 `entrances*.json`（每个前台功能的类型、类别、唯一入口归属、目的地、使用频次；用 Luz-System 的 `entrances_check.py` 检查）、原型逻辑 `proto-logic*.json` 一起作为本阶段的随附产物登记（`project.py artifact … --kind frontend-spec | frontend-spec-page | entrances | proto-logic`，见 [dev-documents.md](dev-documents.md)），受哈希保护；缺少前三类，或入口表没有覆盖每个功能，`approve` 不放行。
6. **design UI 设计**（Design）：交付物是 `02-前端界面设计.html` 和每个前端一个的可交互原型，原型的文件名是“序号 + 前端名称 + 原型”（手机页加后台是 `03-手机原型.html`、`04-后台原型.html`），清单由 `data/stages/design.json` 的 `prototype` 块决定（`init`、`migrate`、`context`、`document` 都按它生成，`document` 同时把这些原型文件登记为本阶段产物），设计文档还没有时用矩阵默认；读架构前端视图与客户品牌素材；先完成本阶段检索并实际查看同类成熟界面，再按 Design 的组件复用合同做出完整界面包并做真实浏览器审阅，用户给过版本化的界面配置时优先复用。设计不增删功能与入口。
7. **technical-plan 后端设计规范**（Dev）：读系统全视图、设计交接和客户答案；写合同、实体、迁移、权限、部署和回滚，规则类功能写成可配置的规则集与回归样例。
8. **implementation 产品开发**（Dev）：按批准方案把代码写进项目目录的 src/test/infra/config，输出实现报告与里程碑证据。
9. **verification 验收测试**（Ops）：按使用端选检查（浏览器自动化、压力测试、小程序自动化、智能体评测、规则核算回归等），证据绑定文件哈希，并映射到验收清单的每一项。
10. **release 发布交付**（Ops）：发布计划、迁移、回滚演练、监控；用户明确授权才执行发布动作。
11. **operations 运行交付**（Ops）：运行手册、告警、备份恢复、遗留风险。
12. **handover 交付验收**（Project 编排；Ops、Writing、Design 协助）：使用说明 PDF、验收清单 Excel（客户逐项签字）、变更台账快照；全部通过后项目完成。

全程：任何新增、修改、删除、补充，按 [change-control.md](change-control.md) 先登记到全局变更台账。

## 交接输入矩阵（每个技能读什么，写什么）

`project.py context <项目> <阶段> --skill <技能>` 只读，返回 `state_root`、`deliver_root`（成果写进它的 `docs\…`）、owner、前序阶段全部产物（绝对路径与哈希）、`client` 段（数据文件路径、交付物清单与是否已登记、待确认变更、最近变更、该阶段要调用的技能规则卡命令、目录约定）、检索范围、阻断项。有 blockers 不是执行授权。

| 阶段 | 读取 | 写出（唯一事实来源 → 派生物；data、reviews 在状态根，docs 在项目目录） |
|---|---|---|
| requirements | 用户原话 | data/client/requirements.json → 01 需求说明书 PDF；data/stages/requirements.json → reviews/01-需求评审.html |
| research | 需求页 | Crawl 任务与结论页 → reviews/02-调研结论.html |
| proposal | 需求、调研、`config/documents.json` 的 `estimate` 开关 | data/client/{features,proposal,architecture}.json（开了报价才读 quote.json）→ 02 方案 PDF、03 架构 PDF、04 功能清单 Excel + reviews/03-方案评审.html |
| client-intake | features.json、intake-extra.json | data/client/intake.json → 05 业务逻辑确认表与回填 + reviews/04-业务逻辑确认评审.html |
| architecture | features.json、intake.json 答案、变更 | data/stages/architecture.json → docs/02-产品开发/01-系统架构.html；link 登记 arch |
| design | 架构前端视图、品牌素材答案 | 02-前端界面设计.html 与各前端原型、令牌、资产清单；link 登记 design |
| technical-plan | 架构、设计、intake 规则答案、变更 | 05-后端设计规范.html、合同、迁移；link 登记 dev |
| implementation | 技术方案 | src/test/infra/config、06-实现报告.html、07-用户协议.pdf、08-隐私政策.pdf（有账号或收集个人信息时） |
| verification | 实现、设计绑定、checklist.json（先 `client acceptance-plan`） | data/ops/checks.json、04-验收测试报告.pdf |
| release | 验收测试报告 | 发布报告、回滚证据、05-发布说明.pdf |
| operations | 发布 | 运行手册、监控与备份证据、06-运维手册.pdf |
| handover | features.json、manual 事实、checklist、ops 证据、变更台账 | manual.json → 01-使用说明.pdf；checklist.json → 02-验收清单.xlsx；03-台账快照 |

跨阶段不丢上下文的三个机制：稳定 ID（REQ/FN/ACC/CHG）、`data/` 单一事实来源、哈希门禁（来源变化使下游批准作废）。技能不得复制一份“自己的版本”，改动经 Project 的命令或变更台账。

## 可执行交接

```powershell
python -X utf8 D:\Codes\Luz-Project\scripts\project.py context "<project>" proposal --skill luz-writing
python -X utf8 D:\Codes\Luz-Project\scripts\project.py gate "<project>" proposal
python -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<project>" proposal
python -X utf8 D:\Codes\Luz-Project\scripts\project.py document "<project>" proposal --file "<评审事实.json>"
python -X utf8 D:\Codes\Luz-Project\scripts\project.py next "<project>"
python -X utf8 D:\Codes\Luz-Project\scripts\project.py checklist "<project>" proposal
python -X utf8 D:\Codes\Luz-Project\scripts\project.py approve "<project>" proposal --doc "docs/01-需求对接/02-方案说明书.pdf" --note "<用户原话>" --approver "<实际审批的用户>"
python -X utf8 D:\Codes\Luz-Project\scripts\project.py change "<project>" add --type 修改 --title … --detail …
python -X utf8 D:\Codes\Luz-Project\scripts\project.py trace "<project>"
```

**技术底座**见 [tech-baseline.md](tech-baseline.md)：技术栈、前端规范、基础功能先在技能里固定，项目只在 `data/baseline.json` 里对每一项写沿用、调整、新增或不用并给理由；`init` 之后、写任何开发文档之前先写这份表态。

**登记表与交付物的检查**：`project.py check` 报告产物编号重复（`data/artifacts.json` 里同一个 ART 号出现两次、同一阶段的 `artifact_ids` 里同一个号登记两次、一个号属于两个阶段），登记产物时遇到重复编号直接拒绝（先 `project.py migrate` 去掉阶段列表里重复的号，登记表里重复的要人工处理），已经发过的号（登记表、阶段列表、审批里出现过的）不会再发给新产物；还报告交付物文件不存在：一个阶段的评审页或开发文档一旦登记，它在 `project.json` 里列为必须的其他 HTML 交付物（设计阶段的各前端原型）必须存在，PDF 和 XLSX 不在这里查（客户文件由 `approve` 把关，协议和运维文档由 Luz-Ops、Luz-Dev 把关）。交付物清单过期（例如设计文档已把原型改叫 `03-手机原型.html` 而 `project.json` 还列着 `03-小程序原型.html`）时，运行 `project.py migrate` 按设计文档刷新。

**开发文档的标准**见 [dev-documents.md](dev-documents.md)：四份设计文档（系统架构、前端界面设计、后端设计规范、实现报告）的名字、标签页、必须有的底座对照表、功能卡、表和图、来源和检查；阶段路由 `project.py route` 会给出标准文件、要读的规则卡和文档路径。评审页的事实 JSON（`document --file`）的字段见 [stage-document.md](stage-document.md)。

**写文档之前先 Crawl**：阶段评审页（`document`）、需求说明书（`client requirements`、`requirements-draft`；没有需求文档就先写它，方案以它为前提）、方案说明书与系统架构图和功能清单（`client proposal`、`proposal-draft`）、业务逻辑确认表（`client intake-form`）、使用说明与验收清单（`client manual`、`client acceptance`）在对应阶段的前置检索没有 conclude 并通过 check 时直接报错，什么都不写；Ops 的三份客户 PDF 和 Dev 的协议 PDF 同样。变更台账、客户回填的导入和汇总页不受此限。gate 检查前序阶段的文件是否都由用户逐个批准（含预先授权待复核的）、前序阶段的内部步骤是否仍通过、文件哈希和当前阶段的 Crawl。`approve --doc` 另要求：顺序在前的文件都已通过、没有未处理的修改意见、本阶段的内部步骤（含真实评审 HTML、客户文档齐全且不过期、没有待确认变更影响本阶段，见 [client-documents.md](client-documents.md)）全部通过，并自动把本阶段检索记录与结论 HTML 纳入哈希。不能手写 approved 状态、代用户确认或复用另一阶段的审批。

**给其它技能的只读接口**：`project.py action-status <项目> <阶段> <动作>`（动作门是否已被用户授权且仍有效，退出码 0/1，Ops 的发布命令调用）、`project.py crawl-expiry-waived <项目> <阶段>`（阶段已完成则 Crawl 记录不受七天约束，退出码 0/1，各技能的 crawl_gate 调用），以及 `context` 输出里的 `rule_files`（luz-ops、luz-crawl 没有 context.py 规则卡，该读的文件列在这里）。调用方式见 [runbook.md](runbook.md) 第 12 节。

**预算、人日与报价（默认不写）**：`config/documents.json` 的 `estimate` 有两个独立的开关（`workdays` 人日、`quote` 报价；报价要同时开人日），默认都关，打开必须带 `requested_by`、`requested_at`、`request_note` 三项证据，没有证据就打不开（命令和 `check` 都拒绝）。`project.py client <项目> estimate …` 改开关，`client <项目> quote …` 记录人工报价；开了报价而没有合格的 quote.json 时项目“等待人工报价”，`next`、`checklist`、汇总页把它列为用户待办并阻断方案文件的生成与出示。改开关是变更：已有批准文件时自动登记变更台账并重开方案阶段。proposal 阶段的 `specialist` 与 `build` 内部步骤都以 estimate 开关为判据。

项目模式直接用本项目的 HTML/JSON 和审批，不再要求把项目复制进旧 System 会话或旧 Dev plan。保留专业规则和实质检查：System 对模块/页面/动作/异常的核对；Design 的完整界面包、真实浏览器审阅和 check_document 与对比度检查；Dev 的合同/源码/测试与技术依据；Ops 的真实文件证据。旧 new_session.py、add_mode.py、publish.py 和 tech_plan.py/design_intake.py 的会话路径门禁用于 standalone，不能再对项目 HTML 强套旧目录。

## 目录与配置

见 [project-structure.md](project-structure.md)。`init` 在项目目录只建 docs 的三个目录，在状态根建 `data`、`config`（`paths.json`、`documents.json` 文档主题与 `estimate` 人日、报价开关、`keys.example.json` 仅列密钥引用）；项目参数、URL、环境、功能开关这几类产品配置（`project/environments/urls/features/validation.json`）写在项目目录的 `config/`，在有内容要写的阶段才创建，不造空文件；真实 key 放本机 .env 或密钥服务。
