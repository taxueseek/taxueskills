# Changelog

## 2026-10-02

- **13-skill taxue decision system replaces the previous 3 standalone skills**（13 件互相路由的决策系统取代原 3 件独立技能）
- Entry point `taxue` v3.5.5 + 12 sub-skills（见 README 技能清单；versions: diagnosis/solve/job-search/content/industry/shopping/state/build 4.1.0, learn 4.5.0, career 3.7.0, insight/calm 3.4.1）
- All 13 skills carry English trigger words（13 件全部具备英文触发词）
- Zero hardcoded personal paths — personal data locations resolve at runtime via `skills/taxue/references/vault.md`（指定 → `TAXUE_VAULT` → `~/.taxue/config.json` → 探测 → 三态：接入已有库 / 从零新建 / 无库轻用）
- `taxue-learn` v4.5.0 highlights: 课题档案（连续学习 + 复盘驱动）、知识原子/素材双轨、学习成果升级进素材库
- Career sub-skills from older releases（v3.4.2 的 career-direction/resume/channel/interview/offer/onboard/fail）have been consolidated into `taxue-career` v3.7.0; earlier release assets are superseded
- Removed: `ultimate-problem-solver` v5.2.0、`哲思伙伴` v1.1.0、`skill设计师` v1.1.0（开发版已另行归档）

## 2026-03-11

- `ultimate-problem-solver`: v5.2.0 (public release; removed references to non-public skills)
- `哲思伙伴`: v1.1.0 (public release; removed references to non-public skills)
- `skill设计师`: v1.1.0 (public release; removed bundled examples/references to keep repo minimal)
