from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from wisburg_sync.config import BASE_URL


class WisburgError(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("WISBURG_API_KEY", "").strip()
    if not key:
        raise WisburgError(
            "未配置 WISBURG_API_KEY。请先 export WISBURG_API_KEY=... ，不要把密钥写进仓库。"
        )
    return key


def get(path: str, params: dict[str, Any] | None = None) -> Any:
    """返回 data。404 返回 None。其他错误抛出 WisburgError。"""
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
    url = f"{BASE_URL}{path}{query}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key()}", "Accept": "application/json"},
    )
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            body = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in (401, 403):
                raise WisburgError(f"鉴权失败 HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After", "").strip()
            try:
                delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
            except ValueError:
                delay = 1.5 * (attempt + 1)
            last_error = WisburgError(f"HTTP {exc.code}: {body}")
            time.sleep(min(delay, 900) + random.uniform(0, 0.2))
            continue
        except urllib.error.URLError as exc:
            last_error = WisburgError(f"网络错误: {exc.reason}")
            time.sleep(1.5 * (attempt + 1))
            continue
        if payload.get("status") != 0 or payload.get("code") != 200:
            raise WisburgError(
                f"业务错误 ({path}): {payload.get('message')} code={payload.get('code')}"
            )
        time.sleep(0.25)
        return payload.get("data")
    raise WisburgError(f"请求失败 ({path}): {last_error}")


def list_page(source: str, *, first: int, after: str | None, start: str, end: str) -> tuple[list[dict], str | None]:
    data = get(
        f"/api/{source}",
        {"first": first, "after": after, "startTime": start, "endTime": end},
    )
    if not isinstance(data, dict):
        raise WisburgError(f"列表响应异常: {source}")
    items = data.get("items") or []
    page = data.get("page_info") or data.get("pageInfo") or {}
    cursor = page.get("end_cursor") or page.get("endCursor") or None
    return items, cursor
