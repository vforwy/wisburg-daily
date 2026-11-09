from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wisburg_sync import client, db
from wisburg_sync.client import WisburgError
from wisburg_sync.config import BACKFILL_DAYS, MAX_PAGES, OVERLAP_HOURS, PAGE_SIZE, SOURCES

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "wisburg.sqlite"


def now() -> datetime:
    return datetime.now(TZ).replace(microsecond=0)


def stamp(value: datetime) -> str:
    return value.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def list_body(source: str, item: dict) -> str:
    if source == "mikko-logs":
        return item.get("content") or ""
    if source == "feed":
        return item.get("content") or item.get("summary") or item.get("description") or ""
    return ""


def detail_body(source: str, detail: dict) -> str:
    if source == "articles":
        return detail.get("body") or ""
    if source == "mikko-logs":
        return detail.get("content") or ""
    return detail.get("summary") or detail.get("content") or detail.get("body") or ""


def institution_of(detail: dict | None) -> str:
    meta = (detail or {}).get("meta") or {}
    name = meta.get("name") if isinstance(meta, dict) else None
    return str(name or "").strip()


def looks_truncated(text: str) -> bool:
    stripped = text.strip()
    return stripped == "" or stripped.endswith(("...", "…", "……"))


def needs_mikko_detail(item: dict) -> bool:
    return bool(item.get("images")) or looks_truncated(item.get("content") or "")


def _rows_for_pairs(conn, pairs: list[tuple[str, str]]) -> list[dict]:
    rows = []
    for source, remote_id in pairs:
        row = conn.execute(
            """
            SELECT source, remote_id, title, institution, published_at, body
            FROM items
            WHERE source = ? AND remote_id = ?
            """,
            (source, remote_id),
        ).fetchone()
        if row is not None:
            rows.append(dict(row))
    return rows


def sync(db_path: Path = DEFAULT_DB, *, backfill_days: int = BACKFILL_DAYS, trigger: str = "manual") -> int:
    from wisburg_sync.notify import load_local_env

    load_local_env()
    started = now()
    conn = db.connect(db_path)
    run_id = db.start_run(conn, stamp(started), trigger)
    conn.commit()
    worst = "success"
    new_pairs: list[tuple[str, str]] = []
    try:
        for source in SOURCES:
            if not source.enabled:
                print(f"skip {source.name}", flush=True)
                continue
            stats = sync_source(conn, source.name, source.detail, started, backfill_days)
            new_ids = stats.pop("new_ids", [])
            new_pairs.extend((source.name, remote_id) for remote_id in new_ids)
            stats["source"] = source.name
            db.save_run_source(conn, run_id, stats)
            conn.commit()
            print(
                f"{source.name}: status={stats['status']} pages={stats['pages']} "
                f"listed={stats['listed']} new={stats['new_count']} "
                f"updated={stats['updated_count']} detail_ok={stats['detail_ok']} "
                f"detail_fail={stats['detail_fail']}",
                flush=True,
            )
            if stats["status"] in ("error", "truncated"):
                worst = stats["status"]
    except Exception as exc:
        worst = "error"
        print(f"sync failed: {exc}")
        raise
    finally:
        db.finish_run(conn, run_id, stamp(now()), worst)
        try:
            rows = _rows_for_pairs(conn, new_pairs)
            from wisburg_sync.notify import build_message, send_text

            send_text(build_message(rows))
            print(f"飞书通知已发送，新增 {len(rows)} 条", flush=True)
        except Exception as exc:
            print(f"飞书通知失败: {exc}", flush=True)
        conn.commit()
        conn.close()
    print(f"database: {db_path}")
    return 0 if worst == "success" else 1


