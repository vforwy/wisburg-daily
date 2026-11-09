# 智堡本地库

这个仓库把智堡的列表和详情同步到本地 SQLite，供后续分析使用。没有网页。每天北京时间 8:00 和 15:00 各同步一次。

数据库文件是 `data/wisburg.sqlite`。它不进 git。分析时只读这个文件，不要改表。

## 文档

| 文档 | 谁来读 |
|---|---|
| [docs/workflow.md](docs/workflow.md) | 同步怎么跑、失败时断点怎么处理 |
| [docs/database.md](docs/database.md) | 其他 agent 查库时先读这份 |
| [docs/wisburg-sync.md](docs/wisburg-sync.md) | 设计约定。改同步行为时改这份，并记修订 |

## 运行同步

需要 Python 3.9 以上，只用标准库。密钥放在环境变量里，不要写进仓库。

```bash
export WISBURG_API_KEY=...
python3 -m wisburg_sync
```

没有断点时回填 7 天。之后从断点往回重叠 48 小时再拉。可以重复执行。

换电脑时带走仓库、`data/wisburg.sqlite`（含 `-wal`、`-shm`，若正在写入）和 `WISBURG_API_KEY`。飞书通知还要本机 `.env` 里的 `FEISHU_WEBHOOK_URL` 和 `FEISHU_BOT_SECRET`，这两个值不进仓库。
