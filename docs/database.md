# 数据库用法

给要读这份智堡库的 agent。只读，不要建表、改行或另拉一套平行数据。

## 文件

路径：`data/wisburg.sqlite`（相对本仓库根目录）。

用只读方式打开，避免和同步抢写锁：

```bash
sqlite3 "file:data/wisburg.sqlite?mode=ro"
```

```python
import sqlite3
conn = sqlite3.connect("file:data/wisburg.sqlite?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
```

文件不在 git 里。仓库克隆下来如果没有这个文件，说明这台机器还没跑过同步，或文件没一起拷来。不要用空库假装有数据。

最近一次完整同步覆盖的发布时间大约是 `2026-11-02T12:28:59+08:00` 到 `2026-11-09T12:14:27+08:00`，共 1962 条。这是当时的结果，不是永远的范围。查之前先看下面的覆盖查询。

## 先看覆盖

```sql
SELECT source,
       COUNT(*) AS n,
       MIN(published_at) AS oldest,
       MAX(published_at) AS newest
FROM items
GROUP BY source
ORDER BY source;

SELECT last_status, latest_published_at, last_success_at
FROM checkpoints
ORDER BY source;
```

`checkpoints.last_status` 不是 `success` 或 `empty` 时，这个来源的窗口可能不完整，不要把缺的时间段说成「没有内容」。

## 内容在 items

一行是一篇材料。主键是 `source` + `remote_id`，不是单独的 `remote_id`。同一篇笔记可以同时出现在 `reports` 和 `company-reports`，id 相同，要各算一行，除非分析时明确按标题和发布时间合并。

| 列 | 含义 |
|---|---|
| `id` | 库内自增 id，只用于本库关联全文索引 |
| `source` | 来源，取值见下表 |
| `remote_id` | 智堡条目 id，文本 |
| `title` | 标题。Mikko 短评经常为空 |
| `published_at` | 发布时间，文本，形如 `2026-11-09T12:14:27+08:00`。格式固定，可以直接按字符串比较和排序 |
| `institution` | 机构名，来自详情 `meta.name`。没有这个字段的来源就是空字符串 |
| `body` | 分析用的正文 |
| `list_json` | 列表接口的原始 JSON |
| `detail_json` | 详情接口的原始 JSON。列表已经够用、没再请求详情时为空 |
| `content_hash` | 正文的 SHA-256 |
| `first_seen_at` | 第一次入库时间 |
| `list_fetched_at` | 最近一次写入列表的时间 |
| `detail_fetched_at` | 最近一次写入详情的时间 |
| `updated_at` | 正文最近一次变化的时间 |
| `detail_status` | `ok`：详情已写入。`not_needed`：列表正文已够用。`pending` / `error`：正文可能不完整 |

`body` 和接口字段的对应：

| source | body 里是什么 |
|---|---|
| `reports` | 智堡笔记摘要，接口字段 `summary` |
| `company-reports` | 同上 |
| `am-reports` | 同上 |
| `archives` | 同上 |
| `earningscalls` | 同上 |
| `market-daily` | 同上。详情走 `GET /api/reports/{id}`，因为 `/api/market-daily/{id}` 不存在 |
| `articles` | 文章全文，接口字段 `body` |
| `mikko-logs` | 短评全文，接口字段 `content` |
| `feed` | 这版同步关闭，库里不应有行 |

研报类的 `body` 是智堡写的笔记，不是机构 PDF 原文。笔记里没有的数字不要补。

`institution` 只在详情带了 `meta.name` 时有值。电话会、文章、Mikko 短评、平台日报通常是空的。机构名也可能写在正文句子里。空字符串表示接口没给机构字段，不等于「未具名机构」。

没有主题、行业、股票标签列。不要从别的系统发明标签填进来。

## 来源怎么用

| source | 用途 |
|---|---|
| `reports` | 宏观、策略、行业、商品研报 |
| `company-reports` | 单家公司研究 |
| `am-reports` | 资管、买方 |
| `earningscalls` | 电话会纪要 |
| `archives` | 央行、监管、国际组织等文献的智堡摘要 |
| `articles` | 智堡平台文章全文 |
| `market-daily` | 智堡编辑写的市场综述，不是某一家机构的观点 |
| `mikko-logs` | Mikko 的短评。转述机构时仍算那家机构的话，不要写成 Mikko 本人的判断 |

## 常用查询

按时间和来源读正文：

```sql
SELECT source, remote_id, title, institution, published_at, body
FROM items
WHERE source = 'reports'
  AND published_at >= '2026-11-09T00:00:00+08:00'
  AND published_at < '2026-11-10T00:00:00+08:00'
ORDER BY published_at;
```

按机构：

```sql
SELECT published_at, title, remote_id
FROM items
WHERE source = 'reports'
  AND institution = '高盛'
ORDER BY published_at DESC
LIMIT 20;
```

中文检索用 `LIKE`。全文索引 `items_fts` 用的是 `unicode61`，不会按中文词切开，不要靠它做中文检索。

```sql
SELECT source, remote_id, title, institution, published_at
FROM items
WHERE body LIKE '%美联储%'
ORDER BY published_at DESC
LIMIT 20;
```

看一篇的原始详情：

```sql
SELECT detail_json
FROM items
WHERE source = 'reports' AND remote_id = '113174';
```

未完成的正文：

```sql
SELECT source, remote_id, title, detail_status
FROM items
WHERE detail_status IN ('pending', 'error')
   OR trim(body) = '';
```

## 不要读错的表

`checkpoints`、`runs`、`run_sources` 是同步运行记录，不是研报内容。

`items_fts` 以及 `items_fts_*` 是全文索引的内部表，不要当内容表查。
