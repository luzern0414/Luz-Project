---
name: luz-project
description: 用户要求搭建或规范项目目录、编写项目 README、整理和命名项目资料，或创建、管理和执行完整 Luz 项目时使用。负责交付文档、阶段顺序、审批和需求变更。
metadata:
  short-description: 编排完整 Luz 项目生命周期与客户文档
---

# Luz 项目

负责项目目录、文件用途、阶段顺序、审批与变更。用户显式调用本技能或给出项目上下文（含 `LUZ_PROJECT_ROOT`）才启用矩阵。

## 调用协议

以 [references/runbook.md](references/runbook.md) 为唯一执行手册。各方分工、依据、模板及质量规则见 [技能协作](references/skill-architecture.md)、[阶段检索](../Luz-Crawl/references/evidence-policy.md)、[文档验收](../Luz-Design/references/document-evidence.md) 和 `quality_rules.py list --owner luz-project --stage <阶段>`。

1. 运行 `python -X utf8 scripts/project.py matrix`，读手册和 [经验](experience/catalog.md)。搭建新目录用 `project.py scaffold`，见[项目目录标准](references/project-structure.md#项目目录标准)。启用阶段矩阵用 `project.py init`，既有仓库用 `adopt`，旧布局先预演 `migrate`。阶段执行路径见[现行工具目录](references/project-structure.md#现行工具目录)。
2. `project.py next`、`project.py checklist <项目> <阶段>` 确认当前步骤。取 `project.py context <项目> <阶段> --skill <技能>` 后依次完成规则、阶段依据、领域自检、模板绑定和追溯。遇 `blockers` 先补前置条件。内部步骤不省略。
3. 新商业项目按[三次项目确认](references/commercial-project.md)执行。System 调 Crawl 研究同类系统，同批生成需求与方案。第一次确认后，System 与 Dev 在本阶段联合检索并形成四份功能和技术说明。第二次确认后由 Design 制作可操作的 HTML Demo。第三次确认后定稿对接资料 03 至 06。一次出示整批，用户明确通过才用 `project.py approve` 登记原话与版本。需要修改用 `project.py review`。已有逐文件项目沿用原审批模型。
4. 需求变化先 `project.py change`。受影响的阶段按[变更规则](references/change-control.md)重新确认。生产发布和最终验收是动作门，用 `project.py action` 记录当次授权。项目整体预先授权条件见手册。
5. 预算、人日与报价默认不写。用户或客户明确要求才用 `project.py client <项目> estimate`，记录要求人、日期和原话。没有人工报价时显示“等待人工报价”，agent 不得自拟。
6. 用 `project.py trace`、`project.py render`、`project.py check <项目> --strict` 复核交付。`experience.py note` 写入或确认本次经验。

## 项目文件

涉及应用界面的项目，从第二批前端开发说明开始采用 [Design 成品要求](../Luz-Design/references/design/hard-rules.md)。第三批构建在浏览器逐步检查入口、动作和结果页，把 HTML、规则版本与走查记录绑定到本批确认。Ops 验收浏览器界面时保存内置浏览器的实际操作结果。

每个项目根目录的 `README.md` 按[项目 README 写法](references/project-structure.md#项目-readme)介绍用途、核心功能、业务流程和开发入口。按[中文模板](templates/项目骨架/README.md)填写，开发交接前核对启动步骤和仓库内链接。

项目骨架还包含 Git 忽略清单、环境变量示例、配置与数据库迁移说明。商业项目由矩阵固定对接和开发资料编号，包括第三次确认的 `docs/03-开发资料/05-交互原型.html`。单独整理档案时按[文件命名规则](references/project-structure.md#编号与归档)及已有外发记录编号。开发文种见[开发资料模板](templates/03-开发资料/README.md)。

已有逐文件项目继续按前端名称归档分端原型，在各自的评审记录中保留原路径。

阶段矩阵生成的正式文件及顺序见 `project.py matrix`，内容要求见[客户文档](references/client-documents.md)与[开发文档](references/dev-documents.md)。正式文件从状态根的事实数据生成，沿用 Luz-Design 的版式。

调研、检索和其他通用成文文件按 [Luz-Design 通用文档模板](../Luz-Design/references/design/documents.md#通用文档模板) 制作。[通用文档模板 PDF](templates/通用模板/通用文档模板.pdf)供查阅。

修改技能入口、路由或共享合同后，运行 `python -X utf8 scripts/skill_contracts.py`。
