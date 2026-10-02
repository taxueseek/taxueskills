# 面板 Schema — 可复用 AI 用户画像的数据契约

> 所有面板 JSON 必须符合本 schema。校验脚本：`scripts/validate_panel.py`。

## 文件位置与命名

- 落盘：`~/.agents/skills/persona-studio/panels/<audience-slug>.json`
- slug 规则：小写字母 + 连字符（如 `gen-z-gamers`、`saas-procurement`）

## 顶层结构

```json
{
  "schema_version": "1.0",
  "slug": "gen-z-gamers",
  "name": "Z世代手游玩家",
  "created": "2026-08-04",
  "updated": "2026-08-04",
  "confidence": "L2",
  "reuse_scenarios": ["验证游戏概念", "设计付费系统"],
  "dimensions": {
    "identity": {...},
    "pain_points": {...},
    "motivations": {...},
    "behaviors": {...},
    "decision_path": {...},
    "language": {...},
    "anti_persona": {...}
  },
  "sources": ["社媒语料 ×23", "访谈 ×3"],
  "evidence_log": []
}
```

## 7 维结构（每维相同模式）

```json
"dimensions": {
  "identity": {
    "summary": "一句话描述",
    "attributes": [
      {
        "name": "年龄",
        "value": "18-24",
        "evidence": "社媒语料 C-07",
        "confidence": "high"
      }
    ]
  }
}
```

### 每维的 attributes 示例

| 维度 | 典型 attribute | 证据来源 |
|------|---------------|---------|
| identity | 年龄/职业/场景/设备 | 语料/访谈 |
| pain_points | 抱怨/放弃原因/踩坑 | 负面语料 |
| motivations | 目标/渴望/恐惧 | 求助帖/访谈 |
| behaviors | 工具/习惯/频率 | 使用分享 |
| decision_path | 触发→搜索→比较→行动 | 购买分享 |
| language | 原话/用词/比喻 | 评论原文 |
| anti_persona | 排除人群/特征 | 边界证据 |

## 置信度等级

| 等级 | 含义 | evidence_log 要求 |
|------|------|------------------|
| L1 | 探索性（仅桌面） | 全部来自二手证据 |
| L2 | 已验证（访谈/小组） | 含一手访谈记录 ID |
| L3 | 高置信（多源交叉） | 含量化佐证（如问卷 N=50） |

## evidence_log（证据链）

```json
"evidence_log": [
  {
    "id": "C-07",
    "type": "social_corpus",
    "source_url": "https://...",
    "quote": "原文摘录",
    "captured": "2026-08-03"
  }
]
```

## 校验规则（validate_panel.py 执行）

1. `schema_version` 存在且为 "1.0"
2. `slug` 匹配 `^[a-z0-9-]+$`
3. 7 个维度全部存在
4. 每维 `attributes` 非空且每条有 `evidence` 字段
5. `confidence` ∈ {L1, L2, L3}
6. `evidence_log` 引用的 id 都能在 dimensions 中找到

## 版本兼容

- 本 schema 变更需升级 `schema_version` 并同步更新 `validate_panel.py`
- 旧面板不强制迁移，但新面板必须符合当前版本
