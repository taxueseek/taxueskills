## 4.1.0 — 2026-09-28

### 找回 2026-09-27 重构中丢失的能力

09-27 的「12 技能分层架构」重构把 9 个技能移进 `.trash`（146 KB / 30 文件），但幸存技能只吸收了骨架：标题写着合并后的覆盖面，正文与 `references/` 没搬。本轮把能力接回来。

- **taxue-industry ← taxue-research**：迁回 14 个 references（市场 TAM/SAM/SOM、竞品矩阵、定价策略、GTM、用户画像 7 步、面板 schema、社媒扫描等）+ `scripts/validate_panel.py`；SKILL.md 补「参考文件（按需读取）」双层导航表 + 「面板资产与校验」。
- **taxue-content ← taxue-traffic**：迁回 3 个 references（标题公式库 / 开头模式库 / 平台机制），并把 traffic 的 695 行正文按章节切成 3 个按需 reference（`traffic-diagnosis` / `traffic-writing` / `traffic-distribution`，覆盖度校验 682/682 行）。原来那份 29 KB 是每次触发都全量载入的，现在是按需。
- **taxue-diagnosis ← taxue-business + taxue-roundtable**：补回被丢的执行细节——快诊输出 / 深诊输出 / 成长层级 1-7 阶梯（原版 7 项定性检验的独立资产，旧 diagnosis 用的是另一套打分表）/ 前提挑战 / 内联案例库（3 例）/ Outcome Contract / DO NOT；多视角侧补回方式 C 辩论 / 方式 D 多轮深挖 / 说话方式 / 逼出真正的讨论（听弦外之音·立场追踪·轮空三问·钢人原则）/ 质量校准规则 / 输出格式 / 3 条反模式。
- **taxue-state ← taxue-note-archiver**：迁回 `archive_notes.py` + `categories.py`。state 的 SKILL.md 早就写好了「笔记归档」章节并指向这两个脚本，但脚本留在 `.trash` —— 引用一直是断的。
- 合并世代版本号统一为 **4.1.0**（build/content/diagnosis/industry/learn/shopping/solve/state/job-search）。

### 质量门从「不工作」到「可用」

- **扫描范围修正**：原来用 `taxue-*` 通配，把 19 个生图/视觉技能一起卷进来，再用决策系模板去卡它们 → 0 pass + 202 告警，信号被噪声淹没。改为从 `skill_registry.json` 派生扫描名单：31 → 13 个技能，错误 76 → 25。
- **修 `--verbose` 崩溃**：调用了不存在的 `load_yaml_frontmatter()`（实际函数名 `parse_frontmatter`）。
- **删除 `--repair`**：文档承诺「自动修复版本号不一致」，实现里 `run_quality_gate(verbose, repair)` 完全忽略该参数——空壳功能，删掉而不是留着骗人。
- **删除主版本线检查**：决策系自身就是多版本线（3.4.1 / 3.5.4 / 3.6.0 / 4.1.0），拿一条线去卡等于每次全量误报。
- **新增一致性检查（registry ↔ 文件系统 ↔ 主入口路由表）**：路由信息原来散在四处靠手工同步，现在其中两处变成机器可校验——路由表里出现但未登记的技能会直接报 error。
- **新增「自带资产可达性」检查**：`references/` `scripts/` 里的文件若未被自己的 SKILL.md 引用，就是「能力到位但运行时不可达」——正是 09-27 翻车的形态。这条检查让同类问题下次能被机器抓住。

### 子技能模板补齐（质量门首次清 0 错误）

- **8 个技能补「反模式声明」**：industry ← research 4 条、content ← traffic 6 条、solve ← speak 5 条 + 2 条（跳过问题清洗 / 给虚假希望）、build / career / learn / shopping / state 依据各自既有规则与承诺提炼（build ← 三条核心原则，career ← 四个硬规矩，learn ← 入库三问与使用前置门控，shopping ← 「绝不做的事」，state ← 三种模式的边界）。共 39 条，统一 `### 失败 N` 体例。
- **6 个技能补「DO NOT 边界声明」**：industry ← research、learn ← material，其余按自身 scope 与 registry 的 `combo_exits` 写。
- **质量门：14 错误 → 0 错误**（退出码 2 → 1，剩余 41 条均为 warning 级建议项）。

### 警告清零（质量门首次全绿）

