# 技术底座取材时发现的源规范矛盾与空白

底座（stack.json、frontend.json、functions.json）是从 Luz-System、Luz-Design、Luz-Dev、Luz-Ops 的规则页、规范文本、模块说明和一个已交付项目归纳出来的。归纳时发现这些来源之间有互相矛盾和没写清的地方。底座每处都取了一个值，括号里写明取舍；**来源自己还没有改**，所以改来源时应以这份清单逐项对齐，对齐后从这里删掉那一项。

读法：每条写“哪两处说法不同 → 底座取了哪一边”。没有被取用的一边不是错，只是与底座不一致。

## 一、前端与视觉（frontend.json 的来源）

| 编号 | 矛盾或空白 | 底座取舍 |
|---|---|---|
| F-01 | 断点两套并存：通用五档（小于 600、600–839、840–1199、1200–1599、1600 以上，列数 4/8/12）写在 ui-standards.html 四 › 响应与适配和 visual-design.html 二 › 各端排布参数；后台表（1440、1280–1439、761–1279、760 以下）、智能体表（1200、840）、平台矩阵（后台 1280、1366、1440、1920 加 760 抽屉，网站 600、840、1200、1600）用另一套 | 各端分档并列写出（FE-LY-03），不硬配五档与 4/8/12 列 |
| F-02 | 间距刻度：visual-design.html 写 4 的倍数（4、8、12、16、20、24、32、48、64、96），ui-standards.html 写 4、8、12、16、24、32、48、64 和 8 像素网格，少了 20 和 96 | 取前者刻度，同时保留 8 像素网格 |
| F-03 | 骨架屏出现时机：ui-standards.html 状态体系写超过 300 毫秒，同页列表变更与动画写超过 1 秒 | 取 1 秒 |
| F-04 | 面积图填充：visual-design.html 写不超过主色 12% 透明度，ui-standards.html 写不填充、必须填充时 6% 以内 | 取更严的 6% |
| F-05 | 对话框面板宽度：visual-design.html 写桌面 480–640，admin-design.html 写 560–640 | 两个数都保留，后台 560–640 |
| F-06 | 导出异步阈值：admin-design.html 写“超过一页的数据异步生成”（每页 20 条时几乎所有导出都异步），Luz-Dev admin.md 写超过 5000 行 | 两个值都写出，由项目选 |
| F-07 | 轻提示时长：miniprogram-design.html 约 1.5 秒（仅图标型、仅成功），ui-standards.html 2–3 秒，admin-design.html 约 3 秒 | 按端分别写 |
| F-08 | 小程序分类左栏：visual-design.html 和 miniprogram-design.html 写宽 88、选中条 2 像素，commerce-design.html 写宽 80–96、选中条 4×16 | 取 2 像素 |
| F-09 | 圆角：visual-design.html 写卡片、图片 12，commerce-design.html 双列商品卡图片 8；commerce-design.html “果色活力”写 20–28，违反 visual-design.html 的“档位之外的圆角数值不出现” | 取 12 |
| F-10 | 金刚区文案字数：miniprogram-design.html 最长 5 个汉字，visual-design.html 公式与示例允许 6 字（按每字 14 像素，5 字时最大列数降为 4，6 字降为 3；见 F-21） | FE-LY-08 不固定字数，按公式推导：每格最小宽取 56 与（文案字数 × 14 + 8）的较大值 |
| F-11 | 瀑布流：ui-standards.html 成熟组件表把瀑布流给环境照片，同页“同类元素一致”写环境图同比例、功能区不用错落的瀑布流 | FE-AS-01、FE-PR-03：同组图片统一宽高比，功能区不用瀑布流，营销区可以不规则 |
| F-12 | 面包屑出现条件三处口径不同：多级目录（三级、深链、详情页）、admin-design.html 多级菜单（二级及更深和全部详情页）、常用控件做法（深于一级） | 取 admin-design.html |
| F-13 | 图标尺寸：visual-design.html 图标设计方案写只取 16、20、24（入口块里 22），同书图标块写 18–24、底部标签写 22–24 | 取 16、20、24，入口块 22 |
| F-14 | 金额小数位：commerce-design.html 列表与卡片去末尾的零，ui-standards.html 和 admin-design.html 写两位小数 | 按端拆开 |
| F-15 | 背景亮度下限：visual-design.html 配色写浅色表面不低于 0.80，极浅主色底写 0.85，同页并存且没说为什么不同 | 两个数并列写出 |
| F-16 | 动效令牌：导出脚本 slow 为 250（visual-design.html 写范围 250–300），原型 kit.css 的 --dur-slow 是 300 | FE-MO-01 取五档 100、150、200、250–300、280–320 毫秒；FE-SK-04 的令牌表写中 250、页面 300 |
| F-17 | 空白：套餐图没有像素规格（只有宽高比 4:3 或 1:1、2 倍显示尺寸、菜单商品图 72–88）；图片缺失时的显示样式没有定义 | 底座只写宽高比，缺图样式留给项目 |
| F-18 | 重叠：stack.json 的 STK-MP、STK-AD 层与 frontend.json 的 FE-SK-01/02/03、FE-LG-02/05 说的是同一批规定（框架、目录、请求层、路由权限、列表分页），项目要在两处各表态 | 暂不去重；去重时让 FE-SK 只留令牌、设计接入、适配器、测试、样式兼容 |
| F-19 | 阅读型网页字号：旧写法桌面与手机都是正文 16、字阶 14/16/20/24/32、窄屏不缩小字号（FE-FT-02、FE-FT-06、FE-LG-08、FE-LY-07 同写）；用户 2026-11-04 要求桌面端字不能太小、手机端可以小一点、层级按 Markdown 渲染 | 底座取桌面（768 及以上）正文 18、手机 16 两套，层级与数值见 Luz-Design 的 file-design.html 网页文件 › 排版参数（FE-FT-02、FE-FT-06 已改）；产品界面（后台、小程序、智能体）仍窄屏不缩小字号（FE-LG-08、FE-LY-07 注明“产品界面”）。Luz-Project 自己写的 HTML 页（开发文档、项目索引）按这一条，样式取 scripts/reading_style.py |
| F-20 | 小程序字阶：旧写法是 2026-10-29 按商用小程序录屏确认的紧凑字阶（正文 14、商品名 14、描述与标签 12），微信官方设计指南的常用字号是 22、17、15、14、12，标准字号 iOS 17、Android 16；用户 2026-11-04 要求小程序的字按官方推荐或主流设计适配、不能太小 | 底座取官方向字阶靠拢：正文、按钮、商品名 16，描述与图标下的说明 14，区块标题 18，页面主标题与详情页价格 22，标签、角标、划线价 12（FE-FT-04）；字号随微信字体大小七档与关怀模式 1.4 倍等比放大，间距不变 |
| F-21 | 金刚区文案字号：旧写法取 12 像素每字（每格最小宽 56 与 文案字数 × 12 + 8 的较大值），与新的小程序字阶里“图标下的说明 14”相冲突 | 取 14 像素每字（文案字数 × 14 + 8）；4 字文案仍可 5 列，5 字文案最多 4 列，6 字文案最多 3 列（FE-LY-08；Luz-Design style_match.py 与 visual-design.html 的推导示例同步改）|
| F-22 | 焦点样式：旧写法是输入框“聚焦变主色”、键盘聚焦 3 像素主色 24% 的实色环（visual-design.html 边缘线条、图标状态，themes.json 的 focusRing，本底座 FE-AX-02），石墨主题还写“彩色只给链接与焦点”；用户 2026-11-04 说点文本框出现蓝色选中框太丑，严格禁止 | 取新写法（FE-AX-02）：文本框聚焦只把 1 像素边框加深到次要文字色，禁止蓝色或主色选中框、外发光、粗描边、浏览器默认轮廓；按钮、链接、标签页等用 :focus-visible，键盘到达才显示 2 像素深色轮廓、外移 2 像素，不用主色；手机端关掉点按高亮；focusRing 令牌改为 0 0 0 2px。次要文字色 ink2 在主题库里对白底只有约 6:1，不到 7:1 的取它与正文深色之间的一阶 |
| F-23 | 深色与浅色：旧写法是“默认只做浅色，深色只在用户明确要求时做、且只对该次产出生效”（visual-design.html 旧小节“用户明确要求深色时”、配色“禁止”里的深色主题、组件库的“浅色底”行写“不开深色”，themes.json 只有 3 个主题有 dark 映射，本底座 FE-CL-07 旧名“深色模式何时才做”且非强制，FE-CL-02、FE-CL-05 的“后台不用深色…”“禁止深色主题”）；用户 2026-11-04 说“所有前端需要有深色浅色的主题色” | 取新写法（FE-CL-07 深色与浅色两套主题，强制）：产品前端（后台、小程序、手机网页、网站、智能体界面及其可交互原型）同时有浅色与深色两套主题，默认跟随系统外观，并有“跟随系统 / 浅色 / 深色”三选一的手动切换；浅色是第一套与验收基准，深色是第二套，取主题库 25 个主题全部带有的 dark 映射与 shared.dark，不是取反；阅读页、海报、幻灯片与文件仍只做浅色；FE-CL-02、FE-CL-05 里“不用深色大块”只约束浅色主题，每套主题内霓虹与发光仍不用；组件库的暗色走各库自己的机制并与页面主题同步 |