def sync_source(conn, source: str, detail_mode: str, started: datetime, backfill_days: int) -> dict:
    stats = {
        "pages": 0,
        "listed": 0,
        "new_count": 0,
        "updated_count": 0,
        "detail_ok": 0,
        "detail_fail": 0,
        "status": "success",
        "error": "",
        "new_ids": [],
    }
    point = db.checkpoint(conn, source)
    window_start, window_end = window_for(point, started, backfill_days)
    preexisting = db.existing_ids(conn, source)
    known = set(preexisting)
    newest: tuple[datetime, str] | None = None
    if point and point["latest_published_at"]:
        previous = parse_dt(point["latest_published_at"])
        if previous is not None:
            newest = (previous, point["latest_id"] or "")

    try:
        listed_ids = collect_list(
            conn, source, detail_mode, window_start, window_end, known, preexisting, stats
        )
    except WisburgError as exc:
        stats["status"] = "error"
        stats["error"] = str(exc)
        keep_checkpoint(conn, source, point, "error")
        return stats

    detail_ids = list(listed_ids)
    if detail_mode != "never":
        for row in db.pending_details(conn, source):
            if row["remote_id"] not in detail_ids:
                detail_ids.append(row["remote_id"])
    if detail_mode == "try":
        for row in conn.execute(
            """
            SELECT remote_id FROM items
            WHERE source = ? AND detail_status = 'not_needed'
              AND trim(coalesce(body, '')) = ''
            """,
            (source,),
        ):
            if row["remote_id"] not in detail_ids:
                detail_ids.append(row["remote_id"])
    fetch_details(conn, source, detail_mode, detail_ids, preexisting, stats)
    if stats["status"] == "truncated":
        keep_checkpoint(conn, source, point, "truncated")
        return stats

    rows = conn.execute(
        "SELECT remote_id, published_at FROM items WHERE source = ? AND published_at IS NOT NULL",
        (source,),
    ).fetchall()
    for row in rows:
        published = parse_dt(row["published_at"])
        if published is None:
            continue
        if newest is None or published > newest[0]:
            newest = (published, row["remote_id"])

    status = "empty" if stats["listed"] == 0 and stats["new_count"] == 0 else "success"
    if stats["detail_fail"] and stats["detail_fail"] >= max(3, stats["detail_ok"]):
        status = "error"
        stats["error"] = f"详情失败 {stats['detail_fail']} 条，断点不推进"
    stats["status"] = status
    if status == "error":
        keep_checkpoint(conn, source, point, "error")
        return stats

    db.save_checkpoint(
        conn,
        source=source,
        latest_id=newest[1] if newest else None,
        latest_published_at=stamp(newest[0]) if newest else stamp(window_end),
        last_success_at=stamp(started),
        last_status=status,
    )
    return stats


def window_for(point, started: datetime, backfill_days: int) -> tuple[datetime, datetime]:
    if point and point["latest_published_at"]:
        latest = parse_dt(point["latest_published_at"])
        if latest is not None:
            return latest - timedelta(hours=OVERLAP_HOURS), started
    return started - timedelta(days=backfill_days), started


def keep_checkpoint(conn, source: str, point, status: str) -> None:
    db.save_checkpoint(
        conn,
        source=source,
        latest_id=point["latest_id"] if point else None,
        latest_published_at=point["latest_published_at"] if point else None,
        last_success_at=point["last_success_at"] if point else None,
        last_status=status,
    )


def collect_list(conn, source, detail_mode, window_start, window_end, known, preexisting, stats) -> list[str]:
    after = None
    seen_cursors: set[str] = set()
    listed_ids: list[str] = []
    fetched_at = stamp(now())
    while stats["pages"] < MAX_PAGES:
        items, cursor = client.list_page(
            source,
            first=PAGE_SIZE,
            after=after,
            start=stamp(window_start),
            end=stamp(window_end),
        )
        stats["pages"] += 1
        print(f"  {source} page {stats['pages']}: {len(items)}", flush=True)
        stop = False
        for item in items:
            published = parse_dt(item.get("datetime"))
            if item.get("id") is None or published is None or published < window_start:
                stop = True
                continue
            remote_id = str(item.get("id"))
            listed_ids.append(remote_id)
            stats["listed"] += 1
            write_list_item(
                conn, source, detail_mode, item, remote_id, published, fetched_at, known, preexisting, stats
            )
        conn.commit()
        if stop or not cursor or len(items) < PAGE_SIZE:
            return listed_ids
        if cursor in seen_cursors:
            stats["status"] = "truncated"
            stats["error"] = "分页游标重复"
            return listed_ids
        seen_cursors.add(cursor)
        after = cursor
    stats["status"] = "truncated"
    stats["error"] = f"翻页达到上限 {MAX_PAGES}"
    return listed_ids


