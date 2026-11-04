# 项目目录与数据文件

```
<项目根>/
  project.json  MANIFEST.json  APPROVALS.json  README.html      状态、审批与索引（project.json 为准）
  config/       paths.json documents.json keys.example.json            init 就有：目录对应、文档主题、密钥引用清单（密钥只写引用）
                project/environments/urls/features/validation.json      技术方案、实现等阶段有内容要写时才建，init 不造空文件
  data/
    client/     features.json proposal.json architecture.json intake.json intake-extra.json manual.json
                trace-links.json build.json ledger-snapshot.json                   客户文档的事实来源
    changes.json                                                                    全局变更台账（事实）
    baseline.json                                                                   项目对技术底座的表态（stack、frontend、modules 三段）
    acceptance/ checklist.json                                                      验收清单（事实，Ops 读取；交付阶段生成时才建）
    stages/     各阶段评审 HTML 的事实 JSON
    ops/        checks.json 与 Ops 机器结果
    schema/ users/ roles/ business/ fixtures/ seeds/ imports/ exports/ snapshots/   业务数据模型与开发数据（有内容时才建）
  docs/
    01-需求对接/   需求对接阶段交给客户的文件，平铺，只有 PDF、XLSX：01 需求说明书、02 方案说明书、03 系统架构图、04 功能清单、05 业务逻辑确认表与回填、06 需求变更台账
    02-产品开发/   开发阶段的 HTML，平铺、一个序号顺序：01 系统架构、02 前端界面设计、各前端的原型（03 起，文件名是“序号 + 前端名称 + 原型”，有几个前端就几个：手机网页加后台是 03-手机原型、04-后台原型，小程序加后台是 03-小程序原型、04-后台原型）、05 后端设计规范、06 实现报告、07 验收测试评审、08 发布评审、09 运维评审
    03-验收交付/   交付给客户的文件，平铺，只有 PDF、XLSX：使用说明、验收清单、变更台账快照、验收测试报告、发布说明、运维手册、用户协议、隐私政策
  src/ test/ assets/ infra/    实现、测试、素材、部署与迁移
  raw/          00-crawl/ Crawl 前置检索记录与证据（project.json 的 crawl.evidence_index 指向这里），uploads/ 客户上传，reviews/ 各阶段给你审批、给开发看的评审页（内部页），client-docs/ 客户文档的构建中间件与渲染总览图
```

## 规则

1. **一个事实一个来源**：功能清单、规则、台账、验收项都只在 `data/` 里有一份 JSON；PDF、Excel、HTML 都是派生物，不手改。
2. **docs 里只放交付物，每个目录只有一层**：01 和 03 只放给客户的 PDF、XLSX，02 只放开发阶段的 HTML；给你审批、给开发看的评审页（需求、调研、方案、客户信息、交付）是内部页，放 `raw/reviews/`，不进 docs，也不和客户的文件混放；docs 下不建任何子目录，也不放 Markdown、Word 和客户原始资料（它们放 `raw/`）。`check` 逐个文件检查类型，并按登记的阶段检查放没放对位置，旧项目用 `migrate` 搬家。
3. **空目录不预先建**：`init` 只建第一层（src、test、assets、infra、raw、scripts、config、data、docs 的三个目录）和工具马上要写的 `data/client`、`data/stages`、`data/ops`；`data/acceptance`、`data/schema` 这类以及 src、test、infra、assets 下面的目录，有东西要写时才建。`config/` 只有 `paths.json`、`documents.json`、`keys.example.json`，`project/environments/urls/features/validation.json` 由有内容要写的阶段创建，不造空文件；没有任何工具读取的 `data/sources.json`、`data/decisions.json`、`raw/crawl/evidence.json` 不再生成（旧项目运行 `migrate` 后指针改指 `raw/00-crawl`，空骨架文件由你决定删不删）。`.gitignore` 起手就忽略 `.env`、`node_modules/`、`dist/`、`build/`、`raw/client-docs/`、`raw/uploads/` 等；`adopt`、`migrate` 只补缺的行。
4. **派生物带来源哈希**：`data/client/build.json` 记录每份客户文档构建时的来源哈希，来源变化即“已过期”，重新生成后才能再审批。
5. **批准后的来源不能悄悄改**：阶段批准时记录跟踪文件的哈希（requirements：requirements；proposal：features/proposal/architecture；client-intake：intake；architecture：`data/baseline.json` 的 stack 与 modules 两段（记作 `data/baseline.json#stack,modules`，frontend 段属于 design，不在内）；handover：manual/checklist/changes）；之后变化必须经变更台账重开阶段。
6. **config 不放秘密值**，`data/` 里只放开发/测试/脱敏数据，线上数据在业务服务里。
7. 旧项目用 `project.py migrate <项目>` 升级：把文件搬到平铺的新目录并改写台账里的路径（内容不变，审批哈希不变），补新增阶段，已批准阶段不动，并提示需要补做的客户文档和无法判断去向的文件。
