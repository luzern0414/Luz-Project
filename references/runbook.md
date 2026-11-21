# 项目执行手册

给执行项目的 agent 的唯一操作手册：从 `init` 到最终验收的完整路径。不看任何对话也能照做。下面的命令写 `project.py` 时都指 `py -X utf8 D:\Codes\Luz-Project\scripts\project.py`；`"<项目>"` 是项目目录（如 `D:\Codes\014-示例`）或状态根，两种写法都行。

## 商业项目入口

普通 `init` 启动[商业项目执行路线](commercial-project.md)。Project 先把客户原件与目标交给 System。System 调用 Crawl 查证，再形成第一批两份文件。后续按功能与技术方案、HTML Demo 两批确认，定稿实施基线后接产品开发、测试、发布和移交。项目的阶段、所有者与文件位置从其自身矩阵读取。

以下第 0 至 12 节描述已有逐文件项目。商业项目后半段沿用其中适用的执行和动作授权规则；路径及批次以项目当前矩阵为准。

## 0 三条铁律

1. **用户只审批 docs 里的文件，一次一个。** 一个文件生成并通过内部检查后，只向用户报这一个文件（路径、是什么、怎么看，三行以内），然后停下等用户回复；收到“通过”才记录审批、才开始下一个文件。同一阶段的几个文件可以由同一条命令一次构建（它们同源），但**当前待审文件永远只有一个**，没轮到的文件不出示、不审批。
2. **其余一切是内部记录，必须做完、必须通过，但不让用户审，也不向用户罗列。** 评审页、Crawl 记录与结论页、规则卡采用记录、专家技能的自检、trace、基线对账，都属于内部步骤。减少的是用户要看的东西，不是要做的事：缺一步，生成命令、`approve`、下游阶段都会拒绝，并指出缺的是哪一步。
3. **不绕过。** 不手改 `APPROVALS.json`、`project.json`、`data/steps.json`、`data/review-notes.json`；不代用户批准（备注里写用户的原话，不写“默认通过”“整体通过”）；不拿别的阶段的 Crawl 记录或审批顶替；不因为用户“看起来不看”就把任何内部步骤改成可选。整体预先授权只有用户在 `project.json` 里显式把 `approval_policy.mode` 设为 `blanket` 才成立（见第 8 节），不是默认路径。

用户的原话（项目的出发点）：「我只关注 docs 的产出的文件，每个文件都由我审批，其余 raw 下的 html 等我不需要审核，所以，每次的路径就是生成一个文件，我审批修改，通过后生成下一个。但是要保证路径完整，不能跳过步骤，不能偷工减料。」

## 1 开始之前

