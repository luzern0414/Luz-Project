# 显式项目上下文与交接

仅用户调用 luz-project、给出 LUZ_PROJECT_ROOT 或提供项目 context 才启用完整目录和矩阵。读取规则卡、运行检查或单独调用专业 skill 不自动 init。LUZ_PROJECT_ROOT 指向已有 project.json；缺失时报错，不在附近目录猜测或创建。

## 接入既有仓库

已有代码和文档的项目不重建目录：`project.py adopt <项目根> --name <名称> --move <旧路径>=<新路径> … --alias test=tests --alias infra=config --alias raw/logs=logs`。文档按 `--move` 用 `git mv` 迁入 01/02/03（01 只留给客户的文件，开发文档进 02，测试与交付进 03），代码目录不改名，只在 `config/paths.json` 的 `aliases` 记录标准目录与实际目录的对应；迁移后自动修复 Markdown 相对链接和 `docs/…` 路径提及（`project.py relink` 可重跑）。不预设任何阶段为已批准，历史文档只当输入材料；`.gitignore` 追加 `raw/client-docs/`。

## 路由（十二个阶段，每个阶段都先做 Crawl 前置检索，再审批）

1. **requirements 需求对接**（Project）：用户一句话补成需求评审页（目标、用户、范围、成功标准、待决项）。
2. **research 调研结论**（Crawl）：行业、同类产品、平台与技术信息，来源、发现、采用位置、未覆盖范围。
3. **proposal 方案文档**（Project 编排；System 写功能清单，Writing 写方案文字，Design 出版式，Crawl 检索）：产出给客户的两份 PDF（方案说明书：先做需求分析，再给出解决方案；系统架构图册）加一份 Excel（功能清单，含报价清单）；同时产出稳定功能 ID `FN-001…`。开发版评审 HTML 放 `raw/reviews/`。客户确认后才进入下一步。
4. **client-intake 业务逻辑确认**（Project；System、Design 协助）：下发 Excel 业务逻辑确认表：每个功能拟定的业务逻辑和待决定的规则由客户确认或修改，另收只有客户才有的资料（小程序 AppID、域名、首批名单与套餐等）；回收后结构化入库，修改的逻辑进变更台账；必填资料未答、选了需修改却没写新逻辑，不得进入设计。
5. **architecture 系统架构**（System）：读已批准的功能清单与客户答案，产出系统架构文档（`01-系统架构.html`，标签页与必须有的内容见 [dev-documents.md](dev-documents.md)）；在 `project.py link` 登记每个功能的落点。前端页签只写功能：页面与路由、入口、标签栏项数与名称、组件清单、按钮动作、状态、数据需求，不选颜色、字体、图标、圆角阴影、配图与动画（见 Luz-Design `references/ui-ownership.md`）；同时交入口表 `entrances.json`（每个前台功能的类型、类别、唯一入口归属、目的地、使用频次），用 Luz-System 的 `entrances_check.py` 检查。
6. **design UI 设计**（Design）：读架构前端视图与客户品牌素材；先请用户选风格，再交 UI 交接（令牌、图标、状态、断点、动作绑定）；整个阶段按 Luz-Design 的规则卡 `design-path` 的路径走，首页与页面范式读 `page-patterns`，据 architecture 阶段交来的入口表 `entrances.json` 做首页，缺的、冲突的退回 architecture。构图、卡片、按钮外观、图标、配图、动效、主题和原型的全部外观都在这一阶段由 Design 决定；不增删架构已批准的页面、入口、标签栏项数、组件与按钮动作，需要改时退回 architecture 并走变更台账。
7. **technical-plan 技术方案**（Dev）：读系统全视图、设计交接和客户答案；写合同、实体、迁移、权限、部署和回滚，规则类功能写成可配置的规则集与回归样例。
8. **implementation 产品开发**（Dev）：按批准方案写 src/test/infra/config，输出实现报告与里程碑证据。
9. **verification 验收测试**（Ops）：按使用端选检查（浏览器自动化、压力测试、小程序自动化、智能体评测、规则核算回归等），证据绑定文件哈希，并映射到验收清单的每一项。
10. **release 发布交付**（Ops）：发布计划、迁移、回滚演练、监控；用户明确授权才执行发布动作。
11. **operations 运行交付**（Ops）：运行手册、告警、备份恢复、遗留风险。
12. **handover 交付验收**（Project 编排；Ops、Writing、Design 协助）：使用说明 PDF、验收清单 Excel（客户逐项签字）、变更台账快照；全部通过后项目完成。

全程：任何新增、修改、删除、补充，按 [change-control.md](change-control.md) 先登记到全局变更台账。

## 交接输入矩阵（每个技能读什么，写什么）

`project.py context <项目> <阶段> --skill <技能>` 只读，返回 owner、前序阶段全部产物（绝对路径与哈希）、`client` 段（数据文件路径、交付物清单与是否已登记、待确认变更、最近变更、该阶段要调用的技能规则卡命令、目录约定）、检索范围、阻断项。有 blockers 不是执行授权。