## 二、技术栈与运维（stack.json 的来源）

| 编号 | 矛盾或空白 | 底座取舍 |
|---|---|---|
| S-01 | HSTS 有效期：Luz-Dev operations.md §2 写 2 年，backend/SECURITY.md §5 写 max-age=31536000（1 年） | STK-DP-03 不写数字，STK-SE-04 写应用层 1 年 |
| S-02 | 网关限流与应用限流两套：operations.md §2 的 nginx 表通用 10 r/s（burst 20）、登录 10 r/m、短信 1 r/m；SECURITY.md §6 和 base.toml 每 IP 20 次/秒（突发 40）、登录 5 次/分钟、短信 5 次/分钟；SECURITY.md 却声称“限流阈值只在本文” | STK-SE-06：两层不同时以更严者为准 |
| S-03 | Redis 用途：SPEC.md §1、operations.md §2 默认一个 redis 放限流、缓存、锁、库存预扣；standards.json CACHE-002 要求缓存与持久状态分实例并把会话、幂等记录列为 Redis 持久数据，而 SPEC.md §6.5、§11 写幂等在数据库同事务、会话每请求查库 | STK-CQ-01 按 SPEC 写单实例，拆分作为“用量上来后”的做法 |
| S-04 | “MySQL 8 可选”无法落地：SPEC.md §6.6 用 SKIP LOCKED，§3.5 用部分唯一索引，base.toml 语句超时“仅 PostgreSQL”，operations.md §5 备份与时间点恢复只有 PostgreSQL，upload.json 用 JSONB；没有任何文件给出 MySQL 的备份、迁移或并发做法 | STK-DB-01 的 replace_when 把这些列为换 MySQL 时必须补写的内容 |
| S-05 | 导出规则三处不一致：SPEC.md §3.4 和 admin.md 写同步 ≤ 5000 行、更多转异步（24-report 规划中）；admin-design.html 写超过一页就异步；格式上 SPEC 是 CSV（UTF-8 BOM），admin-design 是 make_xlsx.py 的 xlsx | 基础功能里同步上限写 5000 行、超出提示异步导出（后台审计导出默认上限 50000，超出返回 4225），格式沿用 admin-design 的 xlsx；项目可调 |
| S-06 | 顾客端列表每批条数：SPEC §3.4、API.md §1.4 游标默认 limit=10（上限 20），miniprogram-design.html 每批 20 条 | STK-MP-03 写端上显式传 limit=20 |
| S-07 | 文档上传上限三个值：base.toml doc_max_mb = 5，upload.json 写 PDF ≤ 20 MB，config-design.html 案例 10 MB | STK-ST-03 写“由 doc_max_mb 配置，项目定值”，不写死 |
| S-08 | 熔断参数配置承载不全：SPEC §9 说写在 [http]、[breaker] 并给地图、短信、第三方配送“打开 60s”，base.toml 的 [http] 只有 max_body_kb，[breaker] 只有全局 open_s = 30 | 底座写原则，数值留给项目 |
| S-09 | 内部服务 mTLS：SECURITY.md §4 要求，SPEC §1、SECURITY §2、MICROSERVICES §3 只写 HMAC 签名，默认 compose 没有 mTLS | STK-SE-04 两者都写 |
| S-10 | 幂等作用域：SPEC §6.5 是（操作者、用例名、键），implementation-architecture.md 写成含租户 | 按 SPEC |
| S-11 | RPO：operations.md §5 写“RPO ≈ 1 分钟”，同节 WAL 每 5 分钟才外传、15 分钟无外传才告警；基础备份保留份数没写，只写逻辑备份 30 天 | STK-DB-06 如实写：本地 WAL 归档 RPO 约 1 分钟，WAL 每 5 分钟加密外传，RPO 与 RTO 目标由商户确认后实测 |
| S-12 | 零碎：会员新鲜认证失败用 4010 fresh_required，后台用 4011 reauth_required，SPEC §4 把 4011 定义为“需要 MFA 或重新认证”；SECURITY §5 说 Cache-Control: no-store 统一添加，API.md §1.3 说配置和文案接口是 no-cache 加 ETag | 底座按 4010 刷新、4011 重新认证写，安全头统一 no-store |
| S-13 | 空白：前端没有任何版本号；后台 HTTP 客户端、lint、格式化、前端单测工具都没指定；TDesign 与 Vant Weapp 只写“二选一”；uni-app 等跨端框架没提；小程序客户端超时与重试没有数字；没有行覆盖率要求；xlsx 导入导出没有技术规定 | AD-01、AD-07 的“取当前稳定主版本、锁文件锁定、Node 取活跃 LTS”是按 SECURITY §10 推出的策略；xlsx 归 functions.json 的“导入导出” |