只需要把项目目录和基础文件搭好时，使用 `project.py scaffold`。骨架文件、Git 和存放规则见[项目目录标准](project-structure.md#项目目录标准)。下列命令用于开始阶段执行。

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py matrix --workflow legacy
py -X utf8 D:\Codes\Luz-Project\scripts\project.py init <名称> --project-dir <项目目录> --workflow legacy
py -X utf8 D:\Codes\Luz-Project\scripts\project.py next "<项目>"
```

- 只有用户明确要求做完整项目（调用 `luz-project`、给出 `LUZ_PROJECT_ROOT` 或项目 context）才 `init`；项目目录名是 `NNN-项目名`（如 `D:\Codes\015-示例`），会话和状态根建在 `E:\Skill输出\Luz-Project\NNN-项目名\raw`。已有仓库用 `adopt`，旧布局项目用 `migrate`（见 [project-mode.md](project-mode.md)）。
- 读：`SKILL.md`、本手册、[project-mode.md](project-mode.md)、[client-documents.md](client-documents.md)、[dev-documents.md](dev-documents.md)、[tech-baseline.md](tech-baseline.md)、[change-control.md](change-control.md)、`experience/catalog.md`。
- 先 `client "<项目>" theme <主题>` 选一次文档主题（Luz-Design 的主题表，按行业和受众）。
- 每个阶段先用 `project.py checklist "<项目>" <阶段>` 看完整路径：哪一步做了、哪一步没做、被什么挡住、现在该执行哪条命令。**`next` 告诉你现在该做什么，不用自己判断。**
- 同一项目的联网阶段共用一个 Crawl 任务。首次联网时运行 `node D:\Codes\Luz-Crawl\scripts\luz-crawl.mjs begin "<主题>" --out E:\Skill输出\Luz-Crawl --new`，之后每个联网阶段的 `crawl_preflight.py run` 都带 `--task` 指向 `project.json` 里 `crawl.task_root`（第一个有联网记录的阶段审批时绑定任务）。

## 2 每个文件的循环

同一阶段可以先批量完成内部构建；例如 `client proposal` 一次生成方案、架构图册、功能清单，`build` 检查该阶段整组文件。**展示、意见和审批仍严格一次一个文件、按矩阵顺序进行**，不能把一次构建视为一次整组批准。模板、Crawl 和其他内部检查由 agent 完成，不要求用户审批这些过程。

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py next "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py checklist "<项目>" <阶段>
```

`next` 的 `kind` 决定做什么：

| kind | 意思 | 你做什么 |
|---|---|---|
| `internal` | 文件还不能出示，内部步骤没做完 | 执行 `current_step.command`（或按下面各阶段的路径做），做完再 `next`；**不用向用户汇报内部步骤** |
| `present` | 内部步骤全部通过，可以出示 | 把输出里“给用户的汇报”三行发给用户，**然后停下** |
| `revise` | 用户对它提过修改意见，还没处理完 | 按意见改、重新生成、`review done`，再 `next` |
| `waiting` | 本阶段的文件都已通过，在等客户或用户的动作；或开了报价在等人工报价 | 客户回填/签字 → 导入；动作门 → 向用户要明确授权；等待人工报价 → 把 `user_todos` 的话告诉用户（要人天单价或报价单），停下，不自拟数字（第 11 节） |
| `done` | 全部完成 | 交付前最后检查（第 10 节） |

出示给用户的汇报，三行以内，只报这一个文件，不提别的文件、别的阶段、任何内部记录：

```text
文件：docs\01-需求对接\02-方案说明书.pdf
是什么：给客户的方案：先做需求分析，再给出解决方案和交付内容
怎么看：用 PDF 阅读器通读；重点看系统构成、各系统的功能与业务逻辑、交付内容是否与你和客户谈的一致。请回复“通过”或提修改意见。
```

用户回复之后：

- **“通过”**：`approve "<项目>" <阶段> --doc "<路径>" --note "<用户原话>" --approver "<用户>"`（按顺序强制、绑定文件哈希；前面的文件没通过、有未处理的意见、内部步骤有缺都会被拒绝）。再 `next`，进入下一个文件的内部步骤。
- **修改意见**：`review "<项目>" add --doc "<路径>" --text "<意见原文>"`（原话，不改写）。按意见修改数据、重新生成文件；`review "<项目>" done --id <编号> --resolution "<怎么改的>"`（文件没变化会被拒绝；意见撤回或无需改时加 `--unchanged` 并写明原因）；再 `next`，**重新出示同一个文件**。改动让文件哈希变了，后面的文件还没生成就不受影响。
- **沉默、含糊或“都行”**：不是批准。再问一次，或说明你在等什么。

已通过的文件之后又要改：不能直接改，也不能 `review add`。走变更台账（第 6 节）：该文件的批准作废，顺序在它之后的文件（含下游阶段）随之作废，重新生成、重新逐个审批。

## 3 命令速查

每一行是一条能直接运行的命令（`<项目>`、`<阶段>`、`<路径>` 等换成实际值）：

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py next "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py checklist "<项目>" <阶段>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py status "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py route "<项目>" <阶段>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py context "<项目>" <阶段> --skill <技能>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py gate "<项目>" <阶段>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py action-status "<项目>" <阶段> <动作>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py crawl-expiry-waived "<项目>" <阶段>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py step "<项目>" <阶段> rules --note "读了…；采用的规则：…"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py step "<项目>" <阶段> specialist --note "<哪个技能产出了什么；检查结论>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py approve "<项目>" <阶段> --doc "<路径>" --note "<用户原话>" --approver "<用户>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py confirm "<项目>" --doc "<路径>" --note "<用户原话>" --approver "<用户>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py approve "<项目>" research
py -X utf8 D:\Codes\Luz-Project\scripts\project.py review "<项目>" add --doc "<路径>" --text "<意见原文>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py review "<项目>" done --id <编号> --resolution "<怎么改的>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py review "<项目>" done --id <编号> --unchanged --resolution "<为什么不用改>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py review "<项目>" list
py -X utf8 D:\Codes\Luz-Project\scripts\project.py action "<项目>" release production-release --note "<用户原话>" --approver "<用户>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py document "<项目>" <阶段> --file "<评审事实.json>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py artifact "<项目>" <阶段> "<文件>" --kind <类型>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py link "<项目>" FN-001 --arch M01
py -X utf8 D:\Codes\Luz-Project\scripts\project.py trace "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py check "<项目>" --strict
py -X utf8 D:\Codes\Luz-Project\scripts\project.py render "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py approvals-upgrade "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py approvals-upgrade "<项目>" --apply
```

客户文档（经 Luz-Design 版式与检查，生成前同样要内部步骤通过）：

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" theme <主题>
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" requirements-draft
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" requirements
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" proposal-draft
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" proposal
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" intake-form
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" intake-import "<回填表.xlsx>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" intake-status
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" acceptance-plan
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" acceptance
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" acceptance-import "<回填表.xlsx>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" manual-draft
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" manual
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" estimate
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" estimate --workdays on --requested-by "<要求的人>" --requested-at "<日期>" --request-note "<要求的原话>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" estimate --workdays on --quote on --requested-by "<要求的人>" --requested-at "<日期>" --request-note "<要求的原话>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" estimate --quote off --note "<关闭的原因>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" quote --unit-price <数字> --provided-by "<提供报价的人>" --evidence "<提供数字的原话或来源>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" quote --from-file "<报价单.xlsx>" --provided-by "<提供报价的人>"
```

## 4 完整路径

十二个阶段，阶段内的步骤顺序固定（矩阵 `steps`，`checklist` 实时显示）：

| 步骤 | 谁来保证 | 判据 |
|---|---|---|
| `upstream` 上游已通过 | 内部门 | 前面各阶段的 docs 文件都由用户逐个批准，前面阶段的内部步骤仍然通过（它们的 Crawl 记录核对有效性，联网记录还核对已生成结论，**不看是否超过七天**），客户的回填/动作门已完成；`gate` 没有“前置审批未完成”和“待用户复核” |
| `rules` 读 context 与规则卡并记录采用的规则 | 内部门 | `data/steps.json` 有该阶段的 rules 记录（读了哪些卡、采用什么） |
| `crawl` Luz-Crawl 前置检索 | 内部门 | 本地 `run --research local` → `check`，联网另读正文并 `conclude`。`00-crawl` 保留本地依据记录或联网记录及结论页。进行中的联网阶段超过七天要复核 |
| `specialist` 专家技能产出 | 内部门 | 专家技能的事实文件在，`data/steps.json` 有 specialist 记录（产出了什么、技能自带的检查结论）；方案阶段还要确认 `estimate` 开关（默认都关；开了要有证据，开了人日每个功能有 `hours` 与 `hours_basis`） |
| `build` 生成 docs 里的文件 | 内部门 | 文件已生成、已登记、来源没有变化；真实模板最终输出路径与 SHA-256 通过 `phase=post`（只登记产物不能替代）；格式与内容检查通过；开了报价而没有人工报价单就等待，不生成 |
| `records` 内部记录 | 内部门 | 评审页、阶段事实数据已生成并登记，Crawl 记录齐全 |
| `trace` 追溯与基线对账（架构、交接阶段） | 内部门 | `project.py trace` 没有缺口 |
| `present` / `decide` / `record` | 用户门 | 出示这一个文件 → 用户回复 → 记录审批 |
| 客户回填、客户签字 | 客户输入 | 导入后必填项全部有答案 / 验收清单每项通过或豁免 |
| 动作门 | 动作门 | 用户明确授权不是文件的对外动作 |

逐文件审批模型中，已批准阶段仍须通过当前内部门检查。`next` 在跳过阶段或报告项目完成前重验；检索记录、模板最终绑定或完整来源失效时，返回该阶段的首个失败步骤，状态刷新会撤销阶段的缓存完成状态。原始审批历史保留；修复后重新核验，内容有变化时继续按原有哈希与审批规则处理。保留的旧按阶段审批路线也在 `gate` 和 `approve` 统一复核正式文件的真实模板 `phase=post`；重新登记修改后的文件不能替代模板最终哈希。

**每个阶段，按这个顺序做：**

1. `next` / `checklist` 看现在在哪一步。
2. `context "<项目>" <阶段> --skill <技能>` 取交接上下文（`client.skill_cards` 与 `rule_cards` 列出要读的规则卡）；逐张读规则卡，记下采用的规则；然后 `step "<项目>" <阶段> rules --note "读了…；采用的规则：…"`。**luz-ops 和 luz-crawl 没有 context.py 规则卡**：`context` 输出里的 `rule_files` 列出该读的文件（Ops：`SKILL.md`、`references/operations-matrix.json`、`references/release-gates.md`、`references/evidence-formats.md`，加本阶段的手册：验收测试读 `references/test-playbooks/` 里各检查对应的一份，发布读 `ops-playbooks` 的 release-rollback、backup-restore、monitoring-alerting、compliance-baseline，运行读 handoff-runbook、incident-response；Crawl：`SKILL.md`、`references/preflight.md`、`references/research-method.md`），逐个读，rules 记录里写明读了哪几个、采用什么；`checklist` 的 rules 一步会把这些文件的路径列在“要读的文件”下。
3. 按 [检索与依据合同](../../Luz-Crawl/references/evidence-policy.md) 判定本阶段需要的证据。本地资料足够时，执行 `run --research local --reason "<实际依据>"` 和 `check`，在正文指出所用材料，`sources` 留空。需要联网时按 [前置命令](../../Luz-Crawl/references/preflight.md) 选择参数并执行：
   ```powershell
   python -X utf8 D:\Codes\Luz-Crawl\scripts\crawl_preflight.py run --caller <技能> --session "<项目>" --topic "<主题>" --task "<Crawl 任务目录>" --stage <阶段> --research <search|deep|urls> <查询或网址参数>
   python -X utf8 D:\Codes\Luz-Crawl\scripts\crawl_preflight.py conclude --caller <技能> --session "<项目>" --stage <阶段> --file "<补充信息.json>"
   python -X utf8 D:\Codes\Luz-Crawl\scripts\crawl_preflight.py check --caller <技能> --session "<项目>" --stage <阶段>
   ```
   `<技能>` 是该阶段的负责技能（`checklist` 的 crawl 行和 `route` 的 `owner` 都写着）。数量下限、什么算正文、补充信息的字段都在 Luz-Crawl 的 `references/evidence-policy.md`，命令在 `references/preflight.md`（`status` 看还差什么，`review-init`、`supplement-init` 生成待填文件），每个阶段独立 `check`，联网记录须有正文和结论。**七天期限只管正在做的阶段**：上游已批准的联网记录仍须有效、已 conclude，超过七天也不挡下游，不要为了它重跑已批准阶段的调研；变更把某个阶段重开后，它重新算作进行中，记录超过七天就要为它重新检索。
   文档的来源表必须准确采用已存 finding 的 `summary` 或 `quote`；即使填写有效 `finding_id`，也不能另写没有登记的断言或扩大 `applies_to`。采用位置须来自同一 finding 或通过其 finding ID 连接的 coverage；本次方案推导先以 `kind: decision` 登记其依据。
4. 让专家技能产出事实数据，用技能自带的检查；`step "<项目>" <阶段> specialist --note "<哪个技能产出了什么；检查结论>"`。
   `requirements-draft`、`proposal-draft`、`manual-draft` 只准备带占位的内部 JSON，先通过上游、规则卡、本阶段 Crawl 即可；它们是专家填充资料的输入，不能反过来要求尚未产生的 specialist 输出，也不能当作正式文件。
5. 为每份正式输出先执行 Luz-Design 模板库 `list`、`select`，保存真实模板文件、SHA-256、准确输出路径，使用对应生成器生成 docs 里的文件和评审页（命令见下面各阶段），再核验最终 `phase=post`。模板选择、旧文件、手工登记或其他阶段的模板记录不能代替真实生成与最终绑定。**生成命令在前面的内部步骤没做完时会拒绝**，错误里写明缺哪一步。
6. 需要时登记产物、功能落点，运行 `trace`。
7. `next` 变成 `present` 后向用户出示；通过后记录审批；该阶段所有文件逐个通过、客户输入和动作门完成，阶段才算完成。

### 4.1 requirements 需求对接

- 技能：luz-project 编排；luz-writing 写正文（`06-context.py client-document` 卡），luz-system 的 `function-list` 卡，luz-design 的 `docx` 卡；luz-crawl 检索。
- 先写需求资料：`client "<项目>" requirements-draft` 生成 `data/client/requirements.json` 草稿，填完（不留“待补充”）；客户有自己的需求文档时放状态根 `uploads/` 并在 `requirements.json` 的 `client_document` 登记，这时本阶段没有文件，内部门通过后 `approve "<项目>" requirements` 自动完成。
- 文件：`docs/01-需求对接/01-需求说明书.pdf`（`client "<项目>" requirements`，Word 排版导出）。
- 内部记录：`reviews/01-需求评审.html`（`document "<项目>" requirements --file "<评审事实.json>"`，目标、用户、范围、成功标准、待决项）。
- 活文件 `06-需求变更台账.xlsx` 随台账变化，不单独审批；交接阶段以快照审批。

### 4.2 research 调研结论

- 技能：luz-crawl（行业、同类产品、平台与技术）；其他技能协助。
- **没有 docs 文件，用户不看。** 内部记录：`reviews/02-调研结论.html`。步骤 `upstream`、`rules`、`crawl`、`specialist`、`records` 全部通过后：`approve "<项目>" research`，自动完成并留 `scope=stage、mode=internal` 的记录。

### 4.3 proposal 方案文档

- 技能：luz-system（`function-list`、`client-docs` 卡，`features_check.py`）写功能清单 `data/client/features.json`（稳定 FN-ID、基础/可选）；luz-writing 写 `proposal.json`；luz-design 出版式（`docx`、`showcase` 卡）。
- 先 `client "<项目>" proposal-draft`，填完草稿；`client "<项目>" proposal` 一次构建三个文件，**用户仍然一个一个审，顺序是 02 → 03 → 04**：`02-方案说明书.pdf`、`03-系统架构图.pdf`、`04-功能清单.xlsx`。**功能清单默认只列功能，不写人日、预算和报价**；用户明确要求才按第 11 节走。
- 内部记录：`reviews/03-方案评审.html`。

### 4.4 client-intake 业务逻辑确认

- 技能：luz-system 拟定每个功能的业务逻辑；luz-design 的 `xlsx` 卡。
- 文件：`docs/01-需求对接/05-业务逻辑确认表.xlsx`（`client "<项目>" intake-form`）。用户通过后把它发给客户。
- 客户填完交回的 `05-业务逻辑确认表-回填.xlsx` 是**客户的输入，不审批**：`client "<项目>" intake-import "<回填表.xlsx>"` 导入；必填项没答完不能进入下一阶段（`client "<项目>" intake-defer` 可记录责任人和期限）；客户改了的逻辑自动进变更台账。
- 内部记录：`reviews/04-业务逻辑确认评审.html`。

### 4.5 architecture 系统架构

- 技能：luz-system（`system-design` 卡）；写 `data/baseline.json` 的 stack 与 modules 表态（对技术底座逐项沿用/调整/新增/不用，见 [tech-baseline.md](tech-baseline.md)）、功能卡、界面功能说明、入口表。
- 文件：`docs/02-产品开发/01-系统架构.html`（`document "<项目>" architecture --file "<评审事实.json>"`，标准见 [dev-documents.md](dev-documents.md)）。
- 有界面的项目还要登记界面功能说明与入口表：`artifact "<项目>" architecture "<文件>" --kind frontend-spec`（另 `frontend-spec-page`、`entrances`）。
- 每个功能登记落点：`link "<项目>" FN-001 --arch M01`；`trace "<项目>"` 没有缺口才算 `trace` 步骤通过。

### 4.6 design 前端界面设计

- 技能：luz-design（`design-path`、`page-patterns`、`interface-visual`、`interface-layout`、`interface-motion` 卡）与 luz-system（`prototype`、`interaction`、`miniprogram`、`admin-list` 卡）。先完成本阶段检索，再由 Design 按组件复用合同在关联的 Design 会话 raw 里做出完整界面包（`frontend.py init → seal → review → check`，`ui_package.py check` 通过）。设计不增删功能与入口，缺的、冲突的退回 architecture；不把响应式 Web 说成原生小程序。
- 文件，**顺序固定**：各前端原型（`03-手机原型.html`、`04-后台原型.html` 或 `03-小程序原型.html`，清单由 `data/stages/design.json` 的 `prototype` 块决定）→ `02-前端界面设计.html`（它内嵌原型，所以在原型之后审）。
- 命令：先 `project.py session` 登记本项目 luz-design/design 会话；`prototype.source` 记录真实 session/package/entry，每个访问页按准确路径 select `reading-html`。`document "<项目>" design --file "<评审事实.json>"` 核验界面包并生成、登记访问页；图册内嵌包里已审阅的入口，资产留在 Design raw。出示与审批时重验模板 post 哈希、包的回执与完整性和当前审阅。

### 4.7 technical-plan 后端设计规范

- 技能：luz-dev（`backend-module`、`api-data`、`config-logging` 卡）。文件：`docs/02-产品开发/05-后端设计规范.html`（`document "<项目>" technical-plan --file "<评审事实.json>"`）。

### 4.8 implementation 产品开发

- 技能：luz-dev（`project-handoff` 卡）。代码写进项目目录的 `src`、`test`、`infra`；文件顺序：`06-实现报告.html`（`document "<项目>" implementation --file …`）→ `07-用户协议.pdf` → `08-隐私政策.pdf`（Luz-Dev 的 `formal_doc.py build` 起草，经 Design 的 Word 排版导出，再 `artifact … --kind legal-pdf` 登记）。

### 4.9 verification 验收测试

- 技能：luz-ops：`ops.py check <项目> acceptance`，证据绑定文件哈希。先 `client "<项目>" acceptance-plan` 生成验收清单数据。文件顺序：`07-验收测试评审.html` → `04-验收测试报告.pdf`（`ops.py client-doc <项目> test-report`）。

### 4.10 release 发布交付

- 技能：luz-ops。文件顺序：`08-发布评审.html` → `05-发布说明.pdf`。**动作门 `production-release`**：文件都通过后，向用户要明确授权（第 7 节），才执行真实生产发布；没有授权，阶段不算完成，`operations` 不放行。

### 4.11 operations 运行交付

- 技能：luz-ops。文件顺序：`09-运维评审.html` → `06-运维手册.pdf`。

### 4.12 handover 交付验收

- 技能：luz-project 编排，luz-writing 写使用说明，luz-ops 提供验收证据。
- 文件顺序：`docs/03-验收交付/01-使用说明.pdf`（`client "<项目>" manual`，先写 `data/client/manual.json`）→ `02-验收清单.xlsx`（`client "<项目>" acceptance`）→ `03-需求变更台账-交付快照.xlsx`（`change "<项目>" snapshot`，要求变更都已实施：`change "<项目>" update --all-confirmed --note "随版本实施"`）。
- 客户在验收清单上逐项签字 → `client "<项目>" acceptance-import "<回填表.xlsx>"`；签字只来自客户自己的回填，不代签，豁免要有确认人和理由。
- **动作门 `final-acceptance`**：客户签完后，向用户要明确确认（第 7 节）。
- 内部记录：`reviews/05-交付评审.html`。

## 5 内部步骤做完之前，哪些命令会拒绝

| 命令 | 在什么情况下拒绝 |
|---|---|
| `client …`、`document …`（生成任何文件） | 本阶段的 `upstream`、`rules`、`crawl` 没做完：错误里列出缺的步骤；前面有文件还没由用户通过（含“待用户复核”）也是 `upstream` 缺 |
| `step … rules` | `upstream` 没通过 |
| `step … specialist` | `upstream`、`rules`、`crawl` 没做完，或专家技能的事实文件还不在 |
| `approve … --doc` | 顺序在前的文件没通过；文件有未处理的修改意见；内部步骤（`upstream` 到 `trace`）有一步没通过；文件没登记或与登记的哈希不一致 |
| `approve …`（不带 `--doc`） | 阶段有 docs 文件（要逐个审批）；或没有 docs 文件但内部步骤没通过 |
| `action …` | 阶段的文件没有全部由用户通过；内部步骤没通过；备注写成整体预先授权 |

上游阶段的内部记录事后丢了（Crawl 结论、评审页、规则卡记录），即使它的文件都已被用户批准，下游阶段也不放行：`gate "<项目>" <阶段>` 会写“前置阶段 … 的内部步骤未通过”。

## 6 变更

客户新增需求、改规则、补细节、删功能，**先登记再动手**（[change-control.md](change-control.md)）：

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py change "<项目>" add --type 修改 --category 规则 --title "<标题>" --detail "<变更后的具体逻辑>" --source 客户 --requester "<提出人>" --refs FN-002 --affects proposal,architecture --status 已确认 --confirmed-by "<确认人与方式>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py change "<项目>" update <编号> --status 已确认 --confirmed-by "<确认人>" --note "<过程记录>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py change "<项目>" snapshot
```

按文件作废：已确认的变更重开最早受影响的阶段——该阶段所有文件的批准和它之后各阶段的批准全部作废（保留为历史，写明原因）；文件被改动也是同样：该文件的批准作废，顺序在它之后的文件随之作废。作废的文件重新生成（必要时）后再次逐个出示、逐个审批。待确认的变更会阻断它所影响的阶段。`next` 会把作废的文件重新排回队列。

登记先写 `data/changes.json`；若当前阶段的检索、专业资料或模板未就绪，返回的 `ledger_render.status` 是 `deferred` 并说明原因，**登记已成功，不要重复 add**。`data/client/ledger-render.json` 保存工作簿刷新状态。补齐当前阶段的规则与模板后再 `change render`；显式生成仍严格拒绝未过的门禁。活台账随 `current_stage` 校验本阶段的 Crawl 与准确模板，不借用方案阶段的旧记录。`change snapshot` 先通过 handover 门禁，再从事实数据直接生成快照，不以重写活台账作为前置动作。

## 7 动作门

真实生产发布（release 阶段的 `production-release`）和客户最终验收（handover 阶段的 `final-acceptance`）不是文件，是对外动作。该阶段的文件由用户逐个通过后，向用户说明将要发生什么并请他明确授权；收到明确的话再记录：

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py action "<项目>" release production-release --note "<用户原话>" --approver "<用户>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py action "<项目>" handover final-acceptance --note "<用户原话>" --approver "<用户>"
```

动作门没有预先授权的写法（备注写整体预先授权会被拒绝）；授权绑定该阶段文件的哈希，之后文件变了授权作废。

## 8 旧项目、预先授权、blanket

- 旧项目（阶段级批准）：`project.py approvals-upgrade "<项目>"` 预演，确认后加 `--apply`（写之前自动备份 `APPROVALS.json` 与 `project.json` 到状态根 `backup/`；重复运行不改任何东西）。旧批准按文件拆成记录；备注以“用户整体预先授权”开头的记为 `pre-authorized`，其余记为 `user`。
- `pre-authorized` 的文件**视为待用户复核**：它们的哈希不变，下游文件不作废；但 `next` 把它们排在最前，按顺序逐个出示，用户逐个说“通过”后用 `approve --doc`（或 `confirm`）记 `user` 记录。复核期间文件被改过，则需要重新审。**存在待复核文件时，不得生成新阶段的文件**（生成命令和 `gate` 都会指出是哪个文件）。
- `blanket`：只有用户明确说“这个项目的文件我都预先批准”并在 `project.json` 里把 `approval_policy.mode` 改成 `blanket`，才允许 `approve --doc … --pre-authorized`，备注必须以“用户整体预先授权”开头并写用户的原话，写明未逐件审阅；这样记的文件按 `pre-authorized` 记录，`next` 仍会列出它们等用户复核，但不阻止新阶段生成。agent 不得自己改这个设置，也不得把它当默认。

## 9 常见错误与处理

| 报错或现象 | 原因 | 处理 |
|---|---|---|
| “内部步骤没有全部完成”，列出 `rules`、`crawl` 等 | 对应的内部步骤没做 | `checklist` 看顺序，逐步补；`rules`/`specialist` 用 `step` 记录 |
| “不能批准这个文件，前面还有没通过的” | 顺序在前的文件没有用户批准，或前面阶段的客户回填/动作门没完成 | `next` 看当前该审哪个；一次只审一个 |
| “还有 N 条未处理的修改意见” | 用户提过意见，还没 `review done` | 改文件、重新生成、`review done` |
| “自登记这条意见后没有变化” | 没改文件就想标记完成 | 先改；意见撤回时加 `--unchanged` 并写原因 |
| “前置阶段 X 的内部步骤未通过（即使文件已批准，下游也不放行）” | X 阶段的 Crawl 记录/评审页/规则卡记录/检查事后缺了、被改坏或还没 conclude（**记录超过七天不算**：已批准阶段的记录只核对存在、有效、已 conclude） | 回到 X 阶段补做该步骤，不绕过 |
| “待用户复核：…” | 预先授权的文件还没有用户逐个通过 | 按 `next` 的顺序逐个出示 |
| “阶段 X 有 docs 文件，由用户逐个审批” | 对有文件的阶段用了不带 `--doc` 的 `approve` | 用 `--doc <路径>` |
| 文件“已过期”（`build` 步骤） | 数据来源变了，文件是旧的 | 重新生成；已批准的会因哈希变化作废，重新审 |
| 生成命令报“Crawl”相关错误 | 本阶段 `crawl` 步骤没做，或正在做的阶段的记录超过七天（变更重开过的阶段也算） | 重新 `run`、读正文、`conclude`、`check` |
| “等待人工报价” | 开了报价（`estimate.quote`），还没有人工提供的 quote.json | 这是用户待办：向用户要人天单价或客户的报价单和出处，`client "<项目>" quote …` 记录；不自拟、不暂估 |
| “估算开关无效”“缺 requested_by …” | `config/documents.json` 的 `estimate` 开着但证据不全，或要求的人不是具体的人，或报价开着人日没开 | 问清谁、何时、什么原话，用 `client "<项目>" estimate …` 重新打开；不手改 |
| “报价单不合格”“quote.json 缺人工证据字段” | quote.json 缺 `provided_by`/`evidence` 等，或来源是暂估/示例/智能体 | 请提供报价的人确认后用 `client "<项目>" quote …` 重新记录 |
| “04-功能清单 不应有人天、工时”“出现金额” | 没有开对应开关，文件或数据里却有人日或金额 | 去掉；确需写的，先让用户明确要求并打开开关 |
| 汇总页没更新 | 汇总页由 `render` 生成 | `project.py render "<项目>"` |

## 10 交付前最后检查

```powershell
py -X utf8 D:\Codes\Luz-Project\scripts\project.py check "<项目>" --strict
py -X utf8 D:\Codes\Luz-Project\scripts\project.py trace "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py status "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py render "<项目>"
py -X utf8 D:\Codes\Luz-Project\scripts\project.py next "<项目>"
```

`check --strict` 无错误（含 `estimate` 开关与客户文件一致），`trace` 无缺口，`next` 报 `done`；写或确认一条经验（`scripts/experience.py note`），并在 BRIEF 写明“采用的规则”和“本次沉淀”。汇总页 `NNN-项目名.html` 是用户的入口：顶部是当前待审文件和按顺序的文件清单，评审页、调研、Crawl 等过程记录折叠在末尾，无需审阅。

## 11 用户要求预算或报价时怎么走（默认不写）

**默认**：没有人明确要求，功能清单只列功能，客户文件和 docs 里任何地方都不出现人日、工时、预算、单价、金额、合计、报价；“基础/可选”是功能分级，不是价格。不要因为“看起来该有”替用户打开开关，也不要自拟任何估算数字。用户的原话：「有一些项目是不需要写预算的，只有明确要求写人日和报价，才写，否则只需要给出清单即可，且报价必须人工报价，不允许 agent 随便填」。

用户或客户明确要求时，按顺序做：

1. **先记证据，再开开关**。问清谁要求的、哪天、原话，然后：
   ```powershell
   py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" estimate --workdays on --requested-by "<要求的人>" --requested-at "<日期>" --request-note "<要求的原话>"
   ```
   只要人日就到此为止；要报价就同时加 `--quote on`（报价必须同时有人日）。三项证据缺一项，或要求的人是智能体、技能、系统、示例，命令拒绝，`check` 也报错。不带开关参数运行 `estimate` 显示现状；关闭用 `--workdays off`、`--quote off` 并写 `--note` 原因。
2. **写人日要有依据**。开了人日，`features.json` 每个在范围内的功能写 `hours`（0.5 的倍数）和 `hours_basis`（功能复杂度、涉及的页面与接口数、参照的同类功能，不能只有数字），再 `step … specialist` 记录。人日是你的估算，不是承诺：用户批准功能清单之前一律“拟定”，`next` 的汇报会写明，出示时照实告诉用户。
3. **等人工数字**。开了报价，`next` 把“等待人工报价”列为用户待办，方案阶段的文件先不生成：向用户要人天单价（或客户的报价单文件）和出处，**不自拟、不暂估、不套用示例**，停下等。用户给了数字再记录：
   ```powershell
   py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" quote --unit-price <数字> --provided-by "<提供报价的人>" --evidence "<提供数字的原话或来源>"
   py -X utf8 D:\Codes\Luz-Project\scripts\project.py client "<项目>" quote --from-file "<报价单.xlsx>" --provided-by "<提供报价的人>"
   ```
   `provided_by` 不能是你自己或任何工具，`evidence` 不能是“暂估”“默认值”；报价单文件里找不到单价、或有几个不同的单价时命令拒绝，去问提供报价的人。
4. **生成、检查、出示**。`client "<项目>" proposal`，`check` 会核对工时、金额只出现在开了开关的地方；按 02 → 03 → 04 一个一个出示，04 出示时 `next` 的汇报会写“工时是拟定值，估算依据在 features.json，报价的单价来自 …”，照读。
5. **开关或数字之后又变**（改成不写、加上报价、换了单价）：照样用 `estimate`、`quote` 命令。方案阶段已有批准文件时，它们自动登记变更台账并作废 02、03、04 的批准，重新生成、逐个重审；这是变更，不能直接改文件。

## 12 给其它技能的只读接口

三个只读接口，其它技能（Luz-Ops 的发布命令、各技能的 `crawl_gate.py`（Writing 是 `08-crawl_gate.py`））在项目模式下调用。项目参数是项目目录或状态根都行。**命令行最稳**（单独的进程，不会和调用方的模块重名）；要 import，就把 Luz-Project 的 scripts 目录用 `sys.path.append`（追加，不是插到最前，调用方自己的模块优先）加进去再 `import approval_docs`。

| 要问的 | 命令 | 可 import 的函数 | 结果 |
|---|---|---|---|
| 动作门（release 的 `production-release`、handover 的 `final-acceptance`）用户授权了没有、现在还有效吗 | `py -X utf8 D:\Codes\Luz-Project\scripts\project.py action-status "<项目>" <阶段> <动作> --json`（不带 `--json` 输出人读的几行） | `approval_docs.action_granted(状态根, 阶段, 动作)` 返回 `(是否已授权, 原因)`；要授权人、时间、绑定的文件：`approval_docs.action_status(...)` 返回字典 | 退出码 0=已授权（有效的用户授权记录，绑定的文件哈希与现在一致），1=未授权，原因写明：从未授权、被变更作废、哪个文件变了、没有这个动作门、旧模型 |
| 这个阶段的 Crawl 记录还受不受七天约束 | `py -X utf8 D:\Codes\Luz-Project\scripts\project.py crawl-expiry-waived "<项目>" <阶段> --json` | `approval_docs.crawl_expiry_waived(状态根, 阶段)` 返回 `bool`；要原因：`approval_docs.crawl_expiry_status(...)` 返回 `(bool, 原因)` | 退出码 0=阶段已完成（文件都由用户批准，客户输入和动作门都通过），豁免；1=不豁免（阶段在进行，或被变更重开） |
| 这个阶段该先读哪些文件（没有 context.py 规则卡的技能） | `py -X utf8 D:\Codes\Luz-Project\scripts\project.py context "<项目>" <阶段> --skill <技能>` 输出里的 `rule_files` | `project_core.rule_files(阶段)` | 每项有 `skill`、`file`、`path`（绝对路径）、`exists`、`for` |

各技能的 `crawl_gate.py` 在项目模式下这样用同一个判定（不要自己再造一套）：

```python
import sys
sys.path.append(r"D:\Codes\Luz-Project\scripts")
import approval_docs
errors = validate_preflight(session, caller, stage)              # 本技能原来的校验
if approval_docs.crawl_expiry_waived(state_root, stage):          # 阶段已完成：记录只核对存在、有效、已 conclude
    errors = [e for e in errors if "检索记录超过七天" not in e]
```

Luz-Ops 的发布命令要确认用户授权了生产发布时：`approval_docs.action_granted(state_root, "release", "production-release")`，或看 `action-status` 的退出码；未授权就停下，把原因告诉用户，不自己记授权。
