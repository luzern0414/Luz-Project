# 项目目录与数据文件

一个项目有两个根。**项目目录**（`D:\Codes\NNN-项目名`）放产品实现、软件源代码和正式交付物。制作源稿、项目审批和过程记录在状态根。**状态根**是项目会话的 `raw\`，放工具的全部状态与过程文件。会话目录与项目目录同名，根上只有 `raw\` 和汇总页：

```
E:\Skill输出\Luz-Project\NNN-项目名\        会话（项目总览）
  NNN-项目名.html                                 汇总页：成果清单（项目内路径）、各阶段状态与审批、各技能会话索引、过程文件
  raw\                                            状态根（LUZ_PROJECT_ROOT 和 project context 指这里）
    project.json  MANIFEST.json  APPROVALS.json   状态、审批（project.json 为准，deliver_root 记项目目录；approval_policy 记审批模型 document 与模式 user|blanket；APPROVALS.json 里逐文件记录 scope=document，内部完成 scope=stage，动作门 scope=action）
    config\     paths.json documents.json keys.example.json    目录对应、文档主题和 estimate 开关（人日与报价，默认都关）、密钥引用清单（密钥只写引用）；init 就有
    data\
      client\   features.json proposal.json architecture.json requirements.json intake.json intake-extra.json manual.json
                trace-links.json build.json ledger-snapshot.json                   客户文档的事实来源
      changes.json  artifacts.json  baseline.json  sessions.json                   变更台账、产物登记、对技术底座的表态（stack、frontend、modules）、其他技能的会话
      steps.json  review-notes.json            内部步骤记录（规则卡采用、专家产出）、用户对文件的修改意见
      acceptance\ checklist.json               验收清单（事实，Ops 读取；交付阶段生成时才建）
      stages\   各阶段文档的事实 JSON
      ops\      checks.json 与 Ops 机器结果
    00-design\  实际使用的 Design 模板选择、快照与输出哈希；init 为机器状态汇总页生成首条记录
    00-crawl\   Crawl 前置检索记录与结论页（project.json 的 crawl.evidence_index 指这里；爬取的原始内容在 Skill输出\Luz-Crawl 的任务里，crawl.task_root 指它）
    reviews\    需求、调研、方案、客户信息、交付阶段的评审页（内部记录，用户不审阅）
    uploads\    客户上传的原始资料
    client-docs\  客户文档的 Word 源文件、构建中间件、页面总览图
    architecture\frontend-spec\  架构阶段的随附产物（界面功能说明、入口表、原型逻辑，登记在 architecture 阶段下，见 dev-documents.md）
    backup\     迁移时搬来的旧索引页与备份；approvals-upgrade 写之前的 APPROVALS.json、project.json 备份
D:\Codes\NNN-项目名\                              项目目录（deliver_root）
  docs\
    01-需求对接\   客户需求、方案、确认和变更
    02-产品开发\   开发阶段的设计、实现与评审
    03-验收交付\   客户验收、使用与运行资料
  src\ test\ assets\ infra\ scripts\                 产品的实现、测试、素材、部署与迁移（有东西要写时才建）
  data\schema users roles business fixtures seeds imports exports snapshots   开发与测试用的业务数据（有内容时才建）
  config\       产品自己的配置：project environments urls features validation.json（有内容要写的阶段才建）
  .gitignore  .env.example