## 三、基础功能（functions.json 的来源）

取材优先级：已实现的代码和 `backend/NN-*/MODULE.md` > `module-specs/*.json` > 其他文字。下面各条“按”的一边就是底座采用的一边。

| 编号 | 模块 | 矛盾或空白 | 底座取舍 |
|---|---|---|---|
| B-01 | login | 路径、表名、错误码风格对不上（login.json 写 /app/auth/wechat 与 members 表和字符串错误码；MODULE.md 写 /app/auth/login 与 users 表和数字码）；刷新令牌被重放时 login.json 整链吊销、MODULE.md 有 10 秒宽限；会话状态 login.json 读缓存、SPEC 与 MODULE.md 每请求查库；code2Session 重试 SPEC 写 2 次、28-wechat-mp 写不重试、login.json 写 1 次；session_key login.json 缓存 1 天、MODULE.md 加密入列；刷新令牌有效期 login.json 30 天、MODULE.md 空闲 14 天加绝对 30 天；协议提交字段不同 | 按 MODULE.md |
| B-02 | admin | 表名、权限码格式（order.refund.approve 对 `<module>:<action>`）、权限缓存、越界返回 NOT_FOUND 对 4031、验证码是否必填、锁定字段位置、手机号是否用于二次验证；导出上限 SPEC 5000 行对 MODULE.md 的 export_max_rows 50000（之间没说清）；standard-modules.json 仍用已退役的环境变量名 | 按 MODULE.md |
| B-03 | tenant | 02-store 只有 models.py（规划），没有 MODULE.md；状态值 store.json（preparing、open、paused、closed、resting）对 models.py（open、closed、paused）；报错码 STORE_NOT_OPEN 对 4221；字段健身向对餐饮向；履约参数“只存在门店表”对“登记为经营设置 store.*”；联系电话公开对加密 | 公开客服电话明文、个人手机号加密；其余取 models.py 与 SPEC |
| B-04 | catalog | 03-catalog 没有 MODULE.md 和代码（规划）；catalog.json 写“商品与库存”，混了库存与购物车，没有分类表、套餐、图片列表、批量导入；“商品导入”没有权限码 | 取 MODULES.md、patterns/catalog-cart.md、purchase-rules.md、SPEC §11 与真实项目；导入沿用 write 权限 |
| B-05 | config | 热加载防抖 1 秒、1–2 秒（默认 1.5）、1.5 秒三个值；MODULE.md §1 把经营设置列为本模块职责，§13 又写“不包含门店经营设置”；§1 有一处乱码；“隐藏”含义混用（公开接口“不含隐藏的技术配置”对 texts 含 admin_visible=false 的键） | 防抖 1.5 秒；隐藏键只是不在后台展示，照常下发 |
| B-06 | legal | “同意记录只追加”与撤回方式冲突（新增 withdrawn 行对原行写 withdrawn_at）；唯一约束 UNIQUE(kind) WHERE published 对唯一（类型、版本）；need_reconsent 开关只在 legal.json；版本不一致的错误码三种；27-legal 只有函数没有路由 | 按 MODULE.md 与代码；唯一约束两条都写 |
| B-07 | file | 21-media 没有 MODULE.md 和代码；文档上限 PDF 20 MB 对 doc_max_mb 默认 5；真实项目服务端同步上传本地磁盘、图片限 2 MB，与 FILE-001“拍照图片不因大小拒收”相反；缩略图档位原文没有 | 按 Luz-Dev 规则和配置键；缩略图只写“原档加副本（长边 2048）”，档位留给项目 |
| B-08 | notify | 重试次数 3 次（1/5/30 分钟）对最多 5 次（60/300/1800/7200 秒）；站内信是否所有通知都写；一次授权的模板数 3 个对 5 个；表结构完全不同 | 按 MODULE.md |
| B-09 | order | 表字段（biz_type、goods_cents 对 kind、items_cents 并拆分摊字段）；状态（只有 closed 对 cancelled 与 closed 并多 fulfilling、completed）；价格确认（expected_payable_cents 对 quote_token 与 4223）；已支付订单取消的错误码 | 按 08-order/MODULE.md |
| B-10 | order、wallet、card | order.json、wallet.json、membership.json 写充值和会员卡走统一订单，08-order §13 写“不包含充值类行种类”，15-recharge 与 29-member-card 各有购买单 | 各走自己的购买单 |
| B-11 | coupon | 0 元订单与券：coupon.json “优惠最多减到 1 分”对 08-order §4.9“0 元订单提交即成交”；券类型、状态枚举、退券规则、过期券处理、到期提醒（3 天对 48 小时）；折扣取整方向（16-coupon §4.10 对 pricing.md §5 与代码）；折扣率范围 100–9900 对代码 100–9999 | 按代码；BF-COUPON-03 提示项目可调整封顶 |
| B-12 | payment | 表和状态名；回调路径；prepay_id 复用窗口 6900 秒；支付结果轮询节奏三种（1 秒×10、1/2/3 秒×10、1/2/4/6/8 秒）；金额不符应答成功对 400 加人工；任务频率（1 分钟/5 分钟对 30 秒/60 秒） | 轮询按 result-patterns.md；其余按 09-wechat-pay/MODULE.md |
| B-13 | refund | 状态集合差很多；进行中的申请按订单唯一对按订单行；赠送金“不退”对 15-recharge §4.7 按比例冲回；会员卡有两条退款路径，refund.json 只写一条 | 按 10-after-sales 与 15-recharge |
| B-14 | card | 表与状态命名；预约冻结 membership.json 登记计划对 29 §13 不包含；名字撞车：module-specs 的 membership 是会员卡，backend/14-membership 是积分，function-catalog.json 的 membership 又是“等级与积分” | 按 29-member-card；模块 id 用 card |
| B-15 | wallet | 表字段；扣减取整给谁（本金向下取整对赠送金向下取整余数归本金）；充值上限 100–500000 元、赠送不超过 50% 对预付规则单笔不超过 5000 元；钱包状态 active、frozen 对 active、closed 加冻结金额 | 按 15-recharge |
| B-16 | report | backend/24-report 目录是空的，SPEC §3.4 却写异步导出由它提供；范围上限三个值（366 天、31 天、92 天）；report.daily 每日 02:00 对 25-jobs 只支持固定间隔；指标全是门禁场景的，没有通用指标目录 | 各功能按自己的出处写（通知统计范围最长 92 天，导出最长 31 天、最多 5000 行），通用指标目录由项目补 |
| B-17 | exchange | Luz-Dev 没有任何 Excel 导入规格，BF-EXCHANGE-01、02 依据真实项目和 result-patterns.md §6，失败行下载文件是补的；export.py 只出 CSV 且时间带秒，admin-design 要求 xlsx 与 yyyy-mm-dd HH:mm | 依据真实项目与规范页 |
| B-18 | job | 发件箱失败（foundation.json 10 次进死信对 SPEC 与 25-jobs 的 1m/5m/30m/2h/12h 退避、5 次后 failed）；多实例防重（数据库咨询锁对 Redis 锁，scheduler.md §4.2 说锁只作优化）；25-jobs/MODULE.md 章节号不连续，缺数据模型、接口、事件、配置、错误码 | 按 SPEC 与 25-jobs |
| B-19 | audit | 字段名（object_type、before_data 对 resource、before_json、reason、user_agent）；保留期 3 年对建议 1 年、个人信息批量导出与越权操作 3 年；安全事件写审计表对单独成日志流；真实项目 operation_log 缺前后对比、原因、链路编号，不记读取，保留 180 天 | 按 audit.py 与 config-logging.md；BF-AUDIT-01 写“最小形态”并要求项目标“调整” |
| B-20 | 预约、营销 | 13-reservation 是“设计加待接入”，接口没有实现，与订单的预约履约钩子没有对上；营销只是半成品 | 底座不收预约，营销只收券与抽奖 |

## 四、本轮检索与已交付项目对照又发现的两处

| 编号 | 矛盾或空白 | 处理 |
|---|---|---|
| R-01 | 十二要素第 11 条要求日志写标准输出由运行环境收集，STK-OB-01 也这么写；已交付项目把日志写在容器里的文件，没有集中采集 | 项目在 STK-OB-01 写“调整”并给理由 |
| R-02 | OWASP 口令存储把 Argon2id 列为首选，bcrypt 只列为沿用系统的选项（工作因子至少 10、口令限 72 字节）；STK-SE-02 写 Argon2id，Java 项目常见 BCrypt | 项目用 BCrypt 时在 STK-SE-02 写“调整”，写明工作因子与 72 字节限制 |
