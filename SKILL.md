---
name: luz-project
description: 用户明确要求创建、管理或执行完整 Luz 项目时使用，覆盖需求、客户方案文档、客户资料收集、系统架构、视觉设计、开发、测试、发布、运维和最终交付；负责目录、交付文件定义、阶段审批与需求变更台账。
metadata:
  short-description: 编排完整 Luz 项目生命周期与客户文档
---

# Luz 项目

负责项目目录、文件用途、阶段顺序、审批与变更。用户显式调用本技能或给出项目上下文（含 `LUZ_PROJECT_ROOT`）才启用矩阵。

## 调用协议

以 [references/runbook.md](references/runbook.md) 为唯一执行手册。各方分工、依据、模板及质量规则见 [技能协作](references/skill-architecture.md)、[阶段检索](../Luz-Crawl/references/evidence-policy.md)、[文档验收](../Luz-Design/references/document-evidence.md) 和 `quality_rules.py list --owner luz-project --stage <阶段>`。

1. 运行 `python -X utf8 scripts/project.py matrix`，读手册和 [经验](experience/catalog.md)。新项目用 `project.py init`，既有仓库用 `adopt`，旧布局先预演 `migrate`。按[目录规范](references/project-structure.md)分开放产品成果与状态记录。
2. `project.py next`、`project.py checklist <项目> <阶段>` 确认当前步骤。取 `project.py context <项目> <阶段> --skill <技能>` 后依次完成规则、阶段依据、领域自检、模板绑定和追溯。遇 `blockers` 先补前置条件。内部步骤不省略。
3. 一次一个文件。展示当前 `docs/` 文件的路径、是什么、怎么看，三行以内。用户明确通过才用 `project.py approve` 记原话、审批人及当前文件。修改意见用 `project.py review` 登记，更新后重新出示。
4. 需求变化先 `project.py change`。受影响的阶段按[变更规则](references/change-control.md)重新确认。生产发布和最终验收是动作门，用 `project.py action` 记录当次授权。项目整体预先授权条件见手册。
5. 预算、人日与报价默认不写。用户或客户明确要求才用 `project.py client <项目> estimate`，记录要求人、日期和原话。没有人工报价时显示“等待人工报价”，agent 不得自拟。
6. 用 `project.py trace`、`project.py render`、`project.py check <项目> --strict` 复核交付。`experience.py note` 写入或确认本次经验。

## 项目文件

正式文件及顺序来自 `project.py matrix`。`docs/01-需求对接` 读[客户文档](references/client-documents.md)。`docs/02-产品开发` 读[开发文档](references/dev-documents.md)，原型按前端名称命名。各技能提供本方内容和证据，正式文档从状态根的事实数据生成，采用 Luz-Design 的模板和排版。

修改技能入口、路由或共享合同后，运行 `python -X utf8 scripts/skill_contracts.py`。
