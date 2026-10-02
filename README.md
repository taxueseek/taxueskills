# taxue skills — 踏雪决策系统

13 个互相路由的技能：**1 个总入口 + 12 个子技能**。一个入口接住模糊的问题，路由到对的方法论，收束成可执行的行动。

13 mutually-routed skills: **1 entry point + 12 sub-skills**. One entry catches the vague question, routes to the right method, and lands on an actionable next step.

## 技能清单 / Skills

| Skill | Version | 定位 | Trigger (EN) |
|---|---|---|---|
| [taxue](skills/taxue/) | 3.5.5 | 总入口：路由 + 收束 | "stuck", "help me decide" |
| [taxue-diagnosis](skills/taxue-diagnosis/) | 4.1.0 | 系统诊断 + 商业判断 + 多视角 | "life audit", "is this business viable" |
| [taxue-solve](skills/taxue-solve/) | 4.1.0 | 问题清洗 + 执行落地 | "what should I do", "how to execute" |
| [taxue-insight](skills/taxue-insight/) | 3.4.1 | 一句话看透本质 | "what's the essence", "root cause" |
| [taxue-career](skills/taxue-career/) | 3.7.0 | 职业全周期：方向到入职 | "career change", "interview prep" |
| [taxue-job-search](skills/taxue-job-search/) | 4.1.0 | 真实在招岗位搜索 | "who's hiring", "job listings" |
| [taxue-content](skills/taxue-content/) | 4.1.0 | 内容创作 + 流量 | "content creation", "headline" |
| [taxue-industry](skills/taxue-industry/) | 4.1.0 | 行业研究 + 用户研究 | "market analysis", "competitor analysis" |
| [taxue-learn](skills/taxue-learn/) | 4.5.0 | 学习方法 + 素材库 + 连续学习 | "how do I learn this", "keep learning" |
| [taxue-shopping](skills/taxue-shopping/) | 4.1.0 | 购物决策 + 家居避坑 | "worth it", "best price" |
| [taxue-calm](skills/taxue-calm/) | 3.4.1 | 情绪转化为可操作的问题 | "feeling anxious", "burned out" |
| [taxue-state](skills/taxue-state/) | 4.1.0 | 状态存档 + 笔记归档 | "resume last session", "log this decision" |
| [taxue-build](skills/taxue-build/) | 4.1.0 | 经验沉淀为工具 | "turn this into a tool" |

## 安装 / Install

- **单个技能**：把 `skills/<name>/` 复制进你的 skill 目录（如 `~/.claude/skills/`、`~/.agents/skills/`）。
- **整包**：从 [Releases](../../releases) 下载 zip。
- **推荐**：从 `taxue/` 总入口开始——它会路由到对的子技能，不用记 13 个名字。

Recommended: start from `taxue/` — it routes to the right sub-skill for you.

## 个人数据 / Personal data

技能**零硬编码路径**。涉及个人知识库（素材库、原子库、学习档案）时走运行时发现链：

对话指定 → 环境变量 `TAXUE_VAULT` → `~/.taxue/config.json` → 常见位置探测（`~/素材库`、`~/知识库`）→ 三态问询（**接入已有库 / 从零新建 / 无库轻用**）。

无库也可用：学习档案是纯文件机制，放当前工作区即可；素材检索为可选增强。详见 [skills/taxue/references/vault.md](skills/taxue/references/vault.md)。

No hardcoded paths. Personal data locations are resolved at runtime — connect your own knowledge base, build one from scratch, or use the methods without any vault. See [skills/taxue/references/vault.md](skills/taxue/references/vault.md).

## 设计约定 / Design notes

- **路由单点真源**：子技能信号与别名集中在 `skills/taxue/references/skill_registry.json`，主入口路由表由此派生。
- **连招收尾**：子技能输出收束后按 `combo_map` 推荐下一条路径，至多一个，不硬连。
- **声线分化**：12 个子技能各有说话人格（诊断像做过生意的人，solve 像带过项目的老手，learn 像苏格拉底式导师）。

## Changelog

见 [CHANGELOG.md](CHANGELOG.md)。历史版本（v3.4.2 及更早）中的 career 子技能已并入 `taxue-career` 单件，旧 Release 资产由本版取代。

Career sub-skills from older releases have been consolidated into `taxue-career` v3.7.0; earlier release assets are superseded.
