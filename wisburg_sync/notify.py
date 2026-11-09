from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE_LABELS = {
    "reports": "投行研报",
    "company-reports": "企业研究",
    "market-daily": "平台日报",
    "mikko-logs": "Mikko 短评",
    "am-reports": "资管",
    "articles": "文章",
    "earningscalls": "电话会",
    "archives": "文献",
}
SOURCE_ORDER = list(SOURCE_LABELS)
INSTITUTION_NAMES = (
    "美银美林",
    "摩根士丹利",
    "摩根大通",
    "德意志银行",
    "威灵顿资管",
    "高盛",
    "巴克莱",
    "花旗",
    "杰富瑞",
    "德银",
    "瑞银",
    "汇丰",
    "美银",
    "野村",
)


def load_local_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _first_clause(text: str, limit: int = 42) -> str:
    cleaned = " ".join((text or "").replace("**", "").split())
    for sep in ("。", "！", "？", "；"):
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0]
            break
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned or "（无正文）"


def display_institution(row: dict) -> str:
    name = (row.get("institution") or "").strip()
    if name:
        return name
    source = row.get("source")
    if source in ("market-daily", "articles"):
        return "智堡"
    if source == "mikko-logs":
        opening = (row.get("body") or "")[:120]
        for candidate in INSTITUTION_NAMES:
            if candidate in opening:
                return candidate
    return "未具名"


def display_title(row: dict) -> str:
    title = (row.get("title") or "").strip()
    if title:
        return title
    return _first_clause(row.get("body") or "")


def display_time(published_at: str) -> str:
    if published_at and len(published_at) >= 16:
        return published_at[11:16]
    return ""


def build_message(rows: list[dict]) -> str:
    dates = sorted({(row.get("published_at") or "")[:10] for row in rows if row.get("published_at")})
    date_line = "、".join(dates) if dates else "无"
    lines = [
        "智堡入库完成",
        f"发布日期 {date_line}",
        f"本次新增 {len(rows)} 条",
    ]
    if not rows:
        return "\n".join(lines)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("source") or "", []).append(row)
    for source in SOURCE_ORDER:
        items = grouped.get(source) or []
        if not items:
            continue
        label = SOURCE_LABELS.get(source, source)
        note = "（无标题，下面是正文首句）" if source == "mikko-logs" else ""
        lines.append("")
        lines.append(f"{label} {len(items)} 条{note}")
        items.sort(key=lambda item: item.get("published_at") or "")
        for item in items:
            lines.append(
                f"{display_time(item.get('published_at') or '')} {display_institution(item)}｜{display_title(item)}"
            )
    return "\n".join(lines)


def send_text(text: str) -> None:
    load_local_env()
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    secret = os.environ.get("FEISHU_BOT_SECRET", "").strip()
    if not webhook:
        print("飞书通知未发送：未配置 FEISHU_WEBHOOK_URL", flush=True)
        return
    payload: dict = {"msg_type": "text", "content": {"text": text}}
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _sign(timestamp, secret)
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("code") not in (0, None) or body.get("StatusCode") not in (0, None):
        raise RuntimeError(body.get("msg") or body.get("StatusMessage") or "飞书通知失败")