- **12 个分支补「共享规则与纪律」**：一段指向 `../taxue/references/shared-rules.md` 的定式，显式点出 **结果优先** 与 **证据来源** 两个术语并声明冲突时以真源为准。这是指针不是复述——避免 v3.5.5 已经消除过的「双份漂移」重新长回来。一次覆盖 3 类告警（共享规则引用 / 结果优先 / 证据来源）。
- **7 个技能补「Outcome Contract」**：build / content / industry / learn / shopping / solve / state，产出、做完的标准、不做的事三项按各自 scope 写。
- **8 个技能补「版本脚注」**：build / content / industry / job-search / learn / shopping / solve / state。其中 job-search 的脚注缺 `taxue-` 前缀，正则认不出，一并补上。
- **job-search 两处特化修正**：`## 输出末尾` 补「导流交给主入口」（原本只有「不要在此定义导流规则」）；H1 从「求职岗位搜索引擎（双引擎）」对齐为 family 体例 `# taxue-job-search：真实在招岗位搜索（双引擎）`。
- **顺手修掉自己引入的排版隐患**：7 处 `--------` 分隔线紧贴正文行，Markdown 会把它误判成 setext H2 标题、吃掉上一行。已补空行。
- **质量门：41 告警 → 0，rc=0，「所有检查通过」**。系列首次全绿——此后任何一次改动，门禁只要响就一定是新问题，而不是陈年噪声。

### 死子系统退场

- `taxue-adapter-bridge.py` / `enhanced-mode-guide.md` / `setup-adapter.sh` / `interface.json` 移入 `.trash/2026-09-28_dead-enhanced-mode/`。适配器桥依赖 `skill-orchestrator/scripts/skill-adapter.py`，而该技能在 2026-08-24、2026-09-23 已被两次归档 → 增强模式从 8 月起就不可用（实跑 FileNotFoundError）。文档还教用户运行 `setup-adapter.sh`，属于误导。全部移入垃圾桶而非删除，可回滚。
- 同步清理 `skill_registry.json` 描述里的 adapter-bridge 引用。

### 子技能体积回归：career 常驻瘦身

- **问题**：13 个技能里 `taxue-career` 的 SKILL.md 高达 34 KB，比主入口 `taxue`（19.5 KB）还大——触发 career 就全量灌进上下文，是常驻离群点。质量门只查「资产可达性」，不管单体体积，所以没拦住。
- **做法**：沿用它自己的「主路由」分组轴（方向 / 简历 / 执行阶段 / 失败复盘 + 案例工厂），把 8 个子流程的方法细节下沉为 5 份按需 reference：`direction.md` / `resume-jd.md` / `execution.md` / `failure.md` / `case-factory.md`（含求职漏斗量化）。SKILL.md 保留身份管理、快速路由、职业诊断公理、Outcome Contract、质量门、反模式、DO NOT、共享规则指针、说话风格与参考文件导航表。
- **结果**：SKILL.md 34,261 B → 9,218 B（−73%，565 → 170 行），26 KB 转为按需读取；触发 career 时只再读命中的那一份，最坏路径（失败诊断）也只需 8 KB。版本 3.6.0 → 3.7.0。
- **待办（未做）**：质量门还没有「单体 SKILL.md 体积预算」检查，career 这类膨胀下次仍不会被机器抓住。

## 3.5.5 — 2026-08-05

- **实测驱动改进（embed_retrieval 主路由实测）**：
  - 设计 30 条真实口语 query 覆盖主路由表全部信号，实测 Top-1 命中率 **83% → 97%**（25/30 → 29/30）
  - 修复 5 个 description 触发词缺口：shopping-home（一行 description 补全为完整触发词版）、shopping（补 3C/笔记本/手机词）、roundtable（补「换个角度/换个视角」）、build（补「把重复的工作流程做成工具」）、career（补「该不该转行/转行做运营还是开发」口语句式）
  - 剩余 1 条（「不知道做什么方向好」→ career 而非 career-direction）属设计内：career 主技能内部会分流到 direction，符合「主入口 → 主技能 → 内部导航」架构
- **契约层改进（shared-rules v1.3 → v1.4）**：
  - **证据硬门下沉到 shared-rules**：主入口 SKILL.md 的「证据硬门」6 条纪律原只在主入口，子技能通过 shared-rules 继承却无法获得 → 现下沉为共享契约，主入口改为引用 + 精炼要点（消除双份漂移，单一真源）
  - 质量门控新增 **shared-rules 真源完整性检查**（error 级）：验证真源包含连招收尾/记忆后置/证据硬门/结果优先 4 项纪律——真源缺纪律 = 全部子技能继承失败，单点检查而非 31 次重复检查
  - 新增 **纪律遵循检查层**（DISCIPLINE_SECTIONS）：度量子技能执行层纪律（证据来源/结果优先）。调度层纪律（连招收尾/记忆后置）由主入口 + combo_map 负责，不在子技能层重复检查（修正检查层级，去噪 62 项）
  - 清理质量门控 4 行「计划未实现」的死注释（证据硬门/描述完整性的占位注释）