| 阶段 | 读取 | 写出（唯一事实来源 → 派生物） |
|---|---|---|
| requirements | 用户原话 | data/client/requirements.json → 01 需求说明书 PDF；data/stages/requirements.json → raw/reviews/01-需求评审.html |
| research | 需求页 | Crawl 任务与结论页 → raw/reviews/02-调研结论.html |
| proposal | 需求、调研 | data/client/{features,quote,proposal,architecture}.json → 02 方案 PDF、03 架构 PDF、04 功能清单 Excel + raw/reviews/03-方案评审.html |
| client-intake | features.json、intake-extra.json | data/client/intake.json → 05 业务逻辑确认表与回填 + raw/reviews/04-业务逻辑确认评审.html |
| architecture | features.json、intake.json 答案、变更 | data/stages/architecture.json → docs/02-产品开发/01-系统架构.html；link 登记 arch |
| design | 架构前端视图、品牌素材答案 | 02-前端界面设计.html 与各前端原型、令牌、资产清单；link 登记 design |
| technical-plan | 架构、设计、intake 规则答案、变更 | 05-后端设计规范.html、合同、迁移；link 登记 dev |
| implementation | 技术方案 | src/test/infra/config、06-实现报告.html、用户协议.pdf、隐私政策.pdf（有账号或收集个人信息时） |
| verification | 实现、设计绑定、checklist.json（先 `client acceptance-plan`） | data/ops/checks.json、验收测试报告.pdf |
| release | 验收测试报告 | 发布报告、回滚证据、发布说明.pdf |
| operations | 发布 | 运行手册、监控与备份证据、运维手册.pdf |
| handover | features.json、manual 事实、checklist、ops 证据、变更台账 | manual.json → 使用说明.pdf；checklist.json → 验收清单.xlsx；台账快照 |

跨阶段不丢上下文的三个机制：稳定 ID（REQ/FN/ACC/CHG）、`data/` 单一事实来源、哈希门禁（来源变化使下游批准作废）。技能不得复制一份“自己的版本”，改动经 Project 的命令或变更台账。

## 可执行交接

```powershell
python -X utf8 D:\Codes\Luz-Project\scripts\project.py context "<project>" proposal --skill luz-writing
python -X utf8 D:\Codes\Luz-Project\scripts\project.py gate "<project>" proposal
python -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<project>" proposal
python -X utf8 D:\Codes\Luz-Project\scripts\project.py document "<project>" proposal --file "<评审事实.json>"
python -X utf8 D:\Codes\Luz-Project\scripts\project.py approve "<project>" proposal --note "<客户确认原话与方式>" --approver "<实际确认人>"
python -X utf8 D:\Codes\Luz-Project\scripts\project.py change "<project>" add --type 修改 --title … --detail …
python -X utf8 D:\Codes\Luz-Project\scripts\project.py trace "<project>"
```

**技术底座**见 [tech-baseline.md](tech-baseline.md)：技术栈、前端规范、基础功能先在技能里固定，项目只在 `data/baseline.json` 里对每一项写沿用、调整、新增或不用并给理由；`init` 之后、写任何开发文档之前先写这份表态。

**开发文档的标准**见 [dev-documents.md](dev-documents.md)：四份设计文档（系统架构、前端界面设计、后端设计规范、实现报告）的名字、标签页、必须有的底座对照表、功能卡、表和图、来源和检查；阶段路由 `project.py route` 会给出标准文件、要读的规则卡和文档路径。评审页的事实 JSON（`document --file`）的字段见 [stage-document.md](stage-document.md)。

**写文档之前先 Crawl**：阶段评审页（`document`）、需求说明书（`client requirements`、`requirements-draft`；没有需求文档就先写它，方案以它为前提）、方案说明书与系统架构图和功能清单（`client proposal`、`proposal-draft`）、业务逻辑确认表（`client intake-form`）、使用说明与验收清单（`client manual`、`client acceptance`）在对应阶段的前置检索没有 conclude 并通过 check 时直接报错，什么都不写；Ops 的三份客户 PDF 和 Dev 的协议 PDF 同样。变更台账、客户回填的导入和项目索引页不受此限。gate 检查前序用户审批、文件哈希和当前阶段的 Crawl。approve 另要求：当前阶段有真实评审 HTML；三个客户阶段还要求客户文档齐全、位于规定目录且不过期（见 [client-documents.md](client-documents.md)）；没有待确认变更影响本阶段；approve 自动把本阶段检索记录与结论 HTML 纳入哈希审批。不能手写 approved 状态、代用户确认或复用另一阶段的审批。

项目模式直接用本项目的 HTML/JSON 和审批，不再要求把项目复制进旧 System 会话或旧 Dev plan。保留专业规则和实质检查：System 对模块/页面/动作/异常的核对；Design 的风格确认、check_document/contrast；Dev 的合同/源码/测试与技术依据；Ops 的真实文件证据。旧 new_session.py、add_mode.py、publish.py 和 tech_plan.py/design_intake.py 的会话路径门禁用于 standalone，不能再对项目 HTML 强套旧目录。

## 目录与配置

见 [project-structure.md](project-structure.md)。config 存项目参数、URL、环境、功能开关和文档主题，keys.example.json 仅列密钥引用；真实 key 放本机 .env 或密钥服务。
