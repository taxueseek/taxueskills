# 引擎 A：腾讯校招官方 API 直连

> 数据源：`join.qq.com/api/v1` 腾讯校招官网公开接口，无需鉴权，无 API Key。

## 定位

| 引擎 | 数据源 | 覆盖范围 | 何时用 |
|------|--------|---------|--------|
| **A：腾讯官方 API** | join.qq.com | 腾讯系校招/实习/青云岗位、公告、宣讲会 | 用户意图含「腾讯/鹅厂/校招」，或需官方原始 JD |
| **B：全平台搜索** | argo / 基础搜索 | BOSS/猎聘/智联/前程无忧/ncss 等全平台 | 其他场景，或与 A 交叉验证 |

## 脚本用法（scripts/ 目录）

```bash
# 岗位/JD 搜索（引擎 A 主入口）
python3 scripts/fetch_recruit_jds.py search --keyword "后台" --page-size 10
python3 scripts/fetch_recruit_jds.py search --keyword "Python 深圳" --work-city-ids 3 --position-family-ids 2
python3 scripts/fetch_recruit_jds.py detail <post_id>          # 完整 JD
python3 scripts/fetch_recruit_jds.py all --keyword "青云"       # 全量抓取 + 字段匹配
python3 scripts/fetch_recruit_jds.py match "Python 后台 MySQL 深圳"  # 简历文本匹配岗位
python3 scripts/fetch_recruit_jds.py dicts                     # 筛选字典（项目/岗位类别/城市）

# 公告/宣讲会（引擎 A 辅助）
python3 scripts/fetch_recruit_info.py latest                   # 最新公告 + 宣讲会
python3 scripts/fetch_recruit_info.py notices                  # 公告列表
python3 scripts/fetch_recruit_info.py notice <id>              # 公告全文
python3 scripts/fetch_recruit_info.py flow "投递后多久有回复" --question-time "<当前时间>"
python3 scripts/fetch_recruit_info.py talks                    # 宣讲会日程
```

所有命令支持 `--compact`（默认紧凑）/ `--pretty` / `--limit N`（默认 30）/ `--full`。Python 3.10+，仅标准库。

### 输出与召回开关

| 开关 | 默认 | 作用 |
|------|------|------|
| `--limit N` | 30 | 列表最多渲染多少条；`positions_total` 标出实际总数 |
| `--full` | 关 | 不截断，慎用：全量近千条会撑爆上下文 |
| `recall`（`search` 专属） | 自动 | 是否做「全量抓取 + 本地字段补召回」 |
| `--recall` / `--no-recall` | — | 强制开启 / 关闭补召回 |
| `--recall-pages N` | 12 | 补召回最多扫几页（目录约 10 页） |

召回自动开关的依据（实测）：地点词与招聘批次词补召回收益极大（深圳 +601、实习 +556、青云 +99），职能与技能词收益为 0（后台/算法/产品/数据/测试/运营），因此只对前两类补扫，另外官网标题完全没命中（`api_total == 0`）时也补扫，保证任意地名不漏。

## 数据字段说明

- `search` 返回 `positions[]`：title、project_name、recruit_label（校招/实习/青云）、bgs（BG 事业群）、work_cities、apply_url
- `count` = 合并去重后的实际岗位数；`api_total` = API 标题匹配总数；`local_field_match_count` = 本地字段补充匹配数（青云等标题不含关键词的岗位靠 recruit_label/project_name 补召回）
- `detail` 返回完整 JD：description/requirements（普通岗），topicDetail/topicRequirement（青云课题岗），`description_source_field` 标注实际来源字段

## 红线

1. **零编造**：接口未返回的信息不猜测。岗位匹配不输出分数或百分比给用户
2. 腾讯岗位以 `join.qq.com` 官网为准，`apply_url` 必须随岗位输出
3. 薪酬、offer 承诺、录取率等敏感信息不输出，引导以 HR 沟通为准
4. `flow` 的 `--question-time` 传入当前提问时间，选公告按「相关度 × 时效」打分，公告未覆盖的问题引导 join.qq.com 官网

## 缓存与重试

- 字典类接口（项目/岗位类别/城市）24h 缓存；公告列表 5 分钟；公告详情 1h；宣讲会 10 分钟
- **缓存是进程内的**：每次 `python3 scripts/...` 都是新进程，缓存不跨命令复用。只有同一次命令内部的重复请求会命中（如 `match` 的搜索阶段与详情阶段）。需要跨命令复用要另行设计持久缓存。
- 失败自动重试 2 次，退避 0.4s → 0.8s（单次上限 3s）
- 请求时间戳在进程内复用（60s 一刷），提升接口可缓存性