```

完整文件名、条件和阶段由 [开发矩阵](development-matrix.json) 登记。原型文件按前端名称命名。每份文件的用途、内容结构和生成入口见 [客户文档](client-documents.md) 与 [开发文档](dev-documents.md)。

## 规则

1. **项目目录只放成果**：docs 的三个目录和产品的实现。raw、检索记录、客户上传件、评审页、project.json、MANIFEST.json、APPROVALS.json、台账与事实 JSON、Luz 工具的 config、描述文件和生成脚本、构建中间件、备份与临时文件都在状态根。`project.py check` 调用 `check_output_layout.py project` 把混入的这些报成错误。
2. **一个事实一个来源**：功能清单、规则、台账、验收项都只在状态根的 `data/` 里有一份 JSON；PDF、Excel、HTML 都是派生物，不手改。
3. **docs 里只放交付物，每个目录只有一层**：01 和 03 只放给客户的 PDF、XLSX，02 只放开发阶段的 HTML，文件名都是 `NN-名称`（两位序号）；评审页是内部记录（用户不审阅），放状态根的 `reviews\`；docs 下不建子目录，也不放 Markdown、Word 和客户原始资料。`check` 逐个文件检查类型和序号，并按登记的阶段检查放没放对位置。
4. **路径怎么写、怎么找**：成果（docs、src、test、assets、infra、scripts、`data` 下的 schema/seeds/fixtures 等业务数据、产品自己的 config）写进项目目录；其余（project.json、`data` 下的 client/stages/ops/acceptance 与 changes/artifacts/baseline/sessions.json、`config` 下的 paths/documents/keys.example.json、00-crawl、reviews、uploads、client-docs）写进状态根。登记的产物路径相对它所在的根（`docs/01-需求对接/01-需求说明书.pdf`、`reviews/01-需求评审.html`），工具按这条规则找回文件；project.json 里其他技能读取的路径（`crawl.evidence_index`）相对状态根。
5. **给一个路径找状态根**：该路径下有 project.json，它就是状态根（旧项目的项目根也适用）；否则当作项目目录，状态根是 `E:\Skill输出\Luz-Project\<该目录名>\raw`（环境变量 `LUZ_PROJECT_OUTPUT` 改输出根）。`project.py` 接收项目路径的命令（init 以外）两种写法都能用。成果写到 `deliver = project.json 的 deliver_root，没有则状态根`，再写到 `deliver\docs\…`。
6. **空目录不预先建**：`init` 在项目目录只建 docs 的三个目录，在状态根建 `config`、`data` 和工具马上要写的 `data/client`、`data/stages`、`data/ops`，并为实际生成的机器状态汇总页保存 `00-design` 模板选择、源快照与输出哈希；这不是业务方案，也不递归触发研究。`00-crawl`、`reviews`、`uploads`、`client-docs`、`data/acceptance`，以及项目目录里的 src、test、assets、infra、scripts、`data/schema` 这类，有东西要写时才建。`config/` 在状态根只有 `paths.json`、`documents.json`、`keys.example.json`。项目目录的 `.gitignore` 起手就忽略 `.env`、`node_modules/`、`dist/`、`build/` 等；`adopt`、`migrate` 只补缺的行。
7. **派生物带来源哈希**：`data/client/build.json` 记录每份客户文档构建时的来源哈希，来源变化即“已过期”，重新生成后才能再审批。
8. **批准后的来源不能悄悄改**：阶段批准时记录跟踪文件的哈希（requirements：requirements；proposal：features/proposal/architecture；client-intake：intake；architecture：`data/baseline.json` 的 stack 与 modules 两段（记作 `data/baseline.json#stack,modules`，frontend 段属于 design，不在内）；handover：manual/checklist/changes）；之后变化必须经变更台账重开阶段。被审批绑定哈希的文件（登记的数据文件与评审页、跟踪的客户数据）迁移时不改内容。
   旧布局的 `00-design` 记录与快照也原样移入状态根。迁移前核验原模板与产物，迁移后只为实际移动且字节相同的输出保存独立凭据；读取时核对原记录哈希、准确旧新路径、模板和产物字节。该凭据不允许新生成沿用旧位置的选择，重新生成仍需准确 `select`。
9. **config 不放秘密值**，`data/` 里只放开发/测试/脱敏数据，线上数据在业务服务里。
10. **汇总页**是会话根的 `NNN-项目名.html`，由 `project.py render`（以及 init、adopt、migrate、每次审批）生成，是用户读的页面：顶部只有“当前待审文件”（路径、是什么、怎么看）和按顺序的文件清单与状态；各阶段内部检查、审批记录、`project.py session` 登记的各技能会话、过程文件折叠在末尾“过程记录（无需审阅）”（旧模型的项目仍是成果清单加阶段审批表）；项目目录里不生成 README.html 之类的索引。
11. **旧项目**（project.json 在项目目录里、没有 `deliver_root`、工具文件在 `raw\`）继续按原样工作，成果仍在原项目根；用 `project.py migrate <项目>` 预演，确认后加 `--apply` 迁移：状态与过程文件搬到新建的状态根，项目目录只留成果，台账里的路径改写（内容不变，审批哈希不变），旧 docs 布局的文件按名字搬进平铺的新目录并补两位序号，补新增阶段；默认不改任何文件。检索记录里写着旧项目根下日志的绝对路径，搬家后 `project_crawl_gate.py` 在新的 `00-crawl` 下按同样的位置读取，日志哈希照样核对。
