from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import UsageEvent


def log_usage(
    db: Session,
    event_type: str,
    *,
    client_id: str = "",
    meta: Optional[dict[str, Any]] = None,
) -> None:
    db.add(
        UsageEvent(
            event_type=event_type[:64],
            client_id=(client_id or "anonymous")[:64],
            meta=json.dumps(meta or {}, ensure_ascii=False),
        )
    )


def build_analytics(db: Session, days: int = 30) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=days)
    since_7 = datetime.utcnow() - timedelta(days=7)

    events = (
        db.query(UsageEvent)
        .filter(UsageEvent.created_at >= since)
        .order_by(UsageEvent.created_at.desc())
        .all()
    )

    def count_since(event_type: str, start: datetime) -> int:
        return sum(
            1 for e in events if e.event_type == event_type and e.created_at >= start
        )

    def unique_since(start: datetime) -> int:
        return len(
            {
                e.client_id
                for e in events
                if e.created_at >= start and e.client_id and e.client_id != "anonymous"
            }
        )

    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

    daily_map: dict[str, dict[str, Any]] = {}
    for e in events:
        day = e.created_at.strftime("%Y-%m-%d")
        if day not in daily_map:
            daily_map[day] = {
                "date": day,
                "page_views": 0,
                "unique_visitors": set(),
                "chats": 0,
                "account_scrapes": 0,
            }
        row = daily_map[day]
        if e.event_type == "page_view":
            row["page_views"] += 1
        if e.client_id and e.client_id != "anonymous":
            row["unique_visitors"].add(e.client_id)
        if e.event_type in ("chat_plan", "chat_copy"):
            row["chats"] += 1
        if e.event_type == "account_scrape_ok":
            row["account_scrapes"] += 1

    daily = []
    for day in sorted(daily_map.keys(), reverse=True):
        row = daily_map[day]
        daily.append(
            {
                "date": row["date"],
                "page_views": row["page_views"],
                "unique_visitors": len(row["unique_visitors"]),
                "chats": row["chats"],
                "account_scrapes": row["account_scrapes"],
            }
        )

    recent = []
    for e in events[:80]:
        recent.append(
            {
                "event_type": e.event_type,
                "client_id": e.client_id[:8] + "…" if len(e.client_id) > 8 else e.client_id,
                "meta": json.loads(e.meta or "{}"),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )

    chat_total = sum(v for k, v in by_type.items() if k.startswith("chat_"))
    scrape_ok = by_type.get("account_scrape_ok", 0)
    scrape_fail = by_type.get("account_scrape_fail", 0)

    return {
        "period_days": days,
        "summary": {
            "unique_visitors_7d": unique_since(since_7),
            "unique_visitors_30d": unique_since(since),
            "page_views_7d": count_since("page_view", since_7),
            "page_views_30d": count_since("page_view", since),
            "chat_messages_7d": sum(
                1
                for e in events
                if e.event_type in ("chat_plan", "chat_copy") and e.created_at >= since_7
            ),
            "chat_messages_30d": chat_total,
            "account_scrapes_ok": scrape_ok,
            "account_scrapes_fail": scrape_fail,
            "ref_post_scrapes": by_type.get("ref_post_scrape_ok", 0),
            "presets_created": by_type.get("preset_saved", 0),
        },
        "by_event_type": [
            {"event_type": k, "count": v}
            for k, v in sorted(by_type.items(), key=lambda x: -x[1])
        ],
        "daily": daily[:14],
        "recent_events": recent,
    }