- **子技能纪律补强**：taxue-insight / taxue-job-search 补「结果优先」显式声明（内容已隐含，补术语使其可度量），结果优先缺口 2 → 0
- **删除方法论技能**：归档 taxue-peizhe-allocator-method + taxue-jimin-citrus-method（纯方法论文档，风格复刻能力已被 taxue-style-replicator 完整覆盖「配置说 × 基民柠檬」两种风格）。同步清理主路由表 / 注册表 / routes.json / combo_map / skill_index.json / 软链。系列 34 → 32
- **求职技能整合评估**：9 个系列外求职技能中，归档 6 个零引用残留（full-career / job-hunter-pro / job-navigator / job-search-skill / interview-coach-noamseg / interview-coach-openclaw）——清理记录声称已并入 taxue-career 但磁盘残留；保留 3 个有活跃引用的（interview-coach / resume-auditor / resume-builder），enhanced-mode-guide 的 interview-coach 引用更新为 taxue-career-interview
- **主路由扩展（18 → 30 条信号）**：career 系列 7 子技能 + 独立技能（shopping / shopping-home / weread / skill / style-replicator）纳入主路由；组合信号表新增 5 条；router 不入主路由（内部引擎）
- **五层路由一致性（sync_routes.py 全绿）**：registry=31 / routes=31 / combo=30 / router=38 / disk=31，无硬性问题
- **技能精简**：归档 taxue-save（94 行简化版，功能被 taxue-state 221 行完整版覆盖）与 taxue-upgrade（45 行幽灵技能）。系列 36 → 34
- **质量门控修复**：硬编码扫描日期 → 动态日期；新增 TOOL_SKILLS 工具类豁免；删除重复章节、归档 compare_systems.py

## 3.5.4 — 2026-07-15

- **记忆后置按需**：禁止无条件前置读 whisper/patterns/decisions/平台记忆；记忆只服务收束、连招、避坑、显式续聊
- whisper：取消「有且 <24h 必问接着上次」硬门；仅用户显式续聊才读，读后删；话题无关则忽略
- patterns：从「执行前」改为「已选定子 skill 后」grep 1-2 条
- 默会边界：有路由信号不得因旧记忆跳过读 skill；禁止复读历史答案
- 技能透明：有路由信号必须开口声明当前 skill
- state 别名：去掉裸「继续/上次/之前」，改为「继续上次/接着上次/恢复存档」等整词
- shared-rules v1.3；回滚备份：`SKILL.md.bak-pre-memory-post-20260715`
- 清理正文/变更说明中的外部系列名引用（不在 taxue 文档中点名其他 skill 产品）

## 3.5.3 — 2026-07-15

- 技能透明重写：当前唯一声明 + 结论驱动下一技能（单步可见时间轴）
- 禁止片头「先 A 再 B」管线预告；禁止对用户黑话（拆结构/定生死/三问快诊等）
- 组合信号「原因」列标为内部；并行用户可见只报主交付 skill
- 收束话术：`可以接着用 /taxue-xxx 分析`；shared-rules 连招收尾 v1.2
- style-reference 增加本轮真实坏/好对照

## 3.5.2 — 2026-07-15

- 结果优先元原则：先结果后过程、边界大于步骤剧本
- taxue-solve v3.5.0：六步顺序流 → 交付物+硬边界+内部检查表
- shared-rules：全系列结果优先继承
- business 深诊：去掉「等回应再下一项」剧本
- 度量脚本 measure-outcome-first.py；回滚 tag: taxue-pre-outcome-first-20260715

# taxue 成长日志

> 由 taxue-save 在每次存档时自动追加。本文件不参与运行时路由。

## 成长日志

本文件的更新记录，由 taxue-save 在每次存档时自动追加。

### v2.14 — 2026-07-06
**恢复**：description 加回「帮我」触发词和「/t」快捷触发
**恢复**：路由后加手递手信号「明白了，这个交给 {skill} 来处理」
**优化**：路由行为不暴露内部词（路由到、优先级匹配等）

### v2.12 — 2026-06-08
**新增**：参考文件索引节（渐进式信息披露，来自 Anthropic Agent Skills 设计原则）
**新增**：agent 按需导航机制——不预加载参考文件，仅在需要时读取

### v2.11 — 2026-06-08
**重构**：输出风格从 7 条刚性规则改为三层结构（底线 + 真人特征 + 声线分化）
**新增**：子 skill 声线分化表（9 个独立人格）
**新增**：真人特征正面引导（犹豫/过渡/节奏/口语/温度）
**新增**：消解话术人话化，去掉占位符格式
**新增**：style-reference.md 渐进式参考文件

### v2.10 — 2026-06-05
**优化**：路由改为优先级表，消解情绪/求解/洞察/圆桌冲突
**优化**：description 移除泛触发「帮我」，增加搜岗直达 `taxue-job-search`
**优化**：P013 仅用于同级双匹配，单一匹配仍立即执行

### v2.9 — 2026-06-05
**新增**：`taxue-industry` — 行业认知引擎（概览/深度/商业判断三层）
**更新**：路由表增加行业相关触发词

### v2.8.1 — 2026-06-04
**新增**：默会知识注入（执行前读取 patterns.md）
**新增**：taxue-save v3.0 默会知识外化层
**优化**：路由表补充口语化触发词，提升路由匹配精度
**优化**：patterns.md 增加置信度维度（一级/二级/三级）
**优化**：关键子技能补反模式声明
**版本**：全部子技能统一升级到 v2.8