def write_list_item(conn, source, detail_mode, item, remote_id, published, fetched_at, known, preexisting, stats):
    current = db.get_item(conn, source, remote_id)
    body = list_body(source, item)
    if detail_mode == "never":
        status = "not_needed"
    elif detail_mode == "mikko" and not needs_mikko_detail(item):
        status = "not_needed"
    elif current and current["detail_status"] == "ok":
        status = "ok"
        body = current["body"] or body
    else:
        status = "pending"
        if current and current["body"]:
            body = current["body"]
    institution = current["institution"] if current else ""
    detail_json = current["detail_json"] if current else None
    detail_fetched_at = current["detail_fetched_at"] if current else None
    previous_hash = current["content_hash"] if current else None
    row = item_row(
        source=source,
        remote_id=remote_id,
        title=str(item.get("title") or ""),
        published_at=stamp(published),
        institution=institution,
        body=body,
        list_json=json.dumps(item, ensure_ascii=False),
        detail_json=detail_json,
        first_seen_at=current["first_seen_at"] if current else fetched_at,
        list_fetched_at=fetched_at,
        detail_fetched_at=detail_fetched_at,
        updated_at=fetched_at if previous_hash != digest(body) else (current["updated_at"] if current else fetched_at),
        detail_status=status,
    )
    is_new = remote_id not in preexisting and remote_id not in known
    changed = remote_id in preexisting and current is not None and current["content_hash"] != row["content_hash"]
    db.upsert_item(conn, row)
    known.add(remote_id)
    if is_new:
        stats["new_count"] += 1
        stats["new_ids"].append(remote_id)
    elif changed:
        stats["updated_count"] += 1


def fetch_detail(source: str, remote_id: str):
    if source == "market-daily":
        detail = client.get(f"/api/market-daily/{remote_id}")
        if detail is None:
            detail = client.get(f"/api/reports/{remote_id}")
        return detail
    return client.get(f"/api/{source}/{remote_id}")


def fetch_details(conn, source, detail_mode, remote_ids, preexisting, stats) -> None:
    if detail_mode == "never":
        return
    targets = []
    seen: set[str] = set()
    for remote_id in remote_ids:
        if remote_id in seen:
            continue
        seen.add(remote_id)
        row = db.get_item(conn, source, remote_id)
        if row is None:
            continue
        if detail_mode == "mikko" and row["detail_status"] in ("ok", "not_needed"):
            continue
        if detail_mode == "try" and row["detail_status"] == "not_needed" and (row["body"] or "").strip():
            continue
        if row["detail_status"] == "ok" and remote_id in preexisting:
            continue
        targets.append(remote_id)
    if not targets:
        return
    print(f"  {source} details: {len(targets)}", flush=True)
    workers = 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_detail, source, remote_id): remote_id
            for remote_id in targets
        }
        done = 0
        for future in as_completed(futures):
            remote_id = futures[future]
            done += 1
            try:
                detail = future.result()
                error = None
            except Exception as exc:
                detail = None
                error = str(exc)
            apply_detail(conn, source, detail_mode, remote_id, detail, error, preexisting, stats)
            if done % 25 == 0 or done == len(targets):
                conn.commit()
                print(f"  {source} details {done}/{len(targets)}", flush=True)
    conn.commit()


def apply_detail(conn, source, detail_mode, remote_id, detail, error, preexisting, stats) -> None:
    current = db.get_item(conn, source, remote_id)
    if current is None:
        return
    fetched_at = stamp(now())
    if error is not None or detail is None:
        if detail_mode == "try" and error is None and detail is None:
            status = "not_needed"
            body = current["body"]
            stats["detail_ok"] += 1
        else:
            status = "error"
            body = current["body"]
            stats["detail_fail"] += 1
        detail_json = current["detail_json"]
        institution = current["institution"]
    else:
        body = detail_body(source, detail) or current["body"]
        institution = institution_of(detail) or current["institution"]
        detail_json = json.dumps(detail, ensure_ascii=False)
        status = "ok"
        stats["detail_ok"] += 1
    previous_hash = current["content_hash"]
    row = item_row(
        source=source,
        remote_id=remote_id,
        title=str((detail or {}).get("title") or current["title"] or ""),
        published_at=current["published_at"],
        institution=institution,
        body=body,
        list_json=current["list_json"],
        detail_json=detail_json,
        first_seen_at=current["first_seen_at"],
        list_fetched_at=current["list_fetched_at"],
        detail_fetched_at=fetched_at,
        updated_at=fetched_at if previous_hash != digest(body) else current["updated_at"],
        detail_status=status,
    )
    changed = remote_id in preexisting and current["content_hash"] != row["content_hash"]
    db.upsert_item(conn, row)
    if changed:
        stats["updated_count"] += 1


def item_row(**fields) -> dict:
    fields["content_hash"] = digest(fields["body"])
    return fields
