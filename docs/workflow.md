# 同步工作流

定时已开启，每天北京时间 8:00（盘前）和 15:00（下午收盘）各跑一次。本机用 `launchd`，任务名是 `com.wisburg.daily-sync`。日志在 `~/Library/Logs/wisburg-sync.log`。周末也会跑，避免周六日发布的笔记要等到周一。

手动执行仍然可用：

```bash
export WISBURG_API_KEY=...
python3 -m wisburg_sync
```

密钥只放在环境变量里。命令可以重复执行。

跑完后，如果本机 `.env` 里配置了 `FEISHU_WEBHOOK_URL` 和 `FEISHU_BOT_SECRET`，会给飞书机器人发一条增量通知：来源、条数、发布日期、机构、标题。Mikko 没有标题时用正文第一句。本次没有新写入的行时，通知里是「本次新增 0 条」。密钥和 Webhook 不进仓库。

## 一次运行在做什么

程序按来源依次处理。`feed` 关闭，会打印 `skip feed`，不请求。

开启的来源顺序是：`market-daily`、`mikko-logs`、`reports`、`company-reports`、`earningscalls`、`am-reports`、`archives`、`articles`。

每个来源四步：

1. 读 `checkpoints` 里这个来源的断点。没有断点时，窗口是运行时刻往前 7 天。有断点时，窗口从断点发布时间再往回 48 小时，直到这次运行开始。
2. 不带关键词，按时间从新到旧翻列表。每页 100 条。`after` 用上一页的 `end_cursor`。时间参数带 `+08:00`。翻到早于窗口起点就停。
3. 列表先入库。需要详情的再逐条请求。一次只发一条。成功后停 0.25 秒。收到 429 就按 `Retry-After` 等待再试。
4. 列表翻完，且详情没有成批失败，才把断点推到已见到的最新 id 和发布时间。

详情规则：

| 来源 | 行为 |
|---|---|
| `reports`、`company-reports`、`earningscalls`、`am-reports`、`archives` | `GET /api/{来源}/{id}`，正文用 `summary` |
| `articles` | `GET /api/articles/{id}`，正文用 `body` |
| `mikko-logs` | 列表里的 `content` 就是全文。有配图，或正文像被截断时，才再取详情 |
| `market-daily` | `/api/market-daily/{id}` 不存在，改请求 `/api/reports/{id}` |

已经 `detail_status = ok` 的旧行不会在下一轮重拉。所以智堡若改了已入库笔记的正文，本地不会自动跟上。新条目和 `pending`、`error` 会拉。

同一篇出现在投行库和企业库时，各存一行，详情也会各请求一次。

## 跑完看什么

终端每个来源一行，类似：

```text
reports: status=success pages=1 listed=83 new=0 updated=0 detail_ok=0 detail_fail=0
```

`status=success` 或 `empty` 表示这个来源的窗口翻完了。`error` 或 `truncated` 表示断点没推进，下一轮还会盖住同一段。

也可以查库：

```sql
SELECT source, last_status, latest_published_at, last_success_at
FROM checkpoints
ORDER BY source;

SELECT id, status, started_at, finished_at
FROM runs
ORDER BY id DESC
LIMIT 5;
```

某次运行里每个来源的页数、新增、更新、详情成败在 `run_sources`，用 `run_id` 连到 `runs.id`。

## 失败时会怎样

| 情况 | 结果 |
|---|---|
| 没配密钥，或返回 401 / 403 | 该来源 `error`，断点不动 |
| 429 限流 | 按响应头等待后重试，最多 6 次。仍失败的详情记为 `error` |
| 详情失败很多（不少于 3 条，且不少于成功条数） | 断点不推进 |
| 零星详情失败 | 断点仍推进，失败行留在 `pending` 或 `error`，下一轮补 |
| 翻页达到 80 页，或游标重复 | `truncated`，断点不动 |
| 同一把密钥被另一个程序同时使用 | 仍可能被限流 |

发布超过 48 小时才出现在列表里的条目，当前窗口盖不住，会漏。这是重叠窗口的边界，不是断点没写上。

## 不要做的事

- 不要开多进程同时跑 `python3 -m wisburg_sync`。
- 不要把并发调高。当前就是 1。
- 分析时不要写 `data/wisburg.sqlite`。
- 不要把密钥写进仓库或打进日志。
