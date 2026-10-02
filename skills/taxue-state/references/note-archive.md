# 笔记归档（个人数据源配置）

把手机里攒的笔记变成可检索、可提炼、可反哺风格库的资产。提取 → 去重 → 分类 → 增量归档，一条命令完成。

> 本文件是**个人环境配置**，分类桶按当前机器实况填写；换机器/换数据源时只改这里。> 归档目标路径读 `~/.taxue/config.json` 的 entries，解析规范见 `../taxue/references/vault.md`；本文件的分类桶与关键词表按当前机器实况维护。


## 数据源与归档目标
| 项 | 路径 |
|----|------|
| 默认数据源 | ~/Library/Application Support/pcsuite/database/NoteSync.db（vivo PC 套件原子笔记同步库，NoteCache 表） |
| 视觉/生图归档 | `{视觉归档}` = entries.state_archive_visual（16 类分文件） |
| 其他类归档 | `{通用归档}` = entries.state_archive_misc（6 类分文件） |

## 分类体系
**视觉/生图类（16 桶）**：01_水墨国画 / 02_剪纸皮影 / 03_刺绣织锦 / 04_纸雕灯彩 / 05_雕塑摆件 / 06_摄影人像 / 07_海报平面 / 08_城市建筑 / 09_动漫插画 / 10_产品静物 / 11_纹样图腾 / 12_氛围场景 / 13_英文结构化 / 14_多格序列 / 15_其他视觉

**其他类（6 桶）**：01_写作创作 / 02_投资理财 / 03_思维框架 / 04_职场求职 / 05_工具技巧 / 06_生活随记

关键词表统一维护在 scripts/categories.py，新增/调整分类只改该文件，不碰主脚本。

## 使用
```bash
# 增量归档（默认：全量扫描 NoteCache，跳过已归档 guid）
python3 ~/.agents/skills/taxue-state/scripts/archive_notes.py

# 只处理最近 2 天新同步的笔记（手机刚同步完就跑这个）
python3 ~/.agents/skills/taxue-state/scripts/archive_notes.py --since 2

# 先看会归档多少，不写文件
python3 ~/.agents/skills/taxue-state/scripts/archive_notes.py --dry-run

# 指定其他数据库（如换了手机/导出的副本）
python3 ~/.agents/skills/taxue-state/scripts/archive_notes.py --db /path/to/NoteSync.db
```

## 工作流
1. **手机侧**：vivo 原子笔记写好/收藏提示词 → PC 套件同步（NoteCache 缓存落库）
2. **归档**：跑主脚本（建议 --dry-run 看增量，再正式写）
3. **核对**：看分类统计，重点检查「15_其他视觉」桶是否过大（说明关键词表该补词，改 categories.py 后重跑，历史条目不会自动移动，可手动移动或接受归属）
4. **提炼**：新增条目中挑结构完整、可槽位化的精品 → 对照 taxue-creative-style 家族（F1-F9）写提炼稿
