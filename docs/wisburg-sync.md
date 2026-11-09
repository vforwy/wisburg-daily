# 智堡本地库同步

状态：已实现。每天 8:00 与 15:00 定时同步。  
改设计时直接改这份文档，并在文末修订记录加一行。同步入口是 `python3 -m wisburg_sync`。

相关文档：项目入口见仓库根目录 `README.md`，运行步骤见 [workflow.md](workflow.md)，查库见 [database.md](database.md)。

## 目标

每天定时把智堡新增内容拉全，落到本地 SQLite，供后续分析使用。

三件事：

1. 不遗漏。每个来源按时间翻完窗口，失败不推进断点。
2. 能更新。同一篇再次出现且正文变了，替换正文，保留首次看到的时间。
3. 能换机器。仓库、一个数据库文件、一个环境变量即可迁走。

接口已经返回结构化字段。入库只保存这些字段，不补写主题标签，也不做观点抽取。

## 范围

Base：`https://api-omen.wisburg.com`  
鉴权：`Authorization: Bearer $WISBURG_API_KEY`  
Key 只放环境变量，不进库、不进仓库。

列表参数：`first`（1–100）、`query`、`after`、`startTime`、`endTime`。发现阶段不传 `query`。时间必须带 `+08:00`；只写日期会按 UTC 零点解析，北京时间错开 8 小时。

| 来源 | 列表 | 详情 | 正文 |
|---|---|---|---|
| `feed` | `GET /api/feed` | 列表自带正文 | 列表正文 |
| `market-daily` | `GET /api/market-daily` | `GET /api/market-daily/{id}` 不存在时改取 `GET /api/reports/{id}` | 详情里的 `summary` |
| `mikko-logs` | `GET /api/mikko-logs` | 有配图或正文明显截断时再取 `GET /api/mikko-logs/{id}` | 列表里的 `content` |
| `reports` | `GET /api/reports` | `GET /api/reports/{id}` | `summary` |
| `company-reports` | `GET /api/company-reports` | `GET /api/company-reports/{id}` | `summary` |
| `earningscalls` | `GET /api/earningscalls` | `GET /api/earningscalls/{id}` | `summary` |
| `am-reports` | `GET /api/am-reports` | `GET /api/am-reports/{id}` | `summary` |
| `archives` | `GET /api/archives` | `GET /api/archives/{id}` | `summary` |
| `articles` | `GET /api/articles` | `GET /api/articles/{id}` | `body` |

`reports`、`company-reports`、`am-reports`、`archives`、`earningscalls` 的详情是智堡笔记摘要，不是机构 PDF。文章详情是全文。Mikko 列表已经带全文。

`feed` 的列表正文按接口说明最多大约 300 字，且与研报大量重复。表结构给它留来源，默认同步先关闭，需要时再开。`images` 不进这版。

## 存储

数据库文件：`data/wisburg.sqlite`。

同步程序、建表语句和本说明放在同一仓库。不使用 MySQL，也不把 MCP 当成同步入口。

主键是 **来源 + 远端 id**。同一篇笔记可以同时出现在投行库和企业库，id 相同也各存一行。合并交给以后的分析，入库时不丢行。

## 表

### items

一行一篇材料。

| 列 | 含义 |
|---|---|
| `source` | 上表中的来源名 |
| `remote_id` | 接口返回的 id |
| `title` | 标题 |
| `published_at` | 发布时间，保留时区 |
| `institution` | 详情 `meta.name`；没有则为空 |
| `body` | 上表「正文」列对应的文本，供检索 |
| `list_json` | 列表条目的原始 JSON |
| `detail_json` | 详情的原始 JSON；还没拉到则为空 |
| `content_hash` | 正文哈希，用来判断同一篇是否改过 |
| `first_seen_at` | 第一次入库时间 |
| `list_fetched_at` | 最近一次列表写入时间 |
| `detail_fetched_at` | 最近一次详情写入时间 |
| `updated_at` | 最近一次正文或原始 JSON 变化的时间 |
| `detail_status` | `pending`、`ok`、`not_needed`、`error` |

`source + remote_id` 唯一。正文建 FTS5 索引。

### checkpoints

每个来源一行。

| 列 | 含义 |
|---|---|
| `source` | 来源名 |
| `latest_id` | 已完整覆盖到的最新 id |
| `latest_published_at` | 已完整覆盖到的最新发布时间 |
| `last_success_at` | 上次成功跑完的时间 |
| `last_status` | `success`、`empty`、`error`、`truncated` |

### runs / run_sources

`runs` 记录每一次运行：开始、结束、触发方式。  
`run_sources` 记录该次每个来源翻了多少页、新增多少、更新多少、详情失败多少、最终状态。

## 每次运行

程序可以重复执行。

1. 读该来源的断点。没有断点时，从回填起点拉到现在。
2. 不带关键词，按时间从新到旧翻页。`first=100`，`after` 使用上一页的 `end_cursor`。翻到早于「断点时间减去重叠窗口」为止。重叠窗口 48 小时，用来接住发布时间较早、后来才出现在列表里的条目。
3. 列表先入库。需要详情的再请求 `GET /api/{source}/{id}`。同一来源、同一 id 已存在则更新。正文哈希变了就替换正文和原始 JSON，`first_seen_at` 不动。
4. 该来源翻完且详情没有成批失败，才把断点推到本轮见到的最新 id 和时间。中途报错，或页数到顶仍未翻完，状态记为 `error` 或 `truncated`，断点留在原地。

`market-daily` 没有自己的详情路径。列表只有标题和时间，正文改从 `GET /api/reports/{id}` 取。两条都没有正文时，保留列表行，`detail_status` 记为 `not_needed`。

详情请求串行。遇到 HTTP 429 时按响应头 `Retry-After` 等待后再试，避免并发把接口打满。已经成功写入的详情不会在同一次回填里重复请求；断点之后的重叠窗口仍会把新条目的详情拉下来。失败的详情留在 `pending` 或 `error`，下一轮继续补。

## 定时与迁移

定时用本机 `launchd` 触发，每天 8:00 和 15:00。程序不依赖某一台电脑上的定时配置。换机器时重新加一个定时项，或由 agent 手动跑同一条命令。

迁走时带三样东西：

- 这个仓库
- `data/wisburg.sqlite`
- 环境变量 `WISBURG_API_KEY`

另一台机器装好 Python 依赖后执行同步命令，从库里的断点继续拉。

## 待确认

实施前按这里的值为准。要改就改此节，并记一笔修订。

| 项 | 当前取值 |
|---|---|
| 首次回填 | 7 天 |
| `feed` | 关闭 |
| 数据库路径 | `data/wisburg.sqlite` |
| 重叠窗口 | 48 小时 |
| 列表页大小 | 100 |

## 修订记录

| 日期 | 说明 |
|---|---|
| 2026-11-09 | 初稿。根据当日讨论写入，尚未实施。 |
| 2026-11-09 | 重叠窗口由 72 小时改为 48 小时。 |
| 2026-11-09 | 按本文实现同步。去掉旧静态页。定时未开启。平台日报正文改从 `/api/reports/{id}` 取。 |
| 2026-11-09 | 补项目说明、工作流说明和给其他 agent 的数据库用法。 |
| 2026-11-09 | 开启每天 8:00 与 16:00 的定时同步。 |
| 2026-11-09 | 下午场由 16:00 改为 15:00。 |
