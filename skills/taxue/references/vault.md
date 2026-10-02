# 个人数据入口（vault 接入规范）

> taxue-* 子 skill 引用个人数据（素材库、工作站、记忆库、归档）时，一律走本规范。正文和参考件里不写死任何人的具体路径——写了，分享出去就失效。

---

## 发现链（运行时解析一个入口）

按顺序尝试，命中即停：

1. **本次对话指定**：用户说了在哪，就用哪。
2. **环境变量** `TAXUE_VAULT`（库根级，配合各 skill 的入口约定）。
3. **配置文件** `~/.taxue/config.json` 的 `entries.{入口名}`。
4. **常见位置探测**：`~/素材库`、`~/知识库`、当前项目的 `./素材库`。
5. **都没有** → 三态问询，用户选一：
   - **接入已有库**：用户提供位置，写入配置，以后不再问。
   - **从零新建**：按该 skill 的模板建一套空库，写入 entries。
   - **无库轻用**：跳过落盘功能，方法论输出照常，效果不受影响。

---

## 配置格式（`~/.taxue/config.json`）

```json
{
  "entries": {
    "learn_inbox": "~/我的素材库/00_收件箱",
    "learn_atoms": "~/我的素材库/02_原子库/atoms.jsonl",
    "content_workstation": "~/我的工作站"
  }
}
```

- 每条 entry 是**完整路径**（`~` 开头），直接可用。
- 这是用户本机的文件，**永不进公开仓**。

---

## 入口命名约定

`{skill短名}_{用途}`，短名与 skill_registry.json 的 key 一致：

| 例子 | 语义 |
|------|------|
| `learn_inbox` / `learn_quotes` / `learn_insights` / `learn_atoms` / `learn_topics` | 学习技能的五类落盘入口 |
| `content_workstation` / `content_atoms` | 内容技能的工作站与原子库 |
| `industry_memory` / `industry_research` | 行业研究的个人沉淀与历史报告 |
| `state_archive_visual` / `state_archive_misc` | 状态技能的笔记归档目标 |

各 skill 在正文或参考件里**声明自己需要哪些入口**（入口名 + 语义 + 缺失时的降级行为），声明里不出现具体路径。

---

## 分享态

- 公开发布：本规范随 skill 正文走；配置文件留在用户机器上。
- 首次使用触发三态问询；老库目录名不标准的，用 entries 直接指向实际位置适配，不改用户的库。

---

*vault 规范 v1.0 — 发现链五级 · entries 全路径 · 命名 `{skill}_{用途}` · 配置不进仓*
