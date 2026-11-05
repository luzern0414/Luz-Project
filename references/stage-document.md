# 阶段事实 → HTML

`project.py document <project> <stage> --file <json>` 生成该阶段的评审页（需求、调研、方案、客户信息、交付阶段在状态根的 `reviews/`，开发阶段在项目目录的 `docs/02-产品开发/`，文件名见 [dev-documents.md](dev-documents.md) 与 [project-structure.md](project-structure.md)）并把事实写进状态根的 data/stages/*.json 登记。所有阶段含 title、conclusion、sources（id/url/finding/applies_to）。architecture、design、technical-plan、implementation 的 spec 是 `tabs`（实现报告是 `sections`）加 `sources`，标签页、章节和块由 [dev-documents.md](dev-documents.md) 规定，`scripts/dev_documents.py` 校验，不符合的写不出来；汇总页不能充当架构交付物。其余阶段另含 sections 数组：每节 `title` 加 `content`（字符串、列表或字典），或 `title` 加 `blocks`（`text`、`sub` 小标题、`bullets`、带表题的 `table`，表题写成“表 N　名称”由系统编号，表里不留空格，没有内容写“—”，与开发文档同一套写法）；有表的节，来源表也编号。需要对比、对照的内容（同类产品对比、需求与功能对照）用 `blocks` 里的表，不拼成一段段文字；不能只交付空模板。评审页不用“摘要”“小结”这类附属章节标题，段落不以“说明：”“建议：”开头（`check_document` 会报）。

## 三个客户阶段的评审页

proposal、client-intake、handover 的评审 HTML 同样用 `project.py document` 生成（title、conclusion、sections、sources），系统会自动追加：稳定功能 ID 清单与客户文档过期状态（proposal）、客户回填状态（client-intake）、验收进度与追溯缺口（handover），以及待确认变更。客户文档本身（PDF/XLSX）不走 `document`，走 `project.py client …`，详见 `client-documents.md`。
