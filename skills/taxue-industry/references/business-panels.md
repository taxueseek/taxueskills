# 商业面板 Schema — 市场/竞品/GTM 的数据契约

> 与用户面板（panel-schema.md）同体系，覆盖商业研究资产。
> 校验：`scripts/validate_panel.py`（v2.0 起支持 panel_type 分支）。

## 面板类型

| panel_type | 文件名前缀 | 内容 |
|-----------|-----------|------|
| `user` | 任意 slug | 用户画像（7 维，见 panel-schema.md） |
| `market` | `market-*` | 市场分析（TAM/SAM/SOM + 趋势 + verdict） |
| `competitor` | `competitors-*` | 竞品拆解 + 机会矩阵 + verdict |
| `gtm` | `gtm-*` | 上市计划（北极星 + VP + 渠道 + 指标） |

## 通用顶层结构（所有类型）

```json
{
  "schema_version": "1.0",
  "panel_type": "market | competitor | gtm | user",
  "slug": "…",
  "name": "…",
  "created": "…",
  "updated": "…",
  "confidence": "L1|L2|L3",
  "evidence": ["来源链接"],
  "payload": { "类型相关字段" }
}
```

## 各类型 payload

### market
```json
"payload": {
  "tam": {"value": "…", "source": "…", "year": 2025},
  "sam": {"value": "…", "source": "…", "note": "…"},
  "som": {"value": "…", "source": "…", "note": "…"},
  "trend": "增长中|平稳|萎缩",
  "drivers": ["…"],
  "risks": ["…"],
  "verdict": "值得进|谨慎|不进 + 理由"
}
```

### competitor
```json
"payload": {
  "competitors": [
    {"name": "…", "positioning": "…", "pricing": "…", "strengths": [], "weaknesses": [], "evidence": []}
  ],
  "opportunity_matrix": {"痛点": {"竞品A": true, "竞品B": false, "us": "机会"}},
  "verdict": "差异化方向 + 理由"
}
```

### gtm
```json
"payload": {
  "north_star_market": "…",
  "north_star_persona": "引用用户面板 slug",
  "value_proposition": {"for": "…", "who": "…", "that": "…", "unlike": "…"},
  "channels": [{"platform": "…", "content": "…", "evidence": "…"}],
  "launch_metrics": ["…"],
  "timeline": "30-60-90"
}
```

## 校验规则

1. `panel_type` ∈ {user, market, competitor, gtm}
2. user 类型走 7 维校验（panel-schema.md）
3. market 必须有 `tam` 且有 `verdict`
4. competitor 必须有 ≥1 个 `competitors` 且有 `verdict`
5. gtm 必须有 `north_star_market` 和 `value_proposition`
6. 所有类型必须有 `confidence` 和 `evidence`

## 复用逻辑

- 竞品面板引用用户面板（对照需求矩阵）
- GTM 面板引用用户面板（language 维度写文案）
- 市场面板独立，但趋势判断可回写用户面板的动机维度
