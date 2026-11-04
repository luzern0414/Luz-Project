# 阶段事实 → HTML

`project.py document <project> <stage> --file <json>` 生成该阶段的评审页（需求、调研、方案、客户信息、交付阶段在 `raw/reviews/`，开发阶段在 `docs/02-产品开发/`，文件名见 [dev-documents.md](dev-documents.md) 与 [project-structure.md](project-structure.md)）并登记 data/stages/*.json。所有阶段含 title、conclusion、sources（id/url/finding/applies_to）。architecture、design、technical-plan、implementation 的 spec 是 `tabs`（实现报告是 `sections`）加 `sources`，标签页、章节和块由 [dev-documents.md](dev-documents.md) 规定，`scripts/dev_documents.py` 校验，不符合的写不出来；项目索引页不能充当架构交付物。其余阶段另含 sections 数组（title/content），内容可为字符串、列表或字典；不能只交付空模板。

## 三个客户阶段的评审页

proposal、client-intake、handover 的评审 HTML 同样用 `project.py document` 生成（title、conclusion、sections、sources），系统会自动追加：稳定功能 ID 清单与客户文档过期状态（proposal）、客户回填状态（client-intake）、验收进度与追溯缺口（handover），以及待确认变更。客户文档本身（PDF/XLSX）不走 `document`，走 `project.py client …`，详见 `client-documents.md`。
